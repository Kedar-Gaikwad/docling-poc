# Local run — 2 September 2026

Machine: Windows, Python 3.12.8, Docling 2.124.0, RapidOCR ONNX, TableFormer ACCURATE, PyTorch 2.6.0+cu124 on RTX 4080 Laptop GPU (12 GB).

Textract `AnalyzeDocument` was **not** executed: IAM user `Kedar-Gaikwad2` has no `textract:AnalyzeDocument` permission. Quality is scored against generated ground truth. Costs use [official Textract list prices](https://aws.amazon.com/textract/pricing/).

## Quality (bag-of-cells recall vs ground truth)

| Document | Kind | Tables found | Cell recall | Notes |
|---|---|---|---|---|
| invoice_digital | digital | 2 (KV + line items) | **1.000** | Line items exact; extra KV table also recovered |
| invoice_scanned | image-only OCR | 1 | **1.000** | Same grid as digital after RapidOCR |
| financials_digital | digital | 1 | **1.000** | Full P&L including Net margin % |
| financials_scanned | image-only OCR | 1 | **0.976** | Q1 Operating expenses read as `32` instead of `3.2` |
| account_form_digital | digital | 2 | **1.000** | Header KV + service table |

Verdict on **these** pages: Docling is a credible Tables substitute. The only miss was one OCR decimal on a scanned P&L. Real vendor PDFs still need a pass before a production cutover.

## Timing (seconds / page, CUDA layout+TableFormer, RapidOCR CPU)

| Document | Seconds |
|---|---|
| account_form_digital (cold start) | 9.146 |
| financials_digital | 1.551 |
| invoice_digital | 2.587 |
| invoice_scanned | 2.053 |
| financials_scanned | 3.517 |
| **Median (used in cost model)** | **2.587** |

Cold start loads TableFormer weights once. Warm digital pages are ~1.6–2.6 s. Scanned (forced OCR) ~2–3.5 s.

## Dollar model

Assumptions: median 2.587 s/page, `g6.xlarge` $0.8048/hr on-demand us-east-1, 70% utilization, Textract Tables $0.015/page (first 1M).

| Pages / month | Textract Tables | Textract Tables+Forms | Docling compute | Saved vs Tables |
|---|---|---|---|---|
| 10,000 | $150 | $650 | $8.26 | $141.74 (94.5%) |
| 50,000 | $750 | $3,250 | $41.31 | $708.69 (94.5%) |
| 100,000 | $1,500 | $6,500 | $82.62 | $1,417.38 (94.5%) |
| 250,000 | $3,750 | $16,250 | $206.55 | $3,543.45 (94.5%) |
| 500,000 | $7,500 | $32,500 | $413.10 | $7,086.90 (94.5%) |
| 1,000,000 | $15,000 | $65,000 | $826.20 | $14,173.80 (94.5%) |

Docling software is $0. The $8–$826 column is GPU time only. Re-measure seconds/page on the real AWS instance before locking a budget. Forms ($50/1k) is **not** in the replacement set — if you need Textract FORMS, savings vs Tables+Forms are even larger on paper but quality is no longer 1:1.
