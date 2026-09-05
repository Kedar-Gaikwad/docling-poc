from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
OUTPUT_DIR = ROOT / "output"
DOCLING_OUT = OUTPUT_DIR / "docling"
TEXTRACT_OUT = OUTPUT_DIR / "textract"
VLM_OUT = OUTPUT_DIR / "vlm"
REPORTS_DIR = OUTPUT_DIR / "reports"
ROOTKEY_CSV = ROOT / "rootkey.csv"
DEFAULT_AWS_REGION = "us-east-1"

# Cheap VLM for this POC: Claude Haiku 4.5 via Bedrock (vision + native PDF).
# Geo inference profile is more reliable than the bare model ID.
HAIKU_BEDROCK_MODEL_IDS = [
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
    "global.anthropic.claude-haiku-4-5-20251001-v1:0",
]
HAIKU_MODEL_LABEL = "claude-haiku-4-5"

# Official Anthropic list prices, USD per million tokens.
VLM_USD_PER_MTOK = {
    "haiku-4.5": {"input": 1.00, "output": 5.00},
    "sonnet-4.5": {"input": 3.00, "output": 15.00},
}

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
