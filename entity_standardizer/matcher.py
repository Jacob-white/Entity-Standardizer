"""Generic Cross-System Two-Dataset Blocking, Matching, Cardinality & Explanation Engine."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from entity_standardizer.scoring import (
    MatchDisposition,
    SignalEvidence,
    explain_and_score_entities,
    synthesize_scored_match,
)


def _coerce_records(records: Sequence[Mapping[str, Any]] | Any) -> list[dict[str, Any]]:
    """Coerce a sequence of mappings or an Arrow/Polars table into mutable row dictionaries."""
    if hasattr(records, "to_pylist"):
        return [dict(r) for r in records.to_pylist()]
    if hasattr(records, "to_dicts"):
        return [dict(r) for r in records.to_dicts()]
    return [dict(r) for r in records]


def _extract_block_keys(raw: Sequence[str] | str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        val = raw.strip()
        return (val,) if val else ()
    return tuple(str(item).strip() for item in raw if item is not None and str(item).strip())


def compute_switchboard_phones(
    records: Sequence[Mapping[str, Any]] | Any,
    *,
    phone_field: str = "phone_e164",
    group_field: str | None = None,
    entity_id_field: str | None = None,
    min_shared_count: int = 4,
) -> frozenset[str]:
    """Identify local switchboard E.164 phone numbers shared by >= min_shared_count entities (per group or global)."""
    rows = _coerce_records(records)
    buckets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for idx, row in enumerate(rows):
        phone = str(row.get(phone_field) or "").strip()
        if not phone:
            continue
        group_val = str(row.get(group_field) or "").strip() if group_field else "__GLOBAL__"
        if group_field and not group_val:
            continue
        ent_id = str(row.get(entity_id_field) or idx) if entity_id_field else str(idx)
        buckets[(group_val, phone)].add(ent_id)
    return frozenset(phone for (_, phone), entities in buckets.items() if len(entities) >= min_shared_count)


@dataclass(frozen=True, slots=True)
class BlockingRule:
    """Declarative cross-system blocking & scoring rule for CrossSystemMatcher."""

    name: str
    key_fn: Callable[[dict[str, Any]], Sequence[str] | str | None]
    mode: str = "either_unmatched"
    pair_filter: Callable[[dict[str, Any], dict[str, Any]], bool] | None = None
    evidence_fn: Callable[[dict[str, Any], dict[str, Any]], Sequence[SignalEvidence]] | None = None
    min_jaccard: float = 0.50
    min_containment: float = 0.75
    max_primary_links: int | None = None
    roster_field: str | None = None


@dataclass(slots=True)
class MatchPairResult:
    """Resolved or candidate cross-system match pair with cardinality and plain-English explanation."""

    left_id: str
    right_id: str
    rule_name: str
    disposition: str
    cardinality: str
    score: float
    score_100: float
    explanation: str
    matched_signals: tuple[str, ...]
    conflicting_signals: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize match pair result to a JSON-compatible dictionary."""
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "rule_name": self.rule_name,
            "disposition": self.disposition,
            "cardinality": self.cardinality,
            "score": round(self.score, 4),
            "score_100": round(self.score_100, 2),
            "explanation": self.explanation,
            "matched_signals": list(self.matched_signals),
            "conflicting_signals": list(self.conflicting_signals),
        }


@dataclass(slots=True)
class MatchDatasetSummary:
    """Aggregate coverage, cardinality, and rule attribution metrics across a cross-system run."""

    total_left: int
    total_right: int
    matched_left: int
    matched_right: int
    matched_pairs: int
    potential_pairs: int
    unmatched_left: int
    unmatched_right: int
    cardinality_counts: dict[str, int] = field(default_factory=dict)
    rule_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize dataset summary to a JSON-compatible dictionary."""
        return {
            "total_left": self.total_left,
            "total_right": self.total_right,
            "matched_left": self.matched_left,
            "matched_right": self.matched_right,
            "matched_pairs": self.matched_pairs,
            "potential_pairs": self.potential_pairs,
            "unmatched_left": self.unmatched_left,
            "unmatched_right": self.unmatched_right,
            "cardinality_counts": dict(self.cardinality_counts),
            "rule_counts": dict(self.rule_counts),
        }


_CONTACT_SCORING_FIELDS: tuple[str, ...] = (
    "person_name",
    "organization",
    "street1",
    "street2",
    "city",
    "state",
    "postal_code",
    "country",
    "phone",
    "fax",
    "email",
    "website",
    "job_title",
)


def _extract_contact_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in _CONTACT_SCORING_FIELDS if k in row and row[k] is not None}


def _default_evidence_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    rule_name: str,
    switchboard_phones: frozenset[str],
    match_threshold: float,
    potential_threshold: float,
) -> tuple[float, float, str, str, tuple[str, ...], tuple[str, ...]]:
    scored = explain_and_score_entities(
        _extract_contact_payload(left),
        _extract_contact_payload(right),
        switchboard_phones=switchboard_phones,
        match_threshold=match_threshold,
        potential_threshold=potential_threshold,
    )
    if scored.matched_signal_count == 0 and rule_name:
        fallback = synthesize_scored_match(
            [SignalEvidence(rule_name, 0.90, f"matched on rule {rule_name}")],
            match_threshold=match_threshold,
            potential_threshold=potential_threshold,
        )
        return (
            fallback.score,
            fallback.score_100,
            fallback.disposition,
            fallback.explanation,
            fallback.matched_signals,
            fallback.conflicting_signals,
        )
    return (
        scored.score,
        scored.score_100,
        scored.disposition,
        scored.explanation,
        scored.matched_signals,
        scored.conflicting_signals,
    )


def _score_pair_with_rule(
    left: dict[str, Any],
    right: dict[str, Any],
    rule: BlockingRule,
    switchboard_phones: frozenset[str],
    match_threshold: float,
    potential_threshold: float,
) -> tuple[float, float, str, str, tuple[str, ...], tuple[str, ...]]:
    if rule.evidence_fn is not None:
        ev = rule.evidence_fn(left, right)
        scored = synthesize_scored_match(
            ev,
            match_threshold=match_threshold,
            potential_threshold=potential_threshold,
        )
        return (
            scored.score,
            scored.score_100,
            scored.disposition,
            scored.explanation,
            scored.matched_signals,
            scored.conflicting_signals,
        )
    return _default_evidence_pair(
        left,
        right,
        rule.name,
        switchboard_phones,
        match_threshold,
        potential_threshold,
    )


def _assign_cardinality(results: list[MatchPairResult]) -> dict[str, int]:
    left_deg: dict[str, int] = defaultdict(int)
    right_deg: dict[str, int] = defaultdict(int)
    for res in results:
        left_deg[res.left_id] += 1
        right_deg[res.right_id] += 1
    card_counts: dict[str, int] = {"1:1": 0, "N:1": 0, "1:N": 0, "M:N": 0}
    for res in results:
        ld = left_deg[res.left_id]
        rd = right_deg[res.right_id]
        if ld == 1 and rd == 1:
            res.cardinality = "1:1"
        elif ld > 1 and rd == 1:
            res.cardinality = "1:N"
        elif ld == 1 and rd > 1:
            res.cardinality = "N:1"
        else:
            res.cardinality = "M:N"
        card_counts[res.cardinality] += 1
    return card_counts


class CrossSystemMatcher:
    """Configurable tiered cross-system matcher with blocking, cardinality resolution & explanations."""

    def __init__(
        self,
        left_records: Sequence[Mapping[str, Any]] | Any,
        right_records: Sequence[Mapping[str, Any]] | Any,
        *,
        left_id_col: str = "id",
        right_id_col: str = "id",
    ) -> None:
        self.left_records = _coerce_records(left_records)
        self.right_records = _coerce_records(right_records)
        self.left_id_col = left_id_col
        self.right_id_col = right_id_col

    def _row_id(self, row: dict[str, Any], col: str, idx: int) -> str:
        val = row.get(col)
        return str(val) if val is not None and str(val) != "" else str(idx)

    def _build_right_index(self, key_fn: Callable[[dict[str, Any]], Sequence[str] | str | None]) -> dict[str, list[int]]:
        index: dict[str, list[int]] = defaultdict(list)
        for r_idx, r_row in enumerate(self.right_records):
            for key in _extract_block_keys(key_fn(r_row)):
                index[key].append(r_idx)
        return index

    def match(
        self,
        rules: Sequence[BlockingRule],
        *,
        match_threshold: float = 0.70,
        potential_threshold: float = 0.50,
        switchboard_phones: Iterable[str] | None = None,
    ) -> tuple[list[MatchPairResult], list[MatchPairResult], MatchDatasetSummary]:
        """Run prioritized blocking & scoring rules over the two datasets."""
        sw_set = frozenset(switchboard_phones) if switchboard_phones else frozenset()
        matched_left_idx: set[int] = set()
        matched_right_idx: set[int] = set()
        seen_pairs: set[tuple[int, int]] = set()
        matched_results: list[MatchPairResult] = []
        potential_results: list[MatchPairResult] = []

        for rule in rules:
            right_index = self._build_right_index(rule.key_fn)
            cand_pairs: list[tuple[int, int]] = []
            local_seen: set[tuple[int, int]] = set()

            for l_idx, l_row in enumerate(self.left_records):
                for key in _extract_block_keys(rule.key_fn(l_row)):
                    for r_idx in right_index.get(key, ()):
                        pair = (l_idx, r_idx)
                        if pair in seen_pairs or pair in local_seen:
                            continue
                        if rule.mode == "both_unmatched" and (
                            l_idx in matched_left_idx or r_idx in matched_right_idx
                        ):
                            continue
                        if rule.mode == "either_unmatched" and (
                            l_idx in matched_left_idx and r_idx in matched_right_idx
                        ):
                            continue
                        r_row = self.right_records[r_idx]
                        if rule.pair_filter is not None and not rule.pair_filter(l_row, r_row):
                            continue
                        local_seen.add(pair)
                        cand_pairs.append(pair)

            if rule.mode == "set_jaccard":
                self._apply_set_jaccard_rule(
                    rule,
                    cand_pairs,
                    matched_left_idx,
                    matched_right_idx,
                    seen_pairs,
                    matched_results,
                    potential_results,
                )
            elif rule.mode == "greedy_scored":
                self._apply_greedy_scored_rule(
                    rule,
                    cand_pairs,
                    sw_set,
                    match_threshold,
                    potential_threshold,
                    matched_left_idx,
                    matched_right_idx,
                    seen_pairs,
                    matched_results,
                    potential_results,
                )
            else:
                for l_idx, r_idx in cand_pairs:
                    l_row = self.left_records[l_idx]
                    r_row = self.right_records[r_idx]
                    score, score_100, disp, expl, pos_sigs, neg_sigs = _score_pair_with_rule(
                        l_row,
                        r_row,
                        rule,
                        sw_set,
                        match_threshold,
                        potential_threshold,
                    )
                    if score < potential_threshold and rule.evidence_fn is None:
                        continue
                    seen_pairs.add((l_idx, r_idx))
                    pair_res = MatchPairResult(
                        left_id=self._row_id(l_row, self.left_id_col, l_idx),
                        right_id=self._row_id(r_row, self.right_id_col, r_idx),
                        rule_name=rule.name,
                        disposition=disp,
                        cardinality="1:1",
                        score=score,
                        score_100=score_100,
                        explanation=expl,
                        matched_signals=pos_sigs,
                        conflicting_signals=neg_sigs,
                    )
                    if score >= match_threshold or rule.evidence_fn is None:
                        matched_left_idx.add(l_idx)
                        matched_right_idx.add(r_idx)
                        matched_results.append(pair_res)
                    else:
                        potential_results.append(pair_res)

        card_counts = _assign_cardinality(matched_results)
        rule_counts: dict[str, int] = defaultdict(int)
        for res in matched_results:
            rule_counts[res.rule_name] += 1

        summary = MatchDatasetSummary(
            total_left=len(self.left_records),
            total_right=len(self.right_records),
            matched_left=len(matched_left_idx),
            matched_right=len(matched_right_idx),
            matched_pairs=len(matched_results),
            potential_pairs=len(potential_results),
            unmatched_left=len(self.left_records) - len(matched_left_idx),
            unmatched_right=len(self.right_records) - len(matched_right_idx),
            cardinality_counts=card_counts,
            rule_counts=dict(rule_counts),
        )
        return matched_results, potential_results, summary

    def _apply_set_jaccard_rule(
        self,
        rule: BlockingRule,
        cand_pairs: list[tuple[int, int]],
        matched_left_idx: set[int],
        matched_right_idx: set[int],
        seen_pairs: set[tuple[int, int]],
        matched_results: list[MatchPairResult],
        potential_results: list[MatchPairResult],
    ) -> None:
        roster_key = rule.roster_field or "members"
        scored_cands: list[tuple[float, float, int, int, int]] = []
        for l_idx, r_idx in cand_pairs:
            set_a = {str(x) for x in (self.left_records[l_idx].get(roster_key) or ()) if x}
            set_b = {str(x) for x in (self.right_records[r_idx].get(roster_key) or ()) if x}
            if not set_a or not set_b:
                continue
            shared = len(set_a & set_b)
            union = len(set_a | set_b)
            jaccard = shared / union
            containment = shared / min(len(set_a), len(set_b))
            if jaccard >= rule.min_jaccard or containment >= rule.min_containment:
                scored_cands.append((jaccard, containment, shared, l_idx, r_idx))

        scored_cands.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3], item[4]))
        local_left_primary: set[int] = set()
        local_right_primary: set[int] = set()

        for jaccard, containment, shared, l_idx, r_idx in scored_cands:
            seen_pairs.add((l_idx, r_idx))
            l_row = self.left_records[l_idx]
            r_row = self.right_records[r_idx]
            is_primary = (l_idx not in local_left_primary) and (r_idx not in local_right_primary)
            promote = (rule.max_primary_links != 1 and jaccard >= rule.min_jaccard) or (
                is_primary and jaccard >= rule.min_jaccard
            ) or (containment >= rule.min_containment)
            raw_score = round(max(jaccard, 0.72 if promote else 0.58), 4)
            disp = (
                MatchDisposition.STRONG_MATCH.value
                if raw_score >= 0.85
                else (MatchDisposition.PROBABLE_MATCH.value if promote else MatchDisposition.POTENTIAL_MATCH.value)
            )
            expl = (
                f"Roster overlap on {shared} member(s): Jaccard={jaccard:.2f}, containment={containment:.2f}."
            )
            res = MatchPairResult(
                left_id=self._row_id(l_row, self.left_id_col, l_idx),
                right_id=self._row_id(r_row, self.right_id_col, r_idx),
                rule_name=rule.name,
                disposition=disp,
                cardinality="1:1",
                score=raw_score,
                score_100=round(100.0 * raw_score, 2),
                explanation=expl,
                matched_signals=("MEMBER_ROSTER",),
            )
            if promote:
                local_left_primary.add(l_idx)
                local_right_primary.add(r_idx)
                matched_left_idx.add(l_idx)
                matched_right_idx.add(r_idx)
                matched_results.append(res)
            else:
                potential_results.append(res)

    def _apply_greedy_scored_rule(
        self,
        rule: BlockingRule,
        cand_pairs: list[tuple[int, int]],
        switchboard_phones: frozenset[str],
        match_threshold: float,
        potential_threshold: float,
        matched_left_idx: set[int],
        matched_right_idx: set[int],
        seen_pairs: set[tuple[int, int]],
        matched_results: list[MatchPairResult],
        potential_results: list[MatchPairResult],
    ) -> None:
        scored: list[tuple[float, int, int, MatchPairResult]] = []
        for l_idx, r_idx in cand_pairs:
            l_row = self.left_records[l_idx]
            r_row = self.right_records[r_idx]
            score, score_100, disp, expl, pos_sigs, neg_sigs = _score_pair_with_rule(
                l_row,
                r_row,
                rule,
                switchboard_phones,
                match_threshold,
                potential_threshold,
            )
            if score < potential_threshold:
                continue
            seen_pairs.add((l_idx, r_idx))
            res = MatchPairResult(
                left_id=self._row_id(l_row, self.left_id_col, l_idx),
                right_id=self._row_id(r_row, self.right_id_col, r_idx),
                rule_name=rule.name,
                disposition=disp,
                cardinality="1:1",
                score=score,
                score_100=score_100,
                explanation=expl,
                matched_signals=pos_sigs,
                conflicting_signals=neg_sigs,
            )
            scored.append((score, l_idx, r_idx, res))

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        for score, l_idx, r_idx, res in scored:
            if (
                score >= match_threshold
                and l_idx not in matched_left_idx
                and r_idx not in matched_right_idx
            ):
                matched_left_idx.add(l_idx)
                matched_right_idx.add(r_idx)
                matched_results.append(res)
            else:
                potential_results.append(res)
