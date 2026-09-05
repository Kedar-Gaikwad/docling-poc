"""Optional AWS Textract comparison. Skips cleanly when credentials are missing."""

from __future__ import annotations

import json
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.config import TEXTRACT_OUT
from src.credentials import list_sample_pdfs, load_aws_credentials
from src.pdf_utils import page_count, split_pdf


def _client():
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError as exc:
        raise RuntimeError("boto3 is not installed") from exc

    info = load_aws_credentials()
    print(f"Textract credentials: {info['source']} (…{info['access_key_id_suffix']}) region={info['region']}")
    try:
        client = boto3.client("textract", region_name=info["region"])
        return client, (BotoCoreError, ClientError, NoCredentialsError)
    except Exception as exc:
        raise RuntimeError(f"Could not create Textract client: {exc}") from exc


def _blocks_to_tables(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {b["Id"]: b for b in blocks if "Id" in b}
    tables = []
    index = 0
    for block in blocks:
        if block.get("BlockType") != "TABLE":
            continue
        index += 1
        cells: dict[tuple[int, int], str] = {}
        max_row = 0
        max_col = 0
        for rel in block.get("Relationships", []):
            if rel.get("Type") != "CHILD":
                continue
            for cid in rel.get("Ids", []):
                cell = by_id.get(cid, {})
                if cell.get("BlockType") != "CELL":
                    continue
                row = int(cell.get("RowIndex", 1))
                col = int(cell.get("ColumnIndex", 1))
                max_row = max(max_row, row)
                max_col = max(max_col, col)
                texts = []
                for crel in cell.get("Relationships", []):
                    if crel.get("Type") != "CHILD":
                        continue
                    for wid in crel.get("Ids", []):
                        word = by_id.get(wid, {})
                        if word.get("BlockType") in {"WORD", "SELECTION_ELEMENT"}:
                            texts.append(word.get("Text") or word.get("SelectionStatus") or "")
                cells[(row, col)] = " ".join(texts).strip()
        grid = []
        for r in range(1, max_row + 1):
            grid.append([cells.get((r, c), "") for c in range(1, max_col + 1)])
        headers = grid[0] if grid else []
        rows = grid[1:] if len(grid) > 1 else []
        tables.append(
            {
                "index": index,
                "rows": len(rows),
                "cols": max_col,
                "headers": headers,
                "cells": rows,
            }
        )
    return tables


def _kv_from_blocks(blocks: list[dict[str, Any]]) -> dict[str, str]:
    by_id = {b["Id"]: b for b in blocks if "Id" in b}

    def text_of(block: dict[str, Any]) -> str:
        parts = []
        for rel in block.get("Relationships", []):
            if rel.get("Type") != "CHILD":
                continue
            for cid in rel.get("Ids", []):
                child = by_id.get(cid, {})
                if child.get("BlockType") == "WORD":
                    parts.append(child.get("Text", ""))
                elif child.get("BlockType") == "SELECTION_ELEMENT":
                    parts.append(child.get("SelectionStatus", ""))
        return " ".join(parts).strip()

    kvs: dict[str, str] = {}
    for block in blocks:
        if block.get("BlockType") != "KEY_VALUE_SET" or "KEY" not in block.get("EntityTypes", []):
            continue
        key = text_of(block)
        value = ""
        for rel in block.get("Relationships", []):
            if rel.get("Type") != "VALUE":
                continue
            for vid in rel.get("Ids", []):
                value = text_of(by_id.get(vid, {}))
        if key:
            kvs[key] = value
    return kvs


def _analyze_bytes(client, payload: bytes, feature_types: list[str]) -> dict[str, Any]:
    t0 = time.perf_counter()
    response = client.analyze_document(Document={"Bytes": payload}, FeatureTypes=feature_types)
    elapsed = time.perf_counter() - t0
    return {"response": response, "seconds": elapsed}


def analyze_pdf(pdf_path: Path, feature_types: list[str] | None = None) -> dict[str, Any]:
    """Sync AnalyzeDocument. Multi-page PDFs are split (AWS sync limit is 1 page)."""
    pdf_path = Path(pdf_path)
    feature_types = feature_types or ["TABLES", "LAYOUT"]
    client, _err_types = _client()
    pages = page_count(pdf_path)
    out_dir = TEXTRACT_OUT / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    page_runs: list[dict[str, Any]] = []
    all_tables: list[dict[str, Any]] = []
    all_kvs: dict[str, str] = {}
    block_counts: dict[str, int] = defaultdict(int)
    raw_pages: list[Any] = []
    wall0 = time.perf_counter()

    if pages <= 1:
        result = _analyze_bytes(client, pdf_path.read_bytes(), feature_types)
        raw_pages.append(result["response"])
        page_runs.append({"page": 1, "seconds": round(result["seconds"], 3)})
        blocks = result["response"].get("Blocks", [])
        for table in _blocks_to_tables(blocks):
            table["index"] = len(all_tables) + 1
            all_tables.append(table)
        all_kvs.update(_kv_from_blocks(blocks))
        for name, count in _count_block_types(blocks).items():
            block_counts[name] += count
    else:
        chunk_dir = out_dir / "_pages"
        chunks = split_pdf(pdf_path, chunk_dir, pages_per_chunk=1)
        for i, chunk in enumerate(chunks, start=1):
            result = _analyze_bytes(client, chunk.read_bytes(), feature_types)
            raw_pages.append({"page": i, "seconds": result["seconds"], "blocks": result["response"].get("Blocks", [])})
            page_runs.append({"page": i, "seconds": round(result["seconds"], 3), "file": chunk.name})
            blocks = result["response"].get("Blocks", [])
            for table in _blocks_to_tables(blocks):
                table["index"] = len(all_tables) + 1
                table["source_page"] = i
                all_tables.append(table)
            all_kvs.update(_kv_from_blocks(blocks))
            for name, count in _count_block_types(blocks).items():
                block_counts[name] += count
            print(f"    page {i}/{pages}  {result['seconds']:.2f}s  tables+={len(_blocks_to_tables(blocks))}")

    elapsed = time.perf_counter() - wall0
    (out_dir / "raw.json").write_text(json.dumps(raw_pages, default=str, indent=2), encoding="utf-8")
    for table in all_tables:
        csv_path = out_dir / f"table_{table['index']:02d}.csv"
        lines = [",".join(table["headers"])]
        for row in table["cells"]:
            lines.append(",".join(row))
        csv_path.write_text("\n".join(lines), encoding="utf-8")
        table["csv"] = str(csv_path)

    billed_pages = pages
    # TABLES is $0.015/page; LAYOUT is free when combined with TABLES.
    usd_tables = round(billed_pages * 0.015, 4)
    usd_tables_forms = round(billed_pages * 0.065, 4)
    usd_layout_alone = round(billed_pages * 0.004, 4)

    summary = {
        "engine": "textract",
        "file": str(pdf_path),
        "stem": pdf_path.stem,
        "feature_types": feature_types,
        "seconds": round(elapsed, 3),
        "pages": pages,
        "seconds_per_page": round(elapsed / max(pages, 1), 3),
        "page_runs": page_runs,
        "table_count": len(all_tables),
        "tables": all_tables,
        "key_values": all_kvs,
        "block_counts": dict(block_counts),
        "usd_tables": usd_tables,
        "usd_tables_forms": usd_tables_forms,
        "usd_layout_alone": usd_layout_alone,
        "output_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _count_block_types(blocks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for block in blocks:
        counts[block.get("BlockType", "UNKNOWN")] += 1
    return dict(counts)


def convert_samples(sample_dir: Path | None = None, only: str | None = "financials") -> list[dict[str, Any]]:
    if sample_dir is not None:
        pdfs = sorted(sample_dir.glob("*.pdf"))
        if only:
            pdfs = [p for p in pdfs if only.lower() in p.stem.lower()]
    else:
        pdfs = list_sample_pdfs(only=only)
    if not pdfs:
        raise FileNotFoundError(f"No matching PDFs (only={only!r})")
    results = []
    try:
        _client()
    except Exception as exc:
        print(f"Textract skipped: {exc}")
        return [{"engine": "textract", "skipped": True, "reason": str(exc)}]

    for pdf in pdfs:
        print(f"\n=== Textract: {pdf.name} ===")
        try:
            summary = analyze_pdf(pdf)
            print(f"  {summary['pages']} page(s) in {summary['seconds']}s  tables={summary['table_count']}")
            results.append(summary)
        except Exception as exc:
            err = {
                "engine": "textract",
                "file": str(pdf),
                "stem": pdf.stem,
                "error": str(exc),
                "trace": traceback.format_exc(),
            }
            print(f"  FAILED: {exc}")
            results.append(err)
    TEXTRACT_OUT.mkdir(parents=True, exist_ok=True)
    (TEXTRACT_OUT / "run_summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results
