"""Download a revision-pinned model into the ignored retrieval directory."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT / 'config/retrieval.json').read_text())['dense']
    directory = ROOT / config['model_dir']
    directory.mkdir(parents=True, exist_ok=True)
    api = f"https://huggingface.co/api/models/{config['model_id']}/revision/{config['revision']}"
    info = json.load(urllib.request.urlopen(api, timeout=60))
    assert info['sha'] == config['revision']
    names = ['config.json', 'tokenizer.json', 'tokenizer_config.json',
             'special_tokens_map.json', 'model.safetensors']
    siblings = {f['rfilename'] for f in info['siblings']}
    if not set(names) <= siblings:
        raise ValueError('Required pinned artifacts unavailable')
    manifest = {'model_id': config['model_id'], 'revision': config['revision'], 'files': {}}
    for name in names:
        path = directory / name
        url = f"https://huggingface.co/{config['model_id']}/resolve/{config['revision']}/{name}"
        # Hub LFS sha is checked for weights; tokenizer/config hashes also match chunking.
        metadata = json.load(urllib.request.urlopen(api + '?blobs=true', timeout=60))
        entry = next(x for x in metadata['siblings'] if x['rfilename'] == name)
        expected = entry.get('lfs', {}).get('sha256')
        if not path.exists() or (expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            temporary = path.with_suffix(path.suffix + '.tmp')
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as out:
                import shutil
                shutil.copyfileobj(response, out)
            temporary.replace(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected and digest != expected:
            raise ValueError(f'Weight hash mismatch: {name}')
        manifest['files'][name] = digest
        print(name, digest, flush=True)
    chunk = json.loads((ROOT / 'config/chunking.json').read_text())['tokenizer']
    assert chunk['revision'] == manifest['revision']
    for name, digest in chunk['files'].items():
        assert manifest['files'][name] == digest, name
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
