"""
Offline Rooftop Reference Index & Coordinate Resolver.
======================================================
Embedded SQLite reference database capable of resolving rooftop / point-level
coordinates and parcel validation without external network calls, featuring
thread-safe zero-downtime atomic hot-swapping.
"""

import copy
import dataclasses
import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from entity_standardizer.address.offline_seed_data import SEED_ROOFTOP_RECORDS, SEED_STREET_RANGES  # noqa: F401


@dataclass
class RooftopRecord:
    """Rooftop / point-level reference delivery point."""
    address_key: str
    building_key: str
    street1: str
    street2: str
    city: str
    state: str
    postal_code: str
    country: str
    latitude: float
    longitude: float
    precision: str = "ROOFTOP"
    accuracy_radius_meters: float = 5.0
    parcel_id: Optional[str] = None
    is_multi_unit: bool = False
    known_units: List[str] = field(default_factory=list)
    rdi: str = "Unknown"
    is_cmra: bool = False
    is_vacant: bool = False
    census_tract: Optional[str] = None
    fips_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "address_key": self.address_key,
            "building_key": self.building_key,
            "street1": self.street1,
            "street2": self.street2,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "precision": self.precision,
            "accuracy_radius_meters": self.accuracy_radius_meters,
            "parcel_id": self.parcel_id,
            "is_multi_unit": self.is_multi_unit,
            "known_units": list(self.known_units),
            "rdi": self.rdi,
            "is_cmra": self.is_cmra,
            "is_vacant": self.is_vacant,
            "census_tract": self.census_tract,
            "fips_code": self.fips_code,
            "metadata": dict(self.metadata),
        }


@dataclass
class ParcelValidationResult:
    """Offline parcel verification outcome."""
    is_valid_parcel: bool
    parcel_id: Optional[str] = None
    is_multi_unit: bool = False
    matched_rooftop: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_radius_meters: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "is_valid_parcel": self.is_valid_parcel,
            "parcel_id": self.parcel_id,
            "is_multi_unit": self.is_multi_unit,
            "matched_rooftop": self.matched_rooftop,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_radius_meters": self.accuracy_radius_meters,
        }


def _street_names_match(range_name: str, wanted: str) -> bool:
    """Equal names, or names that differ only by whole trailing words ("MAIN" vs "MAIN ST"); never a bare prefix."""
    if range_name == wanted:
        return True
    return range_name.startswith(wanted + " ") or wanted.startswith(range_name + " ")


class OfflineReferenceIndex:
    """
    Embedded SQLite reference index supporting rooftop coordinates resolution,
    parcel validation, linear street edge interpolation, and zero-downtime hot-swapping.
    """

    def __init__(self, db_path: Optional[str] = None, seed: bool = True):
        self._db_path = db_path or ":memory:"
        self._seed = seed
        self._pid = os.getpid()
        self._lock = threading.RLock()
        self._resolve_cache: Dict[Tuple[Any, ...], Optional[RooftopRecord]] = {}
        self._resolve_token: Optional[Tuple[int, int, int]] = None
        self._real_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._real_conn.row_factory = sqlite3.Row
        self._init_schema(self._real_conn)

        if seed and self.count() == 0:
            self.insert_records(SEED_ROOFTOP_RECORDS)
        if seed and self.count_ranges() == 0:
            self.insert_street_ranges(SEED_STREET_RANGES)

    @property
    def _conn(self) -> sqlite3.Connection:
        current_pid = os.getpid()
        if current_pid != self._pid:
            with self._lock:
                if current_pid != self._pid:
                    self._pid = current_pid
                    self._real_conn = sqlite3.connect(self._db_path, check_same_thread=False)
                    self._real_conn.row_factory = sqlite3.Row
                    self._init_schema(self._real_conn)
                    if self._seed and self.count() == 0:
                        self.insert_records(SEED_ROOFTOP_RECORDS)
                    if self._seed and self.count_ranges() == 0:
                        self.insert_street_ranges(SEED_STREET_RANGES)
        return self._real_conn

    @_conn.setter
    def _conn(self, val: Optional[sqlite3.Connection]):
        self._real_conn = val
        self._resolve_cache.clear()

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def _init_schema(self, conn: sqlite3.Connection):
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rooftop_reference (
                    address_key TEXT PRIMARY KEY,
                    building_key TEXT NOT NULL,
                    street1 TEXT NOT NULL,
                    street2 TEXT,
                    city TEXT NOT NULL,
                    state TEXT NOT NULL,
                    postal_code TEXT NOT NULL,
                    country TEXT NOT NULL DEFAULT 'USA',
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    precision TEXT NOT NULL DEFAULT 'ROOFTOP',
                    accuracy_radius_meters REAL NOT NULL DEFAULT 5.0,
                    parcel_id TEXT,
                    is_multi_unit INTEGER NOT NULL DEFAULT 0,
                    known_units TEXT,
                    rdi TEXT DEFAULT 'Unknown',
                    is_cmra INTEGER NOT NULL DEFAULT 0,
                    is_vacant INTEGER NOT NULL DEFAULT 0,
                    census_tract TEXT,
                    fips_code TEXT,
                    metadata_json TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rooftop_building ON rooftop_reference(building_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rooftop_zip_st ON rooftop_reference(postal_code, street1);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rooftop_parcel ON rooftop_reference(parcel_id);")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS street_ranges (
                    range_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    street_name TEXT NOT NULL,
                    postal_code TEXT NOT NULL,
                    state TEXT NOT NULL,
                    from_number INTEGER NOT NULL,
                    to_number INTEGER NOT NULL,
                    start_latitude REAL NOT NULL,
                    start_longitude REAL NOT NULL,
                    end_latitude REAL NOT NULL,
                    end_longitude REAL NOT NULL,
                    census_tract TEXT,
                    fips_code TEXT,
                    parity TEXT NOT NULL DEFAULT 'B'
                );
            """)
            existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(street_ranges)").fetchall()}
            if "parity" not in existing_cols:  # databases created before parity support
                conn.execute("ALTER TABLE street_ranges ADD COLUMN parity TEXT NOT NULL DEFAULT 'B'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ranges_zip_st ON street_ranges(postal_code, street_name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ranges_state_st ON street_ranges(state, street_name);")

            if self._db_path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")

    def insert_record(
        self,
        address_key: str,
        building_key: str,
        street1: str,
        city: str,
        state: str,
        postal_code: str,
        latitude: float,
        longitude: float,
        street2: str = "",
        country: str = "USA",
        precision: str = "ROOFTOP",
        accuracy_radius_meters: float = 5.0,
        parcel_id: Optional[str] = None,
        is_multi_unit: bool = False,
        known_units: Optional[List[str]] = None,
        rdi: str = "Unknown",
        is_cmra: bool = False,
        is_vacant: bool = False,
        census_tract: Optional[str] = None,
        fips_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Inserts or replaces a rooftop reference record."""
        with self._lock:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO rooftop_reference (
                        address_key, building_key, street1, street2, city, state, postal_code,
                        country, latitude, longitude, precision, accuracy_radius_meters,
                        parcel_id, is_multi_unit, known_units, rdi, is_cmra, is_vacant,
                        census_tract, fips_code, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        address_key.strip().upper(),
                        building_key.strip().upper(),
                        street1.strip().upper(),
                        street2.strip().upper(),
                        city.strip().upper(),
                        state.strip().upper(),
                        postal_code.strip(),
                        country.strip().upper(),
                        latitude,
                        longitude,
                        precision,
                        accuracy_radius_meters,
                        parcel_id,
                        1 if is_multi_unit else 0,
                        json.dumps(known_units or []),
                        rdi,
                        1 if is_cmra else 0,
                        1 if is_vacant else 0,
                        census_tract,
                        fips_code,
                        json.dumps(metadata or {}),
                    ),
                )

    def insert_records(self, records: List[Dict[str, Any]]):
        """Batch insert rooftop reference records."""
        if not records:
            return
        tuples = []
        for rec in records:
            tuples.append((
                rec["address_key"].strip().upper(),
                rec.get("building_key", "").strip().upper(),
                rec.get("street1", "").strip().upper(),
                rec.get("street2", "").strip().upper(),
                rec.get("city", "").strip().upper(),
                rec.get("state", "").strip().upper(),
                rec.get("postal_code", "").strip(),
                rec.get("country", "USA").strip().upper(),
                float(rec["latitude"]),
                float(rec["longitude"]),
                rec.get("precision", "ROOFTOP"),
                float(rec.get("accuracy_radius_meters", 5.0)),
                rec.get("parcel_id"),
                1 if rec.get("is_multi_unit", False) else 0,
                json.dumps(rec.get("known_units") or []),
                rec.get("rdi", "Unknown"),
                1 if rec.get("is_cmra", False) else 0,
                1 if rec.get("is_vacant", False) else 0,
                rec.get("census_tract"),
                rec.get("fips_code"),
                json.dumps(rec.get("metadata") or {}),
            ))
        with self._lock:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO rooftop_reference (
                        address_key, building_key, street1, street2, city, state, postal_code,
                        country, latitude, longitude, precision, accuracy_radius_meters,
                        parcel_id, is_multi_unit, known_units, rdi, is_cmra, is_vacant,
                        census_tract, fips_code, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuples,
                )

    def insert_street_range(
        self,
        street_name: str,
        postal_code: str,
        state: str,
        from_number: int,
        to_number: int,
        start_latitude: float,
        start_longitude: float,
        end_latitude: float,
        end_longitude: float,
        census_tract: Optional[str] = None,
        fips_code: Optional[str] = None,
        parity: str = "B",
    ):
        """Inserts a street edge range for linear interpolation (Census TIGER style).

        ``parity`` is "O" (odd house numbers only), "E" (even only) or "B" (both sides, the default).
        """
        parity = parity.strip().upper()
        if parity not in ("O", "E", "B"):
            raise ValueError("parity must be 'O', 'E' or 'B'")
        with self._lock:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO street_ranges (
                        street_name, postal_code, state, from_number, to_number,
                        start_latitude, start_longitude, end_latitude, end_longitude,
                        census_tract, fips_code, parity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        street_name.strip().upper(),
                        postal_code.strip(),
                        state.strip().upper(),
                        int(from_number),
                        int(to_number),
                        float(start_latitude),
                        float(start_longitude),
                        float(end_latitude),
                        float(end_longitude),
                        census_tract,
                        fips_code,
                        parity,
                    ),
                )

    def insert_street_ranges(self, ranges: List[Dict[str, Any]]):
        """Batch insert street edge ranges."""
        if not ranges:
            return
        tuples = []
        for r in ranges:
            parity = r.get("parity", "B").strip().upper()
            if parity not in ("O", "E", "B"):
                raise ValueError("parity must be 'O', 'E' or 'B'")
            tuples.append((
                r["street_name"].strip().upper(),
                r["postal_code"].strip(),
                r["state"].strip().upper(),
                int(r["from_number"]),
                int(r["to_number"]),
                float(r["start_latitude"]),
                float(r["start_longitude"]),
                float(r["end_latitude"]),
                float(r["end_longitude"]),
                r.get("census_tract"),
                r.get("fips_code"),
                parity,
            ))
        with self._lock:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    """
                    INSERT INTO street_ranges (
                        street_name, postal_code, state, from_number, to_number,
                        start_latitude, start_longitude, end_latitude, end_longitude,
                        census_tract, fips_code, parity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuples,
                )

    def count_ranges(self) -> int:
        """Returns total records in the street_ranges table."""
        with self._lock:
            cur = self._get_conn().execute("SELECT count(*) FROM street_ranges")
            row = cur.fetchone()
            return row[0] if row else 0

    def interpolate_street_range(
        self,
        street_number: int,
        street_name: str,
        postal_code: str = "",
        state: str = "",
    ) -> Optional[RooftopRecord]:
        """
        Linearly interpolates coordinates along street edge segments (US Census TIGER style).
        Zero external API calls.
        """
        clean_st = street_name.strip().upper()
        zip5 = postal_code[:5] if postal_code else ""
        norm_st = state.strip().upper()

        with self._lock:
            # Candidate ranges are narrowed by ZIP5 (or state) and side-of-street parity in SQL; the street name is
            # compared in Python so user text can never act as a LIKE wildcard ('%', '_').
            query = """
                SELECT * FROM street_ranges
                WHERE (parity = 'B' OR (parity = 'O' AND ? % 2 = 1) OR (parity = 'E' AND ? % 2 = 0))
            """
            params: List[Any] = [street_number, street_number]
            if len(zip5) == 5 and zip5.isdigit():
                query += " AND substr(postal_code, 1, 5) = ?"
                params.append(zip5)
            elif norm_st:
                query += " AND state = ?"
                params.append(norm_st)
            elif zip5:
                return None  # a partial/garbled ZIP and no state: refuse to guess
            query += " ORDER BY CASE parity WHEN 'B' THEN 1 ELSE 0 END, range_id"

            cur = self._get_conn().execute(query, tuple(params))
            rows = [r for r in cur.fetchall() if _street_names_match(r["street_name"], clean_st)]
            for row in rows:
                from_num = int(row["from_number"])
                to_num = int(row["to_number"])
                min_n = min(from_num, to_num)
                max_n = max(from_num, to_num)
                if min_n <= street_number <= max_n:
                    if max_n == min_n:
                        t = 0.5
                    else:
                        t = (street_number - from_num) / (to_num - from_num)
                        t = max(0.0, min(1.0, t))

                    start_lat = float(row["start_latitude"])
                    end_lat = float(row["end_latitude"])
                    start_lon = float(row["start_longitude"])
                    end_lon = float(row["end_longitude"])

                    lat = start_lat + t * (end_lat - start_lat)
                    lon = start_lon + t * (end_lon - start_lon)

                    c_tract = row["census_tract"]
                    f_code = row["fips_code"]
                    r_post = row["postal_code"]
                    r_st = row["state"]

                    return RooftopRecord(
                        address_key=f"{street_number} {clean_st}||{r_st}|{r_post}|USA",
                        building_key=f"{street_number} {clean_st}||{r_st}|{r_post}|USA",
                        street1=f"{street_number} {clean_st}",
                        street2="",
                        city="",
                        state=r_st,
                        postal_code=r_post,
                        country="USA",
                        latitude=round(lat, 6),
                        longitude=round(lon, 6),
                        precision="RANGE_INTERPOLATED",
                        accuracy_radius_meters=15.0,
                        census_tract=c_tract,
                        fips_code=f_code,
                    )
        return None

    def _row_to_record(self, row: sqlite3.Row) -> RooftopRecord:
        known_u = []
        if row["known_units"]:
            try:
                known_u = json.loads(row["known_units"])
            except Exception:
                known_u = []

        meta = {}
        if row["metadata_json"]:
            try:
                meta = json.loads(row["metadata_json"])
            except Exception:
                meta = {}

        c_tract = row["census_tract"] if "census_tract" in row.keys() else None
        f_code = row["fips_code"] if "fips_code" in row.keys() else None
        if not c_tract and meta.get("census_tract"):
            c_tract = str(meta["census_tract"])
        if not f_code and meta.get("fips_code"):
            f_code = str(meta["fips_code"])

        return RooftopRecord(
            address_key=row["address_key"],
            building_key=row["building_key"],
            street1=row["street1"],
            street2=row["street2"] or "",
            city=row["city"],
            state=row["state"],
            postal_code=row["postal_code"],
            country=row["country"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            precision=row["precision"],
            accuracy_radius_meters=float(row["accuracy_radius_meters"]),
            parcel_id=row["parcel_id"],
            is_multi_unit=bool(row["is_multi_unit"]),
            known_units=known_u,
            rdi=row["rdi"] or "Unknown",
            is_cmra=bool(row["is_cmra"]),
            is_vacant=bool(row["is_vacant"]),
            census_tract=c_tract,
            fips_code=f_code,
            metadata=meta,
        )

    _RESOLVE_CACHE_MAX = 8192

    @staticmethod
    def _clone_record(rec: Optional[RooftopRecord]) -> Optional[RooftopRecord]:
        """Cheap copy that isolates the mutable containers of a cached record."""
        if rec is None:
            return None
        return dataclasses.replace(
            rec,
            known_units=list(rec.known_units),
            metadata=copy.deepcopy(rec.metadata) if rec.metadata else {},
        )

    def _resolve_cache_token(self, conn: sqlite3.Connection) -> Tuple[int, int, int]:
        """Changes whenever the data under the cache may have changed.

        `total_changes` covers writes through this connection (including direct `_conn.execute` calls),
        `PRAGMA data_version` covers commits from other connections/processes, and `id(conn)` covers
        reconnects (e.g. after a fork).
        """
        if self._db_path == ":memory:":
            # A private in-memory database can only be changed through this connection.
            return (id(conn), conn.total_changes, 0)
        return (id(conn), conn.total_changes, conn.execute("PRAGMA data_version").fetchone()[0])

    def resolve_coordinates(self, address: Any) -> Optional[RooftopRecord]:
        """
        Memoized front for `_resolve_coordinates_uncached` (structured addresses only). Cached results are
        validated against the database state on every call, so writes made by any route invalidate them.
        """
        if isinstance(address, str):
            return self._resolve_coordinates_uncached(address)
        key = (
            getattr(address, "normalized_address_key", None),
            getattr(address, "building_key", None),
            getattr(address, "street1", None),
            getattr(address, "postal_code", None),
            getattr(address, "state", None),
        )
        with self._lock:
            token = self._resolve_cache_token(self._get_conn())
            if token != self._resolve_token:
                self._resolve_cache.clear()
                self._resolve_token = token
            if key in self._resolve_cache:
                return self._clone_record(self._resolve_cache[key])
            result = self._resolve_coordinates_uncached(address)
            if len(self._resolve_cache) >= self._RESOLVE_CACHE_MAX:
                self._resolve_cache.pop(next(iter(self._resolve_cache)))  # evict the oldest entry
            self._resolve_cache[key] = self._clone_record(result)
            return result

    def _resolve_coordinates_uncached(self, address: Any) -> Optional[RooftopRecord]:
        """
        Resolves rooftop point coordinates for a StandardizedAddress or key.
        Checks normalized_address_key, building_key, (postal_code, street1),
        street number transposition healing, and parcel_id.
        """
        with self._lock:
            conn = self._get_conn()
            # 1. Try normalized_address_key
            norm_key = getattr(address, "normalized_address_key", None)
            if isinstance(address, str):
                norm_key = address

            if norm_key:
                cur = conn.execute(
                    "SELECT * FROM rooftop_reference WHERE address_key = ? OR building_key = ? ORDER BY (address_key = ?) DESC, address_key LIMIT 1",
                    (norm_key.strip().upper(), norm_key.strip().upper(), norm_key.strip().upper()),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_record(row)

            # 2. Try building_key
            b_key = getattr(address, "building_key", None)
            if b_key:
                cur = conn.execute(
                    "SELECT * FROM rooftop_reference WHERE building_key = ? ORDER BY address_key LIMIT 1",
                    (b_key.strip().upper(),),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_record(row)

            # 3. Try (postal_code, street1)
            st1 = getattr(address, "street1", None)
            post = getattr(address, "postal_code", None)
            if st1 and post:
                zip5 = post[:5]
                cur = conn.execute(
                    "SELECT * FROM rooftop_reference WHERE postal_code LIKE ? AND street1 = ? LIMIT 1",
                    (f"{zip5}%", st1.strip().upper()),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_record(row)

                # 4. Street number transposition healing against reference index
                st_tokens = st1.split()
                if len(st_tokens) >= 2 and any(c.isdigit() for c in st_tokens[0]):
                    num_part = st_tokens[0]
                    rest_part = " ".join(st_tokens[1:])
                    cur = conn.execute(
                        "SELECT street1 FROM rooftop_reference WHERE postal_code LIKE ? AND street1 LIKE ?",
                        (f"{zip5}%", f"%{rest_part}"),
                    )
                    rows = cur.fetchall()
                    known_nums = []
                    for r in rows:
                        r_tokens = r["street1"].split()
                        if r_tokens and r_tokens[0].isdigit():
                            known_nums.append(int(r_tokens[0]))
                    if known_nums:
                        from entity_standardizer.address.fuzzy import heal_street_number_transposition
                        ranges = [(n, n) for n in known_nums]
                        healed_num = heal_street_number_transposition(num_part, valid_ranges=ranges)
                        if healed_num and healed_num != num_part:
                            healed_st1 = f"{healed_num} {rest_part}".strip().upper()
                            cur = conn.execute(
                                "SELECT * FROM rooftop_reference WHERE postal_code LIKE ? AND street1 = ? LIMIT 1",
                                (f"{zip5}%", healed_st1),
                            )
                            row = cur.fetchone()
                            if row:
                                return self._row_to_record(row)

            # 5. Try parcel_id or plain string address parsing
            if isinstance(address, str) and norm_key:
                cur = conn.execute(
                    "SELECT * FROM rooftop_reference WHERE parcel_id = ? LIMIT 1",
                    (norm_key.strip().upper(),),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_record(row)

                if "|" not in address:
                    from entity_standardizer.address.standardizer import standardize_address
                    std = standardize_address(address)
                    rec = self.resolve_coordinates(std)
                    if rec:
                        return rec
            # 6. Try street edge range interpolation (US Census TIGER style)
            st1_val = getattr(address, "street1", None)
            post_val = getattr(address, "postal_code", None)
            state_val = getattr(address, "state", None)
            if isinstance(address, str) and not st1_val:
                parts = [p.strip() for p in address.split(",") if p.strip()]
                if parts:
                    st1_val = parts[0]
            if st1_val:
                m_num = re.match(r"^(\d+)\s+(.+)$", str(st1_val).strip().upper())
                if m_num:
                    st_num = int(m_num.group(1))
                    st_name = m_num.group(2).strip()
                    interp_rec = self.interpolate_street_range(
                        street_number=st_num,
                        street_name=st_name,
                        postal_code=str(post_val) if post_val else "",
                        state=str(state_val) if state_val else "",
                    )
                    if interp_rec:
                        return interp_rec

            return None

    def geocode(self, address: Any, fallback_to_centroids: bool = True) -> Dict[str, Any]:
        """
        Pure offline rooftop geocoding (zero external network calls):
        1. Exact point rooftop match (OpenAddresses / Reference)
        2. TIGER street edge range linear interpolation
        3. Regional ZIP / state centroid fallback
        """
        if isinstance(address, str) and "|" not in address:
            from entity_standardizer.address.standardizer import standardize_address
            address = standardize_address(address)

        rec = self.resolve_coordinates(address)
        if rec is not None:
            return {
                "latitude": rec.latitude,
                "longitude": rec.longitude,
                "precision": rec.precision,
                "accuracy_radius_meters": rec.accuracy_radius_meters,
                "census_tract": rec.census_tract,
                "fips_code": rec.fips_code,
            }
        is_us_target = getattr(address, "is_us", False)
        if not is_us_target and isinstance(address, str) and "|" in address:
            parts = address.split("|")
            c_code = parts[5].strip().upper() if len(parts) >= 6 else "USA"
            is_us_target = c_code in ("", "US", "USA", "UNITED STATES")

        if fallback_to_centroids and is_us_target:
            from entity_standardizer.address.geocoder import get_fallback_centroid_tier
            from entity_standardizer.address.tables import STATE_TO_FIPS, US_STATES, ZIP3_TO_STATE
            post = getattr(address, "postal_code", None)
            st = getattr(address, "state", None)
            if isinstance(address, str):
                m_zip = re.search(r"\b(\d{5})\b", address)
                if m_zip:
                    post = m_zip.group(1)
            if not st and post and len(post) >= 3:
                st = ZIP3_TO_STATE.get(post[:3])
            coords = get_fallback_centroid_tier(zip5=post, state=st)
            if coords:
                norm_st = US_STATES.get(str(st).upper(), str(st).upper()) if st else None
                fips = STATE_TO_FIPS.get(norm_st) if norm_st else None
                return {
                    "latitude": coords[0],
                    "longitude": coords[1],
                    # A metro ZIP3 centroid is a postal-area point (~8 km); a state centroid is only a locality hint.
                    "precision": "POSTAL_CENTROID" if coords[2] == "ZIP3" else "LOCALITY",
                    "accuracy_radius_meters": 8000.0 if coords[2] == "ZIP3" else 100000.0,
                    "census_tract": None,
                    "fips_code": fips,
                }
        return {
            "latitude": None,
            "longitude": None,
            "precision": "UNRESOLVED",
            "accuracy_radius_meters": None,
            "census_tract": None,
            "fips_code": None,
        }

    def validate_parcel(self, address: Any) -> ParcelValidationResult:
        """
        Validates whether the address corresponds to a known physical parcel
        in the offline reference database.
        """
        if isinstance(address, str) and "|" not in address:
            with self._lock:
                cur = self._get_conn().execute(
                    "SELECT * FROM rooftop_reference WHERE parcel_id = ? LIMIT 1",
                    (address.strip().upper(),),
                )
                row = cur.fetchone()
                if row:
                    rec = self._row_to_record(row)
                    return ParcelValidationResult(
                        is_valid_parcel=True,
                        parcel_id=rec.parcel_id,
                        is_multi_unit=rec.is_multi_unit,
                        matched_rooftop=True,
                        latitude=rec.latitude,
                        longitude=rec.longitude,
                        accuracy_radius_meters=rec.accuracy_radius_meters,
                    )

        record = self.resolve_coordinates(address)
        if record is not None and record.parcel_id:
            return ParcelValidationResult(
                is_valid_parcel=True,
                parcel_id=record.parcel_id,
                is_multi_unit=record.is_multi_unit,
                matched_rooftop=True,
                latitude=record.latitude,
                longitude=record.longitude,
                accuracy_radius_meters=record.accuracy_radius_meters,
            )

        return ParcelValidationResult(
            is_valid_parcel=False,
            parcel_id=None,
            is_multi_unit=False,
            matched_rooftop=False,
            latitude=None,
            longitude=None,
            accuracy_radius_meters=None,
        )

    def hot_swap(self, new_db_path: str):
        """
        Performs a thread-safe, zero-downtime hot-swap to a newly loaded reference database.
        Verifies schema and integrity before swapping connections.
        """
        if not os.path.exists(new_db_path):
            raise FileNotFoundError(f"Hot-swap database file not found: {new_db_path}")

        # Connect and verify target database
        test_conn = sqlite3.connect(new_db_path, check_same_thread=False)
        test_conn.row_factory = sqlite3.Row
        try:
            cur = test_conn.execute("SELECT count(*) FROM rooftop_reference")
            cur.fetchone()
            # The engine also queries street_ranges; create any other required table/column so a swapped-in
            # reference database that predates it cannot make later lookups raise.
            self._init_schema(test_conn)
            test_conn.execute("PRAGMA journal_mode=WAL;")  # never ":memory:" here: the exists() check above rejects it
        except sqlite3.Error as e:
            test_conn.close()
            raise ValueError(f"Invalid reference database schema in {new_db_path}: {e}")

        # Atomic swap
        with self._lock:
            old_conn = self._conn
            self._conn = test_conn  # the setter also clears the resolve memo
            self._db_path = new_db_path
            old_conn.close()

    def count(self) -> int:
        """Returns total records in the reference table."""
        with self._lock:
            cur = self._get_conn().execute("SELECT count(*) FROM rooftop_reference")
            row = cur.fetchone()
            return row[0] if row else 0

    def close(self):
        """Closes internal database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()


_DEFAULT_OFFLINE_INDEX: Optional[OfflineReferenceIndex] = None
_INDEX_LOCK = threading.Lock()


def get_default_offline_index() -> OfflineReferenceIndex:
    """Returns singleton instance of the offline rooftop reference index."""
    global _DEFAULT_OFFLINE_INDEX
    if _DEFAULT_OFFLINE_INDEX is None:
        with _INDEX_LOCK:
            if _DEFAULT_OFFLINE_INDEX is None:
                _DEFAULT_OFFLINE_INDEX = OfflineReferenceIndex(seed=True)
    return _DEFAULT_OFFLINE_INDEX


def resolve_offline_coordinates(address: Any) -> Optional[RooftopRecord]:
    """Public helper to resolve rooftop coordinates via the default offline index."""
    return get_default_offline_index().resolve_coordinates(address)


def validate_parcel_offline(address: Any) -> ParcelValidationResult:
    """Public helper to validate parcel status via the default offline index."""
    return get_default_offline_index().validate_parcel(address)


def geocode_offline(address: Any, fallback_to_centroids: bool = True) -> Dict[str, Any]:
    """Public helper to perform pure offline geocoding via the default offline index."""
    return get_default_offline_index().geocode(address, fallback_to_centroids=fallback_to_centroids)
