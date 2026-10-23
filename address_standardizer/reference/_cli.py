"""``address-standardizer data ...`` sub-commands (fetch / build / info) for the reference-data layer."""

from __future__ import annotations

import argparse
import json
from typing import Callable

from address_standardizer.reference.geonames import (
    DEFAULT_DOWNLOAD_DIR,
    GeoNamesPostalProvider,
    build_geonames_index,
    download_geonames,
)

DEFAULT_DB = "data/geonames_postal.db"


def _split(value: str) -> list:
    return [c.strip() for c in value.split(",") if c.strip()]


def add_data_parser(subparsers: "argparse._SubParsersAction") -> None:
    """Register the ``data`` command on the main CLI's subparsers."""
    data = subparsers.add_parser("data", help="Fetch, build and inspect reference data (GeoNames postal codes)")
    sub = data.add_subparsers(dest="data_action", required=True)

    fetch = sub.add_parser("fetch", help="Download reference data (network access happens only here)")
    fetch_sub = fetch.add_subparsers(dest="data_source", required=True)
    f_geo = fetch_sub.add_parser("geonames", help="Download GeoNames postal-code zips (CC BY 4.0)")
    f_geo.add_argument("--countries", default="US", help="Comma-separated ISO alpha-2 codes, or ALL (default: US)")
    f_geo.add_argument("--out", default=str(DEFAULT_DOWNLOAD_DIR), help=f"Directory for the zips (default: {DEFAULT_DOWNLOAD_DIR})")
    f_geo.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout in seconds (default: 60)")

    build = sub.add_parser("build", help="Build a local SQLite index from downloaded data (no network)")
    build_sub = build.add_subparsers(dest="data_source", required=True)
    b_geo = build_sub.add_parser("geonames", help="Build the GeoNames postal-code index")
    b_geo.add_argument("--from", dest="source_dir", default=str(DEFAULT_DOWNLOAD_DIR), help="Directory (or file) holding GeoNames .zip/.txt files")
    b_geo.add_argument("--countries", help="Only index these comma-separated ISO alpha-2 codes (default: all in the files)")
    b_geo.add_argument("--out", default=DEFAULT_DB, help=f"Index file to write (default: {DEFAULT_DB})")
    b_geo.add_argument("--as-of", help="Data vintage label (default: today's date)")

    info = sub.add_parser("info", help="Show metadata, coverage and attribution of a built index")
    info.add_argument("path", help="Path to the index file")


def run_data_command(args: argparse.Namespace, emit: Callable[[str], None]) -> None:
    """Run a parsed ``data`` command, writing JSON through ``emit``."""
    if args.data_action == "fetch":
        paths = download_geonames(_split(args.countries), args.out, timeout=args.timeout)
        emit(json.dumps({"downloaded": [str(p) for p in paths]}, indent=2))
    elif args.data_action == "build":
        countries = _split(args.countries) if args.countries else None
        emit(json.dumps(build_geonames_index(args.out, countries, args.source_dir, as_of=args.as_of), indent=2))
    else:
        with GeoNamesPostalProvider(args.path) as provider:
            emit(json.dumps(provider.info(), indent=2))
