"""Claude Haiku 4.5 VLM: extract financial tables from PDF pages.

Uses Amazon Bedrock Converse with a native PDF document block. Falls back to
page images if the account cannot send PDFs. Token usage is recorded so the
cost model can compare Haiku 4.5 (cheap VLM) vs Sonnet 4.5 at the same tokens.
"""

from __future__ import annotations

import json
import re
import time
import traceback
from io import BytesIO
from pathlib import Path
from typing import Any

from src.config import (
    HAIKU_BEDROCK_MODEL_IDS,
    HAIKU_MODEL_LABEL,
    VLM_OUT,
    VLM_USD_PER_MTOK,
)
from src.credentials import list_sample_pdfs, load_aws_credentials
from src.pdf_utils import page_count

EXTRACT_PROMPT = """You are extracting structure from a legal / financial PDF (subscription agreement, statements, or similar).

Return ONLY valid JSON with this shape:
{
  "title": "document title",
  "parties": ["..."],
  "tables":[{"name":"short_snake_case","headers":["..."],"cells":[["row1col1","row1col2"]]}],
  "key_terms":[{"term":"...","value":"..."}]
}

Rules:
- Extract every visible table. Preserve numbers exactly as printed.
- key_terms: 8-15 important fields (parties, effective date, governing law, fees, term, if present).
- Do not invent rows. Empty cell = "".
- No markdown fences, no commentary.
"""


def _vlm_cost(input_tokens: int, output_tokens: int, model: str = "haiku-4.5") -> float:
    rates = VLM_USD_PER_MTOK[model]
    return round((input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000, 6)


def _parse_tables(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        raw = match.group(0)
    payload = json.loads(raw)
    tables = []
    for idx, table in enumerate(payload.get("tables") or [], start=1):
        headers = [str(h) for h in (table.get("headers") or [])]
        cells = [[str(c) for c in row] for row in (table.get("cells") or [])]
        tables.append(
            {
                "index": idx,
                "name": table.get("name") or f"table_{idx}",
                "rows": len(cells),
                "cols": max([len(headers), *(len(r) for r in cells)], default=0),
                "headers": headers,
                "cells": cells,
            }
        )
    return tables


def _page_pngs(pdf_path: Path, scale: float = 2.0) -> list[bytes]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    images = []
    try:
        for index in range(len(doc)):
            page = doc[index]
            bitmap = page.render(scale=scale)
            pil = bitmap.to_pil().convert("RGB")
            buf = BytesIO()
            pil.save(buf, format="PNG")
            images.append(buf.getvalue())
            bitmap.close()
            page.close()
    finally:
        doc.close()
    return images


def _client(region: str):
    import boto3

    return boto3.client("bedrock-runtime", region_name=region)


def _converse(client, model_id: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": 8192, "temperature": 0},
    )


def _text_from_converse(response: dict[str, Any]) -> str:
    parts = []
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "text" in block:
            parts.append(block["text"])
    return "\n".join(parts).strip()


def analyze_pdf(pdf_path: Path, model_id: str | None = None) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    info = load_aws_credentials()
    client = _client(info["region"])
    payload = pdf_path.read_bytes()
    pages = page_count(pdf_path)
    errors: list[str] = []
    response = None
    used_model = model_id
    mode = "pdf"

    model_ids = [model_id] if model_id else list(HAIKU_BEDROCK_MODEL_IDS)
    t0 = time.perf_counter()
    for mid in model_ids:
        try:
            response = _converse(
                client,
                mid,
                [
                    {
                        "document": {
                            "format": "pdf",
                            "name": pdf_path.stem[:200],
                            "source": {"bytes": payload},
                        }
                    },
                    {"text": EXTRACT_PROMPT},
                ],
            )
            used_model = mid
            mode = "pdf"
            break
        except Exception as exc:
            errors.append(f"pdf/{mid}: {exc}")

    if response is None:
        try:
            images = _page_pngs(pdf_path)
        except Exception as exc:
            raise RuntimeError(f"VLM PDF and image fallback both failed. Last PDF error: {errors[-1] if errors else exc}") from exc
        content: list[dict[str, Any]] = [{"image": {"format": "png", "source": {"bytes": img}}} for img in images]
        content.append({"text": EXTRACT_PROMPT})
        mode = "images"
        for mid in model_ids:
            try:
                response = _converse(client, mid, content)
                used_model = mid
                break
            except Exception as exc:
                errors.append(f"image/{mid}: {exc}")

    elapsed = time.perf_counter() - t0
    if response is None:
        raise RuntimeError("Bedrock Haiku 4.5 failed. " + " | ".join(errors[-4:]))

    text = _text_from_converse(response)
    usage = response.get("usage") or {}
    input_tokens = int(usage.get("inputTokens") or 0)
    output_tokens = int(usage.get("outputTokens") or 0)
    try:
        tables = _parse_tables(text)
        parse_error = None
    except Exception as exc:
        tables = []
        parse_error = str(exc)

    out_dir = VLM_OUT / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw.json").write_text(json.dumps(response, default=str, indent=2), encoding="utf-8")
    (out_dir / "extract.json").write_text(text, encoding="utf-8")
    for table in tables:
        csv_path = out_dir / f"table_{table['index']:02d}.csv"
        lines = [",".join(table["headers"])]
        for row in table["cells"]:
            lines.append(",".join(row))
        csv_path.write_text("\n".join(lines), encoding="utf-8")
        table["csv"] = str(csv_path)

    summary = {
        "engine": "vlm",
        "model": HAIKU_MODEL_LABEL,
        "model_id": used_model,
        "mode": mode,
        "file": str(pdf_path),
        "stem": pdf_path.stem,
        "seconds": round(elapsed, 3),
        "pages": pages,
        "seconds_per_page": round(elapsed / max(pages, 1), 3),
        "table_count": len(tables),
        "tables": tables,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "usd_haiku_4_5": _vlm_cost(input_tokens, output_tokens, "haiku-4.5"),
        "usd_sonnet_4_5_same_tokens": _vlm_cost(input_tokens, output_tokens, "sonnet-4.5"),
        "parse_error": parse_error,
        "output_dir": str(out_dir),
        "errors_tried": errors,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


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
        info = load_aws_credentials()
        print(f"VLM credentials: {info['source']} (…{info['access_key_id_suffix']}) region={info['region']}")
        _client(info["region"])
    except Exception as exc:
        print(f"VLM skipped: {exc}")
        return [{"engine": "vlm", "skipped": True, "reason": str(exc)}]

    for pdf in pdfs:
        print(f"\n=== VLM Haiku 4.5: {pdf.name} ===")
        try:
            summary = analyze_pdf(pdf)
            print(
                f"  {summary['pages']} page(s) in {summary['seconds']}s  tables={summary['table_count']}  "
                f"tokens={summary['input_tokens']}/{summary['output_tokens']}  "
                f"${summary['usd_haiku_4_5']}  mode={summary['mode']}"
            )
            results.append(summary)
        except Exception as exc:
            err = {
                "engine": "vlm",
                "file": str(pdf),
                "stem": pdf.stem,
                "error": str(exc),
                "trace": traceback.format_exc(),
            }
            print(f"  FAILED: {exc}")
            results.append(err)
    VLM_OUT.mkdir(parents=True, exist_ok=True)
    (VLM_OUT / "run_summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results
