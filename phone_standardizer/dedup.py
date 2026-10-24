"""Telephony Fuzzy Matching, Keypad/Transposition Distance, Blocking Keys, and Contact Entity Resolution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import re
from typing import Any

from phone_standardizer.models import StandardizedPhone
from phone_standardizer.standardizer import standardize_phone

# Standard ITU-T E.161 / telephone keypad physical adjacency graph
_KEYPAD_ADJACENCY: dict[str, frozenset[str]] = {
    "1": frozenset({"2", "4"}),
    "2": frozenset({"1", "3", "5"}),
    "3": frozenset({"2", "6"}),
    "4": frozenset({"1", "5", "7"}),
    "5": frozenset({"2", "4", "6", "8"}),
    "6": frozenset({"3", "5", "9"}),
    "7": frozenset({"4", "8"}),
    "8": frozenset({"5", "7", "9", "0"}),
    "9": frozenset({"6", "8"}),
    "0": frozenset({"8"}),
}

_CA_POSTAL_RE = re.compile(
    r"^[A-CEGHJ-NPR-TVXY]\d[A-CEGHJ-NPR-TV-Z][\s-]?\d[A-CEGHJ-NPR-TV-Z]\d$",
    re.IGNORECASE,
)
_GB_POSTAL_RE = re.compile(
    r"^[A-Z]{1,2}\d[A-Z\d]?(?:\s*\d(?:[A-Z]{2})?)?$",
    re.IGNORECASE,
)
_JE_POSTAL_RE = re.compile(r"^JE\d", re.IGNORECASE)
_GY_POSTAL_RE = re.compile(r"^GY\d", re.IGNORECASE)
_IM_POSTAL_RE = re.compile(r"^IM\d", re.IGNORECASE)
_BM_POSTAL_RE = re.compile(r"^[0-9]?[A-Z]{2}\s?(?:\d{2}|[A-Z]{2})$", re.IGNORECASE)
_KY_POSTAL_RE = re.compile(r"^KY\d-", re.IGNORECASE)
_JP_POSTAL_RE = re.compile(r"^(?:〒\s*)?\d{3}-\d{4}$")
_BR_POSTAL_RE = re.compile(r"^\d{5}-\d{3}$")
_NL_POSTAL_RE = re.compile(r"^\d{4}\s?[A-Z]{2}$", re.IGNORECASE)
_IE_POSTAL_RE = re.compile(
    r"^[AC-FHKNPRTV-Y]\d[\dW]\s?[0-9AC-FHKNPRTV-Y]{4}$",
    re.IGNORECASE,
)
_PL_POSTAL_RE = re.compile(r"^\d{2}-\d{3}$")
_US_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")


def infer_country_from_postal_code(postal_code: str | None) -> str | None:
    """Infer an ISO 3166-1 alpha-2 country code from distinctive postal/ZIP formats."""
    if not postal_code or not str(postal_code).strip():
        return None
    cleaned = str(postal_code).strip()
    if _CA_POSTAL_RE.match(cleaned):
        return "CA"
    if _JE_POSTAL_RE.match(cleaned):
        return "JE"
    if _GY_POSTAL_RE.match(cleaned):
        return "GG"
    if _IM_POSTAL_RE.match(cleaned):
        return "IM"
    if _KY_POSTAL_RE.match(cleaned):
        return "KY"
    if _GB_POSTAL_RE.match(cleaned):
        return "GB"
    if _BM_POSTAL_RE.match(cleaned):
        return "BM"
    if _JP_POSTAL_RE.match(cleaned):
        return "JP"
    if _BR_POSTAL_RE.match(cleaned):
        return "BR"
    if _NL_POSTAL_RE.match(cleaned):
        return "NL"
    if _IE_POSTAL_RE.match(cleaned):
        return "IE"
    if _PL_POSTAL_RE.match(cleaned):
        return "PL"
    if _US_ZIP_RE.match(cleaned):
        return "US"
    return None


def are_keypad_adjacent(digit_a: str, digit_b: str) -> bool:
    """Return True if two single ASCII digits are physically adjacent on a standard telephone keypad."""
    return digit_b in _KEYPAD_ADJACENCY.get(digit_a, frozenset())


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Optimal String Alignment (Damerau-Levenshtein) distance between two strings."""
    from phone_standardizer._native_dispatch import damerau_levenshtein_distance_dispatch

    return damerau_levenshtein_distance_dispatch(s1, s2)



def _detect_single_transposition(a: str, b: str) -> bool:
    """Return True if equal-length strings a and b differ by exactly one adjacent swap."""
    if len(a) != len(b) or a == b:
        return False
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    return (
        len(diffs) == 2
        and diffs[1] - diffs[0] == 1
        and a[diffs[0]] == b[diffs[1]]
        and a[diffs[1]] == b[diffs[0]]
    )


def _detect_single_substitution(a: str, b: str) -> tuple[bool, bool]:
    """Return (is_single_sub, is_keypad_adjacent) for two equal-length strings."""
    if len(a) != len(b) or a == b:
        return False, False
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diffs) != 1:
        return False, False
    idx = diffs[0]
    return True, are_keypad_adjacent(a[idx], b[idx])


def _coerce_phone(
    phone: str | StandardizedPhone,
    country: str | None = None,
) -> StandardizedPhone:
    if isinstance(phone, StandardizedPhone):
        return phone
    return standardize_phone(phone, country=country)


@dataclass(frozen=True, slots=True)
class PhoneComparisonResult:
    """Structured result of comparing two telephone numbers for entity resolution."""

    phone_a: StandardizedPhone
    phone_b: StandardizedPhone
    is_exact_match: bool
    is_extension_variant: bool
    is_fuzzy_match: bool
    similarity_score: float
    match_type: str
    edit_distance: int
    transposition_detected: bool
    keypad_adjacent_typo: bool
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize comparison result to a JSON-compatible dictionary."""
        return asdict(self)


def compare_phones(
    phone_a: str | StandardizedPhone,
    phone_b: str | StandardizedPhone,
    country: str | None = None,
    fuzzy_threshold: float = 0.88,
) -> PhoneComparisonResult:
    """Compare two telephone numbers using E.164 equivalence, extension awareness, and keypad/transposition distance."""
    pa = _coerce_phone(phone_a, country=country)
    pb = _coerce_phone(phone_b, country=country)

    nsn_a = pa.national_significant_number or ""
    nsn_b = pb.national_significant_number or ""
    if not nsn_a or not nsn_b:
        return PhoneComparisonResult(
            phone_a=pa,
            phone_b=pb,
            is_exact_match=False,
            is_extension_variant=False,
            is_fuzzy_match=False,
            similarity_score=0.0,
            match_type="DISTINCT",
            edit_distance=max(len(nsn_a), len(nsn_b)),
            transposition_detected=False,
            keypad_adjacent_typo=False,
            explanation="One or both inputs do not contain a valid national significant number.",
        )

    # 1. Exact canonical E.164 match
    if pa.e164 and pa.e164 == pb.e164:
        if pa.extension == pb.extension:
            return PhoneComparisonResult(
                phone_a=pa,
                phone_b=pb,
                is_exact_match=True,
                is_extension_variant=False,
                is_fuzzy_match=True,
                similarity_score=1.0,
                match_type="EXACT_MATCH",
                edit_distance=0,
                transposition_detected=False,
                keypad_adjacent_typo=False,
                explanation=f"Exact canonical E.164 match ({pa.e164}).",
            )
        return PhoneComparisonResult(
            phone_a=pa,
            phone_b=pb,
            is_exact_match=False,
            is_extension_variant=True,
            is_fuzzy_match=0.96 >= fuzzy_threshold,
            similarity_score=0.96,
            match_type="EXTENSION_VARIANT",
            edit_distance=0,
            transposition_detected=False,
            keypad_adjacent_typo=False,
            explanation=(
                f"Identical main E.164 line ({pa.e164}) with different extension "
                f"({pa.extension or 'none'} vs {pb.extension or 'none'})."
            ),
        )

    # 2. Identical NSN across ambiguous country context (only when at least one lacked explicit +CC)
    has_intl_a = bool(re.match(r"^[^\d+]*\+", pa.raw_input.strip())) or (
        "IDD_EXIT_PREFIX_STRIPPED" in pa.healing_actions
    )
    has_intl_b = bool(re.match(r"^[^\d+]*\+", pb.raw_input.strip())) or (
        "IDD_EXIT_PREFIX_STRIPPED" in pb.healing_actions
    )
    if nsn_a == nsn_b and len(nsn_a) >= 7 and not (has_intl_a and has_intl_b):
        score = 0.94
        return PhoneComparisonResult(
            phone_a=pa,
            phone_b=pb,
            is_exact_match=False,
            is_extension_variant=False,
            is_fuzzy_match=score >= fuzzy_threshold,
            similarity_score=score,
            match_type="NATIONAL_EQUIVALENT",
            edit_distance=0,
            transposition_detected=False,
            keypad_adjacent_typo=False,
            explanation=f"Identical National Significant Number ({nsn_a}) across country contexts.",
        )


    # 3. Same country calling code: check single transposition or single-digit typo
    same_cc = pa.country_calling_code == pb.country_calling_code
    if same_cc and len(nsn_a) == len(nsn_b) and len(nsn_a) >= 7:
        if _detect_single_transposition(nsn_a, nsn_b):
            score = 0.92
            return PhoneComparisonResult(
                phone_a=pa,
                phone_b=pb,
                is_exact_match=False,
                is_extension_variant=False,
                is_fuzzy_match=score >= fuzzy_threshold,
                similarity_score=score,
                match_type="ADJACENT_TRANSPOSITION",
                edit_distance=1,
                transposition_detected=True,
                keypad_adjacent_typo=False,
                explanation=f"Single adjacent digit transposition detected ({nsn_a} vs {nsn_b}).",
            )
        is_sub, is_keypad = _detect_single_substitution(nsn_a, nsn_b)
        if is_sub:
            if nsn_a.endswith("00") and nsn_b.endswith("00"):
                score = 0.85
            else:
                score = 0.91 if is_keypad else 0.89
            match_type = "KEYPAD_ADJACENT_TYPO" if is_keypad else "SINGLE_DIGIT_EDIT"
            detail = "keypad-adjacent" if is_keypad else "single-digit"
            return PhoneComparisonResult(
                phone_a=pa,
                phone_b=pb,
                is_exact_match=False,
                is_extension_variant=False,
                is_fuzzy_match=score >= fuzzy_threshold,
                similarity_score=score,
                match_type=match_type,
                edit_distance=1,
                transposition_detected=False,
                keypad_adjacent_typo=is_keypad,
                explanation=f"Single {detail} substitution detected ({nsn_a} vs {nsn_b}).",
            )

    # 4. General Damerau-Levenshtein distance over full E.164 digits
    full_a = f"{pa.country_calling_code or ''}{nsn_a}"
    full_b = f"{pb.country_calling_code or ''}{nsn_b}"
    dist = damerau_levenshtein_distance(full_a, full_b)
    max_len = max(len(full_a), len(full_b))
    raw_sim = max(0.0, round(1.0 - (dist / max_len), 4))
    # Cap multi-edit similarity below 0.85 so 2+ digit mutations do not falsely auto-cluster
    capped_sim = min(raw_sim, 0.84) if dist >= 2 else raw_sim
    final_match_type = "SINGLE_DIGIT_EDIT" if dist == 1 else "DISTINCT"
    final_explanation = (
        "Single-digit edit detected (Damerau-Levenshtein distance=1)."
        if dist == 1
        else f"Distinct telephone numbers (Damerau-Levenshtein distance={dist})."
    )

    return PhoneComparisonResult(
        phone_a=pa,
        phone_b=pb,
        is_exact_match=False,
        is_extension_variant=False,
        is_fuzzy_match=capped_sim >= fuzzy_threshold,
        similarity_score=capped_sim,
        match_type=final_match_type,
        edit_distance=dist,
        transposition_detected=False,
        keypad_adjacent_typo=False,
        explanation=final_explanation,
    )


def generate_phone_blocking_keys(
    phone: str | StandardizedPhone,
    country: str | None = None,
) -> tuple[str, ...]:
    """Generate deterministic multi-pass blocking keys for scalable entity resolution and SQL blocking."""
    parsed = _coerce_phone(phone, country=country)
    nsn = parsed.national_significant_number
    if not nsn:
        return ()

    keys: list[str] = []
    if parsed.e164:
        keys.append(f"e164:{parsed.e164}")
    keys.append(f"nsn:{nsn}")
    if len(nsn) >= 7:
        keys.append(f"tail7:{nsn[-7:]}")
    cc = parsed.country_calling_code or "0"
    sorted_nsn = "".join(sorted(nsn))
    keys.append(f"cc_sorted:{cc}:{sorted_nsn}")
    if len(nsn) >= 7:
        keys.append(f"cc_head6:{cc}:{nsn[:6]}")
        keys.append(f"cc_area_tail4:{cc}:{nsn[:3]}:{nsn[-4:]}")
    return tuple(keys)


def _survivorship_rank(phone: StandardizedPhone) -> tuple[int, float, int, int, int]:
    """Compute a deterministic survivorship priority tuple for electing a Golden Phone Record."""
    return (
        1 if phone.is_valid else 0,
        phone.confidence,
        1 if phone.raw_input.strip().startswith("+") else 0,
        1 if phone.extension else 0,
        len(phone.raw_input.strip()),
    )


@dataclass(frozen=True, slots=True)
class PhoneCluster:
    """A deduplicated cluster of telephone numbers resolved to a single Golden Phone Record."""

    cluster_id: str
    golden_phone: StandardizedPhone
    members: tuple[StandardizedPhone, ...]
    raw_inputs: tuple[str, ...]
    match_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize cluster to a JSON-compatible dictionary."""
        return asdict(self)


def deduplicate_phones(
    phones: Sequence[str | StandardizedPhone],
    country: str | None = None,
    fuzzy_threshold: float = 0.88,
) -> list[PhoneCluster]:
    """Cluster and deduplicate a collection of phone numbers into Golden Phone Records."""
    if not phones:
        return []

    str_cache: dict[str, StandardizedPhone] = {}
    parsed_list: list[StandardizedPhone] = []
    for p in phones:
        if isinstance(p, StandardizedPhone):
            parsed_list.append(p)
        else:
            cp = str_cache.get(p)
            if cp is None:
                cp = standardize_phone(p, country=country)
                str_cache[p] = cp
            parsed_list.append(cp)

    # Pre-group identical (e164, extension, nsn) in O(N) before pairwise bucket indexing
    exact_reps: dict[tuple[str | None, str | None, str | None], int] = {}
    rep_members: dict[int, list[int]] = {}
    rep_unique_phones: dict[int, list[StandardizedPhone]] = {}
    seen_raw_per_rep: dict[int, set[str]] = {}
    match_reasons: dict[int, set[str]] = {}
    buckets: dict[str, list[int]] = {}

    for idx, p in enumerate(parsed_list):
        if p.e164 or p.national_significant_number:
            exact_key = (p.e164, p.extension, p.national_significant_number)
            rep = exact_reps.get(exact_key)
            if rep is not None:
                rep_members[rep].append(idx)
                if p.raw_input not in seen_raw_per_rep[rep]:
                    seen_raw_per_rep[rep].add(p.raw_input)
                    rep_unique_phones[rep].append(p)
                reason = "EXACT_MATCH" if p.e164 else "NATIONAL_EQUIVALENT"
                match_reasons[rep].add(reason)
                continue
            exact_reps[exact_key] = idx
        rep_members[idx] = [idx]
        rep_unique_phones[idx] = [p]
        seen_raw_per_rep[idx] = {p.raw_input}
        match_reasons[idx] = set()
        for key in generate_phone_blocking_keys(p):
            buckets.setdefault(key, []).append(idx)

    parent: dict[int, int] = {r: r for r in rep_members}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int, reason: str) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            if ri < rj:
                parent[rj] = ri
                match_reasons[ri].update(match_reasons[rj])
                match_reasons[ri].add(reason)
            else:
                parent[ri] = rj
                match_reasons[rj].update(match_reasons[ri])
                match_reasons[rj].add(reason)
        else:
            match_reasons[ri].add(reason)

    compared_pairs: set[tuple[int, int]] = set()
    for candidate_indices in buckets.values():
        for i_pos in range(len(candidate_indices)):
            for j_pos in range(i_pos + 1, len(candidate_indices)):
                a_idx = candidate_indices[i_pos]
                b_idx = candidate_indices[j_pos]
                pair = (min(a_idx, b_idx), max(a_idx, b_idx))
                if pair in compared_pairs:
                    continue
                compared_pairs.add(pair)
                cmp_res = compare_phones(
                    parsed_list[a_idx],
                    parsed_list[b_idx],
                    fuzzy_threshold=fuzzy_threshold,
                )
                if cmp_res.is_fuzzy_match:
                    union(a_idx, b_idx, cmp_res.match_type)

    groups: dict[int, list[int]] = {}
    group_candidates: dict[int, list[StandardizedPhone]] = {}
    for rep_idx, m_indices in rep_members.items():
        root = find(rep_idx)
        groups.setdefault(root, []).extend(m_indices)
        group_candidates.setdefault(root, []).extend(rep_unique_phones[rep_idx])

    clusters: list[PhoneCluster] = []
    for cluster_num, root_idx in enumerate(sorted(groups.keys()), start=1):
        member_indices = sorted(groups[root_idx])
        members = tuple(parsed_list[i] for i in member_indices)
        golden = max(group_candidates[root_idx], key=_survivorship_rank)
        reasons = tuple(sorted(match_reasons[root_idx] or {"SINGLETON"}))
        clusters.append(
            PhoneCluster(
                cluster_id=f"PHONE-CLUSTER-{cluster_num:04d}",
                golden_phone=golden,
                members=members,
                raw_inputs=tuple(m.raw_input for m in members),
                match_types=reasons,
            )
        )
    return clusters


@dataclass(frozen=True, slots=True)
class ContactCluster:
    """Unified contact entity cluster combining Phone-Standardizer and Address-Standardizer keys."""

    cluster_id: str
    golden_phone: StandardizedPhone
    golden_address_key: str | None
    record_ids: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    linkage_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize contact cluster to a JSON-compatible dictionary."""
        return asdict(self)


def _is_shared_hub_or_cmra(rec: dict[str, Any]) -> bool:
    """Return True if a contact record or its address_context is flagged as a Registered Agent hub or CMRA."""
    if rec.get("is_registered_agent_hub") or rec.get("is_cmra"):
        return True
    ctx = rec.get("address_context")
    if ctx is None:
        return False
    if isinstance(ctx, dict):
        return bool(ctx.get("is_registered_agent_hub") or ctx.get("is_cmra"))
    return bool(getattr(ctx, "is_registered_agent_hub", False) or getattr(ctx, "is_cmra", False))


def cluster_contact_records(

    records: Sequence[dict[str, Any]],
    phone_field: str = "phone",
    address_key_field: str = "address_key",
    country_field: str = "country",
    postal_code_field: str = "postal_code",
    id_field: str = "id",
    fuzzy_threshold: float = 0.88,
) -> list[ContactCluster]:
    """Perform cross-domain entity resolution over contact records using phone and address keys."""
    if not records:
        return []

    from entity_standardizer.company import standardize_company
    from entity_standardizer.person import standardize_person
    from entity_standardizer.web import standardize_email

    n = len(records)
    parsed_phones: list[StandardizedPhone] = []
    addr_keys: list[str | None] = []
    email_buckets: dict[str, list[int]] = {}
    person_org_buckets: dict[str, list[int]] = {}

    for idx, rec in enumerate(records):
        raw_phone = rec.get(phone_field, "")
        explicit_country = rec.get(country_field)
        postal = rec.get(postal_code_field)
        inferred_country = explicit_country or infer_country_from_postal_code(
            str(postal) if postal is not None else None
        )
        addr_ctx = rec.get("address_context")
        parsed_phones.append(
            standardize_phone(
                str(raw_phone) if raw_phone is not None else "",
                country=str(inferred_country) if inferred_country else None,
                address_context=addr_ctx,
            )
        )
        raw_addr_key = rec.get(address_key_field)
        addr_keys.append(str(raw_addr_key).strip() if raw_addr_key else None)

        raw_email = rec.get("email")
        if raw_email:
            em = standardize_email(str(raw_email))
            if em.is_valid and em.email_key and not em.is_role_account and not em.is_disposable:
                email_buckets.setdefault(em.email_key, []).append(idx)

        raw_org = rec.get("organization") or rec.get("company")
        raw_per = rec.get("person_name") or rec.get("name")
        if raw_org and raw_per:
            comp = standardize_company(str(raw_org))
            per = standardize_person(str(raw_per))
            if comp.is_valid and comp.company_key and per.is_valid and per.person_root_key:
                po_key = f"{comp.company_key}||{per.person_root_key}"
                person_org_buckets.setdefault(po_key, []).append(idx)

    parent = list(range(n))
    reasons: dict[int, set[str]] = {i: set() for i in range(n)}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int, reason: str) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            if ri < rj:
                parent[rj] = ri
                reasons[ri].update(reasons[rj])
                reasons[ri].add(reason)
            else:
                parent[ri] = rj
                reasons[rj].update(reasons[ri])
                reasons[rj].add(reason)
        else:
            reasons[ri].add(reason)

    # 1. Pre-group identical (e164, extension, nsn) in O(N), then link by phone blocking keys + fuzzy comparison
    exact_phone_reps: dict[tuple[str | None, str | None, str | None], int] = {}
    phone_buckets: dict[str, list[int]] = {}
    for idx, p in enumerate(parsed_phones):
        if p.e164 or p.national_significant_number:
            exact_key = (p.e164, p.extension, p.national_significant_number)
            if exact_key in exact_phone_reps:
                reason = "PHONE_EXACT_MATCH" if p.e164 else "PHONE_NATIONAL_EQUIVALENT"
                union(exact_phone_reps[exact_key], idx, reason)
                continue
            exact_phone_reps[exact_key] = idx
        for key in generate_phone_blocking_keys(p):
            phone_buckets.setdefault(key, []).append(idx)

    compared: set[tuple[int, int]] = set()
    for indices in phone_buckets.values():
        for i_pos in range(len(indices)):
            for j_pos in range(i_pos + 1, len(indices)):
                a_idx, b_idx = indices[i_pos], indices[j_pos]
                pair = (min(a_idx, b_idx), max(a_idx, b_idx))
                if pair in compared:
                    continue
                compared.add(pair)
                cmp_res = compare_phones(
                    parsed_phones[a_idx],
                    parsed_phones[b_idx],
                    fuzzy_threshold=fuzzy_threshold,
                )
                if cmp_res.is_fuzzy_match:
                    union(a_idx, b_idx, f"PHONE_{cmp_res.match_type}")

    # 2. Link by shared Address-Standardizer normalized_address_key (excluding CMRA & Registered Agent hubs)
    addr_buckets: dict[str, list[int]] = {}
    for idx, ak in enumerate(addr_keys):
        if ak and not _is_shared_hub_or_cmra(records[idx]):
            addr_buckets.setdefault(ak, []).append(idx)

    for indices in addr_buckets.values():
        for i_pos in range(1, len(indices)):
            union(indices[0], indices[i_pos], "SHARED_ADDRESS_KEY")

    # 3. Link by shared personal email_key
    for indices in email_buckets.values():
        for i_pos in range(1, len(indices)):
            union(indices[0], indices[i_pos], "SHARED_EMAIL_KEY")

    # 4. Link by shared (company_key, person_root_key)
    for indices in person_org_buckets.values():
        for i_pos in range(1, len(indices)):
            union(indices[0], indices[i_pos], "SHARED_PERSON_AND_COMPANY_KEY")


    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)

    clusters: list[ContactCluster] = []
    for cluster_num, (root_idx, member_indices) in enumerate(groups.items(), start=1):
        member_phones = [parsed_phones[i] for i in member_indices]
        golden_phone = max(member_phones, key=_survivorship_rank)
        golden_addr = next((addr_keys[i] for i in member_indices if addr_keys[i]), None)
        rec_ids = tuple(
            str(records[i].get(id_field, f"rec-{i + 1}")) for i in member_indices
        )
        clusters.append(
            ContactCluster(
                cluster_id=f"CONTACT-CLUSTER-{cluster_num:04d}",
                golden_phone=golden_phone,
                golden_address_key=golden_addr,
                record_ids=rec_ids,
                records=tuple(records[i] for i in member_indices),
                linkage_reasons=tuple(sorted(reasons[root_idx] or {"SINGLETON"})),
            )
        )
    return clusters
