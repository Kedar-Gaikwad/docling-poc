"""Run Docling locally: layout + OCR + TableFormer, export markdown/JSON/CSV."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any

from src.config import DOCLING_OUT, SAMPLES_DIR


def _accelerator():
    try:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    except ImportError:  # older docling
        from docling.datamodel.pipeline_options import AcceleratorDevice, AcceleratorOptions

    device = AcceleratorDevice.CPU
    try:
        import torch

        if torch.cuda.is_available():
            device = AcceleratorDevice.CUDA
    except Exception:
        pass
    return AcceleratorOptions(device=device), str(device)


_CONVERTERS: dict[bool, tuple] = {}


def build_converter(*, force_full_page_ocr: bool):
    if force_full_page_ocr in _CONVERTERS:
        return _CONVERTERS[force_full_page_ocr]

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    accel, device_name = _accelerator()
    pipeline = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        images_scale=2.0,
        generate_page_images=True,
        table_structure_options=TableStructureOptions(
            do_cell_matching=True,
            mode=TableFormerMode.ACCURATE,
        ),
        ocr_options=RapidOcrOptions(
            lang=["english"],
            force_full_page_ocr=force_full_page_ocr,
            backend="onnxruntime",
        ),
        accelerator_options=accel,
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)}
    )
    _CONVERTERS[force_full_page_ocr] = (converter, device_name)
    return converter, device_name


def _page_count(document, result) -> int:
    for obj in (document, result, getattr(result, "input", None)):
        if obj is None:
            continue
        num_pages = getattr(obj, "num_pages", None)
        if callable(num_pages):
            try:
                value = num_pages()
                if isinstance(value, int) and value > 0:
                    return value
            except TypeError:
                pass
        elif isinstance(num_pages, int) and num_pages > 0:
            return num_pages
        pages = getattr(obj, "pages", None)
        if isinstance(pages, dict) and pages:
            return len(pages)
        if isinstance(pages, (list, tuple)) and pages:
            return len(pages)
    return 1


def _export_tables(document, dest_dir: Path) -> list[dict[str, Any]]:
    summaries = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    for idx, table in enumerate(document.tables, start=1):
        try:
            df = table.export_to_dataframe(doc=document)
        except TypeError:
            df = table.export_to_dataframe()
        csv_path = dest_dir / f"table_{idx:02d}.csv"
        html_path = dest_dir / f"table_{idx:02d}.html"
        df.to_csv(csv_path, index=False)
        try:
            html_path.write_text(table.export_to_html(doc=document), encoding="utf-8")
        except TypeError:
            html_path.write_text(df.to_html(index=False), encoding="utf-8")
        summaries.append(
            {
                "index": idx,
                "rows": int(df.shape[0]),
                "cols": int(df.shape[1]),
                "headers": [str(c) for c in df.columns.tolist()],
                "cells": df.fillna("").astype(str).values.tolist(),
                "csv": str(csv_path),
            }
        )
    return summaries


def convert_pdf(pdf_path: Path, *, force_full_page_ocr: bool | None = None) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    if force_full_page_ocr is None:
        force_full_page_ocr = "scanned" in pdf_path.stem
    out_dir = DOCLING_OUT / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    converter, device = build_converter(force_full_page_ocr=force_full_page_ocr)
    t0 = time.perf_counter()
    result = converter.convert(str(pdf_path))
    elapsed = time.perf_counter() - t0
    document = result.document

    markdown = document.export_to_markdown()
    (out_dir / "document.md").write_text(markdown, encoding="utf-8")
    try:
        json_text = document.export_to_dict()
        (out_dir / "document.json").write_text(json.dumps(json_text, indent=2, default=str), encoding="utf-8")
    except Exception:
        (out_dir / "document.json").write_text(
            json.dumps({"error": "export_to_dict failed", "trace": traceback.format_exc()}, indent=2),
            encoding="utf-8",
        )

    tables = _export_tables(document, out_dir / "tables")
    pages = _page_count(document, result)

    summary = {
        "engine": "docling",
        "file": str(pdf_path),
        "stem": pdf_path.stem,
        "device": device,
        "force_full_page_ocr": force_full_page_ocr,
        "seconds": round(elapsed, 3),
        "pages": pages,
        "seconds_per_page": round(elapsed / max(pages, 1), 3),
        "table_count": len(tables),
        "tables": tables,
        "markdown_preview": markdown[:4000],
        "output_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def convert_samples(sample_dir: Path | None = None) -> list[dict[str, Any]]:
    sample_dir = sample_dir or SAMPLES_DIR
    pdfs = sorted(sample_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs in {sample_dir}. Run: python -m src.run_poc generate")
    results = []
    for pdf in pdfs:
        print(f"\n=== Docling: {pdf.name} ===")
        try:
            summary = convert_pdf(pdf)
            print(
                f"  {summary['pages']} page(s) in {summary['seconds']}s "
                f"({summary['seconds_per_page']}s/page) on {summary['device']}  "
                f"tables={summary['table_count']}"
            )
            results.append(summary)
        except Exception as exc:
            err = {
                "engine": "docling",
                "file": str(pdf),
                "stem": pdf.stem,
                "error": str(exc),
                "trace": traceback.format_exc(),
            }
            print(f"  FAILED: {exc}")
            print(err["trace"])
            results.append(err)
    DOCLING_OUT.mkdir(parents=True, exist_ok=True)
    (DOCLING_OUT / "run_summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results
