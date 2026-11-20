"""User-selectable standardization options and presets for file standardization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_VALID_OPTION_VALUES: dict[str, tuple[str, ...]] = {
    "column_mode": ("overwrite", "append_std", "overwrite_keep_raw"),
    "invalid_policy": ("clear_placeholders_keep_raw", "clear_all_invalid", "keep_all_raw"),
    "couple_split_mode": ("keep_primary", "append_secondary_col", "split_rows"),
    "phone_format": ("e164", "national", "international", "rfc3966", "masked_partial", "masked_full"),
    "extension_mode": ("preserve", "strip"),
    "address_case": ("upper", "title"),
    "country_format": ("auto", "iso2", "iso3", "name"),
    "company_case": ("upper", "title"),
    "company_style": ("legal_name", "brand_stem"),
    "person_case": ("upper", "title"),
    "person_format": ("first_last", "last_comma_first"),
}


@dataclass(slots=True)
class StandardizationOptions:
    """User-selectable standardization, formatting, cross-healing, and output controls."""

    column_mode: str = "overwrite"
    include_audit_cols: bool = False
    include_matching_keys: bool = False
    invalid_policy: str = "clear_placeholders_keep_raw"

    enable_cross_healing: bool = True
    rescue_misplaced_fields: bool = True
    infer_blank_fields: bool = False
    couple_split_mode: str = "keep_primary"

    phone_format: str = "e164"
    extension_mode: str = "preserve"
    default_country: str = "US"

    address_case: str = "upper"
    country_format: str = "auto"
    split_secondary_unit: bool = True
    enable_geocoding: bool = False

    company_case: str = "upper"
    company_style: str = "legal_name"
    person_case: str = "upper"
    person_format: str = "first_last"
    use_nickname_root: bool = False

    email_strip_subaddress: bool = True
    email_canonicalize_gmail_dots: bool = True
    email_heal_typos: bool = True

    id_pad_width: int | None = None
    csv_formula_guard: bool = False

    def __post_init__(self) -> None:
        for field_name, allowed in _VALID_OPTION_VALUES.items():
            val = getattr(self, field_name)
            if val not in allowed:
                raise ValueError(f"Invalid {field_name}={val!r}; expected one of {allowed}.")
        self.default_country = (self.default_country or "US").strip().upper() or "US"
        if self.id_pad_width is not None:
            if isinstance(self.id_pad_width, bool):
                raise ValueError("id_pad_width must be an integer >= 1, not bool.")
            self.id_pad_width = int(self.id_pad_width)
            if self.id_pad_width < 1:
                raise ValueError("id_pad_width must be >= 1 when specified.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize standardization options to a JSON-compatible dictionary."""
        return {
            "column_mode": self.column_mode,
            "include_audit_cols": self.include_audit_cols,
            "include_matching_keys": self.include_matching_keys,
            "invalid_policy": self.invalid_policy,
            "enable_cross_healing": self.enable_cross_healing,
            "rescue_misplaced_fields": self.rescue_misplaced_fields,
            "infer_blank_fields": self.infer_blank_fields,
            "couple_split_mode": self.couple_split_mode,
            "phone_format": self.phone_format,
            "extension_mode": self.extension_mode,
            "default_country": self.default_country,
            "address_case": self.address_case,
            "country_format": self.country_format,
            "split_secondary_unit": self.split_secondary_unit,
            "enable_geocoding": self.enable_geocoding,
            "company_case": self.company_case,
            "company_style": self.company_style,
            "person_case": self.person_case,
            "person_format": self.person_format,
            "use_nickname_root": self.use_nickname_root,
            "email_strip_subaddress": self.email_strip_subaddress,
            "email_canonicalize_gmail_dots": self.email_canonicalize_gmail_dots,
            "email_heal_typos": self.email_heal_typos,
            "id_pad_width": self.id_pad_width,
            "csv_formula_guard": self.csv_formula_guard,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> StandardizationOptions:
        """Deserialize StandardizationOptions from a mapping with defaults for omitted keys."""
        if not data:
            return cls()
        defaults = cls()
        kwargs: dict[str, Any] = {}
        for key, default_val in defaults.to_dict().items():
            if key in data and data[key] is not None:
                kwargs[key] = data[key]
            elif key == "id_pad_width":
                kwargs[key] = None
            else:
                kwargs[key] = default_val
        return cls(**kwargs)
