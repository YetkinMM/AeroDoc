# Extraction Audit — Human Factors

Current implementation: [fixed approved region extraction](approved_region_extraction.md).
The sections below also preserve findings from the earlier three-region baseline.

## Scope

- Document: FAA-H-8083-30B, Aviation Maintenance Technician Handbook — General
- Chapter: Human Factors
- Selected PDF pages: 624–655 inclusive (32 pages)
- Printed pages: 14-1–14-32
- Extractor: PyMuPDF 1.26.6
- Method: text blocks, two-column ordering, optional page-specific figure regions
- Review: historical checks of five sample pages; subsequent human boundary approvals
  cover region geometry only, not full text, internal figure order or semantics

## Boundary checks

| PDF page | Expected printed label | Result |
|---|---|---|
| 623 | No visible label | PASS |
| 624 | 14-1 | PASS |
| 655 | 14-32 | PASS |
| 656 | G-1 | PASS |

## Reviewed samples

| PDF page | Printed page | Layout | Findings |
|---|---|---|---|
| 624 | 14-1 | Two-column body text | Reading order, numbered lists and footer removal checked. Body text remained byte-identical after the figure separation change, verified by file hashes. |
| 625 | 14-2 | Two columns above a full-width figure | Figure 14-1 and its caption separated into one figure record containing 7 text blocks. The body continues from “deployment of systems” to “and services” without figure text between them. |
| 636 | 14-13 | Body text with an upper-right diagram | SHEL diagram and caption separated into one figure record containing 5 text blocks. Body order and the Active & Latent section preserved. |
| 645 | 14-22 | Full-width graph above two columns | Graph and caption separated into one figure record containing 14 text blocks. The sentence spanning columns continues in the correct order. |
| 655 | 14-32 | Full-width incident/cause boxes | Five event–cause pairs appear in the correct order. Figure 14-37 caption retained. Column-crossing warning manually reviewed; content remains in the body output. |

## Page-specific figure regions

Coordinates are PDF points in [x0, y0, x1, y1] order.

| PDF page | Region |
|---|---|
| 625 | [50, 450, 546, 716] |
| 636 | [300, 35, 546, 260] |
| 645 | [50, 35, 546, 290] |

These regions are manual overrides for the reviewed pages, not a general figure detector.

## Known limitations

- Only five sample pages have been visually reviewed. The remaining 27 pages are not yet validated.
- Zero warnings does not guarantee correct extraction or reading order.
- Figure text is preserved separately, but its internal reading order and diagram relationships have not been validated.
- Page 655 is a text-rich figure. Its event–cause content must remain available for retrieval.
- Source line breaks, separated list numbers and column-boundary paragraph breaks remain in the text.
- Line-end hyphenation, such as “uncom-” followed by “manded”, requires careful normalization.
- Sentences can continue across pages. Future chunks must retain all contributing PDF page numbers.
- Generated JSON records still use `needs_manual_review`; this report documents the checks performed.

## Next steps

1. Add layout handling for full-width content while preserving event–cause relationships.
2. Extract all 32 selected pages and flag layouts requiring review.
3. Normalize text without modifying generated TXT files manually.
4. Recheck the five samples after extraction changes.
5. Preserve document identity, source hash, PDF page numbers and printed page labels during chunking.

## Historical batch extraction implementation (v3)

Run `.\.venv\Scripts\python.exe scripts/extract_corpus.py` from the repository root.
The shared extractor is `scripts/extraction.py`; the single-page command remains
available and accepts `--output` for isolated checks. An existing source manifest
is not rewritten.

Batch artifacts are stored under `audit/corpus/` (ignored by Git). `pages.jsonl`
retains raw text, ordered body blocks, removed footer blocks and provenance.
`figures.jsonl` stores separate `type=figure` records, also embedded in the page
records for compatibility. Index each figure only once in future retrieval.
No general figure detection or text normalization has been added.

`baseline/` preserves the five pre-existing sample outputs with file hashes.
`run_summary.json` records exact body, body-block, figure-content and raw-text
comparisons and the full five event/cause pairs on page 655. Regression failure
produces reports and a nonzero exit status. Source validation failures stop before
publishing extraction records. The review reports distinguish automatic warnings
from human review; all new records remain `not_reviewed`.

The full run extracted 32 pages and 3 configured figures. All five samples matched
their prior body text, body blocks, figure blocks and raw text exactly. Page 655
retained five event/cause pairs in the expected order: Excalibur Airways, Emery
Worldwide, China Airlines, Colgan Air, American Airlines. The complete pair texts
also matched the baseline exactly.

Automatic column-boundary warnings occurred on PDF pages 626, 628, 629, 633, 634,
635, 638, 640, 641, 642, 643, 644, 646, 648, 649, 650, 651, 652, 654 and 655.
Page 651 additionally has a body block intersecting the footer region.
Configured figure text on 625, 636 and 645 still needs internal-order review.
The previous sample checks do not validate the other 27 pages or approve the new
batch automatically. Normalization, chunking and retrieval remain future work.

## Fixed approved regions v4

The extractor now reads only `config/figure_regions.json` via `figure_regions_path`.
The old three regions in `corpus.json` remain historical review inputs, not live
extraction rules. PDF hash, approval geometry, duplicate figures, overlapping
active regions and page/footer bounds are validated before extraction starts.

There are 37 unique active regions: 36 inline figure records and one reference-only
record for page 655. Page JSON records contain references, not embedded figure
content. All five event/cause pairs, headings and caption on 655 stay in the page
body in the existing order; the figure reference is not separately indexable.

All 670 source text blocks have one content owner: 245 body, 393 figure, 32 footer.
The five regression page bodies and the three existing manual figure contents are
unchanged. The other 25 pages retain the relative order of remaining body blocks
after figure removal; specific cross-column continuations are checked separately.
Page 647's `very / difficult` continuation is adjacent. Page 651's third list
item is intact; the 0.359314 pt footer intersection remains a warning, not clipping.
Page 655 retains its expected full-width warning. No footer tolerance changed.

Boundary approvals are human_verified only for region_boundary_only. Generated
page/content review status and internal figure order/semantic relations remain
unreviewed. No normalization or chunking has been applied.
