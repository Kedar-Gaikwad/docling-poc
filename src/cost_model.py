"""Dollar model: Textract per-page API vs Docling software ($0) + compute."""

from __future__ import annotations

import json
from typing import Any

from src.config import (
    DEFAULT_SCENARIOS,
    DOCLING_OUT,
    EC2_USD_PER_HOUR,
    REPORTS_DIR,
    TEXTRACT_USD_PER_PAGE,
    VOLUME_TIER_PAGES,
)


def textract_cost(pages: int, feature: str) -> float:
    first_rate, rest_rate = TEXTRACT_USD_PER_PAGE[feature]
    first = min(pages, VOLUME_TIER_PAGES)
    rest = max(pages - VOLUME_TIER_PAGES, 0)
    return first * first_rate + rest * rest_rate


def docling_compute_cost(pages: int, seconds_per_page: float, instance: str, utilization: float = 0.7) -> dict[str, float]:
    """utilization < 1 accounts for queue idle, model load, retries."""
    hours = (pages * seconds_per_page) / 3600.0 / max(utilization, 0.05)
    rate = EC2_USD_PER_HOUR[instance]
    return {
        "hours": round(hours, 3),
        "usd": round(hours * rate, 2),
        "usd_per_page": round((hours * rate) / pages, 6) if pages else 0.0,
    }


def measured_seconds_per_page() -> dict[str, float]:
    summary_path = DOCLING_OUT / "run_summary.json"
    if not summary_path.exists():
        return {}
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    digital, scanned, all_rows = [], [], []
    for row in rows:
        spp = row.get("seconds_per_page")
        if not spp:
            continue
        all_rows.append(spp)
        stem = row.get("stem", "")
        if "scanned" in stem:
            scanned.append(spp)
        else:
            digital.append(spp)

    def _median(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return round(ordered[mid], 3)
        return round((ordered[mid - 1] + ordered[mid]) / 2, 3)

    out = {}
    if all_rows:
        out["all_mean"] = round(sum(all_rows) / len(all_rows), 3)
        out["all"] = _median(all_rows)
    if digital:
        out["digital"] = _median(digital)
    if scanned:
        out["scanned"] = _median(scanned)
    return out


def estimate(
    pages_per_month: int | None = None,
    seconds_per_page: float | None = None,
    instance: str = "g6.xlarge",
    utilization: float = 0.7,
) -> dict[str, Any]:
    measured = measured_seconds_per_page()
    spp = seconds_per_page or measured.get("all") or 2.0
    volumes = [pages_per_month] if pages_per_month else DEFAULT_SCENARIOS

    scenarios = []
    for pages in volumes:
        tex = {
            name: round(textract_cost(pages, name), 2)
            for name in ("detect_text", "tables", "forms", "tables_forms", "tables_forms_queries")
        }
        compute = docling_compute_cost(pages, spp, instance, utilization)
        local = docling_compute_cost(pages, spp, "local_gpu", utilization)
        scenarios.append(
            {
                "pages_per_month": pages,
                "textract_usd": tex,
                "docling": {
                    "instance": instance,
                    "seconds_per_page_used": spp,
                    "utilization": utilization,
                    **compute,
                    "local_gpu_usd": local["usd"],
                },
                "savings_vs_textract_tables": {
                    "usd": round(tex["tables"] - compute["usd"], 2),
                    "pct": round(100 * (1 - compute["usd"] / tex["tables"]), 1) if tex["tables"] else 0,
                },
                "savings_vs_textract_tables_forms": {
                    "usd": round(tex["tables_forms"] - compute["usd"], 2),
                    "pct": round(100 * (1 - compute["usd"] / tex["tables_forms"]), 1) if tex["tables_forms"] else 0,
                },
            }
        )

    payload = {
        "assumptions": {
            "textract_region": "us-east-1 / us-west-2 published pretrained rates",
            "textract_source": "https://aws.amazon.com/textract/pricing/",
            "docling_license": "MIT — $0 software",
            "compute": EC2_USD_PER_HOUR,
            "measured_seconds_per_page": measured,
            "seconds_per_page_used": spp,
            "instance": instance,
            "utilization": utilization,
            "notes": [
                "Textract bills per page per feature. Tables is $0.015/page in the first 1M pages.",
                "Layout is free when requested together with Tables.",
                "Docling cost is compute only. Add EBS, idle capacity, and engineering time for a full TCO.",
                "Docling is strongest as a Tables + layout + OCR substitute. Forms/Queries/Expense/ID are not 1:1.",
            ],
        },
        "scenarios": scenarios,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "cost.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _print(payload)
    return payload


def _print(payload: dict[str, Any]) -> None:
    spp = payload["assumptions"]["seconds_per_page_used"]
    inst = payload["assumptions"]["instance"]
    print(f"\nCost model  |  Docling {spp}s/page on {inst} (70% util) vs Textract pretrained rates")
    print(f"{'pages/mo':>12}  {'Textract tables':>16}  {'Textract T+F':>14}  {'Docling compute':>16}  {'save vs tables':>14}  {'save %':>8}")
    for row in payload["scenarios"]:
        print(
            f"{row['pages_per_month']:>12,}  "
            f"${row['textract_usd']['tables']:>14,.2f}  "
            f"${row['textract_usd']['tables_forms']:>12,.2f}  "
            f"${row['docling']['usd']:>14,.2f}  "
            f"${row['savings_vs_textract_tables']['usd']:>12,.2f}  "
            f"{row['savings_vs_textract_tables']['pct']:>7.1f}%"
        )
    print(f"\nWrote {REPORTS_DIR / 'cost.json'}")
