"""
Real-Time Typeahead & Autocomplete Engine.
==========================================
High-speed in-memory prefix trie and token inverted index providing sub-8ms
address completion with multi-unit secondary unit prompting.
"""

import math
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple, Any

from address_standardizer.tables import SECONDARY_UNITS, US_STATES
from address_standardizer._patterns import RE_SEC_UNIT


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Damerau-Levenshtein edit distance (<= 1 fast path)."""
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > 1:
        return abs(len1 - len2)
    if len1 + 1 == len2:
        for i in range(len2):
            if s2[:i] + s2[i + 1:] == s1:
                return 1
        return 2
    if len2 + 1 == len1:
        for i in range(len1):
            if s1[:i] + s1[i + 1:] == s2:
                return 1
        return 2
    diff_indices = [i for i in range(len1) if s1[i] != s2[i]]
    if len(diff_indices) == 1:
        return 1
    if len(diff_indices) == 2:
        i, j = diff_indices
        if j == i + 1 and s1[i] == s2[j] and s1[j] == s2[i]:
            return 1
    return len(diff_indices)


def _finite_or_none(value: Any) -> Optional[float]:
    """float(value) when it is a finite number, else None (missing, NaN, inf, or not numeric)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _record_key(rec: Dict[str, Any]) -> Tuple[str, ...]:
    return (rec["street1"], rec["street2"], rec["city"], rec["state"], rec["postal_code"], rec["country"])


def calculate_haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance in meters between two lat/lon coordinates."""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    a = min(1.0, max(0.0, a))  # float error can push `a` just outside [0, 1] for antipodal points
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


@dataclass
class AutocompleteSuggestion:
    """Typeahead autocomplete candidate suggestion."""
    text: str
    street1: str
    street2: str
    city: str
    state: str
    postal_code: str
    country: str = "USA"
    secondary_prompt_required: bool = False
    suggested_secondary_units: List[str] = field(default_factory=list)
    highlight_ranges: List[Tuple[int, int]] = field(default_factory=list)
    score: float = 1.0
    prompt_message: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_meters: Optional[float] = None

    @property
    def street_line(self) -> str:
        return self.street1

    def as_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "street1": self.street1,
            "street2": self.street2,
            "street_line": self.street1,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "secondary_prompt_required": self.secondary_prompt_required,
            "suggested_secondary_units": list(self.suggested_secondary_units),
            "highlight_ranges": list(self.highlight_ranges),
            "score": round(self.score, 4),
            "prompt_message": self.prompt_message,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "distance_meters": self.distance_meters,
        }


# Seed records of prominent multi-unit and commercial buildings for typeahead
SEED_AUTOCOMPLETE_RECORDS: List[Dict[str, Any]] = [
    {
        "street1": "100 WALL ST",
        "city": "NEW YORK",
        "state": "NY",
        "postal_code": "10005",
        "is_multi_unit": True,
        "known_units": ["STE 400", "STE 800", "FL 12", "FL 20"],
        "latitude": 40.7061,
        "longitude": -74.0060,
    },
    {
        "street1": "200 PARK AVE",
        "city": "NEW YORK",
        "state": "NY",
        "postal_code": "10166",
        "is_multi_unit": True,
        "known_units": ["STE 1200", "STE 1500", "FL 25"],
        "latitude": 40.7535,
        "longitude": -73.9768,
    },
    {
        "street1": "350 5TH AVE",
        "city": "NEW YORK",
        "state": "NY",
        "postal_code": "10118",
        "is_multi_unit": True,
        "known_units": ["STE 1000", "STE 2000", "FL 50"],
        "latitude": 40.7484,
        "longitude": -73.9857,
    },
    {
        "street1": "1209 N ORANGE ST",
        "city": "WILMINGTON",
        "state": "DE",
        "postal_code": "19801",
        "is_multi_unit": True,
        "known_units": ["STE 400", "STE 600", "FL 2"],
        "latitude": 39.7478,
        "longitude": -75.5492,
    },
    {
        "street1": "30 N GOULD ST",
        "city": "SHERIDAN",
        "state": "WY",
        "postal_code": "82801",
        "is_multi_unit": True,
        "known_units": ["STE R", "STE A", "STE B"],
        "latitude": 44.7972,
        "longitude": -106.9562,
    },
    {
        "street1": "500 N MICHIGAN AVE",
        "city": "CHICAGO",
        "state": "IL",
        "postal_code": "60611",
        "is_multi_unit": True,
        "known_units": ["STE 300", "STE 1400", "FL 14"],
        "latitude": 41.8919,
        "longitude": -87.6243,
    },
    {
        "street1": "101 CALIFORNIA ST",
        "city": "SAN FRANCISCO",
        "state": "CA",
        "postal_code": "94111",
        "is_multi_unit": True,
        "known_units": ["STE 1200", "STE 2400", "FL 30"],
        "latitude": 37.7928,
        "longitude": -122.3980,
    },
    {
        "street1": "160 GREENTREE DR",
        "city": "DOVER",
        "state": "DE",
        "postal_code": "19904",
        "is_multi_unit": True,
        "known_units": ["STE 101", "STE 201"],
        "latitude": 39.1582,
        "longitude": -75.5244,
    },
    {
        "street1": "850 NEW BURTON RD",
        "city": "DOVER",
        "state": "DE",
        "postal_code": "19904",
        "is_multi_unit": True,
        "known_units": ["STE 201"],
        "latitude": 39.1415,
        "longitude": -75.5411,
    },
    {
        "street1": "251 LITTLE FALLS DR",
        "city": "WILMINGTON",
        "state": "DE",
        "postal_code": "19808",
        "is_multi_unit": False,
        "known_units": [],
        "latitude": 39.7570,
        "longitude": -75.6020,
    },
    {
        "street1": "16192 COASTAL HWY",
        "city": "LEWES",
        "state": "DE",
        "postal_code": "19958",
        "is_multi_unit": False,
        "known_units": [],
        "latitude": 38.7420,
        "longitude": -75.1480,
    },
    {
        "street1": "3500 S DUPONT HWY",
        "city": "DOVER",
        "state": "DE",
        "postal_code": "19901",
        "is_multi_unit": False,
        "known_units": [],
        "latitude": 39.1120,
        "longitude": -75.5200,
    },
    {
        "street1": "3773 HOWARD HUGHES PKWY",
        "city": "LAS VEGAS",
        "state": "NV",
        "postal_code": "89169",
        "is_multi_unit": True,
        "known_units": ["STE 500S", "STE 200"],
        "latitude": 36.1180,
        "longitude": -115.1550,
    },
    {
        "street1": "100 MAIN ST",
        "city": "NEW YORK",
        "state": "NY",
        "postal_code": "10001",
        "is_multi_unit": True,
        "known_units": ["APT 1A", "APT 2B", "APT 3C"],
        "latitude": 40.7500,
        "longitude": -73.9900,
    },
    {
        "street1": "123 MARKET ST",
        "city": "SAN FRANCISCO",
        "state": "CA",
        "postal_code": "94105",
        "is_multi_unit": False,
        "known_units": [],
        "latitude": 37.7920,
        "longitude": -122.3970,
    },
]


class AutocompleteEngine:
    """
    Sub-8ms in-memory prefix trie and inverted token index for address typeahead.
    Features typo tolerance (edit distance <= 1), geographic proximity biasing,
    and secondary unit prompting for multi-unit buildings.
    """

    def __init__(self, seed: bool = True):
        self._records: List[Dict[str, Any]] = []
        self._record_keys: Set[Tuple[str, ...]] = set()
        self._prefix_index: Dict[str, Set[int]] = {}
        if seed:
            for rec in SEED_AUTOCOMPLETE_RECORDS:
                self.index_address(**rec)

    def index_address(
        self,
        street1: str,
        city: str,
        state: str,
        postal_code: str,
        street2: str = "",
        country: str = "USA",
        is_multi_unit: bool = False,
        known_units: Optional[List[str]] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> int:
        """Indexes a canonical address into the in-memory prefix inverted index."""
        rec_id = len(self._records)
        lat_f = _finite_or_none(latitude)
        lon_f = _finite_or_none(longitude)
        if lat_f is None or lon_f is None or not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
            lat_f = lon_f = None
        record = {
            "id": rec_id,
            "street1": street1.strip().upper(),
            "street2": street2.strip().upper(),
            "city": city.strip().upper(),
            "state": state.strip().upper(),
            "postal_code": postal_code.strip(),
            "country": country.strip().upper(),
            "is_multi_unit": is_multi_unit,
            "known_units": list(known_units) if known_units else [],
            "latitude": lat_f,
            "longitude": lon_f,
        }
        self._records.append(record)
        self._record_keys.add(_record_key(record))

        # Index all tokens across fields
        units_text = " ".join(record["known_units"])
        full_text = f"{record['street1']} {record['street2']} {record['city']} {record['state']} {record['postal_code']} {units_text}"
        tokens = set(re.findall(r"\w+", full_text.upper()))
        folded_tokens = set()
        for t in tokens:
            folded = unicodedata.normalize("NFKD", t).encode("ASCII", "ignore").decode("utf-8").upper()
            if folded:
                folded_tokens.add(folded)
        all_tokens = tokens.union(folded_tokens)
        for token in all_tokens:
            for i in range(1, min(len(token) + 1, 25)):
                prefix = token[:i]
                if prefix not in self._prefix_index:
                    self._prefix_index[prefix] = set()
                self._prefix_index[prefix].add(rec_id)

        return rec_id

    def index_addresses(self, records: List[Dict[str, Any]]):
        """Batch index multiple address dictionaries."""
        for r in records:
            self.index_address(**r)

    def connect_reference_index(self, index: Optional[Any] = None) -> int:
        """Indexes reference records from the embedded SQLite reference index."""
        if index is None:
            from address_standardizer.offline_index import get_default_offline_index
            index = get_default_offline_index()
        count = 0
        with index._lock:
            cur = index._conn.execute("SELECT * FROM rooftop_reference")
            rows = cur.fetchall()
            for row in rows:
                key = (
                    (row["street1"] or "").strip().upper(),
                    (row["street2"] or "").strip().upper(),
                    (row["city"] or "").strip().upper(),
                    (row["state"] or "").strip().upper(),
                    (row["postal_code"] or "").strip(),
                    (row["country"] or "").strip().upper(),
                )
                if key in self._record_keys:
                    continue  # already indexed (e.g. connecting the same reference index twice)
                known_u = []
                if row["known_units"]:
                    try:
                        known_u = json.loads(row["known_units"])
                    except Exception:
                        known_u = []
                self.index_address(
                    street1=row["street1"],
                    street2=row["street2"] or "",
                    city=row["city"],
                    state=row["state"],
                    postal_code=row["postal_code"],
                    country=row["country"],
                    is_multi_unit=bool(row["is_multi_unit"]),
                    known_units=known_u,
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                )
                count += 1
        return count

    def load_reference_stream(self, stream: Iterable[Dict[str, Any]]) -> int:
        """Stream loads addresses into the index."""
        count = 0
        for rec in stream:
            self.index_address(**rec)
            count += 1
        return count

    def search(
        self,
        query: str,
        max_results: int = 5,
        state_filter: Optional[str] = None,
        client_lat: Optional[float] = None,
        client_lon: Optional[float] = None,
        radius_km: Optional[float] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_miles: Optional[float] = None,
        typo_tolerance: bool = True,
    ) -> List[AutocompleteSuggestion]:
        """
        Executes real-time prefix search with typo tolerance and proximity radius biasing.
        Sub-8ms response time.
        """
        if max_results <= 0:
            return []
        client_lat = client_lat if client_lat is not None else latitude
        client_lon = client_lon if client_lon is not None else longitude
        if radius_miles is not None and radius_km is None:
            radius_km = radius_miles * 1.60934

        clean_q = query.strip().upper()
        if not clean_q:
            return []

        clean_q_fold = unicodedata.normalize("NFKD", clean_q).encode("ASCII", "ignore").decode("utf-8").upper()
        q_tokens = re.findall(r"\w+", clean_q)
        q_tokens_fold = re.findall(r"\w+", clean_q_fold)
        if not q_tokens and not q_tokens_fold:
            return []

        tokens_to_match = q_tokens_fold if q_tokens_fold else q_tokens

        # Find intersecting record IDs for all tokens
        matching_ids: Optional[Set[int]] = None
        has_typo_match = False

        for tok in tokens_to_match:
            rec_ids = self._prefix_index.get(tok, set())
            if not rec_ids and typo_tolerance and len(tok) >= 3:
                # Damerau-Levenshtein typo tolerance check (distance <= 1)
                typo_ids = set()
                for key, ids in self._prefix_index.items():
                    if abs(len(key) - len(tok)) <= 1:
                        if damerau_levenshtein_distance(tok, key) <= 1:
                            typo_ids.update(ids)
                if typo_ids:
                    rec_ids = typo_ids
                    has_typo_match = True

            if matching_ids is None:
                matching_ids = set(rec_ids)
            else:
                matching_ids.intersection_update(rec_ids)
            if not matching_ids:
                break

        # Fallback: if query specifies secondary unit, match base tokens
        if not matching_ids and len(tokens_to_match) > 2:
            sec_idx = None
            for idx, t in enumerate(tokens_to_match):
                if t in SECONDARY_UNITS or t in SECONDARY_UNITS.values() or t.startswith("#"):
                    sec_idx = idx
                    break
            if sec_idx is not None and sec_idx > 0:
                base_tokens = tokens_to_match[:sec_idx]
                fallback_ids: Optional[Set[int]] = None
                for tok in base_tokens:
                    rec_ids = self._prefix_index.get(tok, set())
                    if not rec_ids and typo_tolerance and len(tok) >= 3:
                        typo_ids = set()
                        for key, ids in self._prefix_index.items():
                            if abs(len(key) - len(tok)) <= 1:
                                if damerau_levenshtein_distance(tok, key) <= 1:
                                    typo_ids.update(ids)
                        if typo_ids:
                            rec_ids = typo_ids
                    if fallback_ids is None:
                        fallback_ids = set(rec_ids)
                    else:
                        fallback_ids.intersection_update(rec_ids)
                    if not fallback_ids:
                        break
                if fallback_ids:
                    matching_ids = fallback_ids

        if not matching_ids:
            return []

        # Check if query already specifies a secondary unit
        has_query_sec_unit = (
            "#" in clean_q
            or bool(RE_SEC_UNIT.search(clean_q))
            or any(
                t in SECONDARY_UNITS or t in SECONDARY_UNITS.values()
                for t in q_tokens
            )
            or any(tok in ("APT", "STE", "UNIT", "FL", "SUITE", "ROOM") for tok in q_tokens)
        )

        norm_st_filter = None
        if state_filter:
            raw_st = state_filter.strip().upper()
            norm_st_filter = US_STATES.get(raw_st, raw_st)

        suggestions: List[AutocompleteSuggestion] = []
        for rec_id in matching_ids:
            rec = self._records[rec_id]
            if norm_st_filter and rec["state"] != norm_st_filter:
                continue

            # Geographic proximity distance calculation & filtering
            dist_meters: Optional[float] = None
            has_coords = rec["latitude"] is not None and rec["longitude"] is not None
            if radius_km is not None and client_lat is not None and client_lon is not None and not has_coords:
                continue  # cannot be shown to be inside the radius
            if client_lat is not None and client_lon is not None and has_coords:
                d_m = calculate_haversine_distance_meters(client_lat, client_lon, rec["latitude"], rec["longitude"])
                d_km = d_m / 1000.0
                if radius_km is not None and d_km > radius_km:
                    continue
                dist_meters = round(d_m, 1)

            full_repr = f"{rec['street1']}, {rec['city']}, {rec['state']} {rec['postal_code']}"
            if rec["street2"]:
                full_repr = f"{rec['street1']}, {rec['street2']}, {rec['city']}, {rec['state']} {rec['postal_code']}"

            # Secondary unit prompting logic
            prompt_required = False
            prompt_message: Optional[str] = None
            suggested_units: List[str] = []
            if rec["is_multi_unit"] and not has_query_sec_unit and not rec["street2"]:
                prompt_required = True
                prompt_message = "Requires Suite / Apartment Number"
                suggested_units = rec["known_units"] or ["APT", "STE", "UNIT", "FL"]

            # Calculate match highlight ranges
            raw_ranges: List[Tuple[int, int]] = []
            full_repr_upper = full_repr.upper()
            full_repr_fold = unicodedata.normalize("NFKD", full_repr_upper).encode("ASCII", "ignore").decode("utf-8").upper()
            for tok in dict.fromkeys(q_tokens + q_tokens_fold):
                start_idx = 0
                while True:
                    idx = full_repr_upper.find(tok, start_idx)
                    if idx == -1:
                        idx = full_repr_fold.find(tok, start_idx)
                    if idx == -1:
                        break
                    raw_ranges.append((idx, idx + len(tok)))
                    start_idx = idx + len(tok)

            raw_ranges.sort(key=lambda r: (r[0], r[1]))
            highlight_ranges: List[Tuple[int, int]] = []
            for start, end in raw_ranges:
                if not highlight_ranges:
                    highlight_ranges.append((start, end))
                else:
                    prev_s, prev_e = highlight_ranges[-1]
                    if start <= prev_e:
                        highlight_ranges[-1] = (prev_s, max(prev_e, end))
                    else:
                        highlight_ranges.append((start, end))

            # Score calculation
            score = 1.0
            if full_repr_upper.startswith(clean_q) or full_repr_fold.startswith(clean_q_fold):
                score += 0.5
            if has_typo_match:
                score *= 0.85
            if dist_meters is not None:
                # Proximity boost: decaying boost up to +2.0 for nearby candidates
                dist_km = dist_meters / 1000.0
                proximity_boost = max(0.0, 2.0 - min(dist_km / 50.0, 2.0))
                score += proximity_boost

            suggestions.append(
                AutocompleteSuggestion(
                    text=full_repr,
                    street1=rec["street1"],
                    street2=rec["street2"],
                    city=rec["city"],
                    state=rec["state"],
                    postal_code=rec["postal_code"],
                    country=rec["country"],
                    secondary_prompt_required=prompt_required,
                    prompt_message=prompt_message,
                    suggested_secondary_units=suggested_units,
                    highlight_ranges=highlight_ranges,
                    score=score,
                    latitude=rec["latitude"],
                    longitude=rec["longitude"],
                    distance_meters=dist_meters,
                )
            )

        # Sort by score descending
        suggestions.sort(key=lambda s: s.score, reverse=True)
        return suggestions[:max_results]


_DEFAULT_AUTOCOMPLETE_ENGINE = AutocompleteEngine(seed=True)


def autocomplete_address(
    query: str,
    max_results: int = 5,
    state_filter: Optional[str] = None,
    client_lat: Optional[float] = None,
    client_lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_miles: Optional[float] = None,
    typo_tolerance: bool = True,
    engine: Optional[AutocompleteEngine] = None,
) -> List[AutocompleteSuggestion]:
    """
    Public functional interface for address typeahead autocomplete with
    typo tolerance, geographic radius biasing, and secondary unit prompting.
    """
    active_engine = engine or _DEFAULT_AUTOCOMPLETE_ENGINE
    return active_engine.search(
        query=query,
        max_results=max_results,
        state_filter=state_filter,
        client_lat=client_lat,
        client_lon=client_lon,
        radius_km=radius_km,
        latitude=latitude,
        longitude=longitude,
        radius_miles=radius_miles,
        typo_tolerance=typo_tolerance,
    )
