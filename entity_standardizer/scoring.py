"""Multi-Signal Partial-Match Candidate Scoring and Plain-English Match Explanation Engine."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from entity_standardizer.address.models import extract_street_core_key
from entity_standardizer.company import compare_companies, extract_company_acronym, resolve_brand_lineage
from entity_standardizer.dedup import compare_addresses, compare_phones
from entity_standardizer.group import score_member_rosters
from entity_standardizer.identifiers import compare_external_ids, standardize_crd
from entity_standardizer.joint import StandardizedContact, standardize_contact
from entity_standardizer.person import compare_persons
from entity_standardizer.web import compare_emails, compare_urls


class MatchDisposition(StrEnum):
    """Calibrated resolution tier produced by multi-signal entity scoring."""

    EXACT_MATCH = "EXACT_MATCH"
    STRONG_MATCH = "STRONG_MATCH"
    PROBABLE_MATCH = "PROBABLE_MATCH"
    POTENTIAL_MATCH = "POTENTIAL_MATCH"
    NO_MATCH = "NO_MATCH"


class EntityScoringProfile(StrEnum):
    """Domain-calibrated matching & review threshold presets."""

    FIRM = "FIRM"
    OFFICE = "OFFICE"
    CONTACT = "CONTACT"
    PARTNERSHIP = "PARTNERSHIP"
    TEAM = "TEAM"


_PROFILE_THRESHOLDS: dict[EntityScoringProfile, tuple[float, float]] = {
    EntityScoringProfile.FIRM: (0.72, 0.50),
    EntityScoringProfile.OFFICE: (0.70, 0.50),
    EntityScoringProfile.CONTACT: (0.70, 0.50),
    EntityScoringProfile.PARTNERSHIP: (0.70, 0.50),
    EntityScoringProfile.TEAM: (0.70, 0.50),
}


def synthesize_domain_match(
    profile: str | EntityScoringProfile,
    evidence: Sequence[SignalEvidence],
    *,
    hard_id_matched: bool = False,
) -> ScoredEntityMatch:
    """Score & explain an entity pair using a canonical domain profile ('FIRM', 'OFFICE', 'CONTACT', 'PARTNERSHIP', 'TEAM')."""
    prof = profile if isinstance(profile, EntityScoringProfile) else EntityScoringProfile(str(profile).upper())
    m_thr, p_thr = _PROFILE_THRESHOLDS[prof]
    return synthesize_scored_match(
        evidence,
        match_threshold=m_thr,
        potential_threshold=p_thr,
        hard_id_matched=hard_id_matched,
    )


@dataclass(slots=True)
class SignalEvidence:
    """Single standardized signal contribution (corroborating or conflicting) toward an entity pair score."""

    signal: str
    weight: float
    detail: str
    is_conflict: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize signal evidence to a JSON-compatible dictionary."""
        return {
            "signal": self.signal,
            "weight": round(self.weight, 4),
            "detail": self.detail,
            "is_conflict": self.is_conflict,
        }


@dataclass(slots=True)
class ScoredEntityMatch:
    """Calibrated multi-signal entity match & partial-candidate evaluation with plain-English explanation."""

    is_match: bool
    is_potential_match: bool
    score: float
    score_100: float
    disposition: str
    matched_signal_count: int
    matched_signals: tuple[str, ...]
    conflicting_signals: tuple[str, ...]
    explanation: str
    evidence: tuple[SignalEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the scored entity match result to a JSON-compatible dictionary."""
        return {
            "is_match": self.is_match,
            "is_potential_match": self.is_potential_match,
            "score": round(self.score, 4),
            "score_100": round(self.score_100, 2),
            "disposition": self.disposition,
            "matched_signal_count": self.matched_signal_count,
            "matched_signals": list(self.matched_signals),
            "conflicting_signals": list(self.conflicting_signals),
            "explanation": self.explanation,
            "evidence": [ev.to_dict() for ev in self.evidence],
        }


def synthesize_scored_match(
    evidence: Sequence[SignalEvidence],
    *,
    match_threshold: float = 0.70,
    potential_threshold: float = 0.50,
    hard_id_matched: bool = False,
) -> ScoredEntityMatch:
    """Combine independent positive/conflicting signal weights via noisy-OR into a calibrated score & explanation."""
    pos_ev = [e for e in evidence if not e.is_conflict and e.weight > 0.0]
    neg_ev = [e for e in evidence if e.is_conflict]

    if not pos_ev:
        expl = "No matching standardized signals."
        if neg_ev:
            expl += " Populated differences: " + "; ".join(e.detail for e in neg_ev) + "."
        return ScoredEntityMatch(
            is_match=False,
            is_potential_match=False,
            score=0.0,
            score_100=0.0,
            disposition=MatchDisposition.NO_MATCH.value,
            matched_signal_count=0,
            matched_signals=(),
            conflicting_signals=tuple(e.signal for e in neg_ev),
            explanation=expl,
            evidence=tuple(evidence),
        )

    complement = 1.0
    for ev in pos_ev:
        clamped = min(0.99, max(0.0, ev.weight))
        complement *= 1.0 - clamped
    raw_pos = 1.0 - complement

    penalty = min(0.28, sum(abs(e.weight) for e in neg_ev))
    if hard_id_matched:
        final_score = round(min(1.0, max(0.96, raw_pos - 0.25 * penalty)), 4)
    else:
        final_score = round(max(0.0, min(0.98, raw_pos - penalty)), 4)

    score_100 = round(100.0 * final_score, 2)
    is_match = final_score >= match_threshold
    is_potential = (not is_match) and (final_score >= potential_threshold)

    if final_score >= 0.95:
        disp = MatchDisposition.EXACT_MATCH.value
    elif final_score >= 0.85:
        disp = MatchDisposition.STRONG_MATCH.value
    elif is_match:
        disp = MatchDisposition.PROBABLE_MATCH.value
    elif is_potential:
        disp = MatchDisposition.POTENTIAL_MATCH.value
    else:
        disp = MatchDisposition.NO_MATCH.value

    pos_sigs = tuple(e.signal for e in pos_ev)
    neg_sigs = tuple(e.signal for e in neg_ev)
    sig_cnt = len(pos_sigs)
    pos_text = "; ".join(e.detail for e in pos_ev)

    if is_match:
        expl = f"Matched (score {score_100:.1f}/100 on {sig_cnt} signal{'s' if sig_cnt != 1 else ''}): {pos_text}."
        if neg_ev:
            expl += " Populated differences: " + "; ".join(e.detail for e in neg_ev) + "."
    elif is_potential:
        expl = f"Potential partial match (score {score_100:.1f}/100 on {sig_cnt} signal{'s' if sig_cnt != 1 else ''}): {pos_text}."
        if neg_ev:
            expl += " Does not fully match on: " + "; ".join(e.detail for e in neg_ev) + "."
    else:
        expl = f"Below threshold (score {score_100:.1f}/100 on {sig_cnt} signal{'s' if sig_cnt != 1 else ''}): {pos_text}."
        if neg_ev:
            expl += " Conflicts: " + "; ".join(e.detail for e in neg_ev) + "."

    return ScoredEntityMatch(
        is_match=is_match,
        is_potential_match=is_potential,
        score=final_score,
        score_100=score_100,
        disposition=disp,
        matched_signal_count=sig_cnt,
        matched_signals=pos_sigs,
        conflicting_signals=neg_sigs,
        explanation=expl,
        evidence=tuple(evidence),
    )


def _coerce_contact(item: StandardizedContact | dict[str, Any]) -> StandardizedContact:
    if isinstance(item, StandardizedContact):
        return item
    return standardize_contact(**item)


def explain_and_score_entities(
    entity_a: StandardizedContact | dict[str, Any],
    entity_b: StandardizedContact | dict[str, Any],
    *,
    external_id_a: str | None = None,
    external_id_b: str | None = None,
    crd_a: str | None = None,
    crd_b: str | None = None,
    member_roster_a: Iterable[str] | None = None,
    member_roster_b: Iterable[str] | None = None,
    match_threshold: float = 0.70,
    potential_threshold: float = 0.50,
) -> ScoredEntityMatch:
    """Evaluate all standardized pillars, lineage/acronyms, street cores, and rosters to score & explain a pair."""
    ca = _coerce_contact(entity_a)
    cb = _coerce_contact(entity_b)
    ev: list[SignalEvidence] = []
    hard_id = False

    # 1. External CRM ID & Regulatory CRD
    if external_id_a and external_id_b:
        id_cmp = compare_external_ids(external_id_a, external_id_b)
        if id_cmp.is_match:
            hard_id = True
            ev.append(SignalEvidence("EXTERNAL_ID", 0.97, f"matching external ID ({id_cmp.id_b.canonical_id})"))
        elif id_cmp.id_a.is_valid and id_cmp.id_b.is_valid:
            ev.append(
                SignalEvidence(
                    "EXTERNAL_ID",
                    0.06,
                    f"external ID differs ({id_cmp.id_a.canonical_id} vs {id_cmp.id_b.canonical_id})",
                    is_conflict=True,
                )
            )

    scrd_a = standardize_crd(crd_a) if crd_a else None
    scrd_b = standardize_crd(crd_b) if crd_b else None
    if scrd_a and scrd_b and scrd_a.is_valid and scrd_b.is_valid:
        if scrd_a.canonical_id == scrd_b.canonical_id:
            hard_id = True
            ev.append(SignalEvidence("FINRA_CRD", 0.96, f"exact FINRA CRD ({scrd_a.canonical_id})"))
        else:
            ev.append(
                SignalEvidence(
                    "FINRA_CRD",
                    0.10,
                    f"FINRA CRD differs ({scrd_a.canonical_id} vs {scrd_b.canonical_id})",
                    is_conflict=True,
                )
            )

    # 2. Person Name (Exact / Root / Multi-Root Diminutive / Edit-1 / Initial)
    if ca.person and cb.person and ca.person.is_valid and cb.person.is_valid:
        p_cmp = compare_persons(ca.person, cb.person)
        if p_cmp.is_match:
            w_p = 0.46 if p_cmp.score >= 0.95 else (0.38 if p_cmp.score >= 0.89 else 0.30)
            ev.append(
                SignalEvidence(
                    f"PERSON_{p_cmp.match_type}",
                    w_p,
                    f"person name matches via {p_cmp.match_type} ('{ca.person.full_name}' == '{cb.person.full_name}')",
                )
            )
        else:
            ev.append(
                SignalEvidence(
                    "PERSON_NAME",
                    0.12,
                    f"person name differs ('{ca.person.full_name}' vs '{cb.person.full_name}')",
                    is_conflict=True,
                )
            )

    # 3. Organization / Brand / M&A Lineage / Acronym
    same_org = False
    if ca.organization and cb.organization and ca.organization.is_valid and cb.organization.is_valid:
        o_cmp = compare_companies(ca.organization, cb.organization)
        if o_cmp.is_match:
            same_org = True
            if o_cmp.match_type == "BRAND_LINEAGE_MATCH":
                fam = resolve_brand_lineage(ca.organization)
                ev.append(
                    SignalEvidence(
                        "ORG_BRAND_LINEAGE",
                        0.38,
                        f"affiliated M&A brand family {fam} ('{ca.organization.legal_name}' <-> '{cb.organization.legal_name}')",
                    )
                )
            elif o_cmp.match_type == "ACRONYM_MATCH":
                acr = extract_company_acronym(ca.organization)
                ev.append(
                    SignalEvidence(
                        "ORG_ACRONYM",
                        0.34,
                        f"organization acronym {acr} ('{ca.organization.legal_name}' <-> '{cb.organization.legal_name}')",
                    )
                )
            else:
                w_o = 0.44 if o_cmp.score >= 0.94 else 0.36
                ev.append(
                    SignalEvidence(
                        "ORGANIZATION_NAME",
                        w_o,
                        f"organization matches via {o_cmp.match_type} ('{ca.organization.legal_name}' == '{cb.organization.legal_name}')",
                    )
                )
        else:
            ev.append(
                SignalEvidence(
                    "ORGANIZATION_NAME",
                    0.08,
                    f"organization differs ('{ca.organization.legal_name}' vs '{cb.organization.legal_name}')",
                    is_conflict=True,
                )
            )

    # 4. Validated Address / Building / Directionless Street Core / Locality
    aa, ab = ca.address, cb.address
    if aa.normalized_address_key and ab.normalized_address_key:
        a_cmp = compare_addresses(aa, ab)
        if a_cmp.is_match:
            w_a = 0.42 if a_cmp.score >= 0.96 else 0.36
            ev.append(
                SignalEvidence(
                    "VALIDATED_ADDRESS",
                    w_a,
                    f"address matches via {a_cmp.match_type} ({aa.street1}, {aa.city}, {aa.state} {aa.postal_code})",
                )
            )
        else:
            core_a = extract_street_core_key(f"{aa.street1} {aa.street2}".strip())
            core_b = extract_street_core_key(f"{ab.street1} {ab.street2}".strip())
            z5_a = (aa.postal_code or "")[:5]
            z5_b = (ab.postal_code or "")[:5]
            if core_a and core_a == core_b and z5_a and z5_a == z5_b:
                ev.append(
                    SignalEvidence(
                        "STREET_CORE_AND_ZIP5",
                        0.35,
                        f"matching street core '{core_a}' in ZIP {z5_a} ('{aa.street1}' <-> '{ab.street1}')",
                    )
                )
            elif z5_a and z5_a == z5_b:
                ev.append(SignalEvidence("POSTAL_ZIP5", 0.18, f"same 5-digit ZIP ({z5_a})"))
                ev.append(
                    SignalEvidence(
                        "STREET_ADDRESS",
                        0.05,
                        f"street differs ('{aa.street1}' vs '{ab.street1}')",
                        is_conflict=True,
                    )
                )
            elif aa.state and aa.state == ab.state and (aa.postal_city or aa.city) == (ab.postal_city or ab.city):
                ev.append(SignalEvidence("CITY_STATE", 0.15, f"same city/state ({aa.city}, {aa.state})"))
                ev.append(
                    SignalEvidence(
                        "STREET_ADDRESS",
                        0.06,
                        f"street differs ('{aa.street1}' vs '{ab.street1}')",
                        is_conflict=True,
                    )
                )
            else:
                ev.append(
                    SignalEvidence(
                        "ADDRESS",
                        0.08,
                        f"address differs ('{aa.street1}, {aa.city}, {aa.state}' vs '{ab.street1}, {ab.city}, {ab.state}')",
                        is_conflict=True,
                    )
                )

    # 5. Phone (with Toll-Free Guard) & Fax
    if ca.phone.is_valid and cb.phone.is_valid:
        ph_cmp = compare_phones(ca.phone, cb.phone)
        if ph_cmp.is_exact_match or ph_cmp.is_extension_variant:
            if ca.phone.is_toll_free or cb.phone.is_toll_free:
                ev.append(SignalEvidence("TOLL_FREE_PHONE", 0.10, f"shared toll-free phone ({ca.phone.e164})"))
            else:
                ev.append(SignalEvidence("DIRECT_PHONE", 0.38, f"matching local phone ({ca.phone.e164})"))
        else:
            ev.append(
                SignalEvidence(
                    "PHONE",
                    0.04,
                    f"phone differs ({ca.phone.e164} vs {cb.phone.e164})",
                    is_conflict=True,
                )
            )

    if ca.fax and cb.fax and ca.fax.is_valid and cb.fax.is_valid and ca.fax.e164 == cb.fax.e164:
        ev.append(SignalEvidence("FAX", 0.30, f"matching fax ({ca.fax.e164})"))

    # 6. Email & Website Domain
    if ca.email and cb.email and ca.email.is_valid and cb.email.is_valid:
        em_cmp = compare_emails(ca.email, cb.email)
        if em_cmp.is_match:
            w_em = 0.48 if not ca.email.is_role_account else 0.24
            ev.append(SignalEvidence("EMAIL", w_em, f"matching email ({ca.email.email})"))
        elif not ca.email.is_free_provider and ca.email.domain == cb.email.domain:
            ev.append(SignalEvidence("CORPORATE_EMAIL_DOMAIN", 0.18, f"shared corporate email domain (@{ca.email.domain})"))
        else:
            ev.append(
                SignalEvidence(
                    "EMAIL",
                    0.06,
                    f"email differs ({ca.email.email} vs {cb.email.email})",
                    is_conflict=True,
                )
            )

    if ca.website and cb.website and ca.website.is_valid and cb.website.is_valid:
        u_cmp = compare_urls(ca.website, cb.website)
        if u_cmp.is_match or ca.website.domain == cb.website.domain:
            ev.append(SignalEvidence("WEBSITE_DOMAIN", 0.32, f"matching website domain ({ca.website.domain})"))

    # 7. Member Roster Overlap (Partnerships / Teams / Shared Branch Advisors)
    if member_roster_a is not None and member_roster_b is not None:
        r_res = score_member_rosters(member_roster_a, member_roster_b, same_firm=same_org)
        if r_res.is_match:
            ev.append(
                SignalEvidence(
                    "MEMBER_ROSTER",
                    min(0.60, 0.45 + 0.15 * r_res.jaccard),
                    f"{r_res.shared_count} shared roster member(s) ({r_res.match_type}, Jaccard {r_res.jaccard:.2f})",
                )
            )
        elif r_res.is_partial_candidate:
            ev.append(
                SignalEvidence(
                    "PARTIAL_MEMBER_ROSTER",
                    0.34,
                    f"{r_res.shared_count} shared roster member(s) ({r_res.size_a} vs {r_res.size_b}, Jaccard {r_res.jaccard:.2f})",
                )
            )
        elif r_res.match_type == "DISJOINT_ROSTERS":
            ev.append(SignalEvidence("MEMBER_ROSTER", 0.10, "member rosters are disjoint", is_conflict=True))

    return synthesize_scored_match(
        ev,
        match_threshold=match_threshold,
        potential_threshold=potential_threshold,
        hard_id_matched=hard_id,
    )
