"""Prepare review-only candidates with the unchanged second probe method.

Does not run extraction or write accepted configuration. All regions start pending.
"""

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from probe_figure_regions import candidates, collect, contains, reference_ids

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit/figure_region_candidates"
VERSION = "figure-region-candidates-v1-probe-iteration-2"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot():
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                    cwd=ROOT, encoding="utf-8").splitlines()
    paths = {ROOT / name for name in names}
    paths.update(p for p in (ROOT / "audit").rglob("*") if p.is_file() and OUT not in p.parents)
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths) if p.is_file()}


def label(canvas, region, color, bottom=False):
    rect = pymupdf.Rect(region["bbox"])
    canvas.draw_rect(rect, color=color, width=1.3, overlay=True)
    text = region["candidate_id"] + (" / " + region["figure_id"] if region["figure_id"] else "")
    width = pymupdf.get_text_length(text, fontsize=8) + 6
    x = max(1, min(rect.x0, canvas.rect.width-width-1))
    y = max(22, min(rect.y1-13 if bottom else rect.y0, canvas.rect.height-13))
    box = pymupdf.Rect(x, y, x+width, y+12)
    canvas.draw_rect(box, color=color, fill=(1,1,1), width=0.6, overlay=True)
    canvas.insert_text((x+3,y+9), text, fontsize=8, color=color, overlay=True)


def main():
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("Candidate directory already populated; preserve reviews instead of overwriting.")
    OUT.mkdir(parents=True, exist_ok=True)
    before = snapshot()
    save("initial_state.json", {"git_status": subprocess.check_output(["git", "status", "--short", "--branch"], cwd=ROOT, encoding="utf-8"),
                               "protected_sha256": before})
    config = json.loads((ROOT / "config/corpus.json").read_text(encoding="utf-8"))
    pdf_path = ROOT / config["pdf_path"]
    source_hash = digest(pdf_path)
    manifest = json.loads(pdf_path.with_name("manifest.json").read_text(encoding="utf-8"))
    if source_hash != manifest["sha256"]:
        raise SystemExit("Source PDF hash mismatch.")
    corpus = {r["pdf_page"]: r for r in map(json.loads, (ROOT / "audit/corpus/pages.jsonl").read_text(encoding="utf-8").splitlines())}
    records, checklist, diagnostics = [], [], []
    selected = [n for r in config["page_ranges"] for n in range(r["start"],r["end"]+1)]
    with pymupdf.open(pdf_path) as doc:
        if len(doc) != config["expected_page_count"]:
            raise SystemExit("Page count mismatch.")
        for n in selected:
            page = doc[n-1]
            if corpus[n]["source_sha256"] != source_hash:
                raise SystemExit(f"Existing page {n} source hash mismatch.")
            blocks, captions, images, drawings = collect(page)
            proposals = candidates(page, captions, images, drawings, iteration=2)
            page_records, issues = [], []
            if not proposals:
                issues.append("No caption-anchored candidate; absence of figures is NOT confirmed.")
            for i, proposal in enumerate(proposals,1):
                match = re.match(r"Figure\s+(\d+-\d+)\.", proposal["caption_text"].strip())
                inside = [b for b in blocks if contains(proposal["bbox"], b["bbox"])]
                partial = [b["id"] for b in blocks if pymupdf.Rect(b["bbox"]).intersects(pymupdf.Rect(proposal["bbox"]))
                           and not contains(proposal["bbox"], b["bbox"])]
                notes = ["Unchanged probe iteration-2 method; candidate only; not accepted."]
                if proposal["frame_drawing_id"] is None:
                    notes.append("No enclosing vector frame; image/caption fallback requires review.")
                if not proposal["image_placement_ids"] and proposal["frame_drawing_id"] is None:
                    notes.append("Caption-only candidate: figure extent may be missing.")
                if partial:
                    notes.append(f"Partial text-block overlaps: {partial}; do not clip or drop blocks.")
                if proposal["overshooting_images"]:
                    notes.append(f"Image placements outside selected frame: {proposal['overshooting_images']}; inspect visible extent/shadows.")
                if any(len(b["text"].split()) >= 45 and b["id"] != proposal["caption_id"] for b in inside):
                    notes.append("Long text inside region: could be body or a text-rich figure; visual review required.")
                if n == 655:
                    notes.append("Preserve all five event/cause pairs in current body order for retrieval. This candidate may cover only part of Figure 14-37; do not remove body content.")
                region = {"candidate_id": f"P{n}-A{i:02}", "pdf_page": n, "bbox": proposal["bbox"],
                          "figure_id": match[1] if match else None, "caption": proposal["caption_text"],
                          "origin": "auto", "review_status": "pending", "accepted": False,
                          "intended_handling": "preserve_in_body" if n == 655 else "separate_figure",
                          "notes": notes, "method": proposal["method"],
                          "included_source_block_ids": [b["id"] for b in inside],
                          "partial_source_block_ids": partial, "detector_evidence": proposal}
                page_records.append(region)
                issues.extend(f"{region['candidate_id']}: {note}" for note in notes[1:])
            manual = config["audit"]["figure_regions_by_page"].get(str(n))
            comparison = None
            if manual:
                cap = next((c for c in captions if contains(manual,c["bbox"])), None)
                match = re.match(r"Figure\s+(\d+-\d+)\.", cap["text"].strip()) if cap else None
                region = {"candidate_id": f"P{n}-M01", "pdf_page": n, "bbox": manual,
                          "figure_id": match[1] if match else None, "caption": cap["text"] if cap else None,
                          "origin": "manual", "review_status": "pending", "accepted": False,
                          "intended_handling": "separate_figure",
                          "notes": ["Existing coordinates copied for comparison only; not automatically human_verified."],
                          "included_source_block_ids": [b["id"] for b in blocks if contains(manual,b["bbox"])]}
                page_records.append(region)
                auto_ids = {b for r in page_records if r["origin"] == "auto" for b in r["included_source_block_ids"]}
                manual_ids = set(region["included_source_block_ids"])
                comparison = {"manual_bbox": manual, "auto_bboxes": [r["bbox"] for r in page_records if r["origin"] == "auto"],
                              "auto_only_text_block_ids": sorted(auto_ids-manual_ids),
                              "manual_only_text_block_ids": sorted(manual_ids-auto_ids)}
            auto = [r for r in page_records if r["origin"] == "auto"]
            overlaps = [[a["candidate_id"], b["candidate_id"]] for i,a in enumerate(auto) for b in auto[i+1:]
                        if pymupdf.Rect(a["bbox"]).intersects(pymupdf.Rect(b["bbox"]))]
            if overlaps:
                issues.append(f"Overlapping automatic regions: {overlaps}; association is ambiguous.")
            # Diagnostic review only; never changes the fixed detector's proposal.
            reference = None
            if n in (625,636,645,647,635,654):
                expected = reference_ids(n,blocks,config["audit"]["figure_regions_by_page"])
                actual = {b for r in auto for b in r["included_source_block_ids"]}
                reference = {"reviewer": "agent", "reference": "previous_probe_assistant_labels_not_human_truth",
                             "missed_figure_block_ids": sorted(expected-actual), "extra_block_ids": sorted(actual-expected)}
            noisy = [d for d in drawings if d["noise_flags"] or d["flagged_line_segments"]]
            if noisy:
                issues.append(f"{len(noisy)} drawing paths have possible thin/edge/full-page geometry; retained, may be axes or frames.")
            overlay_name = f"page_{n}.overlay.png"
            overlay = pymupdf.open()
            overlay.insert_pdf(doc,from_page=n-1,to_page=n-1)
            canvas = overlay[0]
            canvas.draw_rect(pymupdf.Rect(0,0,594,19),color=None,fill=(1,1,1),overlay=True)
            canvas.insert_text((8,13),f"PDF {n} | RED auto A / GREEN existing manual M | ALL PENDING",fontsize=9,overlay=True)
            for r in page_records:
                label(canvas,r,(1,0,0) if r["origin"] == "auto" else (0,0.5,0), bottom=r["origin"] == "manual")
            canvas.get_pixmap(dpi=110,alpha=False).save(OUT/overlay_name)
            overlay.close()
            records.extend(page_records)
            checklist.append({"pdf_page":n,"printed_page":corpus[n]["printed_page"],"auto_candidate_count":len(auto),
                              "manual_region_count":int(manual is not None),"region_count":len(page_records),
                              "figure_ids":[r["figure_id"] for r in auto],"candidate_ids":[r["candidate_id"] for r in page_records],
                              "manual_comparison":comparison,"suspicions":issues,
                              "required_check":"Inspect figure extent, body inclusion, caption association, and source block preservation before any acceptance.",
                              "overlay_path":f"audit/figure_region_candidates/{overlay_name}","review_status":"pending"})
            diagnostics.append({"pdf_page":n,"source_blocks":blocks,"captions":captions,"images":images,"drawings":drawings,
                                "overlapping_auto_regions":overlaps,"previous_reference_check":reference})
            print(f"PDF {n}: {len(auto)} auto, {int(manual is not None)} manual",flush=True)
    payload = {"document_id":config["document_id"],"corpus_version":config["corpus_version"],"source_sha256":source_hash,
               "source_url":config["source_url"],"pymupdf_version":pymupdf.VersionBind,"candidate_generator_version":VERSION,
               "detector_source_sha256":digest(ROOT/"scripts/probe_figure_regions.py"),
               "config_sha256":digest(ROOT/"config/corpus.json"),"coordinate_system":"PDF points, top-left origin, x0/y0/x1/y1",
               "created_at_utc":datetime.now(timezone.utc).isoformat(),"acceptance_status":"candidates_only",
               "pages":selected,"regions":records}
    save("figure_regions.candidates.json",payload)
    save("checklist.json",checklist)
    save("diagnostics.json",diagnostics)
    lines = ["# Candidate review checklist", "", "All regions pending; no accepted configuration created.",
             "Red: automatic A IDs. Green: existing manual M IDs (not human verification).", "",
             "| PDF | Printed | Auto / manual | Figures | Manual differences | Suspicion / required check | Overlay |",
             "|---|---|---|---|---|---|---|"]
    for r in checklist:
        comparison = r["manual_comparison"]
        diff = json.dumps(comparison,ensure_ascii=False) if comparison else "No manual reference"
        notes = "; ".join(r["suspicions"]) or "No automatic suspicion; visual review still required."
        lines.append(f"| {r['pdf_page']} | {r['printed_page']} | {r['auto_candidate_count']} / {r['manual_region_count']} | {', '.join(filter(None,r['figure_ids'])) or '-'} | {diff} | {notes} | [PNG](page_{r['pdf_page']}.overlay.png) |")
    (OUT/"checklist.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    changed = [name for name,h in before.items() if digest(ROOT/name) != h]
    save("preservation_check.json",{"protected_file_count":len(before),"changed_files":changed,
                                    "auto_region_count":sum(r["origin"] == "auto" for r in records),
                                    "manual_region_count":sum(r["origin"] == "manual" for r in records),
                                    "overlay_count":len(selected),"all_pending":all(r["review_status"] == "pending" for r in records)})
    if changed:
        raise SystemExit(f"Protected files changed: {changed}")


if __name__ == "__main__":
    main()
