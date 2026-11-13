"""Bounded offline experiment only; never imports or modifies the production extractor.

Two fixed methods: caption-anchored image placements, then enclosing vector frames.
Evaluation labels are assistant-authored references, NOT human validation or a test set.
"""

import collections
import hashlib
import json
import re
import time
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit/figure_region_probe"
PAGES = (625, 636, 645, 647, 635, 654)
CAPTION = re.compile(r"^Figure\s+\d+-\d+\.\s")
BUDGET_SECONDS = 720


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rect_union(rects):
    result = pymupdf.Rect(rects[0])
    for rect in rects[1:]:
        result |= pymupdf.Rect(rect)
    return result


def contains(outer, inner):
    return pymupdf.Rect(outer).contains(pymupdf.Rect(inner))


def noise_flags(rect, page_rect):
    rect = pymupdf.Rect(rect)
    flags = []
    if min(rect.width, rect.height) <= 1:
        flags.append("thin_horizontal_or_vertical_geometry")
    if rect.get_area() >= page_rect.get_area() * 0.9:
        flags.append("near_full_page_rectangle")
    if min(abs(rect.x0-page_rect.x0), abs(rect.x1-page_rect.x1),
           abs(rect.y0-page_rect.y0), abs(rect.y1-page_rect.y1)) <= 5:
        flags.append("near_page_edge")
    return flags


def collect(page):
    blocks = [{"id": b[5], "bbox": list(b[:4]), "text": b[4]}
              for b in page.get_text("blocks", sort=False) if b[6] == 0]
    captions = [b for b in blocks if CAPTION.match(b["text"].strip())]
    drawings = []
    for i, drawing in enumerate(page.get_drawings()):
        thin_segments = []
        for j, item in enumerate(drawing["items"]):
            if item[0] == "l":
                a, b = item[1:3]
                rect = pymupdf.Rect(min(a.x,b.x),min(a.y,b.y),max(a.x,b.x),max(a.y,b.y))
                flags = noise_flags(rect, page.rect)
                if flags:
                    thin_segments.append({"item_index": j, "bbox": list(rect), "flags": flags})
        drawings.append({"id": i, "bbox": list(drawing["rect"]),
                         "path_type": drawing["type"], "stroke_width": drawing.get("width"),
                         "noise_flags": noise_flags(drawing["rect"], page.rect),
                         "flagged_line_segments": thin_segments,
                         "policy": "flag_only_keep_as_context_possible_frame_or_axis"})
    images = [{"id": i, "bbox": list(info["bbox"]),
               "outside_page": not contains(page.rect, info["bbox"])}
              for i, info in enumerate(page.get_image_info())]
    return blocks, captions, images, drawings


def candidates(page, captions, images, drawings, iteration):
    regions = []
    for caption in sorted(captions, key=lambda b: b["bbox"][1]):
        cap = pymupdf.Rect(caption["bbox"])
        lower_bound = max([c["bbox"][3]+8 for c in captions if c["bbox"][3] < cap.y0] or [0])
        # A right-column caption limits the search to that lane. Left-anchored
        # captions may describe a full-width figure. No page-specific tuning.
        left = page.rect.width/2 if cap.x0 >= page.rect.width/2 else 0
        placements = [im for im in images if im["bbox"][0] >= left
                      and im["bbox"][1] >= lower_bound
                      and im["bbox"][3] <= cap.y0+2]
        frame = None
        if iteration == 2:
            eligible = [d for d in drawings
                        if d["bbox"][0] >= left
                        and d["bbox"][1] >= lower_bound
                        and 0 <= cap.y0-d["bbox"][3] <= 20
                        and pymupdf.Rect(d["bbox"]).width >= 120
                        and pymupdf.Rect(d["bbox"]).height >= 70
                        and d["bbox"][0] <= cap.x0+5
                        and d["bbox"][2] >= min(cap.x1, cap.x0+100)]
            if eligible:
                frame = max(eligible, key=lambda d: pymupdf.Rect(d["bbox"]).get_area())
        if frame:
            # Frame, not oversized shadows or image placement extents, bounds
            # visible contents. Primitive overshoots remain logged for review.
            region = rect_union([frame["bbox"], caption["bbox"]])
            region = pymupdf.Rect(region.x0-1, region.y0-1, region.x1+1, region.y1+1) & page.rect
        elif placements:
            region = rect_union([caption["bbox"], *[im["bbox"] for im in placements]]) & page.rect
        else:
            region = cap
        regions.append({"caption_id": caption["id"], "caption_text": caption["text"],
                        "bbox": list(region), "method": "vector_frame_plus_caption" if frame else "image_union_plus_caption",
                        "frame_drawing_id": frame["id"] if frame else None,
                        "image_placement_ids": [im["id"] for im in placements],
                        "overshooting_images": [im["id"] for im in images
                                                if frame and pymupdf.Rect(im["bbox"]).intersects(pymupdf.Rect(frame["bbox"]))
                                                and not contains(frame["bbox"], im["bbox"])],
                        "needs_visual_review": True})
    return regions


def reference_ids(n, blocks, manual_regions):
    """Independent evaluation-only labels from earlier visual samples.

    Existing manual zones are used only here, never for candidate generation.
    New reference labels describe the visually inspected figures on 635/647/654.
    These six pages are development examples, not held-out validation.
    """
    if str(n) in manual_regions:
        return {b["id"] for b in blocks if contains(manual_regions[str(n)], b["bbox"])}
    if n == 635:
        return {b["id"] for b in blocks if b["bbox"][3] <= 390}
    if n == 647:
        return {b["id"] for b in blocks if b["bbox"][0] >= 300 and b["bbox"][3] <= 384}
    if n == 654:
        return {b["id"] for b in blocks if b["bbox"][3] <= 384}
    raise ValueError(n)


def body_order(blocks, excluded, page):
    footer_top = page.rect.y1-54  # Existing cutoff, unchanged even for the experiment.
    body = [b for b in blocks if b["id"] not in excluded and b["bbox"][1] < footer_top]
    return sorted(body, key=lambda b: ((b["bbox"][0]+b["bbox"][2])/2 >= page.rect.width/2,
                                      b["bbox"][1], b["bbox"][0]))


def evaluate(n, page, blocks, regions, expected, manual):
    assignments = {}
    partial = []
    for b in blocks:
        matches = [i for i,r in enumerate(regions) if contains(r["bbox"], b["bbox"])]
        if len(matches) == 1:
            assignments[b["id"]] = matches[0]
        elif len(matches) > 1:
            partial.append({"id": b["id"], "reason": "multiple_regions_keep_in_body"})
        elif any(pymupdf.Rect(r["bbox"]).intersects(pymupdf.Rect(b["bbox"])) for r in regions):
            partial.append({"id": b["id"], "reason": "partial_overlap_keep_in_body"})
    actual = set(assignments)
    footer = {b["id"] for b in blocks if b["bbox"][1] >= page.rect.y1-54} - actual
    body = {b["id"] for b in blocks} - actual - footer
    emitted = list(actual)+list(footer)+list(body)
    preserved = collections.Counter(emitted) == collections.Counter(b["id"] for b in blocks)
    actual_body = body_order(blocks, actual, page)
    expected_body = body_order(blocks, expected, page)
    result = {"pdf_page": n, "source_text_block_count": len(blocks), "figure_block_count": len(actual),
              "expected_figure_block_count": len(expected), "missed_figure_ids": sorted(expected-actual),
              "incorrectly_captured_body_ids": sorted(actual-expected), "partial_overlaps": partial,
              "all_source_blocks_preserved_once": preserved,
              "body_order_matches_reference": [b["id"] for b in actual_body] == [b["id"] for b in expected_body],
              "body_ids": [b["id"] for b in actual_body], "reference_figure_ids": sorted(expected),
              "figure_assignments": assignments, "human_review_status": "not_reviewed",
              "evaluation_reference": "assistant_visual_labels_not_human_ground_truth"}
    if manual:
        union = rect_union([r["bbox"] for r in regions])
        m = pymupdf.Rect(manual)
        intersection = (union & m).get_area()
        result["manual_comparison"] = {"manual_bbox": manual, "candidate_bbox": list(union),
                                       "iou": intersection/(union.get_area()+m.get_area()-intersection),
                                       "same_text_block_membership": actual == expected}
    return result, actual_body


def main():
    started = time.monotonic()
    if not (OUT / "initial_state.json").exists():
        raise SystemExit("Record initial git status and protected hashes first.")
    config = json.loads((ROOT / "config/corpus.json").read_text(encoding="utf-8"))
    summary = {"pages": list(PAGES), "iteration_limit": 2, "budget_seconds": BUDGET_SECONDS,
               "production_changes": False, "iterations": [], "human_approval": False}
    with pymupdf.open(ROOT / config["pdf_path"]) as doc:
        for iteration in (1, 2):
            results = []
            for n in PAGES:
                if time.monotonic()-started > BUDGET_SECONDS:
                    raise SystemExit("Time budget exceeded; stop experiment and prefer manual/hybrid regions.")
                page = doc[n-1]
                blocks, captions, images, drawings = collect(page)
                regions = candidates(page, captions, images, drawings, iteration)
                expected = reference_ids(n, blocks, config["audit"]["figure_regions_by_page"])
                result, body = evaluate(n, page, blocks, regions, expected,
                                        config["audit"]["figure_regions_by_page"].get(str(n)))
                result["regions"] = regions
                result["captions"] = captions
                result["inline_figure_references_not_used_as_captions"] = [b["id"] for b in blocks if "Figure" in b["text"] and b not in captions]
                result["noise_path_count"] = sum(bool(d["noise_flags"] or d["flagged_line_segments"]) for d in drawings)
                results.append(result)
                save(f"iteration_{iteration}_page_{n}.json", {"evaluation": result, "source_blocks": blocks,
                     "images": images, "drawings": drawings, "body_text": "\n\n".join(b["text"] for b in body),
                     "figure_text_blocks": [b for b in blocks if b["id"] in result["figure_assignments"]]})
                # JSON object keys above remain ints until serialization.
                overlay = pymupdf.open()
                overlay.insert_pdf(doc, from_page=n-1, to_page=n-1)
                canvas = overlay[0]
                for r in regions:
                    canvas.draw_rect(pymupdf.Rect(r["bbox"]), color=(1,0,0), width=1.5, overlay=True)
                manual = config["audit"]["figure_regions_by_page"].get(str(n))
                if manual:
                    canvas.draw_rect(pymupdf.Rect(manual), color=(0,0.55,0), width=1, overlay=True)
                canvas.get_pixmap(dpi=110, alpha=False).save(OUT / f"iteration_{iteration}_page_{n}.png")
                overlay.close()
            summary["iterations"].append({"iteration": iteration, "results": results})
            print(f"Iteration {iteration}: " + "; ".join(f"{r['pdf_page']} missed={len(r['missed_figure_ids'])} body_captured={len(r['incorrectly_captured_body_ids'])} order={r['body_order_matches_reference']}" for r in results), flush=True)
    snapshot = json.loads((OUT / "initial_state.json").read_text(encoding="utf-8"))
    changed = [name for name,digest in snapshot["protected_sha256"].items()
               if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest]
    summary["protected_files_changed"] = changed
    summary["elapsed_seconds"] = round(time.monotonic()-started, 3)
    save("summary.json", summary)
    if changed:
        raise SystemExit(f"Protected files changed: {changed}")
    print(f"Protected files unchanged; elapsed {summary['elapsed_seconds']} seconds.")


if __name__ == "__main__":
    main()
