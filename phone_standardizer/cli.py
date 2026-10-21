"""Command Line Interface (CLI) for Phone Standardizer."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from phone_standardizer.batch import stream_standardize_csv
from phone_standardizer.registry import get_dial_plan
from phone_standardizer.standardizer import standardize_phone


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="phone-standardizer",
        description="Universal multi-national phone number standardization, validation, and formatting CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # parse command
    parse_cmd = sub.add_parser("parse", help="Standardize a single phone number and output JSON.")
    parse_cmd.add_argument("phone", help="Raw phone number string to standardize.")
    parse_cmd.add_argument("-c", "--country", default=None, help="Optional ISO country hint (e.g. US, GB, DE).")
    parse_cmd.add_argument("-d", "--default-country", default="US", help="Fallback ISO country (default: US).")

    # country command
    country_cmd = sub.add_parser("country", help="Lookup ITU-T E.164 dial plan metadata for a country.")
    country_cmd.add_argument("identifier", help="ISO-2, ISO-3, numeric code, or country name.")

    # batch command
    batch_cmd = sub.add_parser("batch", help="Batch-standardize a CSV file.")
    batch_cmd.add_argument("input_csv", help="Input CSV file path.")
    batch_cmd.add_argument("output_csv", help="Output CSV file path.")
    batch_cmd.add_argument("--phone-col", default="phone", help="Column containing raw phone numbers.")
    batch_cmd.add_argument("--country-col", default="country", help="Optional column containing country hints.")
    batch_cmd.add_argument("--default-country", default="US", help="Fallback ISO country (default: US).")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning exit status code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse":
        res = standardize_phone(
            args.phone,
            country=args.country,
            default_country=args.default_country,
        )
        sys.stdout.write(json.dumps(res.to_dict(), indent=2) + "\n")
        return 0

    if args.command == "country":
        plan = get_dial_plan(args.identifier)
        if plan is None:
            sys.stderr.write(f"Error: Unknown country identifier '{args.identifier}'\n")
            return 1
        sys.stdout.write(json.dumps(plan.to_dict(), indent=2) + "\n")
        return 0

    # args.command == "batch"
    rows = stream_standardize_csv(
        args.input_csv,
        args.output_csv,
        phone_col=args.phone_col,
        country_col=args.country_col,
        default_country=args.default_country,
    )
    sys.stdout.write(json.dumps({"processed_rows": rows, "output_csv": args.output_csv}) + "\n")
    return 0
