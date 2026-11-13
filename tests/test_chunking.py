"""Behavioral tests for minimal normalization, provenance, boundaries and BGE budgets."""

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from chunking import Mapped, ModelTokenizer, normalize, split_group, trace_spans
from build_chunks import build_groups, heading_ranges, hyphen_evidence, registry, validate_chunks


def source(raw,key="p1:b1",page=1):
    return {"block_key":key,"raw_text":raw,"text":raw,"pdf_page":page,"printed_page":f"1-{page}",
            "source_block_id":1,"owner":"body","column":"left","bbox":[0,0,100,100]}


def mapped(raw,key="p1:b1"):
    return Mapped(raw,[(key,i,i+1) for i in range(len(raw))])


class SmallCounter:
    def count(self,text,special=True):
        return len(text.split())+(2 if special else 0)


class NormalizationTests(unittest.TestCase):
    def test_wraps_collapse_but_paragraphs_lists_and_markers_survive(self):
        raw="First line\nwraps.\n\n1.\t\nFirst item\n2.\t\nSecond item"
        value,_=normalize(raw,"p1:b1")
        self.assertEqual(value.text,"First line wraps.\n\n1. First item\n2. Second item")
        self.assertEqual(len(value.text),len(value.origins))

    def test_only_evidenced_line_end_hyphen_is_removed_and_logged(self):
        raw="uncom-\nmanded long-term long-\nterm"
        value,logs=normalize(raw,"p9:b4",evidence={"uncommanded":[{"pdf_page":3,"raw_text":"uncommanded"}]})
        self.assertEqual(value.text,"uncommanded long-term long- term")
        decisions=[l for l in logs if l["operation"]=="line_end_hyphen"]
        self.assertEqual([l["status"] for l in decisions],["joined","kept_ambiguous"])
        self.assertEqual(decisions[0]["removed_raw_range"],[5,7])
        self.assertEqual(decisions[0]["block_key"],"p9:b4")
        self.assertNotIn(("p9:b4",5,6),value.origins)

    def test_figure_label_line_order_is_not_reconstructed(self):
        value,_=normalize("Human\nFactors\n\nS\nH\nE\nL","p1:b1",preserve_lines=True)
        self.assertEqual(value.text,"Human\nFactors\n\nS\nH\nE\nL")

    def test_word_join_cannot_cross_a_paragraph_break_even_with_evidence(self):
        value,logs=normalize("re-\n\nview","p1:b1",evidence={"review":[{"pdf_page":2,"raw_text":"review"}]})
        self.assertEqual(value.text,"re-\n\nview")
        self.assertFalse(any(l.get("status")=="joined" for l in logs))

    def test_character_offsets_are_unicode_codepoints_and_reference_raw_text(self):
        raw="A  \nβ"
        value,_=normalize(raw,"p1:b1",start=3)
        self.assertEqual(value.text,"A β")
        self.assertEqual(value.origins[-1],("p1:b1",7,8))

    def test_substring_is_not_accepted_as_unhyphenated_word_evidence(self):
        with tempfile.TemporaryDirectory() as temp,pymupdf.open() as pdf:
            page=pdf.new_page()
            page.insert_text((30,30),"longterms")
            block=page.get_text("blocks")[0]
            cache=Path(temp)/"cache.json"
            cache.write_text(json.dumps({"source_sha256":"hash","candidates":["longterm"],"evidence":{
                "longterm":[{"pdf_page":1,"source_block_id":block[5],"raw_start":0,"raw_end":8,"raw_text":block[4]}]}}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"whole source word"):
                hyphen_evidence(pdf,{"p1:b1":source("long-\nterm")},"hash",cache)


class BoundaryAndCoverageTests(unittest.TestCase):
    def fixture(self,heading=False):
        s1=source("Proper documentation of","p624:b1",624)
        s2=source("all maintenance work is a key element.","p625:b1",625)
        sources={s1["block_key"]:s1,s2["block_key"]:s2}
        prepared={k:[{"mapped":mapped(s["raw_text"],k),"heading":None,"block_key":k}] for k,s in sources.items()}
        pages=[{"pdf_page":s["pdf_page"],"chapter":"Human Factors","ordered_blocks":[s]} for s in sources.values()]
        if heading:
            prepared[s2["block_key"]][0]["heading"]={"title":"New source heading"}
        return pages,sources,prepared

    def test_page_continuation_joins_without_losing_source_pages(self):
        pages,sources,prepared=self.fixture()
        logs=[]
        groups=build_groups(pages,[],sources,prepared,logs)
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]["units"][0]["mapped"].text,"Proper documentation of all maintenance work is a key element.")
        self.assertEqual({o[0] for o in groups[0]["units"][0]["mapped"].origins if o},set(sources))
        self.assertEqual(logs[0]["left_pdf_page"],624)
        self.assertEqual(logs[0]["right_pdf_page"],625)

    def test_new_heading_prevents_blind_page_join(self):
        pages,sources,prepared=self.fixture(heading=True)
        groups=build_groups(pages,[],sources,prepared,[])
        self.assertEqual(len(groups),2)
        self.assertEqual(groups[-1]["section_path"],["New source heading"])

    def test_heading_detection_uses_actual_style_not_just_title_case(self):
        with pymupdf.open() as pdf:
            page=pdf.new_page()
            page.insert_text((40,40),"Explicit Heading",fontname="hebo",fontsize=11)
            page.insert_text((40,90),"Capitalized prose is not a heading.",fontname="helv",fontsize=11)
            blocks=page.get_text("blocks")
            styles=page.get_text("dict")["blocks"]
            for b in blocks:
                s={**source(b[4].strip()),"bbox":list(b[:4])}
                found,_=heading_ranges(s,styles)
                self.assertEqual(bool(found),b[4].startswith("Explicit"))
                if found:self.assertEqual(found[0]["hierarchy"],"flat_no_nested_inference")

    def test_footer_and_preserved_figure_never_become_second_text_owner(self):
        b={"source_block_id":1,"bbox":[0,0,50,50],"text":"Body event and cause"}
        footer={"source_block_id":2,"bbox":[0,720,50,740],"text":"14-32"}
        page={"pdf_page":655,"printed_page":"14-32","ordered_blocks":[b],"removed_footer_blocks":[footer]}
        ref={"pdf_page":655,"content_storage":"page_body_reference","indexable":False,"source_block_ids":[1]}
        sources,footers=registry([page],[ref])
        self.assertEqual(set(sources),{"p655:b1"})
        self.assertEqual(footers,{"p655:b2"})
        ref["indexable"]=True
        with self.assertRaisesRegex(ValueError,"separately indexable"):registry([page],[ref])

    def chunk(self,value,src,roles=None,cid="test"):
        roles=roles or ["primary"]*len(value.text)
        refs=trace_spans(value,roles,src)
        chunk={"chunk_id":cid,"type":"body","text":value.text,"token_count":SmallCounter().count(value.text),
               "overlap_token_count":SmallCounter().count("".join(c for c,r in zip(value.text,roles) if r=="overlap"),False),
               "source_refs":refs,"pdf_pages":sorted({r["pdf_page"] for r in refs}),
               "printed_pages":list(dict.fromkeys(r["printed_page"] for r in refs)),
               "source_block_ids":list(dict.fromkeys(r["block_key"] for r in refs))}
        return chunk,{"mapped":value,"roles":roles}

    def test_coverage_rejects_missing_characters_and_accidental_primary_copies(self):
        src={"p1:b1":source("Alpha beta")}
        config={"max_tokens":500,"max_overlap_tokens":50}
        chunk,detail=self.chunk(mapped("Alpha beta"),src)
        result=validate_chunks([chunk],[detail],src,set(),[],SmallCounter(),config)
        self.assertEqual(result["missing_characters"],0)
        other=copy.deepcopy(chunk);other["chunk_id"]="other"
        with self.assertRaisesRegex(ValueError,"Coverage failure"):
            validate_chunks([chunk,other],[detail,detail],src,set(),[],SmallCounter(),config)
        c,d=self.chunk(mapped("Alpha beta").cut(0,5),src)
        with self.assertRaisesRegex(ValueError,"Coverage failure"):
            validate_chunks([c],[d],src,set(),[],SmallCounter(),config)

    def test_intentional_overlap_is_accounted_separately_and_bad_refs_rejected(self):
        src={"p1:b1":source("Alpha beta")}
        a,ad=self.chunk(mapped("Alpha beta"),src)
        b,bd=self.chunk(mapped("Alpha beta").cut(6,10),src,["overlap"]*4,"overlap")
        result=validate_chunks([a,b],[ad,bd],src,set(),[],SmallCounter(),{"max_tokens":500,"max_overlap_tokens":50})
        self.assertEqual(result["intentional_overlap_character_copies"],4)
        b["source_refs"][0]["raw_end"]=999
        with self.assertRaisesRegex(ValueError,"Serialized source"):
            validate_chunks([b],[bd],src,set(),[],SmallCounter(),{"max_tokens":500,"max_overlap_tokens":50})


TOKENIZER_PATH=ROOT/"audit/tokenizers/bge-small-en-v1.5/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a/tokenizer.json"


@unittest.skipUnless(importlib.util.find_spec("tokenizers") and TOKENIZER_PATH.exists(),"Install requirements-chunking.txt and fetch pinned tokenizer")
class ActualBGETokenizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer=ModelTokenizer(TOKENIZER_PATH)

    def test_special_tokens_counted_without_truncation(self):
        self.assertEqual(self.tokenizer.count("word "*498),500)
        self.assertEqual(self.tokenizer.count("word "*499),501)
        self.assertEqual(self.tokenizer.count("word "*1000),1002)
        self.assertIsNone(self.tokenizer.tokenizer.truncation)

    def test_forced_long_sentence_split_keeps_all_text_and_includes_overlap_budget(self):
        value=mapped("word "*1200)
        chunks,forced=split_group(value,self.tokenizer,target=400,maximum=500,overlap=32)
        self.assertTrue(forced)
        self.assertGreater(len(chunks),2)
        primary=[]
        for c in chunks:
            self.assertLessEqual(self.tokenizer.count(c["mapped"].text),500)
            self.assertLessEqual(c["overlap_token_count"],32)
            primary.extend(o[1] for o in c["primary"].origins if o and not value.text[o[1]].isspace())
        self.assertEqual(primary,[i for i,c in enumerate(value.text) if not c.isspace()])

    def test_overlap_never_leaves_separate_section_or_figure_group(self):
        for key in ("section-A","figure-B"):
            parts,_=split_group(mapped("One sentence. Another sentence. "*60,key),self.tokenizer,40,50,8)
            self.assertGreater(len(parts),1)
            self.assertEqual(parts[0]["overlap_token_count"],0)
            self.assertTrue(all(o[0]==key for part in parts for o in part["mapped"].origins if o))


if __name__=="__main__":
    unittest.main()
