# Extraction Audit — Human Factors

## Scope

- Document: FAA-H-8083-30B, Aviation Maintenance Technician Handbook — General
- Chapter: Human Factors
- Selected PDF pages: 624–655 inclusive (32 pages)
- Printed pages: 14-1–14-32
- Extractor: PyMuPDF 1.26.6
- Method: text blocks, two-column ordering, optional page-specific figure regions
- Review: manual comparison of extracted text with rendered page images

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