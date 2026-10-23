"""
Command-Line Interface for Address Standardizer.
================================================
Provides a standalone CLI for single address parsing, batch CSV standardization,
benchmark SLA verification, offline spatial R*Tree geocoding, multi-tier verification cascade,
audit ledger triage, and reference cache management.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List

from address_standardizer.audit import StewardshipAuditLedger, get_audit_ledger
from address_standardizer.batch import stream_standardize_csv
from address_standardizer.cache import (
    clear_cache,
    configure_cache,
    get_cache_stats,
)
from address_standardizer.cli_formatting import (
    _emit_cli_output,
    _format_csv_header,
    _format_csv_row,
    _format_postal_table_header,
    _format_postal_table_row,
    _format_postal_text,
    _format_table_header,
    _format_table_row,
    _format_text_address,
)
from address_standardizer.cascade import resolve_verification_cascade
from address_standardizer.geocoder import CensusGeocoder
from address_standardizer.spatial import (
    SpatialEngine,
    get_default_spatial_engine,
    resolve_spatial_coordinates,
)
from address_standardizer.standardizer import standardize_address


def _has_stdin_data() -> bool:
    """True when stdin is a pipe or file that a blocking read should consume.

    A zero-timeout ``select`` cannot tell "no data" from "producer not ready yet" (``slow_cmd | cli``) and does
    not work on Windows pipes at all, so the stream type decides: pipes and regular files are read (blocking until
    the producer writes or closes), while terminals and ``NUL``/``/dev/null`` are not.
    """
    import stat

    if sys.stdin is None or sys.stdin.isatty():
        return False
    if getattr(sys.stdin, "__class__", None).__name__ == "DontReadFromInput":
        return False
    if hasattr(sys.stdin, "getvalue"):  # in-memory streams (tests, embedding)
        return bool(sys.stdin.getvalue().strip())
    try:
        mode = os.fstat(sys.stdin.fileno()).st_mode
    except Exception:
        mode = None
    if mode is not None:
        return stat.S_ISFIFO(mode) or stat.S_ISREG(mode) or stat.S_ISSOCK(mode)
    if hasattr(sys.stdin, "seekable") and sys.stdin.seekable():
        try:
            pos = sys.stdin.tell()
            char = sys.stdin.read(1)
            sys.stdin.seek(pos)
            return bool(char)
        except Exception:
            return False
    return False


def _execute_postal_validation(
    code_or_text: str, country_hint: Any = None
) -> Dict[str, Any]:
    from address_standardizer.international.countries import CountryRegistry
    from address_standardizer.international.postal import (
        PostalValidationResult,
        extract_postal_code,
        validate_postal_code,
    )

    input_str = (code_or_text or "").strip()
    target_country = str(country_hint).strip() if country_hint else None

    if target_country:
        c_info = CountryRegistry.get(target_country)
        if c_info is None:
            res = validate_postal_code(input_str, target_country, return_details=True)
            if isinstance(res, PostalValidationResult):  # pragma: no branch  (return_details=True always yields a PostalValidationResult)
                return {
                    "is_valid": res.is_valid,
                    "country": res.country_code,
                    "postal_code": res.postal_code,
                    "formatted_code": res.formatted_code,
                    "is_non_postal_country": res.is_non_postal_country,
                    "reason": res.reason,
                }
        norm_country = c_info.alpha3
        if not c_info.has_postal_codes:
            res = validate_postal_code(input_str, norm_country, return_details=True)
            if isinstance(res, PostalValidationResult):  # pragma: no branch  (see above)
                return {
                    "is_valid": res.is_valid,
                    "country": res.country_code,
                    "postal_code": res.postal_code,
                    "formatted_code": res.formatted_code,
                    "is_non_postal_country": res.is_non_postal_country,
                    "reason": res.reason,
                }
        direct_res = validate_postal_code(input_str, norm_country, return_details=True)
        if isinstance(direct_res, PostalValidationResult) and direct_res.is_valid:
            return {
                "is_valid": direct_res.is_valid,
                "country": direct_res.country_code,
                "postal_code": direct_res.postal_code,
                "formatted_code": direct_res.formatted_code,
                "is_non_postal_country": direct_res.is_non_postal_country,
                "reason": direct_res.reason,
            }
        ext = extract_postal_code(input_str, country_hint=norm_country)
        if ext and ext != input_str:
            ext_res = validate_postal_code(ext, norm_country, return_details=True)
            if isinstance(ext_res, PostalValidationResult) and ext_res.is_valid:  # pragma: no branch  (extract_postal_code only returns codes that validate for the same country)
                return {
                    "is_valid": ext_res.is_valid,
                    "country": ext_res.country_code,
                    "postal_code": ext_res.postal_code,
                    "formatted_code": ext_res.formatted_code,
                    "is_non_postal_country": ext_res.is_non_postal_country,
                    "reason": ext_res.reason,
                }
        if isinstance(direct_res, PostalValidationResult):  # pragma: no branch  (see above)
            return {
                "is_valid": direct_res.is_valid,
                "country": direct_res.country_code,
                "postal_code": direct_res.postal_code,
                "formatted_code": direct_res.formatted_code,
                "is_non_postal_country": direct_res.is_non_postal_country,
                "reason": direct_res.reason,
            }

    det = CountryRegistry.detect_country(input_str)
    if det:
        norm_country = det.alpha3
        if not det.has_postal_codes:
            res = validate_postal_code(input_str, norm_country, return_details=True)
            if isinstance(res, PostalValidationResult):  # pragma: no branch  (see above)
                return {
                    "is_valid": res.is_valid,
                    "country": res.country_code,
                    "postal_code": res.postal_code,
                    "formatted_code": res.formatted_code,
                    "is_non_postal_country": res.is_non_postal_country,
                    "reason": res.reason,
                }
        ext = extract_postal_code(input_str, country_hint=norm_country)
        code_to_validate = ext if ext else input_str
        val_res = validate_postal_code(code_to_validate, norm_country, return_details=True)
        if isinstance(val_res, PostalValidationResult):  # pragma: no branch  (see above)
            return {
                "is_valid": val_res.is_valid,
                "country": val_res.country_code,
                "postal_code": val_res.postal_code,
                "formatted_code": val_res.formatted_code,
                "is_non_postal_country": val_res.is_non_postal_country,
                "reason": val_res.reason,
            }

    import re
    if re.match(r"^\d{5}(-\d{4})?$", input_str):
        val_res = validate_postal_code(input_str, "USA", return_details=True)
        if isinstance(val_res, PostalValidationResult):  # pragma: no branch  (see above)
            return {
                "is_valid": val_res.is_valid,
                "country": val_res.country_code,
                "postal_code": val_res.postal_code,
                "formatted_code": val_res.formatted_code,
                "is_non_postal_country": val_res.is_non_postal_country,
                "reason": val_res.reason,
            }

    return {
        "is_valid": False,
        "country": "",
        "postal_code": input_str,
        "formatted_code": None,
        "is_non_postal_country": False,
        "reason": "Country not specified and could not be inferred from input",
    }


def _process_piped_stream(
    lines: Any,
    format_type: str = "json",
    country: str = "USA",
    enable_fuzzy: bool = True,
    enable_geocoding: bool = False,
    confidence: bool = False,
) -> None:
    """Process lines from stdin and emit in requested format (json, table, csv, text, upu)."""
    if format_type == "table":
        _emit_cli_output(_format_table_header())
    elif format_type == "csv":
        _emit_cli_output(_format_csv_header())

    for line in lines:
        addr_text = line.strip()
        if not addr_text:
            continue
        res = standardize_address(
            street1=addr_text,
            country=country,
            enable_fuzzy=enable_fuzzy,
            enable_geocoding=enable_geocoding,
        )
        data = res.as_dict()
        if res.dependent_locality:
            data["dependent_locality"] = res.dependent_locality
        if res.building_name:
            data["building_name"] = res.building_name
        data["country_iso3"] = getattr(res, "country_iso3", None) or res.country or ""
        if confidence:
            data["confidence_score"] = res.confidence_score
            data["routing_tier"] = res.routing_tier
            data["failure_reason_codes"] = res.failure_reason_codes

        if format_type == "table":
            _emit_cli_output(_format_table_row(data))
        elif format_type == "csv":
            _emit_cli_output(_format_csv_row(data))
        elif format_type == "text":
            _emit_cli_output(_format_text_address(data))
        elif format_type == "upu":
            _emit_cli_output(res.format_upu())
        else:
            _emit_cli_output(json.dumps(data))


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value}")
    return number


def _limit_1_50(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 50:
        raise argparse.ArgumentTypeError(f"must be between 1 and 50, got {value}")
    return number


def _port_number(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError(f"must be a TCP port between 1 and 65535, got {value}")
    return number


def _audit_ledger(args: argparse.Namespace) -> StewardshipAuditLedger:
    """The ledger for this invocation.

    The default ledger lives in memory and disappears when the process exits, so records written by one CLI call can
    never be listed by the next. ``--audit-db PATH`` (or ADDRESS_STANDARDIZER_AUDIT_DB) selects a SQLite file that
    persists between invocations.
    """
    path = getattr(args, "audit_db", None) or os.environ.get("ADDRESS_STANDARDIZER_AUDIT_DB")
    return StewardshipAuditLedger(db_path=path) if path else get_audit_ledger()


def _apply_zip_state_flag(args: argparse.Namespace) -> None:
    """Honour --correct-state-from-zip for this process and any batch worker processes it starts."""
    if getattr(args, "correct_state_from_zip", False):
        os.environ["ADDRESS_STANDARDIZER_CORRECT_STATE_FROM_ZIP"] = "1"


def _cmd_parse(args: argparse.Namespace) -> None:
    """Handler for the `parse` subcommand."""
    _apply_zip_state_flag(args)
    if args.no_cache:
        configure_cache(enabled=False)

    if args.address == ["-"] or (not args.address and not args.street1 and _has_stdin_data()):
        _process_piped_stream(
            sys.stdin,
            format_type=args.format,
            country=args.country,
            enable_geocoding=args.enable_geocoding,
            confidence=args.confidence,
        )
        return

    from address_standardizer.audit import LEDGER_OVERRIDE
    from address_standardizer.offline_index import get_default_offline_index

    st1 = args.street1
    if not st1 and args.address:
        st1 = " ".join(args.address)
    ref_provider = None
    if args.reference_db:
        from address_standardizer.reference import GeoNamesPostalProvider

        ref_provider = GeoNamesPostalProvider(args.reference_db)

    ledger = _audit_ledger(args)
    token = LEDGER_OVERRIDE.set(ledger)
    try:
        res = standardize_address(
            street1=st1,
            street2=args.street2,
            city=args.city,
            state=args.state,
            postal_code=args.postal_code,
            country=args.country,
            reference_provider=ref_provider,
            explain=bool(getattr(args, "explain", False)),
            alternatives=int(getattr(args, "alternatives", 0) or 0),
        )
        data = res.as_dict(
            include_explanation=bool(getattr(args, "explain", False) or getattr(args, "alternatives", 0))
        )
        if res.dependent_locality:
            data["dependent_locality"] = res.dependent_locality
        if res.building_name:
            data["building_name"] = res.building_name
        data["country_iso3"] = getattr(res, "country_iso3", None) or res.country or ""
        if ref_provider is not None:
            data["reference_validation"] = res.reference_validation.as_dict()

        if args.enable_geocoding:
            engine_to_close = None
            if args.spatial_db:
                engine = SpatialEngine(db_path=args.spatial_db)
                engine_to_close = engine
                sp_res = engine.resolve(res)
            else:
                sp_res = resolve_spatial_coordinates(res)
            if sp_res:
                unresolved = sp_res.precision == "UNRESOLVED"  # an unresolved lookup must not look like (0, 0)
                data["latitude"] = None if unresolved else sp_res.latitude
                data["longitude"] = None if unresolved else sp_res.longitude
                data["spatial_precision"] = sp_res.precision
                data["geocode_precision"] = sp_res.precision
                data["spatial_source"] = sp_res.source
                data["accuracy_radius_meters"] = sp_res.accuracy_radius_meters
                data["h3_r10_index"] = sp_res.h3_res10
                data["spatial_result"] = sp_res.as_dict()
                res.spatial_result = sp_res
            if engine_to_close:
                engine_to_close.close()

        if getattr(args, "latin", False):
            from address_standardizer.transliterate import LATIN_FIELDS, std_to_latin

            data["native"] = {name: data.get(name) for name in LATIN_FIELDS}
            data.update({name: value for name, value in std_to_latin(res).items() if name in LATIN_FIELDS})

        if args.confidence:
            data["confidence_score"] = res.confidence_score
            data["routing_tier"] = res.routing_tier
            data["failure_reason_codes"] = res.failure_reason_codes

        if args.audit:
            if not res.audit_record:
                raw_dict = {
                    "street1": st1,
                    "street2": args.street2,
                    "city": args.city,
                    "state": args.state,
                    "postal_code": args.postal_code,
                    "country": args.country,
                }
                from address_standardizer.confidence import compute_confidence_score
                conf = compute_confidence_score(res, raw_input=raw_dict)
                res.audit_record = ledger.record_standardized_address(
                    res, conf, raw_input=raw_dict
                )
            if res.audit_record:
                data["audit_record"] = res.audit_record.as_dict()

        if args.geocode and res.is_us and res.street1:
            geocoder = CensusGeocoder()
            geo_res = geocoder.geocode_batch([("1", res.street1, res.city, res.state, res.postal_code)])
            if "1" in geo_res:
                data["latitude"] = geo_res["1"]["latitude"]
                data["longitude"] = geo_res["1"]["longitude"]
                data["geocode_precision"] = geo_res["1"]["precision"]

        if args.cascade and res.is_us:
            casc = resolve_verification_cascade(
                street1=res.street1,
                street2=res.street2,
                city=res.city,
                state=res.state,
                postal_code=res.postal_code,
                country=res.country,
                normalized_address_key=res.normalized_address_key,
                census_geocoder=CensusGeocoder(),
                offline_index=get_default_offline_index(),
            )
            if casc:
                data["latitude"] = casc.latitude
                data["longitude"] = casc.longitude
                data["geocode_precision"] = casc.precision
                data["accuracy_radius_meters"] = casc.accuracy_radius_meters
                data["cascade_source"] = casc.source
                data["cascade_stage"] = casc.stage

        if args.format == "upu":
            _emit_cli_output(res.format_upu())
        elif args.format == "text":
            _emit_cli_output(_format_text_address(data))
        elif args.format == "table":
            _emit_cli_output(_format_table_header())
            _emit_cli_output(_format_table_row(data))
        elif args.format == "csv":
            _emit_cli_output(_format_csv_header())
            _emit_cli_output(_format_csv_row(data))
        else:
            _emit_cli_output(json.dumps(data, indent=2))
    finally:
        LEDGER_OVERRIDE.reset(token)
        if ref_provider is not None:
            ref_provider.close()


def _cmd_validate_postal(args: argparse.Namespace) -> None:
    """Handler for the `validate-postal` subcommand."""
    if args.code_or_text == ["-"] or (not args.code_or_text and _has_stdin_data()):
        if args.format == "table":
            _emit_cli_output(_format_postal_table_header())
        for line in sys.stdin:
            line_str = line.strip()
            if not line_str:
                continue
            res = _execute_postal_validation(line_str, args.country)
            if args.format == "text":
                _emit_cli_output(_format_postal_text(res))
            elif args.format == "table":
                _emit_cli_output(_format_postal_table_row(res))
            else:
                _emit_cli_output(json.dumps(res))
        return

    if args.code_or_text:
        input_str = " ".join(args.code_or_text).strip()
        res = _execute_postal_validation(input_str, args.country)
        if args.format == "text":
            _emit_cli_output(_format_postal_text(res))
        elif args.format == "table":
            _emit_cli_output(_format_postal_table_header())
            _emit_cli_output(_format_postal_table_row(res))
        else:
            _emit_cli_output(json.dumps(res, indent=2))
        return

    _print_subparser_help(args)
    sys.exit(1)


def _cmd_batch(args: argparse.Namespace) -> None:
    """Handler for the `batch` subcommand."""
    _apply_zip_state_flag(args)
    if args.no_cache:
        configure_cache(enabled=False)

    mapping_dict = None
    if getattr(args, "mapping", None):
        m_str = args.mapping.strip()
        if m_str.startswith("{"):
            mapping_dict = json.loads(m_str)
        elif os.path.isfile(m_str):
            with open(m_str, "r", encoding="utf-8") as mf:
                mapping_dict = json.load(mf)
        else:
            mapping_dict = json.loads(m_str)
        if not isinstance(mapping_dict, dict):
            sys.stderr.write("Error: --mapping must be a JSON object, e.g. '{\"address\": \"street1\"}'\n")
            sys.exit(2)

    fmt = getattr(args, "format", "auto").lower()
    if fmt == "auto":
        in_lower = args.input_csv.lower()
        out_lower = args.output_csv.lower()
        if in_lower.endswith(".jsonl") or in_lower.endswith(".ndjson") or out_lower.endswith(".jsonl") or out_lower.endswith(".ndjson"):
            fmt = "jsonl"
        elif in_lower.endswith(".json") or out_lower.endswith(".json"):
            fmt = "json"
        else:
            fmt = "csv"

    geocoder = CensusGeocoder() if args.geocode else None

    if fmt in ("jsonl", "ndjson"):
        from address_standardizer.batch import stream_standardize_jsonl
        total = stream_standardize_jsonl(
            input_path=args.input_csv,
            output_path=args.output_csv,
            chunk_size=args.chunk_size,
            max_workers=args.workers,
            street_col=args.street_col,
            street2_col=args.street2_col,
            city_col=args.city_col,
            state_col=args.state_col,
            zip_col=args.zip_col,
            country_col=args.country_col,
            mapping=mapping_dict,
            geocode=args.geocode,
            geocoder=geocoder,
            include_confidence=args.confidence,
            audit_csv_path=args.audit_csv,
            enable_geocoding=args.enable_geocoding,
            spatial_db=args.spatial_db,
            include_intl=args.include_intl,
            country=args.country,
        )
    elif fmt == "json":
        from address_standardizer.batch import stream_standardize_json
        total = stream_standardize_json(
            input_path=args.input_csv,
            output_path=args.output_csv,
            chunk_size=args.chunk_size,
            max_workers=args.workers,
            street_col=args.street_col,
            street2_col=args.street2_col,
            city_col=args.city_col,
            state_col=args.state_col,
            zip_col=args.zip_col,
            country_col=args.country_col,
            mapping=mapping_dict,
            geocode=args.geocode,
            geocoder=geocoder,
            include_confidence=args.confidence,
            audit_csv_path=args.audit_csv,
            enable_geocoding=args.enable_geocoding,
            spatial_db=args.spatial_db,
            include_intl=args.include_intl,
            country=args.country,
        )
    else:
        total = stream_standardize_csv(
            input_path=args.input_csv,
            output_path=args.output_csv,
            chunk_size=args.chunk_size,
            max_workers=args.workers,
            street_col=args.street_col,
            street2_col=args.street2_col,
            city_col=args.city_col,
            state_col=args.state_col,
            zip_col=args.zip_col,
            country_col=args.country_col,
            mapping=mapping_dict,
            geocode=args.geocode,
            geocoder=geocoder,
            include_confidence=args.confidence,
            audit_csv_path=args.audit_csv,
            enable_geocoding=args.enable_geocoding,
            spatial_db=args.spatial_db,
            include_intl=args.include_intl,
            country=args.country,
        )
    _emit_cli_output(f"Standardized {total} record(s) -> {args.output_csv}")
    if args.audit_csv:
        _emit_cli_output(f"Wrote audit record(s) -> {args.audit_csv}")


def _cmd_benchmark(args: argparse.Namespace) -> None:
    """Handler for the `benchmark` subcommand."""
    import importlib.util

    # Load the harness from this checkout only: importing a "benchmarks" package off sys.path would execute whatever
    # directory the user happens to be in. The harness is not part of the installed wheel.
    bench_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "benchmarks", "run_benchmarks.py"))
    if not os.path.isfile(bench_path):
        sys.stderr.write("Error: the benchmark harness is only available in a source checkout of the repository.\n")
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("address_standardizer_benchmarks_run", bench_path)
    if spec is None or spec.loader is None:
        sys.stderr.write(f"Error: cannot load benchmarks from {bench_path}\n")
        sys.exit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run_all_benchmarks = getattr(mod, "run_all_benchmarks")
    print_report = getattr(mod, "print_report")

    results = run_all_benchmarks(dataset_path=args.dataset, iterations=args.iterations)
    if args.format == "json":
        _emit_cli_output(json.dumps(results, indent=2))
    else:
        print_report(results)


def _print_subparser_help(args: argparse.Namespace) -> None:
    """Print help for the subcommand's own parser (stored by main() via set_defaults)."""
    parser = getattr(args, "_parser", None)
    if parser is not None:
        parser.print_help()


def _emit_spatial_points(results: List[Any], header: str, fmt: str) -> None:
    """Render spatial query results as numbered text lines or a JSON array."""
    if fmt == "text":
        lines = [header]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.latitude}, {r.longitude} ({r.precision}, {r.source}) - H3: {r.h3_res10}")
        _emit_cli_output("\n".join(lines))
    else:
        _emit_cli_output(json.dumps([r.as_dict() for r in results], indent=2))


def _cmd_spatial(args: argparse.Namespace) -> None:
    """Handler for the `spatial` subcommand."""
    if not args.spatial_action:
        _print_subparser_help(args)
        sys.exit(1)

    if args.spatial_action == "build":
        from address_standardizer.spatial.ingestion import (
            OpenAddressesIngestor,
            TigerLineIngestor,
            OsmBuildingIngestor,
        )
        oa_path = getattr(args, "openaddresses_path", None)
        tg_path = getattr(args, "tiger_path", None)
        osm_path = getattr(args, "osm_path", None)

        if oa_path and not os.path.exists(oa_path):
            _emit_cli_output(f"Error: OpenAddresses file not found: {oa_path}")
            sys.exit(1)
        if tg_path and not os.path.exists(tg_path):
            _emit_cli_output(f"Error: TIGER file not found: {tg_path}")
            sys.exit(1)
        if osm_path and not os.path.exists(osm_path):
            _emit_cli_output(f"Error: OSM file not found: {osm_path}")
            sys.exit(1)

        output_path = args.output_db or "data/spatial_index.db"
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        engine = SpatialEngine(db_path=output_path, seed=True)
        pts_added = 0
        segs_added = 0
        osm_added = 0

        if oa_path:
            oa = OpenAddressesIngestor(engine)
            pts_added = oa.ingest_csv(oa_path)
        if tg_path:
            tg = TigerLineIngestor(engine)
            segs_added = tg.ingest_csv(tg_path)
        if osm_path:
            osm = OsmBuildingIngestor(engine)
            osm_added = osm.ingest_geojson(osm_path)

        total_points = engine.count()
        _emit_cli_output(f"Spatial SQLite index built successfully: {output_path}")
        _emit_cli_output(f"Total spatial points: {total_points}")
        if pts_added:
            _emit_cli_output(f"Ingested OpenAddresses points: {pts_added}")
        if segs_added:
            _emit_cli_output(f"Ingested TIGER segments: {segs_added}")
        if osm_added:
            _emit_cli_output(f"Ingested OSM building features: {osm_added}")
        engine.close()
        return

    engine = SpatialEngine(db_path=args.spatial_db) if args.spatial_db else get_default_spatial_engine()
    engine_to_close = engine if args.spatial_db else None
    try:
        if args.spatial_action == "lookup":
            addr_input = args.explicit_address or (" ".join(args.address) if args.address else None)
            if addr_input:
                std_addr = standardize_address(street1=addr_input)
                sp_res = engine.resolve(std_addr)
                if args.format == "text":
                    res_lines = [
                        "SPATIAL RESOLUTION RESULT",
                        "=========================",
                        f"Status:                {sp_res.precision}",
                        f"Latitude:              {sp_res.latitude}",
                        f"Longitude:             {sp_res.longitude}",
                        f"Accuracy Radius (m):   {sp_res.accuracy_radius_meters}",
                        f"Cascade Stage:         {sp_res.stage}",
                        f"Source:                {sp_res.source}",
                        f"H3 Res10:              {sp_res.h3_res10}",
                        f"Parcel ID:             {sp_res.parcel_id or 'None'}",
                    ]
                    _emit_cli_output("\n".join(res_lines))
                else:
                    _emit_cli_output(json.dumps([sp_res.as_dict()], indent=2))
            elif args.bbox:
                try:
                    sep = "," if "," in args.bbox else None
                    parts = [float(x.strip()) for x in (args.bbox.split(",") if sep else args.bbox.split())]
                except ValueError:
                    parts = []
                if len(parts) != 4:
                    sys.stderr.write("Error: --bbox requires 4 values: min_lon,min_lat,max_lon,max_lat\n")
                    sys.exit(2)
                min_lon, min_lat, max_lon, max_lat = parts
                results = engine.query_bounding_box(min_lon, min_lat, max_lon, max_lat, limit=args.limit)
                _emit_spatial_points(results, f"Found {len(results)} spatial point(s) in bounding box:", args.format)
            elif (
                args.min_lat is not None
                and args.min_lon is not None
                and args.max_lat is not None
                and args.max_lon is not None
            ):
                results = engine.query_bounding_box(
                    args.min_lon, args.min_lat, args.max_lon, args.max_lat, limit=args.limit
                )
                _emit_spatial_points(results, f"Found {len(results)} spatial point(s) in bounding box:", args.format)
            elif args.lat is not None and args.lon is not None:
                results = engine.query_radius(
                    lon=args.lon, lat=args.lat, radius_meters=args.radius, limit=args.limit
                )
                _emit_spatial_points(results, f"Found {len(results)} spatial point(s) within {args.radius:.1f}m:", args.format)
            else:
                sys.stderr.write(
                    "Error: spatial lookup requires address, coordinates (--lat and --lon), or bounding box (--min-lat, --min-lon, --max-lat, --max-lon or --bbox).\n"
                )
                sys.exit(2)
        elif args.spatial_action in ("info", "stats"):  # pragma: no branch  (argparse only offers build/lookup/info/stats)
            with engine._lock:
                pts_count = engine.count()
                cur = engine._conn.execute("SELECT count(*) FROM street_segments")
                seg_count = cur.fetchone()[0]
                cur = engine._conn.execute("SELECT count(*) FROM postal_centroids")
                post_count = cur.fetchone()[0]
                cur = engine._conn.execute("SELECT count(*) FROM municipal_centroids")
                muni_count = cur.fetchone()[0]

            stats = {
                "database_path": engine._db_path,
                "total_spatial_points": pts_count,
                "street_segments_count": seg_count,
                "postal_centroids_count": post_count,
                "municipal_centroids_count": muni_count,
                "rtree_index_enabled": True,
                "memory_pragmas": {
                    "journal_mode": "WAL",
                    "cache_size_kb": 64000,
                    "mmap_size_mb": 256,
                    "temp_store": "MEMORY",
                },
            }
            if args.format == "json":
                _emit_cli_output(json.dumps(stats, indent=2))
            else:
                _emit_cli_output(
                    "SPATIAL DATABASE DIAGNOSTICS & INDEX STATISTICS\n"
                    "================================================\n"
                    f"Database Path:             {stats['database_path']}\n"
                    f"Indexed Spatial Points:    {stats['total_spatial_points']:,}\n"
                    f"Street Segments:           {stats['street_segments_count']:,}\n"
                    f"Postal Centroids:          {stats['postal_centroids_count']:,}\n"
                    f"Municipal Centroids:       {stats['municipal_centroids_count']:,}\n"
                    f"R*Tree Index Enabled:      {stats['rtree_index_enabled']}\n"
                    "Pragmas:                   WAL, cache_size=-64000, mmap_size=256MB"
                )
    finally:
        if engine_to_close:
            engine_to_close.close()


def _cmd_audit(args: argparse.Namespace) -> None:
    """Handler for the `audit` subcommand."""
    ledger = _audit_ledger(args)
    if args.clear:
        ledger.clear()
        _emit_cli_output("Audit ledger cleared.")
        return

    records = ledger.list_records(review_status=args.status)
    if args.export == "sql":
        _emit_cli_output(ledger.export(format="sql"))
    elif args.export == "dict":
        lines = [f"Audit ledger contains {len(records)} record(s):"]
        for r in records[:50]:
            lines.append(f"[{r.review_status}] {r.action_type} - {r.record_id} ({r.confidence_score:.4f})")
        _emit_cli_output("\n".join(lines))
    else:
        _emit_cli_output(json.dumps([r.as_dict() for r in records], indent=2))


def _cmd_cache(args: argparse.Namespace) -> None:
    """Handler for the `cache` subcommand."""
    if args.clear:
        clear_cache()
        _emit_cli_output("Cache cleared.")
    else:
        stats = get_cache_stats()
        _emit_cli_output(json.dumps(stats, indent=2))


def _cmd_autocomplete(args: argparse.Namespace) -> None:
    """Handler for the `autocomplete` subcommand."""
    from address_standardizer.autocomplete import autocomplete_address
    suggestions = autocomplete_address(
        query=args.query,
        max_results=args.limit,
        state_filter=args.state,
    )
    if args.format == "json":
        _emit_cli_output(json.dumps([s.as_dict() for s in suggestions], indent=2))
    else:
        if not suggestions:
            _emit_cli_output("No suggestions found.")
        lines = []
        for i, s in enumerate(suggestions, 1):
            sec_notice = f" [Secondary Unit Required: {', '.join(s.suggested_secondary_units)}]" if s.secondary_prompt_required else ""
            lines.append(f"{i}. {s.text}{sec_notice}")
        if lines:
            _emit_cli_output("\n".join(lines))


def _cmd_data(args: argparse.Namespace) -> None:
    """Handler for the `data` subcommand (reference-data fetch / build / info)."""
    from address_standardizer.reference._cli import run_data_command

    run_data_command(args, _emit_cli_output)


def _cmd_serve(args: argparse.Namespace) -> None:
    """Handler for the `serve` subcommand."""
    try:
        import uvicorn
    except ImportError:
        sys.stderr.write(
            "Error: uvicorn is required to run the server daemon. Install with `pip install uvicorn`.\n"
        )
        sys.exit(1)
    uvicorn.run(
        "address_standardizer.server:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload,
    )


def _cmd_mcp(args: argparse.Namespace) -> None:
    from address_standardizer.mcp.server import main as mcp_main

    mcp_args = ["--transport", args.transport, "--host", args.host, "--port", str(args.port)]
    mcp_main(mcp_args)


_COMMAND_HANDLERS = {
    "parse": _cmd_parse,
    "validate-postal": _cmd_validate_postal,
    "batch": _cmd_batch,
    "benchmark": _cmd_benchmark,
    "spatial": _cmd_spatial,
    "audit": _cmd_audit,
    "cache": _cmd_cache,
    "autocomplete": _cmd_autocomplete,
    "serve": _cmd_serve,
    "data": _cmd_data,
    "mcp": _cmd_mcp,
}


def main():
    _known_subcommands = set(_COMMAND_HANDLERS)

    # Shorthand invocation check: when no subcommand or help flag is passed
    if len(sys.argv) > 1 and "-h" not in sys.argv[1:] and "--help" not in sys.argv[1:]:
        shorthand_parser = argparse.ArgumentParser(prog="address-standardizer", add_help=False, exit_on_error=False)
        shorthand_parser.add_argument("--format", choices=["json", "text", "table", "csv", "upu"], default="json")
        shorthand_parser.add_argument("--country", "-c", default=None)
        shorthand_parser.add_argument("--correct-state-from-zip", action="store_true")
        shorthand_parser.add_argument("address", nargs="*")
        unknown_flags: List[str] = []
        try:
            s_args, extras = shorthand_parser.parse_known_args(sys.argv[1:])
            unknown_flags = [a for a in extras if a.startswith("-") and len(a) > 1]
        except argparse.ArgumentError:
            s_args = None  # options this parser does not understand: let the subcommand parser handle them
        # Shorthand mode only when the first positional word is not a subcommand, so an address such as
        # "12 audit rd" or an option value such as "--country cache" is never mistaken for a subcommand.
        if s_args is not None and unknown_flags and not (s_args.address and s_args.address[0] in _known_subcommands):
            sys.stderr.write(
                f"Error: unrecognized option(s): {' '.join(unknown_flags)} "
                f"(shorthand mode accepts --format and --country; use a subcommand such as `parse` for more).\n"
            )
            sys.exit(2)
        if s_args is not None and not (s_args.address and s_args.address[0] in _known_subcommands):
            if s_args.address:
                raw_addr = " ".join(s_args.address)
                res = standardize_address(
                    street1=raw_addr,
                    country=s_args.country,
                    correct_state_from_zip=True if s_args.correct_state_from_zip else None,
                )
                data = res.as_dict()
                if res.dependent_locality:
                    data["dependent_locality"] = res.dependent_locality
                if res.building_name:
                    data["building_name"] = res.building_name
                data["country_iso3"] = getattr(res, "country_iso3", None) or res.country or ""
                if s_args.format == "upu":
                    _emit_cli_output(res.format_upu())
                elif s_args.format == "text":
                    _emit_cli_output(_format_text_address(data))
                elif s_args.format == "table":
                    _emit_cli_output(_format_table_header())
                    _emit_cli_output(_format_table_row(data))
                elif s_args.format == "csv":
                    _emit_cli_output(_format_csv_header())
                    _emit_cli_output(_format_csv_row(data))
                else:
                    _emit_cli_output(json.dumps(data, indent=2))
                return
            elif _has_stdin_data():
                _process_piped_stream(sys.stdin, format_type=s_args.format, country=s_args.country)
                return

    parser = argparse.ArgumentParser(
        prog="address-standardizer",
        description="Standardize US and international addresses to USPS Pub 28 and ISO standards.",
    )
    parser.add_argument("--format", choices=["json", "text", "table", "csv", "upu"], default="json", help="Output format for piped input or address parsing (default: json)")
    parser.add_argument("--country", "-c", default="USA", help="Default country for address standardization (default: USA)")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: parse single address
    parse_parser = subparsers.add_parser("parse", help="Parse and standardize a single address string")
    parse_parser.add_argument("address", nargs="*", help="Full address string (e.g. '100 Wall St, Ste 400, New York, NY 10005')")
    parse_parser.add_argument("--street1", help="Street address line 1")
    parse_parser.add_argument("--street2", help="Street address line 2 (Suite, Floor, Apt)")
    parse_parser.add_argument("--city", help="City name")
    parse_parser.add_argument("--state", help="State / province code or name")
    parse_parser.add_argument("--zip", dest="postal_code", help="Postal code or ZIP")
    parse_parser.add_argument("--country", "-c", default=None, help="Country name or ISO code (default: detected from the address, USA when none is found)")
    parse_parser.add_argument("--format", choices=["json", "text", "table", "csv", "upu"], default="json", help="Output format (default: json)")
    parse_parser.add_argument("--enable-geocoding", action="store_true", help="Enrich with offline spatial R*Tree geocoder")
    parse_parser.add_argument("--spatial-db", "--db", dest="spatial_db", help="Path to offline SQLite spatial database file")
    parse_parser.add_argument("--geocode", action="store_true", help="Enrich with US Census geocoder coordinates")
    parse_parser.add_argument("--cascade", action="store_true", help="Run 4-stage graceful verification cascade")
    parse_parser.add_argument("--confidence", action="store_true", help="Include composite confidence score and routing tier")
    parse_parser.add_argument("--audit", action="store_true", help="Include stewardship audit record details")
    parse_parser.add_argument("--audit-db", help="SQLite file for the audit ledger, so records persist between runs (default: in-memory; env ADDRESS_STANDARDIZER_AUDIT_DB)")
    parse_parser.add_argument("--latin", action="store_true", help="Render street1/street2/city/state in Latin script (Cyrillic and Greek built in; other scripts need the optional anyascii package, otherwise they are left unchanged); the originals are kept under \"native\"")
    parse_parser.add_argument("--no-cache", action="store_true", help="Bypass multi-tier reference cache")
    parse_parser.add_argument("--reference-db", help="GeoNames postal index (see `data build geonames`): validate postal code / city / state and add reference_validation (single address only; docs/reference_data.md)")
    parse_parser.add_argument("--correct-state-from-zip", action="store_true", help="Replace a US state that contradicts the ZIP with the ZIP's state (reported as WARN_STATE_CORRECTED_FROM_ZIP). Default: keep the given state, flag ERR_ZIP_STATE_MISMATCH and mark the address UNDELIVERABLE.")
    parse_parser.add_argument("--explain", action="store_true", help="Include normalization explanation trace in output")
    parse_parser.add_argument("--alternatives", type=int, default=0, help="Number of candidate alternative standardizations to return (default: 0)")

    # Command: batch CSV processing
    batch_parser = subparsers.add_parser("batch", help="Batch standardize a CSV file")
    batch_parser.add_argument("input_csv", help="Path to input CSV file")
    batch_parser.add_argument("output_csv", help="Path to write standardized CSV output")
    batch_parser.add_argument("--format", choices=["auto", "csv", "jsonl", "ndjson", "json"], default="auto", help="File format: csv, jsonl, ndjson, json (default: auto)")
    batch_parser.add_argument("--mapping", help="Column/field mapping as a JSON string or path to a JSON file (e.g. '{\"address\": \"street1\", \"zip\": \"postal_code\"}')")
    batch_parser.add_argument("--street-col", default="street1", help="Column name for street (default: street1)")
    batch_parser.add_argument("--street2-col", default="street2", help="Column name for street line 2 (default: street2)")
    batch_parser.add_argument("--city-col", default="city", help="Column name for city (default: city)")
    batch_parser.add_argument("--state-col", default="state", help="Column name for state (default: state)")
    batch_parser.add_argument("--zip-col", default="postal_code", help="Column name for zip (default: postal_code)")
    batch_parser.add_argument("--country-col", default="country", help="Column name for country (default: country)")
    batch_parser.add_argument("--country", "-c", dest="country", default=None, help="Default country name or ISO code for batch")
    batch_parser.add_argument("--chunk-size", type=_positive_int, default=5000, help="Streaming chunk size (default: 5000)")
    batch_parser.add_argument("--workers", type=_positive_int, default=2, help="Multiprocessing workers, max 2 (default: 2)")
    batch_parser.add_argument("--enable-geocoding", action="store_true", help="Batch geocode with offline spatial engine")
    batch_parser.add_argument("--spatial-db", "--db", dest="spatial_db", help="Path to offline SQLite spatial database file")
    batch_parser.add_argument("--include-intl", action="store_true", help="Include international columns (dependent_locality, building_name)")
    batch_parser.add_argument("--geocode", action="store_true", help="Batch geocode US addresses with Census API")
    batch_parser.add_argument("--confidence", action="store_true", help="Include confidence_score and routing_tier columns")
    batch_parser.add_argument("--audit-csv", help="Path to write audit ledger records as CSV")
    batch_parser.add_argument("--no-cache", action="store_true", help="Disable caching during batch processing")
    batch_parser.add_argument("--correct-state-from-zip", action="store_true", help="Replace a US state that contradicts the ZIP with the ZIP's state (reported as WARN_STATE_CORRECTED_FROM_ZIP). Default: keep the given state, flag ERR_ZIP_STATE_MISMATCH and mark the address UNDELIVERABLE.")

    # Command: benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Execute performance and golden accuracy benchmarks")
    bench_parser.add_argument(
        "--dataset",
        default="domestic",
        help="Benchmark dataset: 'domestic' (US 1k), 'multi_national' (Global 1k), 'all' (Both 2k), or file path (default: domestic)",
    )
    bench_parser.add_argument("--iterations", type=int, default=1, help="Repetitions for throughput profiling (default: 1)")
    bench_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format: 'text' (SLA table report) or 'json' (default: text)")

    # Command: spatial
    spatial_parser = subparsers.add_parser("spatial", help="Offline SQLite R*Tree spatial engine lookup and diagnostics")
    spatial_parser.set_defaults(_parser=spatial_parser)
    spatial_sub = spatial_parser.add_subparsers(dest="spatial_action", help="Spatial action")

    # spatial build
    spatial_build = spatial_sub.add_parser("build", help="Compile parcel points and TIGER edges into offline spatial SQLite database")
    spatial_build.add_argument("--output", "--output-db", "--db", "--spatial-db", dest="output_db", default="data/spatial_index.db", help="Destination path for SQLite spatial database file (default: data/spatial_index.db)")
    spatial_build.add_argument("--openaddresses", dest="openaddresses_path", help="Path to OpenAddresses CSV file")
    spatial_build.add_argument("--tiger", dest="tiger_path", help="Path to TIGER street segments CSV file")
    spatial_build.add_argument("--osm", dest="osm_path", help="Path to OpenStreetMap GeoJSON building features file")

    # spatial lookup
    spatial_lookup = spatial_sub.add_parser("lookup", help="Query spatial database by address, coordinates, or bounding box")
    spatial_lookup.add_argument("address", nargs="*", help="Address string to resolve via spatial cascade")
    spatial_lookup.add_argument("--address", dest="explicit_address", help="Explicit address string")
    spatial_lookup.add_argument("--lat", "--latitude", dest="lat", type=float, help="Latitude for radius query")
    spatial_lookup.add_argument("--lon", "--longitude", dest="lon", type=float, help="Longitude for radius query")
    spatial_lookup.add_argument("--radius", type=float, default=1000.0, help="Search radius in meters (default: 1000.0)")
    spatial_lookup.add_argument("--min-lat", type=float, help="Minimum latitude for bounding box query")
    spatial_lookup.add_argument("--min-lon", type=float, help="Minimum longitude for bounding box query")
    spatial_lookup.add_argument("--max-lat", type=float, help="Maximum latitude for bounding box query")
    spatial_lookup.add_argument("--max-lon", type=float, help="Maximum longitude for bounding box query")
    spatial_lookup.add_argument("--bbox", help="Bounding box as min_lon,min_lat,max_lon,max_lat")
    spatial_lookup.add_argument("--limit", type=_positive_int, default=10, help="Maximum results to return (default: 10)")
    spatial_lookup.add_argument("--spatial-db", "--db", dest="spatial_db", help="Path to offline SQLite spatial database file")
    spatial_lookup.add_argument("--format", choices=["json", "text"], default="json", help="Output format (default: json)")

    # spatial info
    spatial_info = spatial_sub.add_parser("info", help="Display spatial database index statistics and table counts")
    spatial_info.add_argument("--spatial-db", "--db", dest="spatial_db", help="Path to offline SQLite spatial database file")
    spatial_info.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")

    # spatial stats alias
    spatial_stats = spatial_sub.add_parser("stats", help="Alias for spatial info")
    spatial_stats.add_argument("--spatial-db", "--db", dest="spatial_db", help="Path to offline SQLite spatial database file")
    spatial_stats.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")

    # Command: audit ledger triage
    audit_parser = subparsers.add_parser("audit", help="Inspect and export stewardship audit ledger")
    audit_parser.add_argument("--list", action="store_true", help="List recent audit records")
    audit_parser.add_argument("--status", choices=["PENDING", "APPROVED", "MODIFIED", "REJECTED"], help="Filter by review status")
    audit_parser.add_argument("--export", choices=["json", "sql", "dict"], default="json", help="Export format (default: json)")
    audit_parser.add_argument("--clear", action="store_true", help="Clear audit ledger")
    audit_parser.add_argument("--audit-db", help="SQLite file holding the audit ledger (default: in-memory, which is always empty in a new process; env ADDRESS_STANDARDIZER_AUDIT_DB)")

    # Command: cache inspection & management
    cache_parser = subparsers.add_parser("cache", help="Inspect and manage multi-tier reference cache")
    cache_parser.add_argument("--stats", action="store_true", help="Display L1 and L2 cache statistics")
    cache_parser.add_argument("--clear", action="store_true", help="Clear L1 and L2 cache entries")

    # Command: autocomplete typeahead
    auto_parser = subparsers.add_parser("autocomplete", help="Real-time address typeahead and secondary unit prompt")
    auto_parser.add_argument("query", help="Prefix or address query to autocomplete")
    auto_parser.add_argument("--limit", type=_limit_1_50, default=5, help="Maximum suggestions (default: 5)")
    auto_parser.add_argument("--state", help="Filter suggestions by state code")
    auto_parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format (default: text)")

    # Command: validate-postal
    postal_parser = subparsers.add_parser(
        "validate-postal",
        help="Validate or extract international postal codes across 249 ISO-3166-1 jurisdictions",
    )
    postal_parser.set_defaults(_parser=postal_parser)
    postal_parser.add_argument(
        "code_or_text",
        nargs="*",
        help="Postal code or text segment containing a postal code",
    )
    postal_parser.add_argument(
        "--country", "-c",
        default=None,
        help="ISO-3166-1 alpha-2, alpha-3, numeric code, or country name (optional, auto-detected if omitted)",
    )
    postal_parser.add_argument(
        "--format",
        choices=["json", "text", "table"],
        default="json",
        help="Output format: json, text, table (default: json)",
    )

    # Command: serve microservice daemon
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start standalone FastAPI microservice daemon with OpenAPI documentation",
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1; use 0.0.0.0 to listen on all interfaces)")
    serve_parser.add_argument("--port", type=_port_number, default=8000, help="Bind port (default: 8000)")
    serve_parser.add_argument("--workers", type=_positive_int, default=1, help="Number of worker processes (default: 1)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    # Command: mcp AI agent server
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="Start Model Context Protocol (MCP) server for AI agent integration",
    )
    mcp_parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport protocol (default: stdio)",
    )
    mcp_parser.add_argument("--host", default="127.0.0.1", help="Bind host for SSE transport (default: 127.0.0.1)")
    mcp_parser.add_argument("--port", type=_port_number, default=8000, help="Bind port for SSE transport (default: 8000)")

    from address_standardizer.reference._cli import add_data_parser

    add_data_parser(subparsers)

    raw_args = sys.argv[1:]
    normalized_args = []
    i = 0
    while i < len(raw_args):
        arg = raw_args[i]
        if arg == "--bbox" and i + 1 < len(raw_args) and not raw_args[i + 1].startswith("--"):
            normalized_args.append(f"--bbox={raw_args[i + 1]}")
            i += 2
        else:
            normalized_args.append(arg)
            i += 1

    args = parser.parse_args(normalized_args)

    if not args.command:
        if _has_stdin_data():
            _process_piped_stream(
                sys.stdin,
                format_type=getattr(args, "format", "json"),
                country=getattr(args, "country", "USA"),
            )
            return
        parser.print_help()
        sys.exit(1)

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is not None:  # pragma: no branch  (argparse only yields registered subcommands)
        try:
            handler(args)
        except (OSError, ValueError, sqlite3.Error, csv.Error) as exc:
            # Bad paths, malformed input rows and unusable databases are user errors, not crashes.
            sys.stderr.write(f"Error: {exc}\n")
            sys.exit(2)


if __name__ == "__main__":
    main()
