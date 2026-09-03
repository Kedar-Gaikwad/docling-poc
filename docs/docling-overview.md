# How Docling actually works (for this POC)

Docling is an open-source document conversion stack from IBM Research (now LF AI & Data), MIT licensed. Install: `pip install docling`. Docs: https://docling-project.github.io/docling/

## It is not “just OCR”

A raw OCR engine (Tesseract, EasyOCR, RapidOCR, Textract DetectDocumentText) returns **characters + boxes**. Docling wraps that and adds:

1. **PDF backend** — `docling-parse` / pypdfium2 reads the file, native text, and page images
2. **Layout model** — finds text blocks, tables, figures, headers, footers
3. **Reading order** — multi-column reconstruction
4. **OCR plugin** — only where the page is a bitmap (or when `force_full_page_ocr=True`)
5. **TableFormer** — neural table structure: rows, columns, spans, cell matching
6. **`DoclingDocument`** — one Pydantic tree you can export to Markdown, JSON, HTML, pandas

That last step is why it can replace **Textract TABLES**, not merely DetectDocumentText.

## Pipelines

| Pipeline | When |
|---|---|
| `StandardPdfPipeline` (this POC) | PDFs and images; layout + TableFormer + OCR |
| `VlmPipeline` (Granite Docling) | End-to-end vision-language; heavier; better on weird pages |
| `SimplePipeline` | DOCX/PPTX/XLSX/HTML — no TableFormer needed |

We stay on the standard PDF pipeline so the comparison with Textract is apples-to-apples: **detect layout, OCR if needed, rebuild tables**.

## OCR engines Docling can plug in

| Engine | Extra | Notes for this machine |
|---|---|---|
| RapidOCR | `docling[rapidocr]` | **Used here.** ONNX Runtime, no Tesseract install, Windows-friendly |
| EasyOCR | `easyocr` | Common default; heavier; good GPU path |
| Tesseract | system binary | Best language coverage; painful on Windows |
| Auto | default | Picks first available |
| Nemotron OCR | Linux + CUDA 13 | Not for this laptop |

OCR is **opt-in per bitmap**. Digital PDFs with a text layer skip most OCR and still get TableFormer. Scanned (image-only) PDFs in `data/samples/*_scanned.pdf` force full-page OCR — that is the expensive/slow path, and the one that corresponds to “we used Textract because the PDF is a scan.”

## TableFormer (the Textract TABLES analogue)

Configured in this POC as:

```python
TableStructureOptions(mode=TableFormerMode.ACCURATE, do_cell_matching=True)
```

- **ACCURATE** — production quality, slower
- **FAST** — prototype / high volume
- **do_cell_matching=True** — snap predicted grid to actual text cells (including spans)

Export:

```python
for table in result.document.tables:
    df = table.export_to_dataframe(doc=result.document)
    df.to_csv(...)
```

Published TableFormer TEDS numbers are in the 90%+ range on FinTabNet-style academic tables. That is **not** a guarantee on invoices, utility bills, or scanned photocopies. This repo scores **bag-of-cells recall vs ground truth** on generated docs, then you drop real PDFs in `data/samples/`.

## Hardware

From the Docling paper (g6.xlarge, 1× L4, 8 vCPU):

| Stage | L4 GPU | 8-vCPU x86 |
|---|---|---|
| Median page (mixed corpus) | 114 ms | 0.79 s |
| EasyOCR when it fires | ~1.6 s/page | ~13 s/page |
| TableFormer FAST per table | ~400 ms | ~1.74 s |

This laptop: RTX 4080 12 GB. Layout + TableFormer should land on CUDA. RapidOCR is ONNX CPU in phase 1 so Windows install stays boring. Re-measure on AWS before quoting savings.

## API used here

```python
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, TableFormerMode, TableStructureOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

opts = PdfPipelineOptions(
    do_ocr=True,
    do_table_structure=True,
    table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE, do_cell_matching=True),
    ocr_options=RapidOcrOptions(lang=["english"], force_full_page_ocr=is_scan),
)
converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
doc = converter.convert("file.pdf").document
```

CLI equivalent exists (`docling file.pdf`) but the Python API is what we time and export tables from.

## Mapping to Textract APIs

| Textract | Docling in this POC |
|---|---|
| DetectDocumentText | Native PDF text + RapidOCR |
| AnalyzeDocument TABLES | TableFormer ACCURATE |
| AnalyzeDocument LAYOUT | Layout model (always on) |
| AnalyzeDocument FORMS | Partial (KV only if they sit in a table / text) |
| Queries / Expense / ID / Lending | Out of scope |

Hybrid that often wins in production: Docling for bulk tables + layout; Textract only for ID/expense/query pages.
