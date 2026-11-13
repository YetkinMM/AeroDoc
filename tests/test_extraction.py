"""Fail-closed source validation using a small, real PDF fixture."""

import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract_corpus import compare_samples, preserve_baseline, validate_source
from extraction import extract_page, sha256


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.pdf"
        with pymupdf.open() as doc:
            for title, label in (("Previous chapter", None), ("Chapter 14 Human Factors", "14-1"), ("Glossary", "G-1")):
                page = doc.new_page()
                page.insert_text((50, 50), title)
                if label:
                    page.insert_text((500, page.rect.height - 25), label)
            doc.save(self.path)
        self.digest = sha256(self.path)
        self.manifest = {"sha256": self.digest, "document_id": "fixture", "source_url": "https://example.com/source.pdf", "page_count": 3}
        self.write_manifest()
        self.config = {
            "document_id": "fixture", "corpus_version": "test", "chapter": "Human Factors",
            "source_url": self.manifest["source_url"], "expected_page_count": 3,
            "page_numbering": "one_based_inclusive", "page_ranges": [{"start": 2, "end": 2}],
            "audit": {"footer_height_points": 54, "column_split_fraction": 0.5,
                      "boundary_checks": [{"pdf_page": 1, "printed_page": None, "required_text": ["Previous chapter"]},
                                          {"pdf_page": 2, "printed_page": "14-1", "required_text": ["Human Factors"]},
                                          {"pdf_page": 3, "printed_page": "G-1", "required_text": ["Glossary"]}]}}

    def write_manifest(self):
        self.path.with_name("manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def validate(self, config=None):
        with pymupdf.open(self.path) as doc:
            return validate_source(config or self.config, self.path, doc, self.digest)

    def test_valid_source_and_unreviewed_raw_text(self):
        pages, checks = self.validate()
        self.assertEqual(pages, [2])
        self.assertTrue(all(c["passed"] for c in checks))
        with pymupdf.open(self.path) as doc:
            record = extract_page(doc[1], 2, self.config, self.digest, "config-hash", {"by_page":{},"sha256":"none","region_version":"fixture"})
            self.assertEqual(record["raw_text"], doc[1].get_text())
        self.assertEqual(record["human_review_status"], "not_reviewed")
        self.assertEqual(record["automatic_status"], "no_warnings")
        self.assertNotIn("14-1", record["text"])
        self.assertEqual(record["removed_footer_blocks"][0]["text"], "14-1")

    def test_changed_pdf_hash_is_rejected(self):
        self.manifest["sha256"] = "wrong-edition"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.validate()

    def test_page_count_and_ranges_are_rejected(self):
        for field, value in (("expected_page_count", 4), ("page_ranges", [{"start": 2, "end": 4}]),
                             ("page_ranges", [{"start": 2, "end": 2}] * 2),
                             ("page_numbering", "zero_based")):
            with self.subTest(field=field, value=value):
                config = copy.deepcopy(self.config)
                config[field] = value
                with self.assertRaises(ValueError):
                    self.validate(config)

    def test_wrong_chapter_labels_and_markers_are_rejected(self):
        for key, value in (("printed_page", "15-1"), ("required_text", ["Wrong chapter"])):
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                config["audit"]["boundary_checks"][1][key] = value
                with self.assertRaisesRegex(ValueError, "boundary"):
                    self.validate(config)

    def test_clean_checkout_does_not_require_ignored_audit_samples(self):
        with patch("extract_corpus.ROOT", Path(self.temp.name)), patch("extract_corpus.OUTPUT", Path(self.temp.name)/"audit/corpus"):
            baseline, hashes = preserve_baseline()
        self.assertIsNone(baseline)
        self.assertEqual(hashes,{})
        self.assertFalse((Path(self.temp.name)/"audit").exists())

    def test_missing_baseline_is_not_reported_as_a_pass(self):
        comparisons,pairs = compare_samples([{"pdf_page":655,"text":"No event/cause pairs here"}],None)
        self.assertEqual(comparisons,[])
        self.assertIsNone(pairs["text_and_order_identical_to_baseline"])
        self.assertFalse(pairs["five_pairs_in_expected_order"])


if __name__ == "__main__":
    unittest.main()
