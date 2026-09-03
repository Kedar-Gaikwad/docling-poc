# Databricks / AWS later

This folder is the **phase 2** landing zone. Phase 1 of the POC runs entirely on the laptop.

## Intended AWS shape (not built yet)

```
S3 inbound bucket
        │
        ▼
EventBridge / S3 notify
        │
        ▼
ECS/Fargate or g6.xlarge EC2  ── Docling worker (layout + TableFormer + RapidOCR)
        │
        ▼
S3 outbound  (markdown, JSON, per-table CSV)
        │
        ▼
Optional: compare job that still calls Textract AnalyzeDocument TABLES
          on a sample % of pages for quality QA
```

## Why not Lambda

Docling loads layout + TableFormer (+ OCR) models. Cold start and the 10 GB Lambda disk/memory ceiling make ECS/EC2 the honest production target. The IBM paper used `g6.xlarge` (1× L4).

## Cost inputs to carry into the AWS build

| Piece | Rate used in this POC |
|---|---|
| Textract Tables | $0.015 / page (first 1M / month) |
| Textract Forms | $0.050 / page |
| g6.xlarge on-demand us-east-1 | $0.8048 / hour |
| Docling software | $0 (MIT) |

Re-measure `seconds_per_page` on the actual AWS instance before locking a savings number. Laptop GPU (RTX 4080) is faster than an L4 in some cases and not a substitute for a production benchmark.

## Next step

After the local quality/cost run looks good:

1. Containerize `src/docling_runner.py`
2. Push to ECR
3. Run a g6.xlarge / ECS task against the same sample PDFs
4. Recompute `output/reports/cost.json` with AWS-measured seconds/page
