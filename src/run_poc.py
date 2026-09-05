"""CLI: generate samples, run Docling, Textract, Haiku 4.5 VLM, compare, estimate cost."""

from __future__ import annotations

import argparse
import json
import sys

from src.config import OUTPUT_DIR, SAMPLES_DIR


def _only_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--only",
        default="financials",
        help="Substring filter on sample stem. Default: financials. Pass empty string for all samples.",
    )


def _normalize_only(value: str | None) -> str | None:
    if value is None:
        return "financials"
    stripped = value.strip()
    return stripped or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Docling vs AWS Textract vs Claude Haiku 4.5 (financial PDFs)."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("generate", help="Write sample PDFs + ground-truth JSON")
    docling_p = sub.add_parser("docling", help="Run Docling on data/samples")
    _only_flag(docling_p)
    textract_p = sub.add_parser("textract", help="Run Textract if AWS credentials exist")
    _only_flag(textract_p)
    vlm_p = sub.add_parser("vlm", help="Run Claude Haiku 4.5 via Bedrock")
    _only_flag(vlm_p)
    compare_p = sub.add_parser("compare", help="Score extractions against ground truth")
    _only_flag(compare_p)

    cost = sub.add_parser("cost", help="Print Textract vs Docling vs VLM cost")
    cost.add_argument("--pages", type=int, default=None, help="Single monthly page volume")
    cost.add_argument("--sec-per-page", type=float, default=None, help="Override measured Docling seconds/page")
    cost.add_argument("--instance", default="g6.xlarge", help="EC2 instance for Docling compute cost")

    all_p = sub.add_parser("all", help="generate + docling + textract + vlm + compare + cost")
    all_p.add_argument("--skip-textract", action="store_true")
    all_p.add_argument("--skip-vlm", action="store_true")
    all_p.add_argument("--pages", type=int, default=None)
    all_p.add_argument("--instance", default="g6.xlarge")
    _only_flag(all_p)

    args = parser.parse_args(argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    only = _normalize_only(getattr(args, "only", "financials"))

    if args.cmd == "generate":
        from src.generate_samples import generate_all

        generate_all()
        return 0

    if args.cmd == "docling":
        from src.docling_runner import convert_samples

        convert_samples(only=only)
        return 0

    if args.cmd == "textract":
        from src.textract_runner import convert_samples as textract_samples

        textract_samples(only=only)
        return 0

    if args.cmd == "vlm":
        from src.vlm_runner import convert_samples as vlm_samples

        vlm_samples(only=only)
        return 0

    if args.cmd == "compare":
        from src.compare import compare_all

        print(json.dumps(compare_all(only=only), indent=2))
        return 0

    if args.cmd == "cost":
        from src.cost_model import estimate

        estimate(pages_per_month=args.pages, seconds_per_page=args.sec_per_page, instance=args.instance)
        return 0

    if args.cmd == "all":
        from src.compare import compare_all
        from src.cost_model import estimate
        from src.docling_runner import convert_samples
        from src.generate_samples import generate_all

        generate_all()
        convert_samples(only=only)
        if not args.skip_textract:
            from src.textract_runner import convert_samples as textract_samples

            textract_samples(only=only)
        if not args.skip_vlm:
            from src.vlm_runner import convert_samples as vlm_samples

            vlm_samples(only=only)
        compare_all(only=only)
        estimate(pages_per_month=args.pages, instance=args.instance)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
