"""Compare extracted tables against ground truth (and Textract when present)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import DOCLING_OUT, REPORTS_DIR, SAMPLES_DIR, TEXTRACT_OUT, VLM_OUT


def _norm(value: Any) -> str:
    text = str(value or "")
    text = text.replace("$", "").replace(",", "")
    text = re.sub(r"\s+", " ", text).strip().lower()
    if re.fullmatch(r"-?\d+\.0+", text):
        text = text.split(".")[0]
    return text


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _table_cells(table: dict[str, Any]) -> list[list[str]]:
    headers = table.get("headers") or []
    rows = table.get("cells") or []
    grid = []
    if headers:
        grid.append([str(h) for h in headers])
    for row in rows:
        grid.append([str(c) for c in row])
    return grid


def _score_grids(expected: list[list[str]], predicted: list[list[str]]) -> dict[str, Any]:
    exp_flat = [_norm(c) for row in expected for c in row]
    pred_flat = [_norm(c) for row in predicted for c in row]
    exp_set = [c for c in exp_flat if c]
    pred_set = [c for c in pred_flat if c]
    matched = 0
    remaining = list(pred_set)
    for cell in exp_set:
        if cell in remaining:
            remaining.remove(cell)
            matched += 1
    denom = max(len(exp_set), 1)
    return {
        "expected_cells": len(exp_set),
        "predicted_cells": len(pred_set),
        "matched_cells": matched,
        "cell_recall": round(matched / denom, 3),
        "expected_rows": len(expected),
        "predicted_rows": len(predicted),
        "expected_cols": max((len(r) for r in expected), default=0),
        "predicted_cols": max((len(r) for r in predicted), default=0),
    }


def _best_table_score(expected_tables: list[dict[str, Any]], predicted_tables: list[dict[str, Any]]) -> dict[str, Any]:
    if not expected_tables:
        return {"cell_recall": 1.0 if not predicted_tables else 0.0, "note": "no expected tables"}
    if not predicted_tables:
        return {"cell_recall": 0.0, "matched_cells": 0, "expected_cells": sum(len(t["rows"]) * len(t["headers"]) for t in expected_tables)}
    scores = []
    for expected in expected_tables:
        exp_grid = [expected["headers"], *expected["rows"]]
        best = None
        for predicted in predicted_tables:
            score = _score_grids(exp_grid, _table_cells(predicted))
            if best is None or score["cell_recall"] > best["cell_recall"]:
                best = score
                best["expected_name"] = expected.get("name")
                best["predicted_index"] = predicted.get("index")
        scores.append(best)
    avg = sum(s["cell_recall"] for s in scores) / len(scores)
    return {"tables": scores, "avg_cell_recall": round(avg, 3)}


def compare_all(only: str | None = "financials") -> dict[str, Any]:
    reports = []
    for gt_path in sorted(SAMPLES_DIR.glob("*.json")):
        stem = gt_path.stem
        if only and only.lower() not in stem.lower():
            continue
        ground = _load_json(gt_path) or {}
        docling = _load_json(DOCLING_OUT / stem / "summary.json")
        textract = _load_json(TEXTRACT_OUT / stem / "summary.json")
        vlm = _load_json(VLM_OUT / stem / "summary.json")
        row: dict[str, Any] = {
            "stem": stem,
            "kind": ground.get("kind"),
            "ground_table_count": len(ground.get("tables") or []),
        }
        for engine, payload, extra in (
            ("docling", docling, ("seconds", "seconds_per_page", "device", "table_count")),
            ("textract", textract, ("seconds", "table_count")),
            ("vlm", vlm, ("seconds", "table_count", "model", "input_tokens", "output_tokens", "usd_haiku_4_5", "usd_sonnet_4_5_same_tokens", "mode")),
        ):
            if payload and "error" not in payload:
                block = {k: payload.get(k) for k in extra}
                block["quality"] = _best_table_score(ground.get("tables") or [], payload.get("tables") or [])
                if engine == "textract":
                    block["key_values"] = payload.get("key_values")
                row[engine] = block
            else:
                row[engine] = {"missing": True, "error": (payload or {}).get("error")}
        reports.append(row)

    payload = {"only": only, "documents": reports}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "quality.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (REPORTS_DIR / "quality.html").write_text(_html(reports), encoding="utf-8")
    print((REPORTS_DIR / "quality.html").as_posix())
    return payload


def _html(reports: list[dict[str, Any]]) -> str:
    rows = []
    for item in reports:
        d = item.get("docling") or {}
        t = item.get("textract") or {}
        v = item.get("vlm") or {}
        d_q = (d.get("quality") or {}).get("avg_cell_recall", "—")
        t_q = (t.get("quality") or {}).get("avg_cell_recall", "—")
        v_q = (v.get("quality") or {}).get("avg_cell_recall", "—")
        rows.append(
            "<tr>"
            f"<td>{item['stem']}</td><td>{item.get('kind')}</td>"
            f"<td>{d.get('seconds', '—')}</td><td>{d_q}</td><td>{d.get('table_count', '—')}</td>"
            f"<td>{t.get('seconds', '—')}</td><td>{t_q}</td><td>{t.get('table_count', 'skipped' if t.get('missing') else '—')}</td>"
            f"<td>{v.get('seconds', '—')}</td><td>{v_q}</td><td>{v.get('table_count', 'skipped' if v.get('missing') else '—')}</td>"
            f"<td>{v.get('usd_haiku_4_5', '—')}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Financial PDFs: Docling vs Textract vs Haiku 4.5</title>
<style>
body {{ font-family: Georgia, serif; margin: 40px; background: #f6f3ee; color: #1f2a32; }}
h1 {{ font-weight: 600; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; }}
th, td {{ border: 1px solid #cfc6b8; padding: 8px 10px; text-align: left; }}
th {{ background: #1f3b4d; color: #fff; }}
caption {{ text-align: left; margin-bottom: 12px; color: #4d5a63; }}
</style></head><body>
<h1>Financial PDFs — table cell recall</h1>
<p>Recall is bag-of-cells against generated ground-truth tables (P&amp;L + balance sheet). VLM is Claude Haiku 4.5 via Bedrock.</p>
<table>
<caption>Local POC quality snapshot — financials only</caption>
<thead><tr>
<th>Document</th><th>Kind</th>
<th>Docling sec</th><th>Docling recall</th><th>Docling tables</th>
<th>Textract sec</th><th>Textract recall</th><th>Textract tables</th>
<th>Haiku sec</th><th>Haiku recall</th><th>Haiku tables</th>
<th>Haiku USD</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body></html>
"""
