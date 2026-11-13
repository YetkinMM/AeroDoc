"""Independently verify stored corpus ownership, regressions and repeated-run bytes."""

import collections
import json
from pathlib import Path

import pymupdf

from build_dev_questions import build_dataset, load_source
from extract_corpus import event_cause_pairs
from extraction import sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "audit/corpus"
REVISION = ROOT / "audit/accepted_region_migration"


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main():
    config = json.loads((ROOT/"config/corpus.json").read_text(encoding="utf-8"))
    records = read_lines(OUTPUT/"pages.jsonl")
    figures = read_lines(OUTPUT/"figures.jsonl")
    old = {r["pdf_page"]:r for r in read_lines(REVISION/"corpus_before/pages.jsonl")}
    before = json.loads((REVISION/"input_snapshot.json").read_text(encoding="utf-8"))
    by_page = {r["pdf_page"]:r for r in records}
    assert list(by_page)==list(range(624,656))
    figure_ids = [f["record_id"] for f in figures]
    refs = [ref for r in records for ref in r["figure_refs"]]
    assert len(figures)==len(set(figure_ids))==37 and collections.Counter(refs)==collections.Counter(figure_ids)
    counts = collections.Counter()
    page_checks = []
    with pymupdf.open(ROOT/config["pdf_path"]) as pdf:
        for r in records:
            n = r["pdf_page"]
            page = pdf[n-1]
            page_figures = [f for f in figures if f["pdf_page"]==n]
            parts = r["ordered_blocks"]+r["removed_footer_blocks"]+[b for f in page_figures for b in f.get("blocks",[])]
            expected = collections.Counter((b[5],tuple(b[:4]),b[4].strip()) for b in page.get_text("blocks",sort=False) if b[6]==0)
            actual = collections.Counter((b["source_block_id"],tuple(b["bbox"]),b["text"]) for b in parts)
            assert actual==expected,n
            assert r["raw_text"]==page.get_text()==old[n]["raw_text"]
            body_keys = {tuple(b["bbox"]) for b in r["ordered_blocks"]}
            old_remaining = [b for b in old[n]["ordered_blocks"] if tuple(b["bbox"]) in body_keys]
            assert [(b["bbox"],b["text"],b["column"]) for b in old_remaining]==[(b["bbox"],b["text"],b["column"]) for b in r["ordered_blocks"]]
            assert not any(b["text"].startswith("Figure ") for b in r["ordered_blocks"]) or n==655
            assert "figures" not in r and r["human_review_status"]=="not_reviewed"
            counts["body"]+=len(r["ordered_blocks"])
            counts["footer"]+=len(r["removed_footer_blocks"])
            counts["figure"]+=sum(len(f.get("blocks",[])) for f in page_figures)
            page_checks.append({"pdf_page":n,"body_changed":r["text"]!=old[n]["text"],
                                "source_blocks_preserved_once":True,"remaining_body_relative_order_preserved":True})
    continuations = []
    anchors = [(625,"deployment of systems","and services"),(626,"Research is","optimized"),
               (629,"Pilots","are required"),(634,"order to avoid","or reduce"),(638,"When work","resumes"),
               (640,"cause of","fatigue"),(642,"delays","or cancellations"),(643,"having the","proper parts"),
               (644,"technical representative","or technical publications"),(647,"very","difficult"),
               (648,"foods","lacking"),(650,"the","group"),(652,"events is","broken")]
    for n,left,right in anchors:
        blocks = by_page[n]["ordered_blocks"]
        matches = [i for i,b in enumerate(blocks[:-1]) if b["text"].strip().endswith(left)
                   and blocks[i+1]["text"].lstrip().startswith(right)]
        assert len(matches)==1,(n,left,right)
        continuations.append({"pdf_page":n,"left_end":left,"right_start":right,"adjacent":True})
    last_list = next(b for b in by_page[651]["ordered_blocks"] if b["text"].startswith("3."))
    assert last_list["text"]=="3.\t\nElectrical wiring discrepancies to include crossing \nconnections. [Figure 14-32]"
    assert by_page[655]["text"]==old[655]["text"]
    pairs = event_cause_pairs(by_page[655]["text"])
    assert len(pairs)==5 and pairs==event_cause_pairs(old[655]["text"])
    ref = next(f for f in figures if f["pdf_page"]==655)
    assert ref["intended_handling"]=="preserve_in_body" and not ref["indexable"]
    assert "text" not in ref and "blocks" not in ref
    assert ref["source_block_ids"]==[b["source_block_id"] for b in by_page[655]["ordered_blocks"]]
    assert by_page[655]["ordered_blocks"][0]["text"]=="INCIDENT"
    repeated = {}
    for name in ("pages.jsonl","figures.jsonl"):
        first,last = REVISION/("first_run_"+name),OUTPUT/name
        assert first.read_bytes()==last.read_bytes(),name
        repeated[name] = {"identical":True,"sha256":sha256(last)}
    for name,digest in before["original_sample_hashes"].items():
        assert sha256(ROOT/"audit"/name)==digest
    assert sha256(ROOT/"eval/dev_questions.json")==before["dev_questions_sha256"]
    assert sha256(ROOT/"data/raw/manifest.json")==before["manifest_sha256"]
    pdf_path,count = load_source()
    assert build_dataset(pdf_path,count)==json.loads((ROOT/"eval/dev_questions.json").read_text(encoding="utf-8"))
    single = json.loads((REVISION/"single_page_check/page_655.json").read_text(encoding="utf-8"))
    assert single==by_page[655]
    report = {"page_count":len(records),"figure_count":len(figures),"inline_figure_count":sum(f["indexable"] for f in figures),
              "body_reference_figure_count":sum(not f["indexable"] for f in figures),"source_block_counts":dict(counts),
              "total_source_blocks":sum(counts.values()),"page_checks":page_checks,"continuations":continuations,
              "page_651_final_list_item":last_list,"page_655_five_pairs_preserved":True,
              "first_incident_heading_preserved":True,"no_duplicate_index_content_for_655":True,
              "repeat_run":repeated,"single_page_matches_batch":True,"original_samples_unchanged":True,
              "dev_set_and_evidence_unchanged":True,"region_boundaries_only_human_verified":True,
              "internal_order_and_semantics_human_verified":False}
    write_json(REVISION/"verification.json",report)
    print(f"PASS: {len(records)} pages; {len(figures)} figures; {sum(counts.values())} source blocks once; two runs byte-identical.")


if __name__=="__main__":
    main()
