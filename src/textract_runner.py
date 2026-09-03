"""Optional AWS Textract comparison. Skips cleanly when credentials are missing."""

from __future__ import annotations

import json
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.config import SAMPLES_DIR, TEXTRACT_OUT


def _client():
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError as exc:
        raise RuntimeError("boto3 is not installed") from exc

    from dotenv import load_dotenv

    load_dotenv()
    try:
        client = boto3.client("textract")
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


def analyze_pdf(pdf_path: Path, feature_types: list[str] | None = None) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    feature_types = feature_types or ["TABLES", "FORMS", "LAYOUT"]
    client, err_types = _client()
    payload = pdf_path.read_bytes()
    t0 = time.perf_counter()
    response = client.analyze_document(Document={"Bytes": payload}, FeatureTypes=feature_types)
    elapsed = time.perf_counter() - t0
    blocks = response.get("Blocks", [])
    tables = _blocks_to_tables(blocks)
    out_dir = TEXTRACT_OUT / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw.json").write_text(json.dumps(response, default=str, indent=2), encoding="utf-8")
    for table in tables:
        csv_path = out_dir / f"table_{table['index']:02d}.csv"
        lines = [",".join(table["headers"])]
        for row in table["cells"]:
            lines.append(",".join(row))
        csv_path.write_text("\n".join(lines), encoding="utf-8")
        table["csv"] = str(csv_path)
    summary = {
        "engine": "textract",
        "file": str(pdf_path),
        "stem": pdf_path.stem,
        "feature_types": feature_types,
        "seconds": round(elapsed, 3),
        "pages": 1,
        "seconds_per_page": round(elapsed, 3),
        "table_count": len(tables),
        "tables": tables,
        "key_values": _kv_from_blocks(blocks),
        "block_counts": _count_block_types(blocks),
        "output_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _count_block_types(blocks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for block in blocks:
        counts[block.get("BlockType", "UNKNOWN")] += 1
    return dict(counts)


def convert_samples(sample_dir: Path | None = None) -> list[dict[str, Any]]:
    sample_dir = sample_dir or SAMPLES_DIR
    pdfs = sorted(sample_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs in {sample_dir}")
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
            print(f"  {summary['seconds']}s  tables={summary['table_count']}")
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
