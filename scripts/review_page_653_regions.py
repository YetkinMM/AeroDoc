"""Manual review-only correction of two page-653 candidate regions.

Coordinates were selected from rendered PDF page 653, vector frames and text bboxes.
Does not modify extraction, the detector, accepted config, or other candidate records.
"""

import copy
import hashlib
import json
from pathlib import Path

import pymupdf

from build_figure_region_candidates import label

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit/figure_region_candidates"
CORRECTIONS = {
    "P653-A02": {"bbox": [53, 44, 295, 324], "expected_ids": [1, 2, 3, 4, 10]},
    "P653-A04": {"bbox": [300, 309, 548, 564], "expected_ids": list(range(13, 39))},
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    candidate_path = OUT / "figure_regions.candidates.json"
    checklist_path = OUT / "checklist.json"
    package = read(candidate_path)
    before = copy.deepcopy(package)
    checklist = read(checklist_path)
    old_checklist = copy.deepcopy(checklist)
    revision = OUT / "page_653_manual_review"
    if revision.exists():
        raise SystemExit("Review revision exists; do not overwrite review history.")
    revision.mkdir()
    write(revision / "candidates.before.json", before)
    write(revision / "checklist.before.json", old_checklist)
    # Existing production artifacts and prior review records remain read-only.
    protected_paths = set(p for p in (ROOT / "audit").rglob("*") if p.is_file()
                          and p not in (candidate_path, checklist_path, OUT / "checklist.md")
                          and revision not in p.parents)
    for folder in ("config", "eval", "scripts", "docs"):
        protected_paths.update(p for p in (ROOT / folder).rglob("*") if p.is_file())
    protected = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected_paths}
    diagnostics = next(p for p in read(OUT / "diagnostics.json") if p["pdf_page"] == 653)
    blocks = diagnostics["source_blocks"]
    changed = []
    for region in package["regions"]:
        spec = CORRECTIONS.get(region["candidate_id"])
        if spec is None:
            continue
        rect = pymupdf.Rect(spec["bbox"])
        inside = [b["id"] for b in blocks if rect.contains(pymupdf.Rect(b["bbox"]))]
        partial = [b["id"] for b in blocks if rect.intersects(pymupdf.Rect(b["bbox"])) and b["id"] not in inside]
        assert sorted(inside) == spec["expected_ids"], (region["candidate_id"], inside)
        assert not partial
        assert not {0, 39, 40}.intersection(inside), "Footer/body must remain outside"
        old = copy.deepcopy(region)
        region.update({"bbox": spec["bbox"], "origin": "manual", "review_status": "agent_reviewed",
                       "accepted": False, "method": "manual_pdf_image_and_text_bbox_review",
                       "included_source_block_ids": inside, "partial_source_block_ids": [],
                       "notes": ["Manually corrected after PDF image, vector frame and text bbox inspection.",
                                 "Figure content and caption included; body blocks 39/40 and footer excluded.",
                                 "Stable candidate ID retained from original auto proposal; origin is now manual.",
                                 "agent_reviewed only; not accepted and not human_verified."],
                       "correction_history": [{"previous_bbox": old["bbox"], "previous_origin": old["origin"],
                                               "previous_review_status": old["review_status"],
                                               "previous_included_source_block_ids": old["included_source_block_ids"],
                                               "evidence": "Original record preserved in page_653_manual_review/candidates.before.json"}]})
        changed.append({"candidate_id": region["candidate_id"], "figure_id": region["figure_id"],
                        "before_bbox": old["bbox"], "after_bbox": spec["bbox"],
                        "included_source_block_ids": inside, "partial_source_block_ids": partial,
                        "review_status": "agent_reviewed", "accepted": False})
    page_regions = [r for r in package["regions"] if r["pdf_page"] == 653]
    for i,a in enumerate(page_regions):
        for b in page_regions[i+1:]:
            assert not pymupdf.Rect(a["bbox"]).intersects(pymupdf.Rect(b["bbox"]))
    assert {i for r in page_regions for i in r["included_source_block_ids"]} == set(range(1,39))
    for a,b in zip(before["regions"],package["regions"]):
        if a["candidate_id"] not in CORRECTIONS:
            assert a == b
    config = read(ROOT / "config/corpus.json")
    pdf_path = ROOT / config["pdf_path"]
    assert sha(pdf_path) == package["source_sha256"]
    overlay_name = "page_653.manual_review.overlay.png"
    with pymupdf.open(pdf_path) as doc:
        overlay = pymupdf.open()
        overlay.insert_pdf(doc,from_page=652,to_page=652)
        page = overlay[0]
        page.draw_rect(pymupdf.Rect(0,0,594,19),color=None,fill=(1,1,1),overlay=True)
        page.insert_text((8,12),"PDF 653 | RED: auto pending | GREEN: manual agent_reviewed | NOT ACCEPTED",fontsize=8,overlay=True)
        for region in page_regions:
            label(page,region,(0,0.5,0) if region["origin"] == "manual" else (1,0,0))
        page.get_pixmap(dpi=140,alpha=False).save(OUT / overlay_name)
        overlay.close()
    row = next(r for r in checklist if r["pdf_page"] == 653)
    row.update({"auto_candidate_count": 2, "manual_region_count": 2,
                "review_status": "pending", "region_review_statuses": {r["candidate_id"]:r["review_status"] for r in page_regions},
                "overlay_path": "audit/figure_region_candidates/"+overlay_name,
                "suspicions": ["14-32 and 14-35 manually corrected; no missing figure blocks against page-653 reference.",
                               "All four regions together include source blocks 1-38, excluding footer 0 and body 39/40.",
                               "P653-A01 and P653-A03 remain pending; no acceptance inferred.",
                               "Manual corrections are agent_reviewed only; human verification and acceptance remain pending."],
                "required_check": "Review the new 653 overlay; user approval is still required for corrected boundaries."})
    # Preserve other checklist rows byte-for-byte at the value level.
    assert [r for r in checklist if r["pdf_page"] != 653] == [r for r in old_checklist if r["pdf_page"] != 653]
    md_path = OUT / "checklist.md"
    lines = md_path.read_text(encoding="utf-8").splitlines()
    old_row = next(line for line in lines if line.startswith("| 653 |"))
    new_row = f"| 653 | 14-30 | 2 / 2 | {', '.join(row['figure_ids'])} | Manual corrections: 14-32 [53,44,295,324]; 14-35 [300,309,548,564] | {'; '.join(row['suspicions'])} | [PNG]({overlay_name}) |"
    lines = [new_row if line == old_row else line for line in lines]
    lines.insert(3,"Page 653 update: two manual corrections are agent_reviewed, not accepted; all other region statuses remain unchanged.")
    assert all(sha(ROOT/name)==h for name,h in protected.items())
    write(candidate_path,package)
    write(checklist_path,checklist)
    md_path.write_text("\n".join(lines)+"\n",encoding="utf-8")
    write(revision / "review.json", {"pdf_page":653,"changes":changed,"all_other_candidate_records_unchanged":True,
          "four_regions_cover_source_ids":list(range(1,39)),"excluded_footer_and_body_ids":[0,39,40],
          "protected_sha256":protected,"protected_files_changed":[],"overlay_path":row["overlay_path"],
          "other_samples_user_feedback":"User reported no boundary issues on 635,636,647,654; no candidate statuses or acceptance changed here."})
    print(f"Updated only {list(CORRECTIONS)}; new overlay: {OUT / overlay_name}")


if __name__ == "__main__":
    main()
