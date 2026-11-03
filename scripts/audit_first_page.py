"""Audit boundary pages and extract one page.

Body text is read left column first, then right column.
Optional page-specific figure regions come from corpus.json.
Figure text is preserved separately and requires manual review.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/corpus.json"
LABEL = re.compile(r"(?:\d+|[A-Z]{1,4})-\d+")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def footer_label(page, footer_height):
    # Read the visible footer independently of extraction order.
    rect = page.rect
    region = pymupdf.Rect(
        rect.x0, rect.y1 - footer_height, rect.x1, rect.y1
    )
    lines = page.get_text("text", clip=region).splitlines()
    candidates = sorted({
        line.strip()
        for line in lines
        if LABEL.fullmatch(line.strip())
    })

    if len(candidates) > 1:
        raise SystemExit(
            "Multiple footer labels found; inspect the page."
        )

    return candidates[0] if candidates else None


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    if config["page_numbering"] != "one_based_inclusive":
        raise SystemExit(
            "Unsupported page_numbering: use one_based_inclusive."
        )

    pdf_path = ROOT / config["pdf_path"]
    if not pdf_path.is_file():
        raise SystemExit(f"Place the original FAA PDF at: {pdf_path}")

    digest = sha256(pdf_path)
    manifest_path = pdf_path.parent / "manifest.json"

    if manifest_path.exists():
        previous = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        if previous.get("sha256") != digest:
            raise SystemExit(
                "PDF SHA-256 differs from manifest.json. "
                "Check the source edition first."
            )

    audit_config = config["audit"]
    page_number = audit_config["pdf_page"]
    footer_height = audit_config["footer_height_points"]

    with pymupdf.open(pdf_path) as doc:
        for selected in config["page_ranges"]:
            if not 1 <= selected["start"] <= selected["end"] <= len(doc):
                raise SystemExit(
                    "Selected page range is outside this PDF."
                )

        if not any(
            r["start"] <= page_number <= r["end"]
            for r in config["page_ranges"]
        ):
            raise SystemExit(
                "The audit page must be inside the selected page ranges."
            )

        if len(doc) != config["expected_page_count"]:
            raise SystemExit(
                f"Expected {config['expected_page_count']} PDF pages; "
                f"found {len(doc)}."
            )

        checks = []

        for expected in audit_config["boundary_checks"]:
            n = expected["pdf_page"]
            if not 1 <= n <= len(doc):
                raise SystemExit(
                    f"Boundary page {n} is outside this PDF."
                )

            boundary_page = doc[n - 1]
            actual = footer_label(boundary_page, footer_height)
            page_text = " ".join(boundary_page.get_text().split())
            missing = [
                s for s in expected.get("required_text", [])
                if s not in page_text
            ]
            passed = (
                actual == expected["printed_page"] and not missing
            )

            checks.append({
                "pdf_page": n,
                "expected_printed_page": expected["printed_page"],
                "actual_printed_page": actual,
                "missing_markers": missing,
                "passed": passed,
            })

            status = "PASS" if passed else "FAIL"
            print(f"Boundary {n}: label={actual}, {status}")

        output = ROOT / "audit"
        write_json(output / "boundary_check.json", checks)

        if not all(c["passed"] for c in checks):
            raise SystemExit(
                "Boundary check failed. "
                "Inspect audit/boundary_check.json."
            )

        page = doc[page_number - 1]
        printed_page = footer_label(page, footer_height)

        if printed_page is None:
            raise SystemExit(
                "Cannot read one unambiguous printed page label."
            )

        split_x = (
            page.rect.x0
            + page.rect.width * audit_config["column_split_fraction"]
        )
        footer_top = page.rect.y1 - footer_height

        blocks, removed, warnings = [], [], []
        figure_blocks = []

        figure_region = audit_config.get(
            "figure_regions_by_page", {}
        ).get(str(page_number))

        if figure_region is not None:
            if (
                not isinstance(figure_region, list)
                or len(figure_region) != 4
                or not all(
                    isinstance(v, (int, float))
                    for v in figure_region
                )
            ):
                raise SystemExit(
                    "Figure region must contain four numeric coordinates."
                )

            fx0, fy0, fx1, fy1 = figure_region

            if not (
                page.rect.x0 <= fx0 < fx1 <= page.rect.x1
                and page.rect.y0 <= fy0 < fy1 <= footer_top
            ):
                raise SystemExit(
                    "Figure region must be inside the page "
                    "and above the footer."
                )

        for block in page.get_text("blocks", sort=False):
            if block[6] != 0:
                continue

            x0, y0, x1, y1, block_text = block[:5]
            item = {
                "bbox": [x0, y0, x1, y1],
                "text": block_text.strip(),
            }

            if y0 >= footer_top:
                removed.append(item)
                continue

            if figure_region is not None:
                fully_inside = (
                    x0 >= fx0 and y0 >= fy0
                    and x1 <= fx1 and y1 <= fy1
                )

                if fully_inside:
                    figure_blocks.append(item)
                    continue

                overlaps = (
                    x0 < fx1 and x1 > fx0
                    and y0 < fy1 and y1 > fy0
                )
                if overlaps:
                    warnings.append(
                        "A text block partially overlaps the figure "
                        "region; inspect the region boundary."
                    )

            if y1 > footer_top:
                warnings.append(
                    "A body text block intersects the footer region; "
                    "inspect it."
                )

            if x0 < split_x < x1:
                warnings.append(
                    "A text block crosses the column boundary; "
                    "manual ordering is required."
                )

            item["column"] = (
                "left" if (x0 + x1) / 2 < split_x else "right"
            )
            blocks.append(item)

        # Complete the left body column before reading the right.
        blocks.sort(
            key=lambda b: (
                b["column"] == "right",
                b["bbox"][1],
                b["bbox"][0],
            )
        )
        text = "\n\n".join(
            b["text"] for b in blocks if b["text"]
        ) + "\n"

        figures = []

        if figure_region is not None:
            if figure_blocks:
                figures.append({
                    "document_id": config["document_id"],
                    "pdf_page": page_number,
                    "printed_page": printed_page,
                    "bbox": figure_region,
                    "blocks": figure_blocks,
                    "text": "\n\n".join(
                        b["text"] for b in figure_blocks if b["text"]
                    ),
                    "text_order": "pdf_block_order_unverified",
                    "review_status": "needs_manual_review",
                })
            else:
                warnings.append(
                    "The configured figure region contains no "
                    "extractable text blocks; inspect it."
                )

        record = {
            "document_id": config["document_id"],
            "corpus_version": config["corpus_version"],
            "source_sha256": digest,
            "pdf_page": page_number,
            "printed_page": printed_page,
            "chapter": config["chapter"],
            "extraction_method": (
                "blocks_two_columns_with_optional_figure_region_v2"
            ),
            "pymupdf_version": pymupdf.VersionBind,
            "review_status": "needs_manual_review",
            "warnings": sorted(set(warnings)),
            "text": text,
            "ordered_blocks": blocks,
            "figures": figures,
            "removed_footer_blocks": removed,
        }

        stem = f"page_{page_number}"

        (output / f"{stem}.raw.txt").write_text(
            page.get_text(), encoding="utf-8"
        )
        (output / f"{stem}.txt").write_text(
            text, encoding="utf-8"
        )
        write_json(output / f"{stem}.json", record)
        page.get_pixmap(dpi=120, alpha=False).save(
            output / f"{stem}.png"
        )

        manifest = {
            "document_id": config["document_id"],
            "filename": pdf_path.name,
            "sha256": digest,
            "page_count": len(doc),
            "size_bytes": pdf_path.stat().st_size,
            "source_url": config["source_url"],
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }
        write_json(manifest_path, manifest)

    selected_count = sum(
        r["end"] - r["start"] + 1
        for r in config["page_ranges"]
    )

    print(
        f"PDF pages: {manifest['page_count']}; "
        f"selected pages: {selected_count}"
    )
    print(
        f"Extracted ONE page: PDF {page_number}, "
        f"printed {printed_page}"
    )
    print(f"Figure records: {len(figures)}")
    print(f"Figure text blocks: {len(figure_blocks)}")
    print("Manifest: data/raw/manifest.json")
    print(f"Review audit/{stem}.txt beside audit/{stem}.png")
    print(
        "Manual layout review is still required; warnings: "
        + str(len(record["warnings"]))
    )

    for warning in record["warnings"]:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()