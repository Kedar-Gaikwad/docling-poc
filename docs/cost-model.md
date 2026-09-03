# Cost model

All numbers are **USD**. Textract rates are official pretrained list prices (us-east-1 / us-west-2). Docling software is $0; we only cost the machine.

## Textract (per page)

| Meter | ≤ 1M pages/month | > 1M pages/month |
|---|---|---|
| DetectDocumentText | 0.0015 | 0.0006 |
| TABLES | 0.015 | 0.010 |
| FORMS | 0.050 | 0.040 |
| LAYOUT | 0.004 | 0.003 |
| QUERIES | 0.015 | 0.015 |
| TABLES+FORMS | 0.065 | 0.050 |
| TABLES+FORMS+QUERIES | 0.070 | 0.055 |

LAYOUT is **free when combined with TABLES** (AWS pricing example 16). This POC still compares against TABLES alone because that is the line item teams actually feel.

Code: `src/config.py` → `TEXTRACT_USD_PER_PAGE`.

## Docling compute

```
hours = pages * seconds_per_page / 3600 / utilization
cost  = hours * ec2_hourly_on_demand
```

Default utilization = **0.70** (queue idle, model load, retries). Instance defaults:

| Instance | Hourly | Role |
|---|---|---|
| g6.xlarge | 0.8048 | 1× L4 — same class as the Docling paper |
| g4dn.xlarge | 0.5260 | cheaper T4 |
| c6i.2xlarge | 0.3400 | CPU-only |
| local_gpu | 0 | this laptop |

`python -m src.run_poc cost` substitutes **measured** seconds/page from `output/docling/run_summary.json` when present.

## What the model ignores (call these out in any exec summary)

- EBS, ECR, data transfer, CloudWatch
- Engineer time to operate a worker vs calling an API
- GPU spot (often 50–70% cheaper than on-demand)
- Pages that do **not** need tables (those should never have been sent to Textract TABLES)
- Human review / A2I
- Model download on first boot

Even with those, TABLES at $15/1k vs a few dollars of GPU time is the right order of magnitude. The POC exists to replace the order-of-magnitude claim with **your seconds/page and your documents**.

## How to quote savings

Use **one** sentence in reviews:

> At N pages/month, Textract TABLES is $X. Self-hosted Docling on g6.xlarge at our measured S s/page is $Y compute — about Z% less — provided table cell recall on the real corpus stays acceptable.

Do not quote the paper’s 114 ms/page unless we reproduce it on AWS with the same pipeline flags (OCR off vs on changes the number by 10×).
