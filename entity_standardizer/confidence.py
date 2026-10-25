"""Fraud, Fictitious Range, Bogus Pattern Detection, and Composite Confidence Scoring."""

from __future__ import annotations

from entity_standardizer.models import PhoneLineType, PhoneRiskFlag, PhoneRoutingTier

# UK Ofcom TV & Drama reserved prefixes (NSN without leading 0)
_UK_OFCOM_FICTITIOUS_PREFIXES: tuple[str, ...] = (
    "1632960",
    "1134960",
    "1144960",
    "1154960",
    "1164960",
    "1174960",
    "1184960",
    "1214960",
    "1314960",
    "1414960",
    "1514960",
    "1914980",
    "2079460",
    "2896496",
    "2920180",
    "7700900",
    "8081570",
    "9098790",
)

_SEQUENTIAL_RUNS: tuple[str, ...] = (
    "0123456",
    "1234567",
    "2345678",
    "3456789",
    "9876543",
    "8765432",
    "7654321",
    "6543210",
)


def is_fictitious_number(calling_code: str | None, nsn: str | None) -> bool:
    """Return True if the number falls within an official fictitious/TV/drama range."""
    if not calling_code or not nsn:
        return False
    if calling_code == "1" and len(nsn) == 10:
        nxx = nsn[3:6]
        line = nsn[6:10]
        if nxx == "555" and "0100" <= line <= "0199":
            return True
    if calling_code == "44":
        if nsn.startswith(_UK_OFCOM_FICTITIOUS_PREFIXES):
            return True
    return False


def has_repeating_subscriber_digits(subscriber: str | None) -> bool:
    """Return True if a subscriber number (>=6 digits) consists of a single repeated digit."""
    if not subscriber or len(subscriber) < 6:
        return False
    tail = subscriber[-7:] if len(subscriber) >= 7 else subscriber
    return len(set(tail)) == 1


def has_sequential_subscriber_digits(subscriber: str | None) -> bool:
    """Return True if a subscriber number contains a 7-digit sequential run."""
    if not subscriber or len(subscriber) < 7:
        return False
    return any(run in subscriber for run in _SEQUENTIAL_RUNS)


def evaluate_confidence_and_risk(
    *,
    is_valid: bool,
    is_possible: bool,
    calling_code: str | None,
    nsn: str | None,
    subscriber: str | None,
    line_type: str,
    recognized_sub_area: bool,
    healing_actions: list[str],
    extra_risk_flags: list[str],
) -> tuple[float, str, tuple[str, ...]]:
    """Compute (confidence_score, routing_tier, risk_flags) for a standardized phone record."""
    flags: list[str] = list(extra_risk_flags)

    if is_fictitious_number(calling_code, nsn) and PhoneRiskFlag.FICTITIOUS_RANGE not in flags:
        flags.append(PhoneRiskFlag.FICTITIOUS_RANGE)

    if has_repeating_subscriber_digits(subscriber) and PhoneRiskFlag.REPEATING_DIGITS not in flags:
        flags.append(PhoneRiskFlag.REPEATING_DIGITS)

    if has_sequential_subscriber_digits(subscriber) and PhoneRiskFlag.SEQUENTIAL_DIGITS not in flags:
        flags.append(PhoneRiskFlag.SEQUENTIAL_DIGITS)

    if line_type == PhoneLineType.PREMIUM_RATE and PhoneRiskFlag.PREMIUM_RATE_IRSF_RISK not in flags:
        flags.append(PhoneRiskFlag.PREMIUM_RATE_IRSF_RISK)

    if not is_possible or not is_valid:
        base_score = 0.25 if is_possible else 0.0
        return round(base_score, 4), PhoneRoutingTier.MANUAL_STEWARDSHIP, tuple(flags)

    score = 1.0
    if not recognized_sub_area:
        score -= 0.08
    if PhoneRiskFlag.FICTITIOUS_RANGE in flags:
        score -= 0.12
    if PhoneRiskFlag.PREMIUM_RATE_IRSF_RISK in flags:
        score -= 0.10
    if PhoneRiskFlag.ADDRESS_COUNTRY_MISMATCH in flags:
        score -= 0.08
    if PhoneRiskFlag.REPEATING_DIGITS in flags or PhoneRiskFlag.SEQUENTIAL_DIGITS in flags:
        score -= 0.30

    # Minor confidence deduction for aggressive legacy mobile healing
    if any(
        act in healing_actions
        for act in (
            "LEGACY_MEXICO_MOBILE_1_STRIPPED",
            "ARGENTINA_MOBILE_15_HEALED",
            "BRAZIL_MOBILE_9_INSERTED",
        )
    ):
        score -= 0.03

    score = max(0.0, min(1.0, round(score, 4)))
    if score >= 0.95:
        tier = PhoneRoutingTier.AUTO_PASS
    elif score >= 0.80:
        tier = PhoneRoutingTier.FUZZY_REVIEW
    else:
        tier = PhoneRoutingTier.MANUAL_STEWARDSHIP

    return score, tier, tuple(flags)
