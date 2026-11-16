"""Precision/Recall Calibration and Threshold Evaluation Benchmark Harness."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from entity_standardizer.joint import StandardizedContact
from entity_standardizer.scoring import ScoredEntityMatch, explain_and_score_entities


@dataclass(slots=True)
class LabeledEntityPair:
    """Labeled ground-truth pair for evaluating precision, recall, F1, and trap resistance."""

    left: StandardizedContact | dict[str, Any]
    right: StandardizedContact | dict[str, Any]
    expected_match: bool
    external_id_left: str | None = None
    external_id_right: str | None = None
    crd_left: str | None = None
    crd_right: str | None = None
    roster_left: Iterable[str] | None = None
    roster_right: Iterable[str] | None = None
    label_reason: str = ""


@dataclass(slots=True)
class CalibrationReport:
    """Summary precision, recall, F1, false-positive rate, and threshold sweep recommendations."""

    total_pairs: int
    positive_pairs: int
    negative_pairs: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    potential_flags: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    match_threshold: float
    potential_threshold: float
    recommended_match_threshold: float
    recommended_potential_threshold: float
    recommended_f1: float
    signal_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize calibration metrics to a JSON-compatible dictionary."""
        return {
            "total_pairs": self.total_pairs,
            "positive_pairs": self.positive_pairs,
            "negative_pairs": self.negative_pairs,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "potential_flags": self.potential_flags,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "match_threshold": self.match_threshold,
            "potential_threshold": self.potential_threshold,
            "recommended_match_threshold": self.recommended_match_threshold,
            "recommended_potential_threshold": self.recommended_potential_threshold,
            "recommended_f1": round(self.recommended_f1, 4),
            "signal_stats": {k: dict(v) for k, v in self.signal_stats.items()},
        }


def _compute_prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) > 0.0 else 0.0
    return round(prec, 4), round(rec, 4), round(f1, 4)


def recommend_threshold_adjustments(
    scored_outcomes: Sequence[tuple[float, bool]],
    *,
    candidates: Sequence[float] = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85),
) -> tuple[float, float, float]:
    """Sweep candidate match thresholds and return (best_match_threshold, suggested_potential_threshold, best_f1)."""
    best_thr = 0.70
    best_f1 = -1.0
    for thr in candidates:
        tp = sum(1 for sc, exp in scored_outcomes if sc >= thr and exp)
        fp = sum(1 for sc, exp in scored_outcomes if sc >= thr and not exp)
        fn = sum(1 for sc, exp in scored_outcomes if sc < thr and exp)
        _, _, f1 = _compute_prf(tp, fp, fn)
        if f1 > best_f1:
            best_f1 = f1
            best_thr = round(float(thr), 2)
    pot_thr = round(max(0.40, best_thr - 0.20), 2)
    return best_thr, pot_thr, round(max(0.0, best_f1), 4)


def evaluate_scoring_calibration(
    pairs: Sequence[LabeledEntityPair],
    *,
    match_threshold: float = 0.70,
    potential_threshold: float = 0.50,
    switchboard_phones: Iterable[str] | None = None,
) -> CalibrationReport:
    """Evaluate precision, recall, F1, false-positive rate, and signal attribution over labeled pairs."""
    tp = fp = tn = fn = pot_flags = 0
    pos_total = neg_total = 0
    signal_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0})
    raw_outcomes: list[tuple[float, bool]] = []

    for pair in pairs:
        res: ScoredEntityMatch = explain_and_score_entities(
            pair.left,
            pair.right,
            external_id_a=pair.external_id_left,
            external_id_b=pair.external_id_right,
            crd_a=pair.crd_left,
            crd_b=pair.crd_right,
            member_roster_a=pair.roster_left,
            member_roster_b=pair.roster_right,
            switchboard_phones=switchboard_phones,
            match_threshold=match_threshold,
            potential_threshold=potential_threshold,
        )
        raw_outcomes.append((res.score, pair.expected_match))
        if pair.expected_match:
            pos_total += 1
        else:
            neg_total += 1

        if res.is_match:
            if pair.expected_match:
                tp += 1
                for sig in res.matched_signals:
                    signal_stats[sig]["tp"] += 1
            else:
                fp += 1
                for sig in res.matched_signals:
                    signal_stats[sig]["fp"] += 1
        else:
            if pair.expected_match:
                fn += 1
            else:
                tn += 1
            if res.is_potential_match:
                pot_flags += 1

    prec, rec, f1 = _compute_prf(tp, fp, fn)
    fpr = round(fp / neg_total, 4) if neg_total > 0 else 0.0
    rec_thr, rec_pot, rec_f1 = recommend_threshold_adjustments(raw_outcomes)

    return CalibrationReport(
        total_pairs=len(pairs),
        positive_pairs=pos_total,
        negative_pairs=neg_total,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        potential_flags=pot_flags,
        precision=prec,
        recall=rec,
        f1=f1,
        false_positive_rate=fpr,
        match_threshold=match_threshold,
        potential_threshold=potential_threshold,
        recommended_match_threshold=rec_thr,
        recommended_potential_threshold=rec_pot,
        recommended_f1=rec_f1,
        signal_stats=dict(signal_stats),
    )
