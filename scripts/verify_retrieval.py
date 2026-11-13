"""Re-encode the corpus and repeat all rankings; verify protected inputs unchanged."""
import argparse
from pathlib import Path
import time

from retrieval import ROOT, Encoder, Searcher, corpus, dump, lines, ranked, read, sha


def main():
    import numpy as np
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config/retrieval.json')
    parser.add_argument('--record-inputs', action='store_true',
                        help='Record a new protection snapshot and exit; never overwrite an existing snapshot')
    args = parser.parse_args()
    config = read(args.config)
    out = ROOT/config['output_dir']
    if args.record_inputs:
        paths = []
        for directory in ['audit/corpus', 'audit/chunking', 'config', 'eval', 'scripts', 'tests', 'docs']:
            paths.extend(p for p in (ROOT/directory).rglob('*')
                         if p.is_file() and '__pycache__' not in p.parts)
        out.mkdir(parents=True, exist_ok=True)
        with (out/'input_snapshot.json').open('x', encoding='utf-8') as stream:
            import json
            json.dump({p.relative_to(ROOT).as_posix(): sha(p) for p in paths}, stream, indent=2)
        print('Protection snapshot recorded; existing snapshots are never overwritten.')
        return
    snapshot = read(out/'input_snapshot.json')
    changed = [name for name, digest in snapshot.items() if not (ROOT/name).exists() or sha(ROOT/name) != digest]
    if changed:
        raise ValueError(f'Protected inputs changed: {changed}')
    chunks = corpus(ROOT/config['chunks_path'])
    original = np.load(out/'embeddings.npy', allow_pickle=False)
    encoder = Encoder(config['dense'])
    start = time.perf_counter()
    repeated, lengths = encoder.encode([c['text'] for c in chunks])
    seconds = time.perf_counter()-start
    atol, rtol = config['dense']['repeat_atol'], config['dense']['repeat_rtol']
    np.testing.assert_allclose(repeated, original, atol=atol, rtol=rtol)
    np.save(out/'embeddings.repeat.npy', repeated, allow_pickle=False)
    report = {'protected_inputs_unchanged': len(snapshot), 'chunk_count': len(chunks),
              'type_counts': {t: sum(c['type'] == t for c in chunks) for t in ['body', 'figure']},
              'reencode_seconds_excluding_load': seconds,
              'max_embedding_absolute_difference': float(np.max(np.abs(repeated-original))),
              'atol': atol, 'rtol': rtol, 'token_max': max(lengths),
              'repeat_queries': [], 'metadata_preserved': True}
    questions = read(ROOT/'eval/dev_questions.json')['questions']
    for method in ['bm25', 'bge']:
        first = Searcher(method, args.config)
        second = Searcher(method, args.config)
        for q in questions:
            a = first.search(q['question'], len(chunks))
            if method == 'bge':
                query, _ = second.encoder.encode([q['question']], query=True)
                b = ranked(chunks, repeated @ query[0], len(chunks))
            else:
                b = second.search(q['question'], len(chunks))
            assert [c['chunk_id'] for c in a] == [c['chunk_id'] for c in b], (method, q['id'])
            np.testing.assert_allclose([c['score'] for c in a], [c['score'] for c in b], atol=atol, rtol=rtol)
            by_id = {c['chunk_id']: c for c in chunks}
            for result in a:
                assert {k: v for k, v in result.items() if k not in ('score', 'rank')} == by_id[result['chunk_id']]
            report['repeat_queries'].append({'method': method, 'question_id': q['id'], 'ranking_identical': True})
    # Preserve-in-body content is represented exactly once, never a second figure index entry.
    pairs = [c for c in chunks if c.get('event_cause_pair_id')]
    assert len(pairs) == 5 and all(c['type'] == 'body' for c in pairs)
    assert not any(c['type'] == 'figure' and c.get('figure_id') == '14-37' for c in chunks)
    report['p655_pairs_body_only'] = [c['event_cause_pair_id'] for c in pairs]
    footers = {f"p{p['pdf_page']}:b{b['source_block_id']}" for p in lines(ROOT/'audit/corpus/pages.jsonl')
               for b in p['removed_footer_blocks']}
    assert not any(r['block_key'] in footers for c in chunks for r in c['source_refs'])
    report['footer_refs'] = 0
    dump(out/'verification.json', report)
    print(report)


if __name__ == '__main__':
    main()
