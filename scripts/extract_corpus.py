"""Extract configured pages without normalization; retain provenance and review evidence."""

import difflib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from extraction import EXTRACTOR_VERSION, extract_page, footer_label, load_figure_regions, sha256, split_records, write_json

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/corpus.json"
OUTPUT = ROOT / "audit/corpus"
SAMPLES = (624, 625, 636, 645, 655)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_source(config, pdf_path, document, digest):
    """Fail closed before publishing any extraction output."""
    manifest = read_json(pdf_path.with_name("manifest.json"))
    if manifest.get("sha256") != digest:
        raise ValueError("PDF SHA-256 differs from manifest.json")
    for key, value in (("document_id", config["document_id"]),
                       ("source_url", config["source_url"]),
                       ("page_count", len(document))):
        if manifest.get(key) != value:
            raise ValueError(f"Manifest {key} mismatch")
    if len(document) != config["expected_page_count"]:
        raise ValueError("PDF page count differs from config")
    if config["page_numbering"] != "one_based_inclusive":
        raise ValueError("Unsupported page numbering")
    pages = []
    for selected in config["page_ranges"]:
        start, end = selected["start"], selected["end"]
        if not 1 <= start <= end <= len(document):
            raise ValueError("Invalid selected page range")
        pages.extend(range(start, end + 1))
    if not pages or len(pages) != len(set(pages)):
        raise ValueError("Empty or overlapping page ranges")
    checks = []
    for expected in config["audit"]["boundary_checks"]:
        n = expected["pdf_page"]
        if not 1 <= n <= len(document):
            raise ValueError(f"Invalid boundary page: {n}")
        page = document[n - 1]
        label = footer_label(page, config["audit"]["footer_height_points"])
        # Whitespace folding is only for marker checks, never for stored text.
        text = " ".join(page.get_text().split())
        missing = [s for s in expected.get("required_text", []) if s not in text]
        checks.append({"pdf_page": n, "expected_printed_page": expected["printed_page"],
                       "actual_printed_page": label, "missing_markers": missing,
                       "passed": label == expected["printed_page"] and not missing})
    if not checks or not all(c["passed"] for c in checks):
        raise ValueError(f"Chapter boundary checks failed: {checks}")
    return sorted(pages), checks


def preserve_baseline():
    """Create an immutable comparison copy before either command can overwrite audits."""
    baseline = OUTPUT / "baseline"
    index_path = baseline / "files.json"
    if index_path.exists():
        index = read_json(index_path)
        for name, digest in index.items():
            if sha256(baseline / name) != digest:
                raise ValueError(f"Baseline file changed: {name}")
        return baseline, index
    required = [ROOT / "audit" / f"page_{n}.{suffix}"
                for n in SAMPLES for suffix in ("json", "txt", "raw.txt", "png")]
    if not all(path.is_file() for path in required):
        # Historical audit images/text are intentionally not tracked by Git.
        # They are optional comparison inputs, never a source of extraction rules.
        return None, {}
    baseline.mkdir(parents=True, exist_ok=True)
    index = {}
    for n in SAMPLES:
        for suffix in ("json", "txt", "raw.txt", "png"):
            source = ROOT / "audit" / f"page_{n}.{suffix}"
            if not source.is_file():
                raise ValueError(f"Missing sample audit: {source}")
            target = baseline / source.name
            if target.exists() and sha256(target) != sha256(source):
                raise ValueError(f"Refusing to overwrite baseline: {target}")
            shutil.copy2(source, target)
            index[source.name] = sha256(target)
    write_json(index_path, index)
    return baseline, index


def event_cause_pairs(text):
    pattern = r"(?m)^(INCIDENT|ACCIDENT)\n\n(.*?)\n\nCAUSE\n\n(.*?)(?=\n\n(?:INCIDENT|ACCIDENT|Figure 14-37\.)|\Z)"
    return [{"event_type": m[0], "event_text": m[1], "cause_text": m[2]}
            for m in re.findall(pattern, text, flags=re.DOTALL)]


def compare_samples(records, baseline):
    by_page = {r["pdf_page"]: r for r in records}
    comparisons = []
    for n in SAMPLES if baseline is not None else ():
        old, new = read_json(baseline / f"page_{n}.json"), by_page[n]
        def canonical_blocks(blocks):
            return [{k:v for k,v in b.items() if k != "source_block_id"} for b in blocks]
        def canonical_figures(figures):
            return [{"bbox":f["bbox"],"blocks":canonical_blocks(f["blocks"]),"text":f["text"]}
                    for f in figures if f.get("content_storage", "inline") == "inline"]
        old_figures = canonical_figures(old["figures"])
        new_figures = canonical_figures(new["figures"])
        comparisons.append({
            "pdf_page": n,
            "body_identical": old["text"] == new["text"],
            "body_txt_identical": (baseline / f"page_{n}.txt").read_text(encoding="utf-8") == new["text"],
            "body_blocks_identical": old["ordered_blocks"] == canonical_blocks(new["ordered_blocks"]),
            "figure_content_identical": old_figures == new_figures,
            "figure_block_count": sum(len(f.get("blocks",[])) for f in new["figures"]),
            "body_reference_figure_count": sum(f.get("content_storage") == "page_body_reference" for f in new["figures"]),
            "raw_text_identical": (baseline / f"page_{n}.raw.txt").read_text(encoding="utf-8") == new["raw_text"],
            "body_diff": list(difflib.unified_diff(old["text"].splitlines(), new["text"].splitlines(), fromfile="baseline", tofile="new")),
            "figure_diff": list(difflib.unified_diff(json.dumps(old_figures, ensure_ascii=False, indent=2).splitlines(), json.dumps(new_figures, ensure_ascii=False, indent=2).splitlines())),
        })
    old_pairs = event_cause_pairs(read_json(baseline / "page_655.json")["text"]) if baseline is not None else None
    new_pairs = event_cause_pairs(by_page[655]["text"])
    expected_events = ("Excalibur Airways", "Emery Worldwide", "China Airlines", "Colgan Air", "American Airlines")
    pairs_check = {
        "pdf_page": 655, "pair_count": len(new_pairs),
        "five_pairs_in_expected_order": len(new_pairs) == 5 and all(
            name in pair["event_text"] for name, pair in zip(expected_events, new_pairs)),
        "text_and_order_identical_to_baseline": len(old_pairs) == 5 and old_pairs == new_pairs if old_pairs is not None else None,
        "pairs": new_pairs,
    }
    return comparisons, pairs_check


def write_jsonl(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def main():
    config = read_json(CONFIG)
    config_hash = sha256(CONFIG)
    pdf_path = ROOT / config["pdf_path"]
    digest = sha256(pdf_path)
    with pymupdf.open(pdf_path) as document:
        pages, checks = validate_source(config, pdf_path, document, digest)
        region_bundle = load_figure_regions(config, digest, document)
        baseline, baseline_hashes = preserve_baseline()
        records = []
        first = next(c for c in checks if c["pdf_page"] == pages[0])
        prefix, start_label = first["actual_printed_page"].rsplit("-", 1)
        for n in pages:
            record = extract_page(document[n - 1], n, config, digest, config_hash, region_bundle)
            expected_label = f"{prefix}-{int(start_label) + n - pages[0]}"
            if record["printed_page"] != expected_label:
                record["warnings"].append(f"Unexpected printed label; expected {expected_label}.")
                record["automatic_status"] = "warnings"
            records.append(record)
    comparisons, pairs_check = compare_samples(records, baseline)
    figures = [figure for record in records for figure in record["figures"]]
    review_pages = [{"pdf_page": r["pdf_page"], "printed_page": r["printed_page"],
                     "automatic_status": r["automatic_status"], "warnings": r["warnings"],
                     "human_review_status": r["human_review_status"],
                     "figure_review_required": bool(r["figures"])} for r in records]
    regression_passed = (all(all(c[k] for k in ("body_identical", "body_txt_identical", "body_blocks_identical", "figure_content_identical", "raw_text_identical")) for c in comparisons) and pairs_check["five_pairs_in_expected_order"] and pairs_check["text_and_order_identical_to_baseline"]) if comparisons else None
    regression_status = "not_available" if regression_passed is None else ("passed" if regression_passed else "failed")
    summary = {
        "document_id": config["document_id"], "corpus_version": config["corpus_version"],
        "source_sha256": digest, "source_url": config["source_url"], "config_sha256": config_hash,
        "extractor_version": EXTRACTOR_VERSION, "pymupdf_version": pymupdf.VersionBind,
        "figure_regions_sha256": region_bundle["sha256"],
        "figure_region_count": sum(len(rs) for rs in region_bundle["by_page"].values()),
        "source_block_count": sum(r["source_text_block_count"] for r in records),
        "all_source_blocks_preserved_once": all(r["all_source_blocks_preserved_once"] for r in records),
        "inline_figure_count": sum(f["content_storage"] == "inline" for f in figures),
        "body_reference_figure_count": sum(f["content_storage"] == "page_body_reference" for f in figures),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page_count": len(records), "figure_count": len(figures), "pdf_pages": pages,
        "boundary_checks": checks, "sample_comparisons": comparisons,
        "page_655_pairs": pairs_check, "regression_passed": regression_passed,
        "sample_regression_status": regression_status,
        "automatic_warning_pages": [r["pdf_page"] for r in records if r["warnings"]],
        "human_review_required_pages": pages, "baseline_file_sha256": baseline_hashes,
        "normalization_applied": False,
    }
    # Back up the entire prior output directory before replacing any artifacts.
    backup_path = None
    if OUTPUT.exists():
        backup_path = ROOT / "audit/corpus_backups" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8])
        shutil.copytree(OUTPUT, backup_path)
    summary["previous_output_backup"] = str(backup_path) if backup_path else None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUTPUT / "pages.jsonl", [split_records(r)[0] for r in records])
    write_jsonl(OUTPUT / "figures.jsonl", figures)
    write_json(OUTPUT / "review_report.json", review_pages)
    write_json(OUTPUT / "run_summary.json", summary)
    lines = ["# Corpus extraction review", "", f"Pages: {len(records)}; figures: {len(figures)}.",
             f"Sample regression: {regression_status} (historical audit samples are optional, not tracked).",
             "All pages retain human_review_status=not_reviewed. Zero warnings is not human validation.",
             "Prior sample reviews are documented in docs/extraction_audit.md; they are not new approvals.",
             "No normalization applied. Figure text order remains unverified.", "",
             "| PDF page | Printed label | Automatic warnings | Figure review |", "|---|---|---|---|"]
    for r in review_pages:
        lines.append(f"| {r['pdf_page']} | {r['printed_page']} | {'; '.join(r['warnings']) or 'None'} | {r['figure_review_required']} |")
    lines.extend(["", "## Sample comparisons", ""])
    for c in comparisons:
        lines.append(f"- {c['pdf_page']}: body={c['body_identical']}, blocks={c['body_blocks_identical']}, figures={c['figure_content_identical']}, raw={c['raw_text_identical']}; figure blocks={c['figure_block_count']}.")
        if c["body_diff"] or c["figure_diff"]:
            lines.extend(["```diff", *c["body_diff"], *c["figure_diff"], "```"])
    lines.extend(["", f"Page 655: {pairs_check['pair_count']} event/cause pairs; expected order={pairs_check['five_pairs_in_expected_order']}; exact baseline match={pairs_check['text_and_order_identical_to_baseline']}.",
                  "Full event/cause texts are retained in run_summary.json."])
    (OUTPUT / "review_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Extracted {len(records)} pages, {len(figures)} figures into {OUTPUT}")
    print(f"Automatic warning pages: {summary['automatic_warning_pages']}")
    print(f"Sample regression: {regression_status}")
    if regression_passed is False or not pairs_check["five_pairs_in_expected_order"]:
        raise SystemExit("Sample regression failed; inspect run_summary.json before downstream use.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        raise SystemExit(f"Extraction stopped: {exc}") from exc
