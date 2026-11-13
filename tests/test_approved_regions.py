"""Behavioral checks for fixed approvals, ownership, and reference-only figures."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from extraction import extract_page, load_figure_regions, split_records


class ApprovedRegionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc = pymupdf.open()
        self.addCleanup(self.doc.close)
        page = self.doc.new_page(width=594,height=774)
        page.insert_text((60,60),"Figure content one")
        page.insert_text((60,90),"Figure 1-1. Caption one")
        page.insert_text((320,60),"Figure content two")
        page.insert_text((320,90),"Figure 1-2. Caption two")
        page.insert_text((60,200),"Body remains available")
        page.insert_text((510,740),"1-1")
        self.config = {"document_id":"fixture","corpus_version":"test","source_url":"fixture",
                       "chapter":"test","figure_regions_path":"regions.json", "page_ranges":[{"start":1,"end":1}],
                       "audit":{"footer_height_points":54,"column_split_fraction":0.5,
                                "figure_regions_by_page":{"1":[0,0,594,710]}}}
        self.regions = [self.region("R1","1-1",[50,40,290,110]),self.region("R2","1-2",[310,40,550,110])]
        self.payload = {"schema_version":1,"approval_scope":"region_boundary_only","document_id":"fixture",
                        "source_sha256":"pdf-hash","region_version":"fixture-v1","regions":self.regions}

    def region(self,rid,fid,bbox):
        return {"candidate_id":rid,"pdf_page":1,"figure_id":fid,"bbox":bbox,"active":True,
                "boundary_review_status":"human_verified","approval_scope":"region_boundary_only",
                "intended_handling":"separate_figure",
                "boundary_approval":{"candidate_id":rid,"pdf_page":1,"figure_id":fid,"bbox":bbox.copy(),
                                     "accepted":True,"review_status":"human_verified","approval_scope":"region_boundary_only"}}

    def load(self,payload=None):
        (self.root/"regions.json").write_text(json.dumps(payload or self.payload),encoding="utf-8")
        return load_figure_regions(self.config,"pdf-hash",self.doc,self.root)

    def extract(self,bundle):
        return extract_page(self.doc[0],1,self.config,"pdf-hash","config-hash",bundle)

    def test_multiple_regions_have_one_owner_and_no_embedded_text_copy(self):
        record = self.extract(self.load())
        page,figures = split_records(record)
        self.assertEqual(len(figures),2)
        self.assertNotIn("figures",page)
        self.assertEqual(len(page["figure_refs"]),2)
        self.assertNotIn("Figure content",page["text"])
        self.assertIn("Body remains available",page["text"])
        ids = [b["source_block_id"] for b in page["ordered_blocks"]+page["removed_footer_blocks"]]
        ids += [b["source_block_id"] for f in figures for b in f["blocks"]]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(ids),record["source_text_block_count"])

    def test_preserve_in_body_emits_only_references_for_index_deduplication(self):
        self.regions[0]["intended_handling"] = "preserve_in_body"
        page,figures = split_records(self.extract(self.load()))
        figure = next(f for f in figures if f["region_id"]=="R1")
        self.assertIn("Figure content one",page["text"])
        self.assertFalse(figure["indexable"])
        self.assertNotIn("text",figure)
        self.assertNotIn("blocks",figure)
        self.assertEqual(figure["content_storage"],"page_body_reference")
        self.assertTrue(figure["source_block_ids"])
        self.assertEqual(figure["human_review_status"],"not_reviewed")

    def test_partial_block_is_kept_in_body_not_clipped(self):
        self.regions[0]["bbox"][2] = 65
        self.regions[0]["boundary_approval"]["bbox"][2] = 65
        record = self.extract(self.load())
        self.assertIn("Figure content one",record["text"])
        self.assertTrue(any("partially overlaps" in w for w in record["warnings"]))

    def test_hash_scope_and_geometry_mismatches_fail_closed(self):
        for case in ("hash","scope","bbox","unapproved"):
            with self.subTest(case=case):
                value = copy.deepcopy(self.payload)
                if case=="hash": value["source_sha256"]="wrong"
                if case=="scope": value["approval_scope"]="full_text"
                if case=="bbox": value["regions"][0]["bbox"][0]=49
                if case=="unapproved": value["regions"][0]["boundary_approval"]["accepted"]=False
                with self.assertRaises(ValueError): self.load(value)

    def test_duplicates_overlap_and_invalid_coordinates_fail_closed(self):
        for case in ("duplicate","overlap","nan","footer"):
            with self.subTest(case=case):
                value = copy.deepcopy(self.payload)
                if case=="duplicate": value["regions"].append(copy.deepcopy(value["regions"][0]))
                if case=="overlap":
                    value["regions"][1]["bbox"]=[55,45,280,115]
                    value["regions"][1]["boundary_approval"]["bbox"]=[55,45,280,115]
                if case in ("nan","footer"):
                    bbox = [50,40,290,float("nan") if case=="nan" else 730]
                    value["regions"][0]["bbox"]=bbox
                    value["regions"][0]["boundary_approval"]["bbox"]=bbox.copy()
                with self.assertRaises(ValueError): self.load(value)

    def test_legacy_coordinates_are_ignored_and_fixed_file_is_required(self):
        self.payload["regions"]=[]
        record = self.extract(self.load())
        self.assertIn("Figure content one",record["text"])
        self.assertFalse(record["figures"])
        self.config["figure_regions_path"]="missing.json"
        with self.assertRaises(FileNotFoundError):
            load_figure_regions(self.config,"pdf-hash",self.doc,self.root)


if __name__=="__main__":
    unittest.main()
