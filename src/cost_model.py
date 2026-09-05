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
    VLM_OUT,
    VLM_USD_PER_MTOK,
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


def measured_vlm_usage() -> dict[str, float]:
    summary_path = VLM_OUT / "run_summary.json"
    if not summary_path.exists():
        return {}
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    inputs, outputs, haiku_usd, seconds = [], [], [], []
    for row in rows:
        if row.get("error") or row.get("skipped"):
            continue
        if row.get("input_tokens") is not None:
            inputs.append(int(row["input_tokens"]))
        if row.get("output_tokens") is not None:
            outputs.append(int(row["output_tokens"]))
        if row.get("usd_haiku_4_5") is not None:
            haiku_usd.append(float(row["usd_haiku_4_5"]))
        if row.get("seconds"):
            seconds.append(float(row["seconds"]))
    if not inputs:
        return {}

    def _mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 3)

    mean_in = _mean(inputs)
    mean_out = _mean(outputs)
    haiku_rates = VLM_USD_PER_MTOK["haiku-4.5"]
    sonnet_rates = VLM_USD_PER_MTOK["sonnet-4.5"]
    return {
        "pages": len(inputs),
        "mean_input_tokens": mean_in,
        "mean_output_tokens": mean_out,
        "mean_seconds": _mean(seconds) if seconds else 0.0,
        "mean_usd_haiku_4_5": round(sum(haiku_usd) / len(haiku_usd), 6) if haiku_usd else 0.0,
        "usd_per_page_haiku": round(
            (mean_in * haiku_rates["input"] + mean_out * haiku_rates["output"]) / 1_000_000, 6
        ),
        "usd_per_page_sonnet": round(
            (mean_in * sonnet_rates["input"] + mean_out * sonnet_rates["output"]) / 1_000_000, 6
        ),
    }


def estimate(
    pages_per_month: int | None = None,
    seconds_per_page: float | None = None,
    instance: str = "g6.xlarge",
    utilization: float = 0.7,
) -> dict[str, Any]:
    measured = measured_seconds_per_page()
    vlm = measured_vlm_usage()
    spp = seconds_per_page or measured.get("all") or 2.0
    volumes = [pages_per_month] if pages_per_month else DEFAULT_SCENARIOS
    haiku_pp = vlm.get("usd_per_page_haiku") or 0.0
    sonnet_pp = vlm.get("usd_per_page_sonnet") or 0.0

    scenarios = []
    for pages in volumes:
        tex = {
            name: round(textract_cost(pages, name), 2)
            for name in ("detect_text", "tables", "forms", "tables_forms", "tables_forms_queries")
        }
        compute = docling_compute_cost(pages, spp, instance, utilization)
        local = docling_compute_cost(pages, spp, "local_gpu", utilization)
        haiku_usd = round(pages * haiku_pp, 2)
        sonnet_usd = round(pages * sonnet_pp, 2)
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
                "vlm": {
                    "haiku_4_5_usd": haiku_usd,
                    "sonnet_4_5_usd": sonnet_usd,
                    "haiku_usd_per_page": haiku_pp,
                    "sonnet_usd_per_page": sonnet_pp,
                },
                "savings_vs_textract_tables": {
                    "usd": round(tex["tables"] - compute["usd"], 2),
                    "pct": round(100 * (1 - compute["usd"] / tex["tables"]), 1) if tex["tables"] else 0,
                },
                "haiku_vs_textract_tables": {
                    "usd": round(tex["tables"] - haiku_usd, 2),
                    "pct": round(100 * (1 - haiku_usd / tex["tables"]), 1) if tex["tables"] and haiku_pp else 0,
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
            "measured_vlm": vlm,
            "seconds_per_page_used": spp,
            "instance": instance,
            "utilization": utilization,
            "vlm_rates_usd_per_mtok": VLM_USD_PER_MTOK,
            "notes": [
                "Textract bills per page per feature. Tables is $0.015/page in the first 1M pages.",
                "Layout is free when requested together with Tables.",
                "Docling cost is compute only. Add EBS, idle capacity, and engineering time for a full TCO.",
                "Haiku 4.5 is the cheap VLM path (vision/PDF). Sonnet 4.5 uses the same measured tokens at $3/$15 per MTok.",
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
    vlm = payload["assumptions"].get("measured_vlm") or {}
    print(f"\nCost model  |  financial PDFs  |  Docling {spp}s/page on {inst} vs Textract vs Haiku 4.5")
    if vlm:
        print(
            f"VLM tokens/page: {vlm.get('mean_input_tokens')} in / {vlm.get('mean_output_tokens')} out  "
            f"| Haiku ${vlm.get('usd_per_page_haiku')}/page  "
            f"| Sonnet 4.5 same tokens ${vlm.get('usd_per_page_sonnet')}/page"
        )
    print(
        f"{'pages/mo':>12}  {'Textract tables':>16}  {'Docling compute':>16}  "
        f"{'Haiku 4.5':>12}  {'Sonnet 4.5':>12}  {'Docling save':>12}"
    )
    for row in payload["scenarios"]:
        print(
            f"{row['pages_per_month']:>12,}  "
            f"${row['textract_usd']['tables']:>14,.2f}  "
            f"${row['docling']['usd']:>14,.2f}  "
            f"${row['vlm']['haiku_4_5_usd']:>10,.2f}  "
            f"${row['vlm']['sonnet_4_5_usd']:>10,.2f}  "
            f"${row['savings_vs_textract_tables']['usd']:>10,.2f}"
        )
    print(f"\nWrote {REPORTS_DIR / 'cost.json'}")
