"""
Confidence calibration utilities (pure Python, no numpy).
=========================================================
The composite confidence score produced by :mod:`address_standardizer.confidence` is a *heuristic*: a weighted
sum of rule-based sub-scores. It is not a probability. Given ``(score, was_correct)`` pairs from an evaluation
set with independent ground truth, this module measures how well the score tracks observed correctness
(reliability bins, Expected Calibration Error, Brier score) and fits a monotone (isotonic) mapping from raw score
to observed accuracy.

Nothing here changes default scoring behaviour; a fitted :class:`Calibrator` is applied only when explicitly
passed to ``compute_confidence_score(..., calibrator=...)`` or called directly.
"""

import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

Pair = Tuple[float, Union[bool, int, float]]

CALIBRATOR_FORMAT_VERSION = 1


@dataclass(frozen=True)
class ReliabilityBin:
    """One equal-width confidence bin: ``lower <= score < upper`` (the last bin also includes 1.0)."""

    lower: float
    upper: float
    count: int
    mean_confidence: float
    accuracy: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "mean_confidence": self.mean_confidence,
            "accuracy": self.accuracy,
        }


def _validate(pairs: Iterable[Pair]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for score, correct in pairs:
        score = float(score)
        if not 0.0 <= score <= 1.0:  # also rejects NaN
            raise ValueError(f"confidence score {score!r} is outside [0, 1]")
        out.append((score, 1.0 if correct else 0.0))
    if not out:
        raise ValueError("at least one (score, was_correct) pair is required")
    return out


def reliability_bins(pairs: Iterable[Pair], n_bins: int = 10) -> List[ReliabilityBin]:
    """Equal-width reliability bins. Empty bins are omitted."""
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    data = _validate(pairs)
    sums_conf = [0.0] * n_bins
    sums_ok = [0.0] * n_bins
    counts = [0] * n_bins
    for score, ok in data:
        idx = min(int(score * n_bins), n_bins - 1)
        sums_conf[idx] += score
        sums_ok[idx] += ok
        counts[idx] += 1
    return [
        ReliabilityBin(i / n_bins, (i + 1) / n_bins, counts[i], sums_conf[i] / counts[i], sums_ok[i] / counts[i])
        for i in range(n_bins)
        if counts[i]
    ]


def expected_calibration_error(pairs: Iterable[Pair], n_bins: int = 10) -> float:
    """ECE: count-weighted mean of |accuracy - mean confidence| over the reliability bins."""
    data = _validate(pairs)
    total = len(data)
    return sum(b.count / total * abs(b.accuracy - b.mean_confidence) for b in reliability_bins(data, n_bins))


def brier_score(pairs: Iterable[Pair]) -> float:
    """Mean squared error between score and the 0/1 outcome (lower is better)."""
    data = _validate(pairs)
    return sum((s - ok) ** 2 for s, ok in data) / len(data)


class Calibrator:
    """Monotone non-decreasing piecewise-linear map from raw score to calibrated probability of correctness."""

    def __init__(self, xs: Sequence[float], ys: Sequence[float], n_samples: int = 0) -> None:
        if not xs or len(xs) != len(ys):
            raise ValueError("xs and ys must be non-empty and of equal length")
        if any(b <= a for a, b in zip(xs, xs[1:])):
            raise ValueError("xs must be strictly increasing")
        if any(b < a for a, b in zip(ys, ys[1:])):
            raise ValueError("ys must be non-decreasing")
        if not all(0.0 <= float(v) <= 1.0 for v in list(xs) + list(ys)):
            raise ValueError("xs and ys must lie in [0, 1]")
        self.xs: List[float] = [float(v) for v in xs]
        self.ys: List[float] = [float(v) for v in ys]
        self.n_samples = int(n_samples)

    def calibrate(self, score: float) -> float:
        """Map a raw score to a calibrated value; scores outside the fitted range are clamped to its ends."""
        score = float(score)
        if score <= self.xs[0]:
            return self.ys[0]
        if score >= self.xs[-1]:
            return self.ys[-1]
        i = bisect_right(self.xs, score)
        x0, x1 = self.xs[i - 1], self.xs[i]
        y0, y1 = self.ys[i - 1], self.ys[i]
        return y0 + (y1 - y0) * (score - x0) / (x1 - x0)

    def to_dict(self) -> Dict[str, Any]:
        return {"version": CALIBRATOR_FORMAT_VERSION, "method": "isotonic", "n_samples": self.n_samples,
                "xs": self.xs, "ys": self.ys}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Calibrator":
        if data.get("version") != CALIBRATOR_FORMAT_VERSION:
            raise ValueError(f"unsupported calibrator version {data.get('version')!r}")
        return cls(data["xs"], data["ys"], data.get("n_samples", 0))

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Calibrator":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def fit_isotonic(pairs: Iterable[Pair]) -> Calibrator:
    """Fit an isotonic regression (pool-adjacent-violators) of correctness on score."""
    data = sorted(_validate(pairs))
    # Identical scores form one atomic group, so ties are never split by the pooling below.
    groups: List[List[float]] = []  # [score, sum_ok, count]
    for score, ok in data:
        if groups and groups[-1][0] == score:
            groups[-1][1] += ok
            groups[-1][2] += 1
        else:
            groups.append([score, ok, 1])
    # Pool adjacent violators. Blocks are [sum_score, sum_ok, weight].
    blocks: List[List[float]] = []
    for score, sum_ok, count in groups:
        blocks.append([score * count, sum_ok, count])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] >= blocks[-1][1] / blocks[-1][2]:
            last = blocks.pop()
            blocks[-1][0] += last[0]
            blocks[-1][1] += last[1]
            blocks[-1][2] += last[2]
    xs = [b[0] / b[2] for b in blocks]
    ys = [b[1] / b[2] for b in blocks]
    return Calibrator(xs, ys, n_samples=len(data))


def calibrate_score(score: float, calibrator: Optional[Calibrator]) -> float:
    """Map ``score`` through ``calibrator``; with no calibrator the score is returned unchanged."""
    return float(score) if calibrator is None else calibrator.calibrate(score)
