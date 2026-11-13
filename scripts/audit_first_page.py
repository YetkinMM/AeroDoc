"""Audit boundary pages and extract one page.

Body text is read left column first, then right column.
Fixed approved figure regions come from config/figure_regions.json.
Figure text is preserved separately and requires manual review.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from extraction import extract_page, footer_label, load_figure_regions, sha256, split_records, write_json

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/corpus.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "audit")
    output = parser.parse_args().output
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
        region_bundle = load_figure_regions(config, digest, doc)
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

        record = extract_page(page, page_number, config, digest, sha256(CONFIG_PATH), region_bundle)
        text = record["text"]
        figures = record["figures"]
        figure_blocks = [b for f in figures for b in f.get("blocks",[])]

        stem = f"page_{page_number}"

        (output / f"{stem}.raw.txt").write_text(
            page.get_text(), encoding="utf-8"
        )
        (output / f"{stem}.txt").write_text(
            text, encoding="utf-8"
        )
        write_json(output / f"{stem}.json", split_records(record)[0])
        write_json(output / f"{stem}.figures.json", figures)
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
        if not manifest_path.exists():
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
    print(f"Review {output / (stem + '.txt')} beside {output / (stem + '.png')}")
    print(
        "Manual layout review is still required; warnings: "
        + str(len(record["warnings"]))
    )

    for warning in record["warnings"]:
        print(f"WARNING: {warning}")


if __name__ == "__main__":
    main()
