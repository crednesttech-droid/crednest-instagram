# Claude render audit — 22 October–12 November 2026

Inspected all 13 saved JPEGs individually at their native 1080 × 1350 resolution, the contact sheets, the reference carousel `media/car-2026-10-21/`, the supplied Instagram templates, and the five carousels' slides 02–05. No media, queue, captions or renderer were edited for this audit.

## Measurement method

Headline size below is the value returned by Claude's `fit_headline()` using `scripts/render_hooks.py` and the repository's Manrope font files. Line count is the number visibly present in the saved Claude JPEG. These are distinguished because the saved D21 image wraps differently from a fresh evaluation of the current source/font metrics: its visible lines are “Bank statement / says one thing. / ITR says / another?”, while current source calculation returns “Bank / statement says / one thing. ITR / says another?”. Do not claim exact raster font provenance from a JPEG alone.

All 13 have the same bottom readability concern: contact text is specified at 26 px with its origin at y=1222, and the disclaimer at 20 px at y=1266 and y=1292. At a 360 px display width these correspond to about 8.7 px and 6.7 px nominal type. The disclaimer falls wholly in the bottom 120 px and is too small for comfortable phone reading; contrast is adequate, but type size and placement need improvement. All use generic decorative rings instead of a topic-specific visual anchor.

| Item | Source headline size / visible lines | Ring interference and middle whitespace | Carousel consistency / other finding |
| --- | --- | --- | --- |
| D09-feed | 124 px / 4 | Outer ring intersects the last headline's question mark and crosses the subtitle near “discussion.” No large empty middle region. | Same brand palette as 02+, but header scale, kicker/progress treatment and footer differ; see shared carousel findings. Illustrative tag is already small on 01. |
| D10-feed | 116 px / 4 | Rings cross subtitle at its right end (“EMIs, in one”); headline and points are clear. No excessive middle whitespace. | Shared carousel header/footer inconsistency. Forest-to-paper transition alone is consistent with the brand palette and is not a defect. |
| D16-feed | 124 px / 4 | Outer ring crowds lower-right headline edge and crosses the subtitle's final “meeting.” Headline overlap itself is not established. No excessive middle whitespace. | Shared carousel header/footer inconsistency. |
| D20-feed | 124 px / 3 | No headline/point overlap. About 300 px of unstructured space between subtitle and Swipe; the ring is the only lower composition element and has no property-related meaning. | Shared carousel header/footer inconsistency. Paper cover fits the palette of the explanation slides. |
| D21-feed | 116 px calculated / 4 visible | Ring crosses subtitle (“lender asks.”). Unanchored gap of roughly 200 px before Swipe, less severe than D20. No headline/point overlap seen. | Shared carousel header/footer inconsistency. Illustrative tag is already small on 01. |
| D13-feed | 100 px / 3 | No ring/headline/point overlap; right-edge rings stay beyond numbered text. The content-to-CTA gap is modest. | Single; bottom footer readability concern applies. |
| D18-feed | 100 px / 3 | No ring/headline/point overlap. Some spare lower space, but not a cover and no collision. | Single; bottom footer readability concern applies. |
| D19-new | 100 px / 3 | No ring/headline/point overlap. | Single; bottom footer readability concern applies. |
| D22-new | 100 px / 3 | No ring/headline/point overlap. | Single; bottom footer readability concern applies. |
| D23-new | 100 px / 2 | No ring/headline/point overlap. Large unstructured lower middle after the three points (roughly 300 px to CTA); a ledger/60-day motif would give it meaning. | Single; bottom footer readability concern applies. |
| D25-new | **88 px / 3** | No ring/headline/point overlap. | **Fails the 90 px headline threshold.** Bottom footer readability concern applies. |
| D27-feed | 96 px / 3 | No ring/headline/point overlap; small illustrative tag sits above CTA. | Single; bottom footer readability concern applies. |
| D30-new | 100 px / 3 | No ring/headline/point overlap. | Single; bottom footer readability concern applies. |

No saved headline exceeds four lines. D25 is the only source-calculated headline below 90 px.

## Carousel slide audit

The cover background changing from dark/forest to paper explanation slides and lime CTA slides follows the references; that colour transition is not itself a style mismatch. Concrete inconsistencies are the header/logo wordmark scale, cover-only kicker versus 02+ progress-line treatment, and different footers. Slides 02–05 currently lack the required `crednest.io · WhatsApp +91 98199 99057` line, use the obsolete wording “CredNest is an advisory firm, not a lender…”, and use small low footer text. They should receive the same production footer system as the rebuilt covers.

| Carousel | Does existing 02+ copy contradict new cover? | Necessary copy change beyond footer/style |
| --- | --- | --- |
| D09-feed | No. The supply-contract scenario, underlying documents and instrument-to-requirement discussion support the BG hook. | **02:** change “Illustrative scenario: a supply contract.” to “A supply contract.” and print the full illustrative tag small. This enforces the user's prohibition on using the tag as a headline. |
| D10-feed | No. Ownership/title/KYC, income/banking/commitments and use-of-funds content support the papers-ready hook. | None. |
| D16-feed | No. Project explanation, distinct CMA/DPR purposes and consistent records answer the cover question without asserting one document is always sufficient. | None. |
| D20-feed | No. Repayment capacity/obligations, title/valuation and lender's assessment all support “Loan pakka? Nahi.” | None. |
| D21-feed | No. Inconsistent banking/financial records, identifying gaps and preparation support the statement-versus-ITR hook. | **02:** change “Illustrative scenario: a manufacturer.” to “A manufacturer.” and print the full illustrative tag small. |

Recommended additional changed slides: `media/D09-feed/{02,03,04,05}.jpg`, `media/D10-feed/{02,03,04,05}.jpg`, `media/D16-feed/{02,03,04,05}.jpg`, `media/D20-feed/{02,03,04,05}.jpg`, `media/D21-feed/{02,03,04,05}.jpg` — 20 total. All need footer/style consistency; D09/02 and D21/02 additionally need the illustrative-tag title adjustment. No caption edits are recommended by this visual audit.
