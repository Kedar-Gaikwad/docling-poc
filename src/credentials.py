"""Load AWS credentials without printing secrets.

Order: existing env → .env → docling-poc/rootkey.csv (Access key ID, Secret access key).
"""

from __future__ import annotations

import csv
import os

from src.config import DEFAULT_AWS_REGION, ROOT, ROOTKEY_CSV


def load_aws_credentials() -> dict[str, str]:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    source = "environment"

    if not (key_id and secret) and ROOTKEY_CSV.exists():
        with ROOTKEY_CSV.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            row = next(reader, None) or {}
        mapping = {((k or "").strip().lower()): (v or "").strip() for k, v in row.items()}
        key_id = (
            mapping.get("access key id")
            or mapping.get("aws_access_key_id")
            or mapping.get("access_key_id")
            or ""
        )
        secret = (
            mapping.get("secret access key")
            or mapping.get("aws_secret_access_key")
            or mapping.get("secret_access_key")
            or ""
        )
        source = str(ROOTKEY_CSV.name)

    if not (key_id and secret):
        raise RuntimeError(
            "No AWS credentials found. Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY "
            f"or add {ROOTKEY_CSV.name}."
        )

    region = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or DEFAULT_AWS_REGION
    )
    os.environ["AWS_ACCESS_KEY_ID"] = key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret
    os.environ["AWS_DEFAULT_REGION"] = region
    os.environ.setdefault("AWS_REGION", region)
    # Avoid a profile in ~/.aws overriding the CSV keys.
    os.environ.pop("AWS_PROFILE", None)
    return {"source": source, "region": region, "access_key_id_suffix": key_id[-4:]}


def list_sample_pdfs(only: str | None = "financials"):
    from src.config import SAMPLES_DIR

    pdfs = sorted(SAMPLES_DIR.glob("*.pdf"))
    if only:
        needle = only.lower()
        pdfs = [p for p in pdfs if needle in p.stem.lower()]
    return pdfs
