"""GeoNames postal-code reference data: downloader, SQLite index builder and provider.

Data: https://download.geonames.org/export/zip/ (``<ISO2>.zip`` per country, ``allCountries.zip``), licensed
Creative Commons Attribution 4.0 (CC BY 4.0). Anything you publish that uses this data must credit GeoNames; the
index carries the attribution text in its metadata (see :data:`ATTRIBUTION`).

Tab-separated columns: country code, postal code, place name, admin name1, admin code1, admin name2, admin code2,
admin name3, admin code3, latitude, longitude, accuracy.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import urllib.request
import zipfile
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Union

from address_standardizer.reference._match import fold_name
from address_standardizer.reference.base import ReferencePlace

__all__ = [
    "ATTRIBUTION",
    "LICENSE",
    "SOURCE",
    "GEONAMES_BASE_URL",
    "GeoNamesPostalProvider",
    "build_geonames_index",
    "download_geonames",
    "postal_candidates",
]

GEONAMES_BASE_URL = "https://download.geonames.org/export/zip/"
SOURCE = "GeoNames postal codes (https://download.geonames.org/export/zip/)"
LICENSE = "CC-BY-4.0"
ATTRIBUTION = (
    "Postal code data from GeoNames (https://www.geonames.org), licensed under the Creative Commons "
    "Attribution 4.0 License (https://creativecommons.org/licenses/by/4.0/)."
)
USER_AGENT = "address-standardizer (+https://github.com/HobbyHabbit/Address-Standardizer)"
SCHEMA_VERSION = "1"
DEFAULT_DOWNLOAD_DIR = Path("data") / "geonames"

_BATCH = 20000
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE places (
    country TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    place_name TEXT NOT NULL,
    place_key TEXT NOT NULL,
    admin1 TEXT NOT NULL,
    admin1_code TEXT NOT NULL,
    admin2 TEXT NOT NULL,
    admin2_code TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    accuracy INTEGER,
    UNIQUE (country, postal_code, place_name, admin1_code, admin2_code)
);
CREATE INDEX ix_places_postal ON places (country, postal_code);
CREATE INDEX ix_places_place ON places (country, place_key);
"""

PathLike = Union[str, "os.PathLike[str]"]


def postal_candidates(country: str, postal_code: str) -> List[str]:
    """Spellings of ``postal_code`` to try, most specific first.

    GeoNames stores some countries at a coarser level than a full postal code (Canada: the 3-character FSA; Great
    Britain and Ireland: the outward code / routing key; Netherlands: the 4 digits), and US ZIP+4 is stored as the
    5-digit ZIP, so a full code is retried at each coarser spelling.
    """
    raw = " ".join(str(postal_code).upper().split())
    compact = raw.replace(" ", "")
    out: List[str] = []

    def add(value: str) -> None:
        if value and value not in out:
            out.append(value)

    add(raw)
    add(compact)
    add(raw.split(" ")[0])
    add(raw.split("-")[0])
    if country == "CA":
        add(compact[:3])
    elif country == "NL":
        add(compact[:4])
    elif country == "GB":
        add(compact[:-3])
    return out


def download_geonames(
    countries: Iterable[str],
    dest_dir: PathLike = DEFAULT_DOWNLOAD_DIR,
    *,
    timeout: float = 60.0,
    urlopen: Optional[Callable[..., Any]] = None,
) -> List[Path]:
    """Download GeoNames postal-code zips into ``dest_dir`` and return their paths.

    ``countries`` holds ISO alpha-2 codes, or ``"ALL"`` for the (large) ``allCountries.zip``. Network access happens
    only here; ``urlopen`` (default :func:`urllib.request.urlopen`) is injectable so tests never touch the network.
    """
    names: List[str] = []
    for code in countries:
        up = str(code).strip().upper()
        if up == "ALL":
            names.append("allCountries")
        elif _COUNTRY_CODE.match(up):
            names.append(up)
        else:
            raise ValueError(f"invalid country code {code!r}: use ISO alpha-2 (e.g. US) or ALL")
    if not names:
        raise ValueError("no countries given")
    opener = urlopen or urllib.request.urlopen
    out_dir = Path(dest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for name in names:
        request = urllib.request.Request(f"{GEONAMES_BASE_URL}{name}.zip", headers={"User-Agent": USER_AGENT})
        target = out_dir / f"{name}.zip"
        tmp = out_dir / f"{name}.zip.part"
        with opener(request, timeout=timeout) as response, open(tmp, "wb") as fh:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, target)
        paths.append(target)
    return paths


def _source_files(source: Union[PathLike, Iterable[PathLike], None]) -> List[Path]:
    if source is None:
        source = DEFAULT_DOWNLOAD_DIR
    if isinstance(source, (str, os.PathLike)):
        p = Path(source)
        if p.is_dir():
            files = sorted(
                f for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in (".zip", ".txt") and not f.name.lower().startswith("readme")
            )
        else:
            files = [p]
    else:
        files = [Path(f) for f in source]
    if not files:
        raise FileNotFoundError(f"no GeoNames .zip/.txt files found in {source}")
    for f in files:
        if not f.is_file():
            raise FileNotFoundError(f"GeoNames file not found: {f}")
    return files


def _data_lines(path: Path) -> Iterator[str]:
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as zf:
                for entry in sorted(zf.namelist()):
                    base = entry.rsplit("/", 1)[-1].lower()
                    if not base.endswith(".txt") or base.startswith("readme"):
                        continue
                    with zf.open(entry) as raw:
                        yield from TextIOWrapper(raw, encoding="utf-8", newline="")
        except zipfile.BadZipFile as exc:
            raise ValueError(f"{path}: not a valid zip file") from exc
    else:
        with open(path, encoding="utf-8", newline="") as fh:
            yield from fh


def _to_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def _to_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return None


def _rows(files: Sequence[Path], wanted: Optional[frozenset], stats: Dict[str, int]) -> Iterator[tuple]:
    for path in files:
        for line in _data_lines(path):
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 11:
                stats["skipped"] += 1
                continue
            parts += [""] * (12 - len(parts))
            country = parts[0].strip().upper()
            postal = " ".join(parts[1].upper().split())
            place = parts[2].strip()
            if not country or not postal or not place:
                stats["skipped"] += 1
                continue
            if wanted is not None and country not in wanted:
                continue
            yield (
                country, postal, place, fold_name(place), parts[3].strip(), parts[4].strip().upper(),
                parts[5].strip(), parts[6].strip().upper(), _to_float(parts[9]), _to_float(parts[10]),
                _to_int(parts[11]),
            )


def build_geonames_index(
    db_path: PathLike,
    countries: Optional[Iterable[str]] = None,
    source: Union[PathLike, Iterable[PathLike], None] = None,
    *,
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the SQLite index that :class:`GeoNamesPostalProvider` reads, and return a summary dict.

    ``source`` is a directory of downloaded ``.zip`` / ``.txt`` files, one file, or an iterable of files (default
    ``data/geonames``). ``countries`` optionally restricts the index to those ISO alpha-2 codes (useful with
    ``allCountries.zip``). ``as_of`` labels the data vintage and defaults to today's date (the build date: GeoNames
    refreshes its dumps regularly). The index is written to a temporary file and moved into place, so an existing
    index is never left half-written.
    """
    wanted = frozenset(str(c).strip().upper() for c in countries) if countries else None
    files = _source_files(source)
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    stats = {"skipped": 0}
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(_SCHEMA)
        batch: List[tuple] = []
        insert = "INSERT OR IGNORE INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        for row in _rows(files, wanted, stats):
            batch.append(row)
            if len(batch) >= _BATCH:
                conn.executemany(insert, batch)
                batch.clear()
        conn.executemany(insert, batch)
        row_count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        built = sorted(r[0] for r in conn.execute("SELECT DISTINCT country FROM places"))
        meta = {
            "schema_version": SCHEMA_VERSION,
            "source": SOURCE,
            "license": LICENSE,
            "attribution": ATTRIBUTION,
            "as_of": as_of or datetime.now(timezone.utc).date().isoformat(),
            "built_from": ", ".join(f.name for f in files),
            "row_count": str(row_count),
            "countries": ",".join(built),
        }
        conn.executemany("INSERT INTO meta VALUES (?, ?)", list(meta.items()))
        conn.commit()
    except BaseException:
        conn.close()
        tmp.unlink()
        raise
    conn.close()
    os.replace(tmp, target)
    return {"db_path": str(target), "rows": row_count, "countries": built, "skipped": stats["skipped"],
            "as_of": meta["as_of"]}


_PLACE_COLUMNS = "country, postal_code, place_name, admin1, admin1_code, admin2, latitude, longitude"


class GeoNamesPostalProvider:
    """:class:`~address_standardizer.reference.base.ReferenceProvider` backed by a local GeoNames SQLite index.

    The index is opened read-only and queries are serialized with a lock, so one instance can be shared between
    threads (e.g. the REST server).
    """

    name = "geonames-postal"

    def __init__(self, db_path: PathLike) -> None:
        path = Path(db_path)
        if not path.is_file():
            raise FileNotFoundError(f"reference database not found: {path}")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
        meta: Dict[str, str] = {}
        countries: List[str] = []
        try:
            meta = dict(self._conn.execute("SELECT key, value FROM meta").fetchall())
            countries = [r[0] for r in self._conn.execute("SELECT DISTINCT country FROM places")]
        except sqlite3.Error:
            meta = {}
        if meta.get("schema_version") != SCHEMA_VERSION:
            self._conn.close()
            raise ValueError(f"{path} is not a GeoNames postal index built by this version of address-standardizer")
        self._countries = frozenset(countries)
        self.path = path
        self.source = meta.get("source", SOURCE)
        self.license = meta.get("license", LICENSE)
        self.as_of = meta.get("as_of", "")
        self.attribution = meta.get("attribution", ATTRIBUTION)
        self._row_count = int(meta.get("row_count", "0"))

    def covers_country(self, country: str) -> bool:
        return str(country).upper() in self._countries

    def lookup_postal(self, country: str, postal_code: str) -> List[ReferencePlace]:
        code = str(country).upper()
        for candidate in postal_candidates(code, postal_code):
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT {_PLACE_COLUMNS} FROM places WHERE country = ? AND postal_code = ? "
                    "ORDER BY place_name, admin2",
                    (code, candidate),
                ).fetchall()
            if rows:
                return [ReferencePlace(*row, provider=self.name) for row in rows]
        return []

    def lookup_place(self, country: str, place_name: str, admin1_code: Optional[str] = None) -> List[str]:
        sql = "SELECT DISTINCT postal_code FROM places WHERE country = ? AND place_key = ?"
        params: List[Any] = [str(country).upper(), fold_name(place_name)]
        if admin1_code:
            sql += " AND admin1_code = ?"
            params.append(admin1_code.upper())
        with self._lock:
            return [r[0] for r in self._conn.execute(sql + " ORDER BY postal_code LIMIT 1000", params)]

    def info(self) -> Dict[str, Any]:
        """Provider metadata, including the attribution that must accompany published results."""
        return {
            "name": self.name,
            "source": self.source,
            "license": self.license,
            "as_of": self.as_of,
            "attribution": self.attribution,
            "countries": sorted(self._countries),
            "rows": self._row_count,
        }

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "GeoNamesPostalProvider":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
