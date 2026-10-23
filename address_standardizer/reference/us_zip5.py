"""Bundled zero-licensing-cost US 5-digit ZIP reference provider.

Backed by open GeoNames postal code data (CC-BY 4.0).
Provides O(1) lookup of 5-digit ZIP codes to place names, states, counties, and coordinates.
"""

from __future__ import annotations

import gzip
import threading
from pathlib import Path
from typing import Dict, List, Optional, Union

from address_standardizer.reference._match import fold_name, name_tokens
from address_standardizer.reference.base import ReferencePlace

DATA_PATH = Path(__file__).resolve().parent / "data" / "us_zip5.tsv.gz"
SOURCE = "GeoNames US Postal Codes (https://download.geonames.org/export/zip/)"
LICENSE = "CC-BY-4.0"
ATTRIBUTION = (
    "Postal code data from GeoNames (https://www.geonames.org), licensed under the Creative Commons "
    "Attribution 4.0 License (https://creativecommons.org/licenses/by/4.0/)."
)


class USZip5Provider:
    """Read-only in-memory provider for US 5-digit ZIP reference places."""

    name: str = "us_zip5"
    source: str = SOURCE
    license: str = LICENSE
    as_of: str = "2026"

    def __init__(self, data_path: Optional[Union[Path, str]] = None) -> None:
        self._path = Path(data_path) if data_path else DATA_PATH
        self._lock = threading.Lock()
        self._loaded = False
        self._by_zip: Dict[str, List[ReferencePlace]] = {}
        self._by_place: Dict[str, List[str]] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if not self._path.exists():
                self._loaded = True
                return
            with gzip.open(self._path, "rt", encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 7:
                        post, name, adm1, adm1_c, adm2, lat_s, lon_s = parts[:7]
                        try:
                            lat = float(lat_s) if lat_s else None
                        except ValueError:
                            lat = None
                        try:
                            lon = float(lon_s) if lon_s else None
                        except ValueError:
                            lon = None
                        place = ReferencePlace(
                            country="US",
                            postal_code=post,
                            place_name=name,
                            admin1=adm1,
                            admin1_code=adm1_c,
                            admin2=adm2,
                            latitude=lat,
                            longitude=lon,
                            provider=self.name,
                        )
                        self._by_zip.setdefault(post, []).append(place)
                        key = fold_name(name)
                        if key:
                            self._by_place.setdefault(key, []).append(post)
                        tok_key = " ".join(name_tokens(name))
                        if tok_key and tok_key != key:
                            self._by_place.setdefault(tok_key, []).append(post)
            self._loaded = True

    def covers_country(self, country: str) -> bool:
        return country.strip().upper() in ("US", "USA")

    def lookup_postal(self, country: str, postal_code: str) -> List[ReferencePlace]:
        if not self.covers_country(country):
            return []
        self._ensure_loaded()
        zip_clean = postal_code.strip()[:5]
        return list(self._by_zip.get(zip_clean, []))

    def lookup_place(self, country: str, place_name: str, admin1_code: Optional[str] = None) -> List[str]:
        if not self.covers_country(country) or not place_name:
            return []
        self._ensure_loaded()
        key = fold_name(place_name)
        zips = self._by_place.get(key) or self._by_place.get(" ".join(name_tokens(place_name)), [])
        if not admin1_code:
            return list(dict.fromkeys(zips))
        adm_up = admin1_code.strip().upper()
        res = []
        for z in dict.fromkeys(zips):
            places = self._by_zip.get(z, [])
            if any(p.admin1_code.upper() == adm_up for p in places):
                res.append(z)
        return res

    def close(self) -> None:
        pass


_DEFAULT_US_ZIP5_PROVIDER: Optional[USZip5Provider] = None
_PROVIDER_LOCK = threading.Lock()


def get_default_us_zip5_provider() -> USZip5Provider:
    global _DEFAULT_US_ZIP5_PROVIDER
    if _DEFAULT_US_ZIP5_PROVIDER is None:
        with _PROVIDER_LOCK:
            if _DEFAULT_US_ZIP5_PROVIDER is None:
                _DEFAULT_US_ZIP5_PROVIDER = USZip5Provider()
    return _DEFAULT_US_ZIP5_PROVIDER
