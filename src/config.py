from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
OUTPUT_DIR = ROOT / "output"
DOCLING_OUT = OUTPUT_DIR / "docling"
TEXTRACT_OUT = OUTPUT_DIR / "textract"
REPORTS_DIR = OUTPUT_DIR / "reports"

# Official Amazon Textract pretrained rates, US East/West, first 1M pages / month
# then the over-1M rate. Source: https://aws.amazon.com/textract/pricing/
# Amounts are USD per page.
TEXTRACT_USD_PER_PAGE = {
    "detect_text": (0.0015, 0.0006),
    "tables": (0.015, 0.010),
    "forms": (0.050, 0.040),
    "layout": (0.004, 0.003),
    "queries": (0.015, 0.015),
    "tables_forms": (0.065, 0.050),
    "tables_forms_queries": (0.070, 0.055),
    "expense": (0.010, 0.008),
}

# On-demand Linux, us-east-1. Docling itself is MIT-licensed ($0).
# The real cost is the box that runs it.
EC2_USD_PER_HOUR = {
    "g6.xlarge": 0.8048,  # 1x NVIDIA L4 — closest to the Docling paper hardware
    "g4dn.xlarge": 0.5260,  # 1x T4, cheaper GPU option
    "c6i.2xlarge": 0.3400,  # 8 vCPU, CPU-only fallback
    "local_gpu": 0.0,  # this laptop; software is free, electricity ignored
}

VOLUME_TIER_PAGES = 1_000_000

DEFAULT_SCENARIOS = [10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]
