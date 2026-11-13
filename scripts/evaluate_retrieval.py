"""Development-only, whitespace-exact evidence evaluation grounded in raw source ranges."""
import argparse
from collections import defaultdict
from pathlib import Path
import statistics
import time

from retrieval import ROOT, Searcher, dump, lines, read, sha


def whitespace(text):
    return ' '.join(text.split())


def source_stream(blocks):
    """Normalize whitespace, retaining a raw coordinate for every nonspace character.

    Call only with blocks in actual source order in ONE page/body or ONE figure.
    Unrelated retrieval results are never concatenated here.
    """
    text, coords = [], []
    for key, raw in blocks:
        if text and text[-1] != ' ':
            text.append(' ')
            coords.append(None)
        for offset, char in enumerate(raw):
            if char.isspace():
                if text and text[-1] != ' ':
                    text.append(' ')
                    coords.append(None)
            else:
                text.append(char)
                coords.append((key, offset))
    return ''.join(text).rstrip(), coords[:len(''.join(text).rstrip())]


def evidence_locations(quote, streams):
    needle = whitespace(quote['text'])
    matches = []
    if not needle:
        return matches
    for page, stream_id, text, coords in streams:
        if page != quote['pdf_page']:
            continue
        start = text.find(needle)
        while start >= 0:
            positions = [c for c in coords[start:start+len(needle)] if c is not None]
            matches.append({'stream': stream_id, 'positions': positions})
            start = text.find(needle, start+1)
    return matches


def coverage(results):
    intervals = defaultdict(list)
    for chunk in results:
        for ref in chunk['source_refs']:
            intervals[ref['block_key']].append((ref['raw_start'], ref['raw_end']))
    return intervals


def covered(locations, intervals):
    return any(all(any(start <= offset < end for start, end in intervals.get(key, []))
                   for key, offset in match['positions']) for match in locations)


def metrics(question, results, locations):
    flags = [covered(x, coverage(results)) for x in locations]
    return {'page_hit': bool(set(question['source_pages']) & {p for c in results for p in c['pdf_pages']}),
            'evidence_recall': sum(flags)/len(flags), 'all_evidence_hit': all(flags),
            'evidence_hits': flags}


def streams_from_corpus():
    streams = []
    raw = {b['block_key']: b['raw_text'] for b in lines(ROOT/'audit/chunking/normalized_blocks.jsonl')}
    for page in lines(ROOT/'audit/corpus/pages.jsonl'):
        keys = [f"p{page['pdf_page']}:b{b['source_block_id']}" for b in page['ordered_blocks']]
        text, coords = source_stream([(key, raw[key]) for key in keys])
        streams.append((page['pdf_page'], f"body:p{page['pdf_page']}", text, coords))
    for figure in lines(ROOT/'audit/corpus/figures.jsonl'):
        if not figure['indexable']:
            continue  # preserve_in_body already exists in its body stream
        keys = [f"p{figure['pdf_page']}:b{b['source_block_id']}" for b in figure['blocks']]
        text, coords = source_stream([(key, raw[key]) for key in keys])
        streams.append((figure['pdf_page'], figure['figure_id'], text, coords))
    return streams


def summarize_locations(locations):
    output = []
    for location in locations:
        ranges = []
        for key, offset in location['positions']:
            if ranges and ranges[-1]['block_key'] == key and ranges[-1]['raw_end'] == offset:
                ranges[-1]['raw_end'] = offset+1
            else:
                ranges.append({'block_key': key, 'raw_start': offset, 'raw_end': offset+1})
        output.append({'stream': location['stream'], 'raw_ranges': ranges})
    return output


def evaluate(config_path=ROOT/'config/retrieval.json', output=None):
    import numpy as np
    config = read(config_path)
    out = output or ROOT/config['output_dir']
    out.mkdir(parents=True, exist_ok=True)
    dataset = read(ROOT/'eval/dev_questions.json')
    streams = streams_from_corpus()
    report = {'label': 'development baseline', 'denominator': 8,
              'evidence_matching': 'whitespace-only exact source occurrence + retrieved raw-range coverage',
              'evidence_recall_aggregation': 'macro average over answerable questions',
              'dev_questions_sha256': sha(ROOT/'eval/dev_questions.json'),
              'chunks_sha256': sha(ROOT/config['chunks_path']), 'methods': {}}
    for method in ['bm25', 'bge']:
        start = time.perf_counter()
        searcher = Searcher(method, config_path)
        initialization = time.perf_counter()-start
        questions, times = [], []
        repeated = True
        for q in dataset['questions']:
            start = time.perf_counter()
            results = searcher.search(q['question'], len(searcher.chunks))
            seconds = time.perf_counter()-start
            times.append(seconds)
            again = searcher.search(q['question'], len(searcher.chunks))
            if [c['chunk_id'] for c in results] != [c['chunk_id'] for c in again]:
                raise AssertionError(f'Unstable ranking: {method}/{q["id"]}')
            if not np.allclose([c['score'] for c in results], [c['score'] for c in again],
                               rtol=config['dense']['repeat_rtol'], atol=config['dense']['repeat_atol']):
                raise AssertionError('Unstable scores')
            row = {'id': q['id'], 'question': q['question'], 'answerable': q['answerable'],
                   'query_seconds_excluding_load': seconds, 'results': results}
            if searcher.encoder:
                row['final_query_token_count'] = searcher.encoder.token_lengths(
                    [config['dense']['query_instruction']+q['question']])[0]
            if q['answerable']:
                locations = [evidence_locations(e, streams) for e in q['evidence_quote']]
                row['metrics'] = {str(k): metrics(q, results[:k], locations) for k in [1, 3, 5]}
                row['evidence'] = []
                for quote, matches in zip(q['evidence_quote'], locations):
                    first_single = next((c['rank'] for c in results if covered(matches, coverage([c]))), None)
                    prefix = next((i for i in range(1, len(results)+1)
                                   if covered(matches, coverage(results[:i]))), None)
                    row['evidence'].append(quote | {'source_matched': bool(matches),
                        'source_occurrences': summarize_locations(matches),
                        'first_single_chunk_rank': first_single, 'first_complete_prefix_rank': prefix})
            questions.append(row)
        answerable = [r for r in questions if r['answerable']]
        assert len(answerable) == 8 and len(questions)-len(answerable) == 2
        aggregate = {str(k): {metric: statistics.mean(float(r['metrics'][str(k)][metric]) for r in answerable)
                              for metric in ['page_hit', 'evidence_recall', 'all_evidence_hit']}
                     for k in [1, 3, 5]}
        report['methods'][method] = {'aggregate': aggregate, 'questions': questions,
            'initialization_seconds': initialization,
            'model_load_seconds': searcher.encoder.load_seconds if searcher.encoder else 0,
            'query_mean_seconds_excluding_load': statistics.mean(times),
            'query_median_seconds_excluding_load': statistics.median(times),
            'repeat_rankings_identical': repeated, 'repeat_scores_within_tolerance': True}
    dump(out/'evaluation.json', report)
    write_report(report, out, read(ROOT/config['output_dir']/'index.json'))
    return report


def write_report(report, out, index):
    rows = ['# Development baseline', '', '111 chunks: 75 body + 36 figure. No parameter tuning on development questions.',
            'Eight answerable questions; two unanswerable questions excluded from all metric denominators.',
            'Evidence recall is a macro mean; evidence is whitespace-exact in raw page/block text, never metadata.', '',
            '| Method | k | page_hit | evidence_recall | all_evidence_hit |', '|---|---:|---:|---:|---:|']
    for method, result in report['methods'].items():
        for k, values in result['aggregate'].items():
            rows.append(f"| {method} | {k} | {values['page_hit']:.4f} | {values['evidence_recall']:.4f} | {values['all_evidence_hit']:.4f} |")
    rows += ['', f"Device: {index['device']}; dimension: {index['dimension']}; float32; exact cosine.",
             f"Model load: {index['model_load_seconds']:.3f}s. BM25 build: {index['bm25_build_seconds']:.4f}s. Dense build excluding load: {index['dense_build_seconds']:.3f}s.",
             f"Chunks SHA256: `{report['chunks_sha256']}`.", '',
             '## Question results', '', '| Method | Question | k=1 (page/recall/all) | k=3 | k=5 |', '|---|---|---|---|---|']
    for method, result in report['methods'].items():
        for q in result['questions']:
            if q['answerable']:
                values = []
                for k in ['1', '3', '5']:
                    m = q['metrics'][k]
                    values.append(f"{int(m['page_hit'])}/{m['evidence_recall']:.3f}/{int(m['all_evidence_hit'])}")
                rows.append(f"| {method} | {q['id']} | " + ' | '.join(values) + ' |')
    rows += ['', '## Evidence locations and missed-evidence ranks', '',
             'Ranks are over all 111 chunks. Prefix rank allows only source-contiguous, exactly located evidence ranges; unrelated retrieved text is never concatenated.', '']
    for method, result in report['methods'].items():
        rows += [f"### {method}", '', f"Mean query: {result['query_mean_seconds_excluding_load']*1000:.3f}ms; median: {result['query_median_seconds_excluding_load']*1000:.3f}ms (model initialization excluded). Repeated rankings and scores passed.", '']
        for q in result['questions']:
            rows += [f"**{q['id']}** {q['question']}", '']
            if q['answerable']:
                for e in q['evidence']:
                    rows.append(f"- PDF {e['pdf_page']}: {e['text']} — source matched={e['source_matched']}; single chunk rank={e['first_single_chunk_rank']}; complete prefix rank={e['first_complete_prefix_rank']}.")
            else:
                rows.append('Unanswerable: no threshold/abstention decision; excluded from denominator.')
                for c in q['results'][:5]:
                    rows.append(f"- rank {c['rank']}, score {c['score']:.6f}, PDF {c['pdf_pages']}, `{c['chunk_id']}`: {c['text'][:180]}")
            rows.append('')
    rows += ['## Limits', '', 'Only development baseline; no independent test accuracy claim. Figure boundaries are approved only under region_boundary_only; figure text order and semantic relationships remain unverified. No graph values or relationships were inferred. No answer generation, threshold selection, hybrid retrieval, or reranking.', '',
             'Full ranked results, source references, raw evidence ranges, and per-question timings: evaluation.json. Index/model/config/package hashes and passage token lengths: index.json.', '']
    (out/'report.md').write_text('\n'.join(rows), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config/retrieval.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate(args.config, args.output)
    print({m: r['aggregate'] for m, r in result['methods'].items()})
