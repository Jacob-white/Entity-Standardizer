"""Explainable standardization: change trace, per-field confidence and alternative interpretations (all opt-in).

Nothing here runs unless the caller asks: ``standardize_address(..., explain=True)`` attaches
``std.explanation`` (ordered change records) and ``std.field_confidence``; ``alternatives=N`` attaches
``std.alternatives`` (the next-best readings of an ambiguous input). Default calls take none of these code paths and
the default result carries none of these attributes.

How the trace is built
----------------------
* A small :class:`Recorder` is held in a ``ContextVar`` for the duration of one explained call. The pipeline in
  ``standardizer.py`` reads that variable once and, only when it is set, reports the decisions that cannot be
  recovered from the final result (care-of removal, country/script detection, state-from-ZIP policy, parse path).
* Everything else is derived by diffing the supplied value of each field against the final value, so the fast path,
  the rule matrix, the CRF and the international grammars are all explained the same way and nothing is ever
  reported that did not happen.
* Validation outcomes (postal format, ZIP/state agreement, reference data) are appended last.

Every record is ``{"field", "before", "after", "rule", "detail"}`` with a stable machine-readable ``rule`` id (see
``RULES`` and docs/api_reference.md). For token-level street rules ``before``/``after`` are the affected fragment, for
field-level rules the whole field value.
"""

from __future__ import annotations

import contextvars
import difflib
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional

from address_standardizer._inputs import coerce_text
from address_standardizer.confidence import compute_field_confidence
from address_standardizer.tables import DIRECTIONALS, STREET_SUFFIXES, US_STATES, ZIP3_TO_STATE

__all__ = ["MAX_ALTERNATIVES", "RULES", "Recorder", "build_evidence", "standardize_explained"]

MAX_ALTERNATIVES = 5

# Stable rule ids. Adding an id is backwards compatible; renaming or removing one is a breaking change.
RULES: Dict[str, str] = {
    # surface normalisation (any field)
    "case_normalized": "only letter case changed",
    "punctuation_normalized": "only punctuation or whitespace changed",
    "diacritics_folded": "accents were folded to their base letters",
    # street / unit tokens
    "street_type_abbreviation": "street type replaced by its USPS abbreviation (STREET -> ST)",
    "directional_abbreviation": "directional replaced by its abbreviation (NORTH -> N)",
    "ordinal_normalized": "number or number word became an ordinal (FIRST -> 1ST)",
    "unit_designator_abbreviation": "unit designator replaced by its abbreviation (SUITE -> STE)",
    "unit_designator_inserted": "a unit designator was added in front of a bare unit number (# 5 -> APT 5)",
    "number_words_to_digits": "number words became digits (FIVE HUNDRED -> 500)",
    "typo_heal_street": "a street word was corrected to a known word within a small edit distance",
    "token_rewritten": "a token was rewritten by a normalisation rule",
    "tokens_removed": "tokens were dropped from the field",
    "tokens_inserted": "tokens were added to the field",
    "unit_split": "a trailing unit was moved from street1 to street2",
    "street1_moved_to_street2": "a street1 value that is not a street was moved to street2",
    "secondary_promoted_to_street": "street2 content (a PO box, or the rest of the street) became part of street1",
    "house_number_moved_to_front": "a trailing house number was moved in front of the street name",
    "locality_moved_from_street": "city, state or postal code text was cut out of the street line",
    "care_of_removed": "a c/o or attention clause was removed from the delivery line",
    "city_noise_removed": "street1 only repeated the city or a municipal prefix and was cleared",
    "private_residence_detected": "a privacy placeholder replaced the street line",
    # city / locality
    "typo_heal_city": "a misspelled city was corrected to a known city",
    "city_inferred_from_text": "the city was taken from the street line",
    "city_canonicalized": "the city was rewritten to its canonical form",
    "city_discarded": "the supplied city was dropped",
    "dependent_locality_extracted": "a dependent locality (district, urbanization) was separated from the city or street",
    "building_name_extracted": "a building name was separated from the street line",
    # state
    "state_abbreviated": "state name replaced by its postal abbreviation",
    "state_from_zip": "state was missing and taken from the ZIP code",
    "state_inferred_from_text": "state was missing and taken from the address text",
    "state_normalized": "state was rewritten to its canonical form",
    "state_corrected_from_zip": "a state that contradicted the ZIP was replaced (correct_state_from_zip policy)",
    "zip_state_mismatch_kept": "the state contradicts the ZIP and was kept (default policy); the address is flagged",
    # postal code
    "postal_normalized": "postal code was reformatted",
    "postal_transposition_healed": "transposed digits in the postal code were corrected",
    "postal_extracted_from_text": "the postal code was taken from the address text",
    "postal_discarded": "the supplied postal code was dropped",
    "postal_format_invalid": "the postal code does not match the country's format",
    # country / script
    "country_normalized": "country name or code was resolved to ISO alpha-3",
    "country_inferred_from_script": "no country was given; it was inferred from the writing system",
    "country_inferred_from_state": "no country was given; it was inferred from the state or province",
    "country_inferred_from_postal": "no country was given; it was inferred from the postal code",
    "country_inferred_from_text": "no country was given; it was inferred from the address text",
    "country_defaulted_us": "no country evidence at all; the US default was used",
    "script_single_line_split": "a non-Latin single-line address was split into street, city, state and postal code",
    # outcomes
    "registered_agent_hub_detected": "the address is a known registered-agent / formation hub",
    "locality_only_accepted": "no street line; accepted as a locality-only record",
    "parse_failed": "no usable street line could be produced",
    # reference data (only when a reference provider was used)
    "reference_confirmed": "postal code, state and place agree with the reference data",
    "reference_postal_unknown": "the postal code is not in the reference data",
    "reference_place_mismatch": "the city does not resemble any place for the postal code",
    "reference_state_mismatch": "the state differs from the postal code's state in the reference data",
    "reference_not_checked": "the reference data could not check this address",
}

_RECORDER: "contextvars.ContextVar[Optional[Recorder]]" = contextvars.ContextVar(
    "address_standardizer_explain_recorder", default=None
)

_FIELDS = ("street1", "street2", "city", "state", "postal_code", "country")

_NUMBER_WORDS = frozenset(
    "ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN FIFTEEN SIXTEEN SEVENTEEN "
    "EIGHTEEN NINETEEN TWENTY THIRTY FORTY FIFTY SIXTY SEVENTY EIGHTY NINETY HUNDRED THOUSAND".split()
)
_UNIT_ABBR = frozenset(
    "APT STE UNIT FL RM BLDG DEPT LOT SPC TRLR PH BSMT LBBY OFC SLIP STOP PIER HNGR KEY UPPR LOWR REAR SIDE FRNT".split()
)
_RE_ORDINAL = re.compile(r"\d+(?:ST|ND|RD|TH)")
_RE_US_POSTAL = re.compile(r"\d{5}(?:-\d{4})?")
_US_ISO = ("USA", "PRI", "GUM", "VIR", "MNP", "ASM")


class Recorder:
    """Collects the pipeline decisions of one explained call."""

    __slots__ = ("supplied", "events", "parse_path")

    def __init__(self, supplied: Dict[str, str]) -> None:
        self.supplied = dict(supplied)
        self.events: List[Dict[str, Any]] = []
        self.parse_path: Optional[str] = None

    def current(self, field: str) -> str:
        """The field's value as the pipeline last left it (the supplied value until an event changes it)."""
        for event in reversed(self.events):
            if event["field"] == field:
                return event["after"]
        return self.supplied.get(field, "")

    def add(self, field: str, after: str, rule: str, detail: Optional[Dict[str, Any]] = None) -> None:
        self.events.append(
            {"field": field, "before": self.current(field), "after": after, "rule": rule, "detail": dict(detail or {})}
        )

    def country(self, country_raw: str, country_iso: str, state_raw: str, postal_raw: str,
                script_iso: Optional[str]) -> None:
        """Record why a missing country became ``country_iso`` (called only when no country was supplied)."""
        if script_iso and country_iso == script_iso:
            rule, detail = "country_inferred_from_script", {"script_country": script_iso}
        elif state_raw.strip():
            rule, detail = "country_inferred_from_state", {"state": state_raw}
        elif postal_raw.strip():
            rule, detail = "country_inferred_from_postal", {"postal_code": postal_raw}
        elif country_iso == "USA":
            rule, detail = "country_defaulted_us", {}
        else:
            rule, detail = "country_inferred_from_text", {}
        self.add("country", country_iso, rule, detail)


def current_recorder() -> Optional[Recorder]:
    """The recorder of the explained call in progress, or None (always None on default calls)."""
    return _RECORDER.get()


# ---------------------------------------------------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------------------------------------------------

def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _key(text: str, fold: bool = True) -> str:
    base = _fold(text) if fold else unicodedata.normalize("NFKC", text)
    return " ".join(re.sub(r"[^\w\s]|_", " ", base).upper().split())


def _tokens(text: str) -> List[str]:
    return _key(text).split()


def _distance(a: str, b: str) -> int:
    from address_standardizer.fuzzy import damerau_levenshtein_distance

    return damerau_levenshtein_distance(a, b)


def _surface_rule(before: str, after: str) -> Optional[str]:
    """Rule for a change that only touched case, punctuation/whitespace or accents; None when words differ."""
    if _key(before) != _key(after):
        return None
    if before.strip().upper() == after:
        return "case_normalized"
    if _key(before, fold=False) == _key(after, fold=False):
        return "punctuation_normalized"
    return "diacritics_folded"


def _rec(field: str, before: str, after: str, rule: str, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"field": field, "before": before, "after": after, "rule": rule, "detail": dict(detail or {})}


# ---------------------------------------------------------------------------------------------------------------------
# Street / unit diff
# ---------------------------------------------------------------------------------------------------------------------

def _classify_pair(field: str, a: str, b: str) -> Dict[str, Any]:
    """One replaced token ``a`` -> ``b`` inside a street or unit line."""
    if a in _NUMBER_WORDS:
        return _rec(field, a, b, "number_words_to_digits")
    if STREET_SUFFIXES.get(a) == b:
        return _rec(field, a, b, "street_type_abbreviation")
    if DIRECTIONALS.get(a) == b:
        return _rec(field, a, b, "directional_abbreviation")
    if _RE_ORDINAL.fullmatch(b):
        return _rec(field, a, b, "ordinal_normalized")
    if b in _UNIT_ABBR:
        return _rec(field, a, b, "unit_designator_abbreviation")
    distance = _distance(a, b)
    if distance <= 2 and len(b) >= 3 and a.isalpha() and b.isalpha():
        return _rec(field, a, b, "typo_heal_street", {"candidate": b, "distance": distance})
    return _rec(field, a, b, "token_rewritten")


def _token_diff(field: str, before: str, after: str, moved_out: Optional[Dict[str, str]] = None,
                t_before: Optional[List[str]] = None, t_after: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Token-level records for one street/unit line.

    ``moved_out`` maps tokens that left this line for another field to the rule that explains it (``unit_split`` is
    reported separately, ``locality_moved_from_street`` here): a surplus tail made only of such tokens is not an edit.
    """
    t_before = _tokens(before) if t_before is None else t_before
    t_after = _tokens(after) if t_after is None else t_after
    moved_out = moved_out or {}
    out: List[Dict[str, Any]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, t_before, t_after, autojunk=False).get_opcodes():
        old, new = t_before[i1:i2], t_after[j1:j2]
        surplus = old[len(new):]
        if surplus and (op == "delete" or i2 == len(t_before)) and all(t in moved_out for t in surplus):
            old = old[: len(new)]
            if "locality_moved_from_street" in {moved_out[t] for t in surplus}:
                out.append(_rec(field, " ".join(surplus), "", "locality_moved_from_street", {"tokens": surplus}))
            if not old:
                continue
        if op == "replace" and len(old) == len(new):
            out.extend(_classify_pair(field, a, b) for a, b in zip(old, new))
        elif op == "replace":
            rule = "number_words_to_digits" if any(t in _NUMBER_WORDS for t in old) else "token_rewritten"
            out.append(_rec(field, " ".join(old), " ".join(new), rule))
        elif op == "insert":
            rule = "unit_designator_inserted" if all(t in _UNIT_ABBR for t in new) else "tokens_inserted"
            out.append(_rec(field, "", " ".join(new), rule))
        elif op == "delete":
            out.append(_rec(field, " ".join(old), "", "tokens_removed", {"tokens": old}))
    return out


def _line_records(field: str, before: str, after: str, **kwargs: Any) -> List[Dict[str, Any]]:
    if before == after:
        return []
    surface = _surface_rule(before, after)
    if surface is not None:
        return [_rec(field, before, after, surface)]
    return _token_diff(field, before, after, **kwargs)


def _street_records(rec: Recorder, std: Any) -> List[Dict[str, Any]]:
    b1, b2 = rec.current("street1"), rec.current("street2")
    a1, a2 = std.street1, std.street2
    if std.is_private_residence:
        return [_rec("street1", b1, a1, "private_residence_detected")]
    t_b1, t_b2, t_a1, t_a2 = _tokens(b1), _tokens(b2), _tokens(a1), _tokens(a2)
    if not a1 and a2 and b1.strip():
        return [_rec("street1", b1, "", "street1_moved_to_street2", {"street2": a2})]
    gained = [t for t in t_a1 if t not in t_b1]
    if gained and set(gained) <= set(t_b2):
        return [_rec("street1", b1, a1, "secondary_promoted_to_street", {"from": "street2", "tokens": gained})]
    out: List[Dict[str, Any]] = []
    moved: Dict[str, str] = {}
    new_unit = [t for t in t_a2 if t not in t_b2]
    if new_unit and new_unit[-1] in t_b1 and len(t_a1) < len(t_b1):
        removed = [t for t in t_b1 if t not in t_a1]
        if a2 != std.building_name:  # a leading building name is reported as building_name_extracted instead
            out.append(_rec("street2", b2, a2, "unit_split", {"unit": a2, "moved_from_street1": " ".join(removed)}))
        moved.update({t: "unit_split" for t in removed})
        a2 = b2  # the unit line is fully explained by the split
    # City/state/postal text that was cut out of the street line when those fields were empty.
    for field, value in (("city", std.city), ("state", std.state), ("postal_code", std.postal_code)):
        if not rec.current(field).strip():
            moved.update({t: "locality_moved_from_street" for t in _tokens(value)})
    if t_b1 and t_a1 and t_b1[-1].isdigit() and t_a1[0] == t_b1[-1] and t_b1[0] != t_a1[0]:
        out.append(_rec("street1", t_b1[-1], t_a1[0], "house_number_moved_to_front"))
        t_b1, t_a1 = t_b1[:-1], t_a1[1:]
        out.extend(_token_diff("street1", b1, a1, moved, t_b1, t_a1))
    else:
        out.extend(_line_records("street1", b1, a1, moved_out=moved))
    out.extend(_line_records("street2", b2, a2))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Field diffs
# ---------------------------------------------------------------------------------------------------------------------

def _city_records(rec: Recorder, std: Any) -> List[Dict[str, Any]]:
    before, after = rec.current("city"), std.city
    if before == after:
        return []
    if not before.strip():
        return [_rec("city", before, after, "city_inferred_from_text")]
    if not after:
        return [_rec("city", before, after, "city_discarded")]
    surface = _surface_rule(before, after)
    if surface is not None:
        return [_rec("city", before, after, surface)]
    distance = _distance(_key(before), _key(after))
    if std.is_us and distance <= 2:
        return [_rec("city", before, after, "typo_heal_city",
                     {"candidate": after, "distance": distance, "supplied": before})]
    return [_rec("city", before, after, "city_canonicalized", {"distance": distance})]


def _zip_state(postal: str) -> Optional[str]:
    digits = re.sub(r"\D", "", postal or "")
    return ZIP3_TO_STATE.get(digits[:3]) if len(digits) >= 5 else None


def _state_records(rec: Recorder, std: Any) -> List[Dict[str, Any]]:
    before, after = rec.current("state"), std.state
    if before == after:
        return []
    if not before.strip():
        expected = _zip_state(rec.supplied.get("postal_code", ""))
        if expected is not None and expected == after:
            return [_rec("state", before, after, "state_from_zip", {"postal_code": rec.supplied["postal_code"]})]
        return [_rec("state", before, after, "state_inferred_from_text")]
    surface = _surface_rule(before, after)
    if surface is not None:
        return [_rec("state", before, after, surface)]
    if US_STATES.get(before.strip().upper()) == after:
        return [_rec("state", before, after, "state_abbreviated")]
    return [_rec("state", before, after, "state_normalized")]


def _postal_records(rec: Recorder, std: Any) -> List[Dict[str, Any]]:
    before, after = rec.current("postal_code"), std.postal_code
    if before == after:
        return []
    if not before.strip():
        return [_rec("postal_code", before, after, "postal_extracted_from_text")]
    if not after:
        return [_rec("postal_code", before, after, "postal_discarded")]
    c_before, c_after = re.sub(r"[\s-]", "", before.upper()), re.sub(r"[\s-]", "", after.upper())
    if c_before != c_after and len(c_before) == len(c_after) and sorted(c_before) == sorted(c_after):
        return [_rec("postal_code", before, after, "postal_transposition_healed")]
    return [_rec("postal_code", before, after, "postal_normalized")]


def _country_records(rec: Recorder, std: Any) -> List[Dict[str, Any]]:
    before, after = rec.current("country"), std.country
    if before == after:
        return []
    if not before.strip():
        return [_rec("country", before, after, "country_defaulted_us")]  # early exits never reach the detector
    surface = _surface_rule(before, after)
    if surface is not None:
        return [_rec("country", before, after, surface)]
    return [_rec("country", before, after, "country_normalized", {"as_supplied": before})]


def _postal_valid(std: Any) -> Optional[bool]:
    postal = (std.postal_code or "").strip()
    if not postal:
        return None
    if std.country in _US_ISO:
        return bool(_RE_US_POSTAL.fullmatch(postal))
    from address_standardizer.international.postal import validate_postal_code

    return bool(validate_postal_code(postal, std.country))


def _outcome_records(std: Any, rec: Recorder) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if std.is_registered_agent_hub:
        out.append(_rec("street1", std.street1, std.street1, "registered_agent_hub_detected"))
    if std.address_status == "parse_failed":
        out.append(_rec("street1", rec.supplied.get("street1", ""), "", "parse_failed"))
    elif std.is_locality_only:
        out.append(_rec("street1", rec.supplied.get("street1", ""), "", "locality_only_accepted"))
    expected = _zip_state(std.postal_code) if std.is_us else None
    if expected is not None and std.state and std.state != expected and not any(
        e["rule"] == "state_corrected_from_zip" for e in rec.events
    ):
        out.append(_rec("state", std.state, std.state, "zip_state_mismatch_kept",
                        {"zip_state": expected, "postal_code": std.postal_code}))
    if _postal_valid(std) is False:
        out.append(_rec("postal_code", std.postal_code, std.postal_code, "postal_format_invalid",
                        {"country": std.country}))
    return out


_REFERENCE_RULES = {
    "confirmed": ("postal_code", "reference_confirmed"),
    "postal_unknown": ("postal_code", "reference_postal_unknown"),
    "place_mismatch": ("city", "reference_place_mismatch"),
    "state_mismatch": ("state", "reference_state_mismatch"),
}


def _reference_records(std: Any) -> List[Dict[str, Any]]:
    validation = std.reference_validation
    if validation is None:
        return []
    field, rule = _REFERENCE_RULES.get(validation.status, ("postal_code", "reference_not_checked"))
    value = getattr(std, field)
    detail = {"status": validation.status, "provider": validation.provider, "checks": list(validation.checks),
              "detail": validation.detail}
    if validation.candidate_places:
        detail["candidate_places"] = list(validation.candidate_places)
    return [_rec(field, value, value, rule, detail)]


def build_trace(rec: Recorder, std: Any) -> List[Dict[str, Any]]:
    """The ordered change records: pipeline events, then per-field normalisations, then validation outcomes."""
    out = [dict(e) for e in rec.events]
    out.extend(_country_records(rec, std))
    out.extend(_street_records(rec, std))
    out.extend(_city_records(rec, std))
    dep = std.dependent_locality
    if dep:
        source = next((f for f in ("city", "street1") if _key(dep) in _key(rec.current(f))), None)
        out.append(_rec("dependent_locality", "", dep, "dependent_locality_extracted", {"moved_from": source}))
    name = std.building_name
    if name:
        source = next((f for f in ("street1", "street2") if _key(name) in _key(rec.current(f))), None)
        out.append(_rec("building_name", "", name, "building_name_extracted", {"moved_from": source}))
    out.extend(_state_records(rec, std))
    out.extend(_postal_records(rec, std))
    out.extend(_outcome_records(std, rec))
    out.extend(_reference_records(std))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Evidence for field confidence
# ---------------------------------------------------------------------------------------------------------------------

def build_evidence(rec: Recorder, std: Any, trace: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarise the observable evidence behind each field (input of ``compute_field_confidence``)."""
    rules: Dict[str, List[str]] = {}
    distances: Dict[str, int] = {}
    for record in trace:
        rules.setdefault(record["field"], []).append(record["rule"])
        if "distance" in record["detail"]:
            distances[record["field"]] = max(distances.get(record["field"], 0), record["detail"]["distance"])
    expected = _zip_state(std.postal_code) if std.is_us else None
    zip_state = None
    if expected is not None and std.state:
        zip_state = "agree" if std.state == expected else "mismatch"
    validation = std.reference_validation
    return {
        "supplied": {f: bool(rec.supplied.get(f, "").strip()) for f in _FIELDS},
        "rules": rules,
        "distances": distances,
        "parse_path": rec.parse_path,
        "postal_valid": _postal_valid(std),
        "zip_state": zip_state,
        "reference_status": validation.status if validation is not None else None,
    }


# ---------------------------------------------------------------------------------------------------------------------
# Alternatives
# ---------------------------------------------------------------------------------------------------------------------

_WEAK_COUNTRY_RULES = frozenset({"country_inferred_from_postal", "country_inferred_from_text", "country_defaulted_us"})
_COUNTRY_PRIORITY = ("USA", "CAN", "GBR", "AUS", "DEU", "FRA", "ESP", "ITA", "MEX", "BRA", "IND", "JPN", "NLD", "NZL")


def _alt(changes: Dict[str, str], reason: str, score: float) -> Dict[str, Any]:
    return {"changes": dict(changes), "reason": reason, "score": round(score, 3)}


def _rerun(base_kwargs: Dict[str, Any], **overrides: Any) -> Any:
    """Re-standardize with some inputs replaced; never finalizes, so no ledger writes, and never caches."""
    from address_standardizer.standardizer import standardize_address

    kwargs = dict(base_kwargs)
    kwargs.update(overrides)
    kwargs.update(finalize=False, use_cache=False, enable_geocoding=False, reference_provider=None,
                  explain=False, alternatives=0, calibrator=None)
    return standardize_address(**kwargs)


def _changes(base: Any, other: Any) -> Dict[str, str]:
    return {f: getattr(other, f) for f in _FIELDS if getattr(other, f) != getattr(base, f)}


def _country_alternatives(std: Any, rec: Recorder, base_kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
    # An inference from a recognised state/province or from the script is strong evidence; only the weak ones are ambiguous.
    inferred = any(e["rule"] in _WEAK_COUNTRY_RULES for e in rec.events)
    postal = rec.supplied.get("postal_code", "").strip()
    if not inferred or not postal:
        return []
    from address_standardizer.international.countries import CountryRegistry
    from address_standardizer.international.postal import POSTAL_RULES, validate_postal_code

    plausible = [
        c.alpha3 for c in CountryRegistry.all_countries()
        if c.alpha3 != std.country and c.alpha3 in POSTAL_RULES and validate_postal_code(postal, c.alpha3)
    ]
    rank = {iso: i for i, iso in enumerate(_COUNTRY_PRIORITY)}
    plausible.sort(key=lambda iso: (rank.get(iso, len(rank)), iso))
    out = []
    for iso in plausible[:MAX_ALTERNATIVES]:
        other = _rerun(base_kwargs, country=iso)
        changes = _changes(std, other)
        changes["country"] = iso
        # Common destinations rank above obscure ones that merely share a digit pattern.
        out.append(_alt(changes, f"postal code {postal} is also a valid {iso} format; no country was supplied",
                        0.4 if iso in rank else 0.1))
    return out


def _city_alternatives(std: Any, rec: Recorder) -> List[Dict[str, Any]]:
    supplied = rec.supplied.get("city", "").strip()
    if not std.is_us or not supplied:
        return []
    from address_standardizer._patterns import MULTI_WORD_CITIES
    from address_standardizer.fuzzy import PROMINENT_STATE_CITIES

    clean = _key(supplied)
    if clean in MULTI_WORD_CITIES or any(clean in cities for cities in PROMINENT_STATE_CITIES.values()):
        return []  # a known city is never rewritten, so there is nothing ambiguous to offer
    state = std.state if std.state in PROMINENT_STATE_CITIES else ""
    pool = list(PROMINENT_STATE_CITIES.get(state, ()))
    max_distance = 2
    if not state:
        max_distance = 1
        pool = [c for cities in PROMINENT_STATE_CITIES.values() for c in cities]
    pool.extend(sorted(MULTI_WORD_CITIES))
    scored = sorted({(d, c) for c in pool for d in (_distance(clean, c),) if d <= max_distance and c != std.city})
    out = [_alt({"city": c}, f"{c} is {d} edit(s) from the supplied city '{supplied}'", max(0.05, 0.5 - 0.15 * d))
           for d, c in scored[:MAX_ALTERNATIVES]]
    if std.city != clean:
        out.append(_alt({"city": clean}, "the supplied spelling may already be correct", 0.4))
    return out


def _unit_alternatives(std: Any, trace: List[Dict[str, Any]], rec: Recorder) -> List[Dict[str, Any]]:
    split = next((r for r in trace if r["rule"] == "unit_split"), None)
    if split is None:
        return []
    whole = rec.current("street1").strip().upper()
    return [_alt({"street1": whole, "street2": rec.current("street2").strip().upper()},
                 f"treat '{split['detail']['unit']}' as part of the street line instead of a separate unit", 0.3)]


def build_alternatives(std: Any, rec: Recorder, trace: List[Dict[str, Any]], base_kwargs: Dict[str, Any],
                       limit: int) -> List[Dict[str, Any]]:
    """Up to ``limit`` next-best readings, best score first (ties keep a stable, deterministic order)."""
    found = (
        _country_alternatives(std, rec, base_kwargs)
        + _city_alternatives(std, rec)
        + _unit_alternatives(std, trace, rec)
    )
    found.sort(key=lambda a: -a["score"])  # stable: equal scores keep country, city, unit order
    return found[: max(0, min(int(limit), MAX_ALTERNATIVES))]


# ---------------------------------------------------------------------------------------------------------------------
# Entry point (called by standardize_address)
# ---------------------------------------------------------------------------------------------------------------------

def standardize_explained(explain: bool, alternatives: int, calibrator: Optional[Any],
                          call_kwargs: Dict[str, Any]) -> Any:
    """Run one standardization with a recorder attached and add the requested explanation data to the result."""
    from address_standardizer.standardizer import standardize_address

    street = call_kwargs.get("street1")
    if street is None:
        street = call_kwargs.get("street")
    supplied = {
        "street1": coerce_text(street),
        "street2": coerce_text(call_kwargs.get("street2")),
        "city": coerce_text(call_kwargs.get("city")),
        "state": coerce_text(call_kwargs.get("state")),
        "postal_code": coerce_text(call_kwargs.get("postal_code")),
        "country": coerce_text(call_kwargs.get("country")),
    }
    rec = Recorder(supplied)
    call = dict(call_kwargs)
    call.update(use_cache=False, explain=False, alternatives=0, calibrator=None)
    token = _RECORDER.set(rec)
    try:
        std = standardize_address(**call)
    finally:
        _RECORDER.reset(token)
    trace = build_trace(rec, std)
    if explain:
        std.explanation = trace
        std.field_confidence = compute_field_confidence(std, build_evidence(rec, std, trace), calibrator)
    if alternatives:
        std.alternatives = build_alternatives(std, rec, trace, call, alternatives)
    return std

