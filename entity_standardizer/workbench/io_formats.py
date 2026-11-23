"""Multi-format tabular & structured file I/O with lossless round-trip format preservation."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
import csv
from dataclasses import dataclass
from enum import StrEnum
import json
import math
import os
from pathlib import Path
import re
from typing import Any
import uuid
import zipfile

from entity_standardizer.arrow import _ensure_pyarrow

_UNSET: Any = object()
_openpyxl_mod: Any = _UNSET


def _ensure_openpyxl() -> Any:
    global _openpyxl_mod
    if _openpyxl_mod is _UNSET:
        try:
            import openpyxl as _ox  # type: ignore[import-not-found]

            _openpyxl_mod = _ox
        except ImportError:
            _openpyxl_mod = None
    if _openpyxl_mod is None:
        raise ImportError(
            'openpyxl is required for Excel (.xlsx) files. Install with `pip install "entity-standardizer[ui]"`.'
        )
    return _openpyxl_mod


class SupportedFormat(StrEnum):
    """Supported tabular and structured file formats for import and round-trip export."""

    CSV = "csv"
    TSV = "tsv"
    PSV = "psv"
    DELIMITED = "delimited"
    XLSX = "xlsx"
    JSON = "json"
    JSONL = "jsonl"
    PARQUET = "parquet"


_FORMAT_EXTENSION_MAP: dict[str, str] = {
    SupportedFormat.CSV.value: ".csv",
    SupportedFormat.TSV.value: ".tsv",
    SupportedFormat.PSV.value: ".psv",
    SupportedFormat.DELIMITED.value: ".txt",
    SupportedFormat.XLSX.value: ".xlsx",
    SupportedFormat.JSON.value: ".json",
    SupportedFormat.JSONL.value: ".jsonl",
    SupportedFormat.PARQUET.value: ".parquet",
}

_FORMAT_MEDIA_TYPE_MAP: dict[str, str] = {
    SupportedFormat.CSV.value: "text/csv; charset=utf-8",
    SupportedFormat.TSV.value: "text/tab-separated-values; charset=utf-8",
    SupportedFormat.PSV.value: "text/plain; charset=utf-8",
    SupportedFormat.DELIMITED.value: "text/plain; charset=utf-8",
    SupportedFormat.XLSX.value: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    SupportedFormat.JSON.value: "application/json",
    SupportedFormat.JSONL.value: "application/x-ndjson",
    SupportedFormat.PARQUET.value: "application/vnd.apache.parquet",
}

_SUFFIX_TO_DELIM_FORMAT: dict[str, tuple[str, str]] = {
    ".csv": (SupportedFormat.CSV.value, ","),
    ".tsv": (SupportedFormat.TSV.value, "\t"),
    ".psv": (SupportedFormat.PSV.value, "|"),
}


_XLSX_ILLEGAL_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_XLSX_SHEET_INVALID_RE = re.compile(r"[:\\/?*\[\]]")


def _safe_xlsx_sheet_title(title: str | None) -> str:
    return _XLSX_SHEET_INVALID_RE.sub("_", (title or "").strip())[:31] or "Sheet1"


def _normalize_delimiter(raw_delim: str) -> str:
    norm = "\t" if raw_delim == "\\t" else raw_delim
    if len(norm) != 1 or norm in ("\r", "\n", "\x00"):
        raise ValueError(f"Delimiter must be a single printable character, got {raw_delim!r}.")
    return norm


@dataclass(slots=True)
class FileFormatSpec:
    """Format dialect & container metadata enabling exact round-trip file export."""

    format: str
    delimiter: str = ","
    has_bom: bool = False
    lineterminator: str = "\n"
    sheet_name: str | None = None
    json_wrapper_key: str | None = None
    source_extension: str | None = None
    json_envelope: dict[str, Any] | None = None
    encoding: str = "utf-8"

    def extension_for_export(self) -> str:
        """Return canonical filename suffix matching this format."""
        return self.source_extension or _FORMAT_EXTENSION_MAP.get(self.format, ".csv")

    def media_type(self) -> str:
        """Return HTTP Content-Type media type for this format."""
        return _FORMAT_MEDIA_TYPE_MAP.get(self.format, "application/octet-stream")

    def to_dict(self) -> dict[str, Any]:
        """Serialize format specification into a JSON-compatible dictionary."""
        return {
            "format": self.format,
            "delimiter": self.delimiter,
            "has_bom": self.has_bom,
            "lineterminator": self.lineterminator,
            "sheet_name": self.sheet_name,
            "json_wrapper_key": self.json_wrapper_key,
            "source_extension": self.source_extension,
            "json_envelope": dict(self.json_envelope) if self.json_envelope is not None else None,
            "encoding": self.encoding,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FileFormatSpec:
        """Reconstruct a FileFormatSpec from a dictionary."""
        raw_env = data.get("json_envelope")
        return cls(
            format=str(data.get("format", SupportedFormat.CSV.value)),
            delimiter=_normalize_delimiter(str(data.get("delimiter", ","))),
            has_bom=bool(data.get("has_bom", False)),
            lineterminator=str(data.get("lineterminator", "\n")),
            sheet_name=data.get("sheet_name"),
            json_wrapper_key=data.get("json_wrapper_key"),
            source_extension=data.get("source_extension"),
            json_envelope=dict(raw_env) if isinstance(raw_env, Mapping) else None,
            encoding=str(data.get("encoding") or "utf-8"),
        )


def _cell_to_json_scalar(value: Any) -> Any:
    """Convert cell values (None, NaN/Inf, binary, non-primitives) into RFC 8259 JSON-safe scalars."""
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return str(value)


def sanitize_row_for_json(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of row with all cell values converted to strict RFC 8259 JSON-safe scalars."""
    return {k: _cell_to_json_scalar(v) for k, v in row.items()}


def cell_to_input_text(value: Any) -> str:
    """Extract stripped string input for entity standardization, treating None/NaN/Inf as empty and integer floats cleanly."""
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        if abs(value) < 1e16 and value.is_integer():
            return str(int(value))
    return str(value).strip()


def _dedupe_columns(raw_headers: Sequence[Any]) -> list[str]:
    seen: dict[str, int] = {}
    cols: list[str] = []
    for idx, raw in enumerate(raw_headers):
        base = str(raw).strip() if raw is not None else ""
        if not base:
            base = f"col_{idx + 1}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        cols.append(base if count == 1 else f"{base}_{count}")
    return cols


_MAX_XLSX_UNPACKED_BYTES = 2 * 1024**3


def _open_xlsx_workbook(path: Path, *, read_only: bool) -> Any:
    ox = _ensure_openpyxl()
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        with zipfile.ZipFile(path) as zf:
            if sum(i.file_size for i in zf.infolist()) > _MAX_XLSX_UNPACKED_BYTES:
                raise ValueError("Invalid Excel (.xlsx) file: contents expand to more than 2 GiB.")
        return ox.load_workbook(path, read_only=read_only, data_only=read_only)
    except (zipfile.BadZipFile, InvalidFileException, OSError, KeyError, EOFError) as exc:
        raise ValueError(f"Invalid Excel (.xlsx) file: {exc}") from exc


def _open_parquet_file(path: Path) -> Any:
    pa = _ensure_pyarrow()
    import pyarrow.parquet as pq

    try:
        return pq.ParquetFile(path)
    except (pa.ArrowException, OSError) as exc:
        raise ValueError(f"Invalid Parquet file: {exc}") from exc


def _xlsx_sheet_names(path: Path) -> list[str]:
    wb = _open_xlsx_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _detect_text_dialect(path: Path) -> tuple[bool, str, str, str]:
    with path.open("rb") as fb:
        sample = fb.read(65536)
    has_bom = sample.startswith(b"\xef\xbb\xbf")
    lineterm = "\r\n" if b"\r\n" in sample else "\n"
    text_sample = sample[3:] if has_bom else sample
    try:
        decoded = text_sample.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        decoded = text_sample.decode("cp1252", errors="replace")
        encoding = "cp1252"
    first_line = decoded.splitlines()[0] if decoded else ""
    return has_bom, lineterm, encoding, first_line


def detect_file_format(
    path: str | Path,
    *,
    delimiter_override: str | None = None,
    sheet_name: str | None = None,
) -> FileFormatSpec:
    """Detect format, text dialect, sheet selection, or JSON container structure from a file."""
    p = Path(path)
    suffix = p.suffix.lower()
    src_ext = suffix or None

    if suffix == ".xlsx":
        sheets = _xlsx_sheet_names(p)
        chosen = sheet_name if (sheet_name and sheet_name in sheets) else (sheets[0] if sheets else "Sheet1")
        return FileFormatSpec(format=SupportedFormat.XLSX.value, sheet_name=chosen, source_extension=src_ext)

    if suffix == ".parquet":
        with _open_parquet_file(p):
            pass
        return FileFormatSpec(format=SupportedFormat.PARQUET.value, source_extension=src_ext)

    if suffix == ".json":
        try:
            payload = json.loads(p.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid JSON file: {exc}") from exc
        if isinstance(payload, list):
            if not all(isinstance(r, Mapping) for r in payload):
                raise ValueError("JSON file must contain an array of JSON objects.")
            return FileFormatSpec(format=SupportedFormat.JSON.value, source_extension=src_ext)
        if isinstance(payload, dict):
            wrapper_key = next((k for k, v in payload.items() if isinstance(v, list)), None)
            if wrapper_key is not None:
                if not all(isinstance(r, Mapping) for r in payload[wrapper_key]):
                    raise ValueError("JSON file must contain an array of JSON objects.")
                envelope = {k: v for k, v in payload.items() if k != wrapper_key}
                return FileFormatSpec(
                    format=SupportedFormat.JSON.value,
                    json_wrapper_key=wrapper_key,
                    source_extension=src_ext,
                    json_envelope=envelope or None,
                )
        raise ValueError("JSON file must be a list of objects or an object containing a list of records.")

    has_bom, lineterm, encoding, first_line = _detect_text_dialect(p)

    if suffix in (".jsonl", ".ndjson"):
        return FileFormatSpec(
            format=SupportedFormat.JSONL.value,
            has_bom=has_bom,
            lineterminator=lineterm,
            source_extension=src_ext,
            encoding=encoding,
        )

    if delimiter_override is not None and delimiter_override != "":
        delim = _normalize_delimiter(delimiter_override)
        fmt, _ = _SUFFIX_TO_DELIM_FORMAT.get(suffix, (SupportedFormat.DELIMITED.value, delim))
        return FileFormatSpec(
            format=fmt,
            delimiter=delim,
            has_bom=has_bom,
            lineterminator=lineterm,
            source_extension=src_ext,
            encoding=encoding,
        )

    if suffix in _SUFFIX_TO_DELIM_FORMAT:
        fmt, delim = _SUFFIX_TO_DELIM_FORMAT[suffix]
        if suffix == ".csv" and "," not in first_line:
            alt_delim = max((";", "\t", "|"), key=lambda d: first_line.count(d))
            if first_line.count(alt_delim) > 0:
                delim = alt_delim
        return FileFormatSpec(
            format=fmt,
            delimiter=delim,
            has_bom=has_bom,
            lineterminator=lineterm,
            source_extension=src_ext,
            encoding=encoding,
        )

    candidates = ("|", "\t", ",", ";")
    best_delim = max(candidates, key=lambda d: first_line.count(d))
    sniffed = best_delim if first_line.count(best_delim) > 0 else ","
    return FileFormatSpec(
        format=SupportedFormat.DELIMITED.value,
        delimiter=sniffed,
        has_bom=has_bom,
        lineterminator=lineterm,
        source_extension=src_ext,
        encoding=encoding,
    )


class _ClosableRowIter:
    """Row iterator wrapper guaranteeing deterministic resource cleanup even if never started."""

    __slots__ = ("_gen", "_close_cb", "_closed")

    def __init__(self, gen: Iterator[dict[str, Any]], close_cb: Any) -> None:
        self._gen = gen
        self._close_cb = close_cb
        self._closed = False

    def __iter__(self) -> _ClosableRowIter:
        return self

    def __next__(self) -> dict[str, Any]:
        try:
            return next(self._gen)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._gen.close()
            self._close_cb()


def _parse_jsonl_object(line: str) -> dict[str, Any]:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSONL line: {exc}") from exc
    if not isinstance(obj, Mapping):
        raise ValueError("JSONL lines must be JSON objects.")
    return dict(obj)


def _iter_delimited_rows(path: Path, spec: FileFormatSpec) -> tuple[list[str], Iterator[dict[str, Any]]]:
    encoding = "utf-8-sig" if spec.has_bom else spec.encoding
    fin = path.open("r", encoding=encoding, errors="replace", newline="")
    try:
        reader = csv.reader(fin, delimiter=spec.delimiter)
        raw_header = next(reader, None)
        columns = _dedupe_columns(raw_header) if raw_header is not None else []
    except BaseException:
        fin.close()
        raise

    def _gen() -> Iterator[dict[str, Any]]:
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            yield {col: (row[idx] if idx < len(row) else "") for idx, col in enumerate(columns)}

    return columns, _ClosableRowIter(_gen(), fin.close)


_JSONL_SCHEMA_PEEK_LINES = 100


def _iter_jsonl_rows(path: Path, spec: FileFormatSpec) -> tuple[list[str], Iterator[dict[str, Any]]]:
    encoding = "utf-8-sig" if spec.has_bom else spec.encoding
    fin = path.open("r", encoding=encoding, errors="replace")
    peeked: list[dict[str, Any]] = []
    try:
        for line in fin:
            stripped = line.strip()
            if stripped:
                peeked.append(_parse_jsonl_object(stripped))
                if len(peeked) >= _JSONL_SCHEMA_PEEK_LINES:
                    break
    except BaseException:
        fin.close()
        raise

    columns = list(dict.fromkeys(k for obj in peeked for k in obj.keys()))

    def _gen() -> Iterator[dict[str, Any]]:
        for obj in peeked:
            yield dict(obj)
        for line in fin:
            stripped = line.strip()
            if stripped:
                yield _parse_jsonl_object(stripped)

    return columns, _ClosableRowIter(_gen(), fin.close)


def _iter_json_rows(path: Path, spec: FileFormatSpec) -> tuple[list[str], Iterator[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    records: list[dict[str, Any]] = payload[spec.json_wrapper_key] if spec.json_wrapper_key else payload
    columns = list(dict.fromkeys(k for rec in records for k in rec.keys()))

    def _gen() -> Iterator[dict[str, Any]]:
        for rec in records:
            yield {col: rec.get(col, "") for col in columns}

    return columns, _gen()


def _iter_xlsx_rows(path: Path, spec: FileFormatSpec) -> tuple[list[str], Iterator[dict[str, Any]]]:
    wb = _open_xlsx_workbook(path, read_only=True)
    ws = wb[spec.sheet_name] if (spec.sheet_name and spec.sheet_name in wb.sheetnames) else wb.active
    row_iter = ws.iter_rows(values_only=True)
    header = next(row_iter, None)
    if header is None:
        wb.close()
        return [], iter(())
    columns = _dedupe_columns(list(header))

    def _gen() -> Iterator[dict[str, Any]]:
        for values in row_iter:
            if not any(
                v is not None and (not isinstance(v, str) or v.strip() != "")
                for v in values[: len(columns)]
            ):
                continue
            yield {
                col: ("" if (idx >= len(values) or values[idx] is None) else values[idx])
                for idx, col in enumerate(columns)
            }

    return columns, _ClosableRowIter(_gen(), wb.close)


def _iter_parquet_rows(path: Path) -> tuple[list[str], Iterator[dict[str, Any]]]:
    pf = _open_parquet_file(path)
    columns = list(pf.schema_arrow.names)

    def _gen() -> Iterator[dict[str, Any]]:
        for batch in pf.iter_batches(batch_size=4096):
            for rec in batch.to_pylist():
                yield rec

    return columns, _ClosableRowIter(_gen(), pf.close)


def iter_tabular_rows(
    path: str | Path,
    spec: FileFormatSpec,
) -> tuple[list[str], Iterator[dict[str, Any]]]:
    """Stream column headers and row dictionaries from any supported file format."""
    p = Path(path)
    fmt = spec.format
    if fmt == SupportedFormat.XLSX.value:
        return _iter_xlsx_rows(p, spec)
    if fmt == SupportedFormat.JSON.value:
        return _iter_json_rows(p, spec)
    if fmt == SupportedFormat.JSONL.value:
        return _iter_jsonl_rows(p, spec)
    if fmt == SupportedFormat.PARQUET.value:
        return _iter_parquet_rows(p)
    return _iter_delimited_rows(p, spec)


def inspect_tabular_source(
    path: str | Path,
    *,
    sample_limit: int = 25,
    delimiter_override: str | None = None,
    sheet_name: str | None = None,
    count_threshold_bytes: int = 10 * 1024 * 1024,
) -> dict[str, Any]:
    """Inspect a file source's format dialect, column schema, worksheets, and preview rows."""
    p = Path(path)
    spec = detect_file_format(p, delimiter_override=delimiter_override, sheet_name=sheet_name)
    file_size = p.stat().st_size
    sheet_names = _xlsx_sheet_names(p) if spec.format == SupportedFormat.XLSX.value else []

    columns, row_iter = iter_tabular_rows(p, spec)
    sample_rows: list[dict[str, Any]] = []
    try:
        for row in row_iter:
            sample_rows.append(sanitize_row_for_json(row))
            if len(sample_rows) >= sample_limit:
                break

        total_rows: int | None
        if spec.format == SupportedFormat.PARQUET.value:
            with _open_parquet_file(p) as pf:
                total_rows = pf.metadata.num_rows
        elif file_size <= count_threshold_bytes:
            total_rows = len(sample_rows) + sum(1 for _ in row_iter)
        else:
            total_rows = None
    finally:
        close_row_iter(row_iter)

    return {
        "file_name": p.name,
        "file_size_bytes": file_size,
        "format_spec": spec.to_dict(),
        "sheet_names": sheet_names,
        "columns": columns,
        "sample_rows": sample_rows,
        "total_rows": total_rows,
    }


def close_row_iter(row_iter: Any) -> None:
    """Close an iterator returned by iter_tabular_rows if it exposes a close method."""
    close_fn = getattr(row_iter, "close", None)
    if callable(close_fn):
        close_fn()


def _cell_for_flat_export(row: Mapping[str, Any], col: str) -> Any:
    val = row.get(col)
    if val is None or (isinstance(val, float) and not math.isfinite(val)):
        return ""
    return val


def _cell_for_xlsx(row: Mapping[str, Any], col: str) -> Any:
    val = row.get(col)
    if val is None or (isinstance(val, float) and not math.isfinite(val)):
        return ""
    if isinstance(val, str):
        return _XLSX_ILLEGAL_CTRL_RE.sub("", val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        return bytes(val).hex()
    return val


def _text_not_formula(ws: Any, val: Any) -> Any:
    """openpyxl stores any string starting with '=' as a live formula; keep source text as text."""
    if isinstance(val, str) and val.startswith("="):
        from openpyxl.cell import WriteOnlyCell

        cell = WriteOnlyCell(ws, value=val)
        cell.data_type = "s"
        return cell
    return val


def _json_export_value(value: Any) -> Any:
    return None if (isinstance(value, float) and not math.isfinite(value)) else value


def _atomic_temp_path(out: Path) -> Path:
    return out.with_name(f".{out.name}.{uuid.uuid4().hex[:8]}.tmp")


def _write_xlsx_output(
    tmp_path: Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    spec: FileFormatSpec,
    template_xlsx_path: str | Path | None,
) -> int:
    col_list = list(columns)
    row_vals = [[_cell_for_xlsx(row, c) for c in col_list] for row in rows]
    if template_xlsx_path is not None and Path(template_xlsx_path).is_file():
        wb = _open_xlsx_workbook(Path(template_xlsx_path), read_only=False)
        try:
            target_name = spec.sheet_name if (spec.sheet_name and spec.sheet_name in wb.sheetnames) else wb.active.title
            ws = wb[target_name]
            for merged_range in list(ws.merged_cells.ranges):
                ws.unmerge_cells(str(merged_range))
            ws.delete_rows(1, max(ws.max_row, 1))
            ws.append(col_list)
            for vals in row_vals:
                ws.append([_text_not_formula(ws, v) for v in vals])
            wb.save(tmp_path)
            return len(row_vals)
        finally:
            wb.close()

    wb = _ensure_openpyxl().Workbook(write_only=True)
    try:
        ws = wb.create_sheet(title=_safe_xlsx_sheet_title(spec.sheet_name))
        ws.append(col_list)
        for vals in row_vals:
            ws.append([_text_not_formula(ws, v) for v in vals])
        wb.save(tmp_path)
        return len(row_vals)
    finally:
        wb.close()


def _write_parquet_output(
    tmp_path: Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    source_parquet_path: str | Path | None,
) -> int:
    pa = _ensure_pyarrow()
    import pyarrow.parquet as pq

    col_list = list(columns)
    orig_schema = None
    if source_parquet_path is not None and Path(source_parquet_path).is_file():
        with _open_parquet_file(Path(source_parquet_path)) as pf:
            orig_schema = pf.schema_arrow
    rows_list = [{c: row.get(c) for c in col_list} for row in rows]

    arrays: list[Any] = []
    fields: list[Any] = []
    for col in col_list:
        cleaned = [None if v == "" else v for v in (r[col] for r in rows_list)]
        orig_type = (
            orig_schema.field(col).type
            if (orig_schema is not None and col in orig_schema.names)
            else None
        )
        if not rows_list:
            arr = pa.array([], type=orig_type or pa.string())
        else:
            try:
                arr = pa.array(cleaned, type=orig_type) if orig_type is not None else pa.array(cleaned)
            except (pa.ArrowInvalid, pa.ArrowTypeError, TypeError, ValueError):
                arr = pa.array([None if v is None else str(v) for v in cleaned], type=pa.string())
        arrays.append(arr)
        fields.append(pa.field(col, arr.type))

    table = pa.Table.from_arrays(arrays, schema=pa.schema(fields))
    pq.write_table(table, tmp_path)
    return len(rows_list)


def write_tabular_output(
    output_path: str | Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    spec: FileFormatSpec,
    *,
    template_xlsx_path: str | Path | None = None,
    source_parquet_path: str | Path | None = None,
) -> int:
    """Write rows atomically to output_path preserving the exact format specified by FileFormatSpec."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = _atomic_temp_path(out)
    col_list = list(columns)
    fmt = spec.format
    write_enc = "utf-8-sig" if spec.has_bom else spec.encoding

    try:
        if fmt == SupportedFormat.XLSX.value:
            count = _write_xlsx_output(tmp_out, col_list, rows, spec, template_xlsx_path)
        elif fmt == SupportedFormat.PARQUET.value:
            count = _write_parquet_output(tmp_out, col_list, rows, source_parquet_path)
        elif fmt == SupportedFormat.JSON.value:
            out_rows = [{c: (_json_export_value(row[c]) if c in row else "") for c in col_list} for row in rows]
            payload: Any = (
                {**(spec.json_envelope or {}), spec.json_wrapper_key: out_rows}
                if spec.json_wrapper_key
                else out_rows
            )
            tmp_out.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")
            count = len(out_rows)
        elif fmt == SupportedFormat.JSONL.value:
            count = 0
            col_set = set(col_list)
            with tmp_out.open("w", encoding=write_enc, errors="replace", newline="") as fout:
                for row in rows:
                    rec = {
                        **{c: (_json_export_value(row[c]) if c in row else "") for c in col_list},
                        **{k: _json_export_value(v) for k, v in row.items() if k not in col_set},
                    }
                    fout.write(json.dumps(rec, default=str, allow_nan=False) + spec.lineterminator)
                    count += 1
        else:
            count = 0
            with tmp_out.open("w", encoding=write_enc, errors="replace", newline="") as fout:
                writer = csv.DictWriter(
                    fout,
                    fieldnames=col_list,
                    delimiter=spec.delimiter,
                    lineterminator=spec.lineterminator,
                    extrasaction="ignore",
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow({c: _cell_for_flat_export(row, c) for c in col_list})
                    count += 1
        os.replace(tmp_out, out)
        return count
    except BaseException:
        tmp_out.unlink(missing_ok=True)
        raise


def write_xlsx_sheets(
    output_path: str | Path,
    sheets: Mapping[str, tuple[Sequence[str], Iterable[Mapping[str, Any]]]],
) -> None:
    """Atomically write a multi-sheet Excel workbook from named (columns, rows) tuples."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = _atomic_temp_path(out)
    try:
        materialized = [
            (
                _safe_xlsx_sheet_title(title),
                col_list,
                [[_cell_for_xlsx(row, c) for c in col_list] for row in row_iter],
            )
            for title, (cols, row_iter) in sheets.items()
            for col_list in (list(cols),)
        ]
        wb = _ensure_openpyxl().Workbook(write_only=True)
        try:
            for title, col_list, row_vals in materialized:
                ws = wb.create_sheet(title=title)
                ws.append(col_list)
                for vals in row_vals:
                    ws.append([_text_not_formula(ws, v) for v in vals])
            wb.save(tmp_out)
        finally:
            wb.close()
        os.replace(tmp_out, out)
    except BaseException:
        tmp_out.unlink(missing_ok=True)
        raise
