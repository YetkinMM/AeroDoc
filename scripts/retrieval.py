"""Shared immutable-corpus BM25 / exact BGE retrieval and terminal interface."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import re
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ['torch', 'transformers', 'numpy', 'safetensors', 'tokenizers', 'huggingface-hub']
# Indexes produced before the BM25 runtime was separated from BGE.
LEGACY_IMPLEMENTATION_SHA256 = '3befc5f74d32ba6c8fa999eff6c3638e9f340577bf11332860c4e1e1e3e55563'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def versions():
    return {p: importlib.metadata.version(p) for p in PACKAGES} | {'python': platform.python_version()}


def corpus(path):
    chunks = lines(path)
    ids = [c['chunk_id'] for c in chunks]
    if len(ids) != len(set(ids)) or not chunks:
        raise ValueError('Duplicate IDs or empty corpus')
    if any(c['type'] not in ('body', 'figure') or not c['text'].strip() for c in chunks):
        raise ValueError('Invalid chunk')
    return chunks


def ranked(chunks, scores, k):
    if k < 1:
        raise ValueError('k must be positive')
    if len(chunks) != len(scores) or any(not math.isfinite(float(s)) for s in scores):
        raise ValueError('Invalid scores')
    order = sorted(range(len(chunks)), key=lambda i: (-float(scores[i]), chunks[i]['chunk_id']))
    return [dict(chunks[i], score=float(scores[i]), rank=j+1) for j, i in enumerate(order[:k])]


class BM25:
    def __init__(self, chunks, config):
        if (config['lowercase'] is not True or config['stopwords'] is not False
                or config['stemming'] is not False or config['query_term_frequency'] != 'unique'
                or config['idf'] != 'log(1 + (N - df + 0.5)/(df + 0.5))'
                or config['k1'] <= 0 or not 0 <= config['b'] <= 1):
            raise ValueError('Unsupported BM25 policy')
        self.chunks, self.config = chunks, config
        self.tf = [Counter(self.words(c['text'])) for c in chunks]
        self.lengths = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.lengths) / len(chunks)
        self.df = Counter(t for row in self.tf for t in row)

    def words(self, text):
        return re.findall(self.config['token_pattern'], text.lower())

    def search(self, question, k):
        query = sorted(set(self.words(question)))
        n, k1, b = len(self.chunks), self.config['k1'], self.config['b']
        scores = []
        for tf, length in zip(self.tf, self.lengths):
            score = 0.0
            for term in query:
                freq = tf[term]
                if freq:
                    idf = math.log1p((n-self.df[term]+0.5)/(self.df[term]+0.5))
                    score += idf * freq*(k1+1)/(freq+k1*(1-b+b*length/self.avg))
            scores.append(score)
        return ranked(self.chunks, scores, k)


class Encoder:
    def __init__(self, config):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch, self.config = torch, config
        if (config['pooling'] != 'cls' or config['normalize'] is not True
                or config['similarity'] != 'cosine_exact' or config['dtype'] != 'float32'
                or config['device'] != 'cpu' or config['batch_size'] < 1):
            raise ValueError('Unsupported dense inference policy')
        start = time.perf_counter()
        torch.set_num_threads(config['threads'])
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        directory = ROOT / config['model_dir']
        manifest = read(directory / 'manifest.json')
        if manifest['revision'] != config['revision'] or manifest['model_id'] != config['model_id']:
            raise ValueError('Model revision mismatch')
        for name, digest in manifest['files'].items():
            if sha(directory / name) != digest:
                raise ValueError(f'Model artifact changed: {name}')
        self.tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        self.model = AutoModel.from_pretrained(directory, local_files_only=True,
                                              attn_implementation='eager').to(config['device'])
        self.model.eval()
        if self.model.config.hidden_size != config['embedding_dimension']:
            raise ValueError('Embedding dimension mismatch')
        self.limit = min(config['max_tokens'], self.model.config.max_position_embeddings)
        self.load_seconds = time.perf_counter()-start

    def token_lengths(self, texts):
        encoded = self.tokenizer(texts, add_special_tokens=True, truncation=False, padding=False)
        lengths = [len(x) for x in encoded['input_ids']]
        if max(lengths, default=0) > self.limit:
            raise ValueError(f'Input exceeds {self.limit} tokens; no truncation: {lengths}')
        return lengths

    def encode(self, texts, query=False):
        import numpy as np
        texts = [self.config['query_instruction']+s for s in texts] if query else texts
        lengths = self.token_lengths(texts)
        vectors = []
        for start in range(0, len(texts), self.config['batch_size']):
            batch = self.tokenizer(texts[start:start+self.config['batch_size']], padding=True,
                                   truncation=False, return_tensors='pt').to(self.config['device'])
            with self.torch.inference_mode():
                output = self.model(**batch)[0][:, 0]
                output = self.torch.nn.functional.normalize(output, p=2, dim=1)
            vectors.append(output.cpu().numpy())
        return np.concatenate(vectors).astype('float32'), lengths


def fingerprint(config_path, config, chunks, *, bm25_only=False):
    identity = {'chunks_sha256': sha(ROOT/config['chunks_path']),
                'config_sha256': sha(config_path), 'implementation_sha256': sha(__file__),
                'chunk_ids': [c['chunk_id'] for c in chunks]}
    if not bm25_only:
        identity['versions'] = versions()
    return identity


def bm25_artifact(backend):
    return {'tf': [dict(t) for t in backend.tf], 'lengths': backend.lengths,
            'df': dict(backend.df), 'average_length': backend.avg}


def build(config_path=ROOT/'config/retrieval.json', *, bm25_only=False):
    if bm25_only:
        config = read(config_path)
        chunks = corpus(ROOT/config['chunks_path'])
        out = ROOT/config['output_dir']
        if (out/'embeddings.npy').exists():
            raise ValueError('BGE embeddings already exist; use the full build to refresh both indexes')
        out.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        dump(out/'bm25.json', bm25_artifact(BM25(chunks, config['bm25'])))
        manifest = fingerprint(config_path, config, chunks, bm25_only=True) | {
            'bm25_sha256': sha(out/'bm25.json'), 'bm25_build_seconds': time.perf_counter()-start}
        dump(out/'index.json', manifest)
        return manifest

    import numpy as np
    config = read(config_path)
    chunks = corpus(ROOT/config['chunks_path'])
    out = ROOT/config['output_dir']
    out.mkdir(parents=True, exist_ok=True)
    encoder = Encoder(config['dense'])
    if any(c['tokenizer_revision'] != config['dense']['revision']
           or c['tokenizer_model_id'] != config['dense']['model_id'] for c in chunks):
        raise ValueError('Chunk tokenizer/model revision mismatch')
    start = time.perf_counter()
    bm25 = BM25(chunks, config['bm25'])
    bm25_seconds = time.perf_counter()-start
    start = time.perf_counter()
    embeddings, lengths = encoder.encode([c['text'] for c in chunks])
    if lengths != [c['token_count'] for c in chunks]:
        raise ValueError('Passage tokenizer counts differ from chunking')
    dense_seconds = time.perf_counter()-start
    np.save(out/'embeddings.npy', embeddings, allow_pickle=False)
    dump(out/'bm25.json', bm25_artifact(bm25))
    manifest = fingerprint(config_path, config, chunks) | {
        'config': config, 'device': config['dense']['device'], 'dimension': embeddings.shape[1],
        'model_files': read(ROOT/config['dense']['model_dir']/'manifest.json'),
        'platform': platform.platform(), 'processor': platform.processor(),
        'model_load_seconds': encoder.load_seconds, 'bm25_build_seconds': bm25_seconds,
        'dense_build_seconds': dense_seconds, 'passage_token_lengths': lengths,
        'embeddings_sha256': sha(out/'embeddings.npy'), 'bm25_sha256': sha(out/'bm25.json')}
    dump(out/'index.json', manifest)
    return manifest


class Searcher:
    """Both backends return identical chunk schemas, plus rank and score."""
    def __init__(self, method, config_path=ROOT/'config/retrieval.json'):
        self.config = read(config_path)
        self.chunks = corpus(ROOT/self.config['chunks_path'])
        self.method, self.encoder = method, None
        out = ROOT/self.config['output_dir']
        manifest = read(out/'index.json')
        if method == 'bge' and 'embeddings_sha256' not in manifest:
            raise ValueError('BGE index missing; run the full retrieval build')
        current = fingerprint(config_path, self.config, self.chunks, bm25_only=method == 'bm25')
        implementation = manifest.get('implementation_sha256')
        if implementation == LEGACY_IMPLEMENTATION_SHA256:
            current['implementation_sha256'] = LEGACY_IMPLEMENTATION_SHA256
        if any(manifest.get(key) != val for key, val in current.items()):
            raise ValueError('Stale index: corpus/config/code/environment changed; rebuild explicitly')
        if method == 'bm25':
            if sha(out/'bm25.json') != manifest['bm25_sha256']:
                raise ValueError('Corrupt BM25 index')
            self.backend = BM25(self.chunks, self.config['bm25'])
            saved = read(out/'bm25.json')
            if saved != bm25_artifact(self.backend):
                raise ValueError('BM25 mapping mismatch')
        elif method == 'bge':
            import numpy as np

            self.encoder = Encoder(self.config['dense'])
            if sha(out/'embeddings.npy') != manifest['embeddings_sha256']:
                raise ValueError('Corrupt embedding index')
            self.embeddings = np.load(out/'embeddings.npy', allow_pickle=False)
            if self.embeddings.shape != (len(self.chunks), self.config['dense']['embedding_dimension']):
                raise ValueError('Index mapping/dimension mismatch')
            if not np.isfinite(self.embeddings).all() or not np.allclose(np.linalg.norm(self.embeddings, axis=1), 1, atol=1e-6):
                raise ValueError('Invalid normalized embeddings')
            if manifest['model_files'] != read(ROOT/self.config['dense']['model_dir']/'manifest.json'):
                raise ValueError('Model artifacts changed; rebuild')
        else:
            raise ValueError('Unknown retrieval method')

    def search(self, question, k=5):
        if not question.strip():
            raise ValueError('Empty question')
        if self.method == 'bm25':
            return self.backend.search(question, k)
        vector, _ = self.encoder.encode([question], query=True)
        return ranked(self.chunks, self.embeddings @ vector[0], k)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'search'])
    parser.add_argument('--config', type=Path, default=ROOT/'config/retrieval.json')
    parser.add_argument('--method', choices=['bm25', 'bge'], default='bm25')
    parser.add_argument('--bm25-only', action='store_true', help='build BM25 without BGE artifacts')
    parser.add_argument('--question')
    parser.add_argument('-k', type=int, default=5)
    args = parser.parse_args()
    if args.command == 'build':
        result = build(args.config, bm25_only=args.bm25_only)
        print(json.dumps({k: v for k, v in result.items() if k.endswith('seconds')}, indent=2))
    else:
        if not args.question:
            parser.error('--question required')
        print(json.dumps(Searcher(args.method, args.config).search(args.question, args.k), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
