"""Ranking, source-grounded metrics, token safety and persisted index contracts."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from retrieval import BM25, Encoder, Searcher, corpus, dump, fingerprint, ranked, read
from evaluate_retrieval import coverage, covered, evidence_locations, metrics, source_stream
import verify_retrieval


def chunk(identifier, text, start=0, end=None, page=1):
    return {'chunk_id': identifier, 'text': text, 'type': 'body', 'section_path': ['Title'],
            'pdf_pages': [page], 'printed_pages': ['1-1'],
            'source_refs': [{'block_key': 'p1:b1', 'raw_start': start,
                             'raw_end': end if end is not None else start+len(text)}]}


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.config = read(ROOT/'config/retrieval.json')['bm25']

    def test_bm25_formula_ranking_and_metadata(self):
        chunks = [chunk('b', 'alpha beta'), chunk('a', 'alpha beta'), chunk('c', 'gamma')]
        engine = BM25(chunks, self.config)
        results = engine.search('ALPHA', 3)
        self.assertEqual([c['chunk_id'] for c in results], ['a', 'b', 'c'])
        self.assertGreater(results[0]['score'], 0)
        self.assertAlmostEqual(results[0]['score'], math.log(1.6)*2.5/(1+1.5*(0.25+0.75*2/(5/3))))
        self.assertEqual(results[-1]['score'], 0)
        for key in chunks[1]:
            self.assertEqual(results[0][key], chunks[1][key])
        self.assertNotIn('score', chunks[1])
        self.assertEqual(engine.search('alpha alpha', 3), results)

    def test_invalid_scores_and_k(self):
        with self.assertRaises(ValueError):
            ranked([chunk('a', 'a')], [float('nan')], 1)
        with self.assertRaises(ValueError):
            ranked([chunk('a', 'a')], [1], 0)

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'chunks.jsonl'
            path.write_text('\n'.join(json.dumps(chunk('a', 'word')) for _ in range(2)))
            with self.assertRaises(ValueError):
                corpus(path)

    def test_protection_snapshot_never_overwrites_existing_work(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'audit/corpus').mkdir(parents=True)
            (root/'audit/corpus/pages.jsonl').write_text('existing source')
            config_path = root/'config.json'
            dump(config_path, {'output_dir': 'audit/retrieval'})
            argv = ['verify_retrieval.py', '--config', str(config_path), '--record-inputs']
            with patch.object(verify_retrieval, 'ROOT', root), patch.object(sys, 'argv', argv):
                verify_retrieval.main()
                snapshot = root/'audit/retrieval/input_snapshot.json'
                before = snapshot.read_bytes()
                with self.assertRaises(FileExistsError):
                    verify_retrieval.main()
                self.assertEqual(snapshot.read_bytes(), before)

    def test_index_mapping_and_config_changes_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            chunks = [chunk('a', 'alpha'), chunk('b', 'beta')]
            path = directory/'chunks.jsonl'
            path.write_text('\n'.join(json.dumps(c) for c in chunks))
            config = read(ROOT/'config/retrieval.json')
            config['chunks_path'] = str(path)
            config['output_dir'] = str(directory)
            config_path = directory/'config.json'
            dump(config_path, config)
            manifest = fingerprint(config_path, config, chunks)
            manifest['chunk_ids'].reverse()
            dump(directory/'index.json', manifest)
            with self.assertRaisesRegex(ValueError, 'Stale index'):
                Searcher('bm25', config_path)
            manifest = fingerprint(config_path, config, chunks)
            dump(directory/'index.json', manifest)
            config['bm25']['k1'] = 1.2
            dump(config_path, config)
            with self.assertRaisesRegex(ValueError, 'Stale index'):
                Searcher('bm25', config_path)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.text, self.coords = source_stream([('p1:b1', 'alpha \n beta gamma delta')])
        self.streams = [(1, 'body', self.text, self.coords)]

    def test_split_evidence_requires_both_contiguous_raw_ranges(self):
        quote = {'pdf_page': 1, 'text': 'beta gamma'}
        locations = evidence_locations(quote, self.streams)
        left, right = chunk('a', 'alpha beta', 0, 12), chunk('b', 'gamma delta', 12, 24)
        self.assertFalse(covered(locations, coverage([left])))
        self.assertFalse(covered(locations, coverage([right])))
        self.assertTrue(covered(locations, coverage([right, left])))
        missing = chunk('c', 'gamma delta', 15, 24)
        self.assertFalse(covered(locations, coverage([left, missing])))

    def test_no_cross_page_metadata_or_unrelated_concatenation(self):
        self.assertFalse(evidence_locations({'pdf_page': 2, 'text': 'beta gamma'}, self.streams))
        self.assertFalse(evidence_locations({'pdf_page': 1, 'text': 'Title'}, self.streams))
        self.assertFalse(evidence_locations({'pdf_page': 1, 'text': 'alpha gamma'}, self.streams))
        streams = [(1, 'figure1', *source_stream([('a', 'alpha')])),
                   (1, 'figure2', *source_stream([('b', 'beta')]))]
        self.assertFalse(evidence_locations({'pdf_page': 1, 'text': 'alpha beta'}, streams))

    def test_multiple_evidence_page_hit_is_not_evidence_recall(self):
        q = {'source_pages': [1, 2]}
        locations = [evidence_locations({'pdf_page': 1, 'text': word}, self.streams)
                     for word in ['alpha', 'delta']]
        result = metrics(q, [chunk('a', 'alpha', 0, 5)], locations)
        self.assertTrue(result['page_hit'])
        self.assertEqual(result['evidence_recall'], 0.5)
        self.assertFalse(result['all_evidence_hit'])
        result = metrics(q, [chunk('a', 'everything', 0, 24)], locations)
        self.assertEqual(result['evidence_recall'], 1)
        self.assertTrue(result['all_evidence_hit'])

    def test_whitespace_only_no_fuzzy(self):
        self.assertTrue(evidence_locations({'pdf_page': 1, 'text': 'alpha beta'}, self.streams))
        self.assertFalse(evidence_locations({'pdf_page': 1, 'text': 'Alpha beta'}, self.streams))

    def test_multi_page_evidence_is_evaluated_separately(self):
        streams = [(1, 'body1', *source_stream([('p1:b1', 'alpha')])),
                   (2, 'body2', *source_stream([('p2:b1', 'beta')]))]
        locations = [evidence_locations({'pdf_page': page, 'text': word}, streams)
                     for page, word in [(1, 'alpha'), (2, 'beta')]]
        first = chunk('a', 'alpha', 0, 5)
        second = chunk('b', 'beta', 0, 4, page=2)
        second['source_refs'][0]['block_key'] = 'p2:b1'
        q = {'source_pages': [1, 2]}
        self.assertEqual(metrics(q, [first], locations)['evidence_hits'], [True, False])
        self.assertTrue(metrics(q, [first, second], locations)['all_evidence_hit'])


@unittest.skipUnless((ROOT/'audit/retrieval/model/manifest.json').exists(), 'Pinned model not downloaded')
class ActualBGETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = read(ROOT/'config/retrieval.json')['dense']
        cls.encoder = Encoder(cls.config)

    def test_tokens_include_instruction_and_specials_no_truncation(self):
        encoder = self.encoder
        self.assertEqual(encoder.token_lengths(['hello'])[0], 3)
        self.assertGreater(encoder.token_lengths([self.config['query_instruction']+'hello'])[0], 3)
        self.assertEqual(encoder.token_lengths(['word '*498]), [500])
        with self.assertRaisesRegex(ValueError, 'no truncation'):
            encoder.token_lengths(['word '*499])
        with self.assertRaisesRegex(ValueError, 'no truncation'):
            encoder.encode(['word '*501], query=True)

    def test_cls_normalized_eval_exact_cosine(self):
        import numpy as np
        import torch
        encoder = self.encoder
        self.assertFalse(encoder.model.training)
        texts = ['Aircraft maintenance documentation', 'Fatigue affects performance']
        actual, _ = encoder.encode(texts)
        batch = encoder.tokenizer(texts, padding=True, truncation=False, return_tensors='pt')
        with torch.inference_mode():
            expected = torch.nn.functional.normalize(encoder.model(**batch)[0][:, 0], p=2, dim=1).numpy()
        np.testing.assert_allclose(actual, expected, atol=1e-6)
        np.testing.assert_allclose(np.linalg.norm(actual, axis=1), 1, atol=1e-6)
        again, _ = encoder.encode(texts)
        np.testing.assert_allclose(actual, again, atol=1e-6)
        self.assertGreater(float(actual[0] @ actual[0]), float(actual[0] @ actual[1]))
        with patch.object(encoder, 'token_lengths', wraps=encoder.token_lengths) as count:
            encoder.encode(['hello'], query=True)
            self.assertEqual(count.call_args.args[0], [self.config['query_instruction']+'hello'])


if __name__ == '__main__':
    unittest.main()
