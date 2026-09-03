# Docling as an alternative to AWS Textract

**Question:** can IBM Docling replace AWS Textract for OCR + table layout extraction, and how much money does that save?

**Answer shape:** local run first (this repo), then the same worker on AWS (`aws/`). Docling is MIT-licensed — the software is $0. Textract Tables is **$15 per 1,000 pages**. That gap is the POC.

Docling is **not** a raw OCR engine. It is a document-understanding pipeline: layout model → optional OCR → TableFormer (rows/columns/cells) → `DoclingDocument` (markdown / JSON / CSV). OCR is a plugin (RapidOCR here). The expensive Textract feature it actually competes with is **AnalyzeDocument TABLES**, not DetectDocumentText.

## What Textract charges (us-east-1 / us-west-2, pretrained)

| Feature | First 1M pages / month | What you get |
|---|---|---|
| Detect Document Text | $1.50 / 1,000 pages | Words + geometry |
| AnalyzeDocument **Tables** | **$15 / 1,000 pages** | Rows, columns, cells (OCR included) |
| AnalyzeDocument Forms | $50 / 1,000 pages | Key-value pairs |
| Tables + Forms | $65 / 1,000 pages | Both, billed additively |
| Tables + Forms + Queries | $70 / 1,000 pages | All three |
| Layout with Tables | Layout is free when combined with Tables | |

Source: [Amazon Textract pricing](https://aws.amazon.com/textract/pricing/). Volume discount after 1M pages/month (Tables drops to $10 / 1,000).

**Implication:** if you only need plain text, Textract is already cheap. The bill blows up when every page goes through Tables (and worse, Forms). This POC targets that Tables path.

## What Docling costs

| Piece | Cost |
|---|---|
| Software (MIT) | $0 |
| This laptop | $0 software; we measure **seconds/page** |
| AWS `g6.xlarge` (1× L4, paper hardware) | $0.8048 / hour on-demand us-east-1 |
| AWS `c6i.2xlarge` (CPU) | ~$0.34 / hour |

Compute formula used in `src/cost_model.py`:

```
hours = pages × seconds_per_page / 3600 / 0.70 utilization
usd   = hours × instance_hourly_rate
```

IBM's [Docling technical report](https://arxiv.org/abs/2408.09869) measured **median 114 ms/page on L4** and **0.79 s/page on 8-vCPU x86** *without* treating OCR as always-on. OCR is the slow part (their numbers: ~1.6 s/page EasyOCR on L4, ~13 s/page on CPU). Our local run records the real seconds/page for *these* PDFs; the cost table uses that, not the paper.

## What this POC does *not* claim

Docling is a weak 1:1 for:

- **AnalyzeExpense / AnalyzeID / AnalyzeLending** — specialized APIs, keep Textract
- **Queries / Custom Queries** — no equivalent without an extra LLM step
- **Forms key-value** — Docling can emit tables and text; it is not Textract FORMS
- **Handwriting / signatures** — Textract still wins
- **SLA / managed scale** — you operate the box

The honest replacement set is: **printed OCR + page layout + table structure**.

## Local quick start

Python 3.12 via `uv` (system Python here is 3.14; Docling/torch are pinned to 3.12).

```powershell
cd D:\Research\docling-poc
uv python pin 3.12
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -e .
```

GPU: this machine has an RTX 4080. Layout + TableFormer will use CUDA if PyTorch sees it. RapidOCR in this POC uses the ONNX Runtime CPU backend (Windows-friendly). Phase 2 on AWS can switch OCR to a GPU engine.

```powershell
python -m src.run_poc all --skip-textract
```

That will:

1. Write five one-page PDFs under `data/samples/` (digital + scanned invoice, digital + scanned financials, digital account form)
2. Run Docling with TableFormer **ACCURATE** + RapidOCR
3. Score cell recall against ground truth
4. Print a monthly savings table vs Textract Tables

Optional Textract leg (sync `AnalyzeDocument` on the same one-page PDFs):

```powershell
copy .env.example .env
# fill AWS_PROFILE / region
python -m src.run_poc textract
python -m src.run_poc compare
```

Commands:

| Command | Purpose |
|---|---|
| `python -m src.run_poc generate` | Sample PDFs + JSON ground truth |
| `python -m src.run_poc docling` | Convert samples |
| `python -m src.run_poc textract` | Optional AWS comparison |
| `python -m src.run_poc compare` | Cell recall HTML/JSON |
| `python -m src.run_poc cost --pages 50000` | Savings at a volume you care about |
| `python -m src.run_poc all` | Everything |

Outputs land in `output/`.

Drop your own PDFs into `data/samples/` and re-run `docling` — that is the actual go/no-go, not the synthetic invoices.

## Repo layout

```
src/generate_samples.py   synthetic PDFs (text-layer vs image-only)
src/docling_runner.py     layout + OCR + TableFormer
src/textract_runner.py    optional AnalyzeDocument TABLES/FORMS/LAYOUT
src/compare.py            bag-of-cells recall vs ground truth
src/cost_model.py         Textract API $ vs Docling compute $
docs/                     how Docling works, cost assumptions
aws/                      phase 2 notes (ECS/g6.xlarge) — not built yet
```

## Local results (this laptop, 2 Sep 2026)

RTX 4080 + Docling 2.124, TableFormer ACCURATE, RapidOCR. Five one-page samples:

| Document | Cell recall vs ground truth | Seconds / page |
|---|---|---|
| invoice (digital) | 1.000 | 2.59 |
| invoice (scanned / OCR) | 1.000 | 2.05 |
| financials (digital) | 1.000 | 1.55 |
| financials (scanned / OCR) | 0.976 | 3.52 |
| account form (digital) | 1.000 | 9.15 cold-start |

The 0.976 miss is one OCR decimal (`3.2` → `32`) on the scanned P&L. Details: [docs/local-run.md](docs/local-run.md).

Textract was not called: the current AWS IAM user has no `textract:AnalyzeDocument` permission. Cost uses official list prices; quality uses our ground truth.

## Savings at the measured 2.587 s/page median

On `g6.xlarge` ($0.8048/hr) at 70% utilization vs Textract Tables ($15 / 1,000 pages):

| Pages / month | Textract Tables | Docling compute | Saved |
|---|---|---|---|
| 10,000 | $150 | $8 | $142 (94.5%) |
| 50,000 | $750 | $41 | $709 (94.5%) |
| 100,000 | $1,500 | $83 | $1,417 (94.5%) |
| 500,000 | $7,500 | $413 | $7,087 (94.5%) |
| 1,000,000 | $15,000 | $826 | $14,174 (94.5%) |

If those pages also go through Textract Forms, the Textract bill is ~4× higher ($65 / 1,000) — but Docling is **not** a Forms replacement. Quote the Tables column unless you have proven KV extraction on your forms.

## Decision rule for this POC

Ship Docling instead of Textract Tables when:

1. Cell recall on *your* documents is acceptable (run real PDFs, not only samples)
2. You can run a GPU/CPU worker (laptop now, `g6.xlarge` later)
3. You do not need Queries / Expense / ID / handwriting as the primary output

Keep Textract (or a hybrid) when Forms/Queries/IDs dominate, or when you want a managed API with no model ops.
