"""Steward review UI support: the static page, the pending-record listing and the decision (override) logic.

The review surface is **off by default**. ``review_enabled`` turns it on when API-key authentication is configured or
``ADDRESS_STANDARDIZER_ENABLE_REVIEW_UI=1`` is set explicitly. The page itself (``static/review.html``) is public and
holds no data and no secrets; every record it shows is fetched from ``GET /v1/audit`` with the steward's API key.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from address_standardizer.audit import ReviewStatus, StewardshipAuditLedger

ENABLE_ENV = "ADDRESS_STANDARDIZER_ENABLE_REVIEW_UI"
PAGE_PATH = "/review"
NONCE_PLACEHOLDER = "__CSP_NONCE__"
EDITABLE_FIELDS = ("street1", "street2", "city", "state", "postal_code", "country")
DECISIONS = {"approve": ReviewStatus.APPROVED, "modify": ReviewStatus.MODIFIED, "reject": ReviewStatus.REJECTED}
MAX_LIST = 500

_STATIC = Path(__file__).resolve().parent / "static" / "review.html"


def review_enabled(has_auth: bool, env: Mapping[str, str]) -> bool:
    """True when the review UI and its audit endpoints should be served."""
    return has_auth or env.get(ENABLE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def render_page() -> Tuple[str, Dict[str, str]]:
    """The page with a fresh CSP nonce substituted, and the headers that lock it down (no external origins at all)."""
    nonce = secrets.token_urlsafe(18)
    html = _STATIC.read_text(encoding="utf-8").replace(NONCE_PLACEHOLDER, nonce)
    csp = (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
        "connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    return html, {"Content-Security-Policy": csp, "Cache-Control": "no-store"}


def _explain_record(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-run the (side-effect free) standardization of the original input with explain=True."""
    from address_standardizer.standardizer import standardize_address

    std = standardize_address(
        street1=raw.get("street1"), street2=raw.get("street2"), city=raw.get("city"), state=raw.get("state"),
        postal_code=raw.get("postal_code"), country=raw.get("country"),
        allow_locality=bool(raw.get("allow_locality")), finalize=False, explain=True, alternatives=3,
    )
    return {
        "explanation": std.explanation, "field_confidence": std.field_confidence, "alternatives": std.alternatives,
    }


def list_records(ledger: StewardshipAuditLedger, status: str, limit: int) -> List[Dict[str, Any]]:
    """Audit records with the given review status, newest first, each with a freshly computed explanation.

    ``finalize=False`` keeps the re-run from writing new audit records, so listing never changes the ledger.
    """
    out = []
    for record in ledger.list_records(review_status=status, limit=limit):
        item = record.as_dict()
        item.update(_explain_record(record.raw_input_payload))
        out.append(item)
    return out


def apply_decision(
    ledger: StewardshipAuditLedger,
    audit_id: str,
    steward_id: str,
    decision: str,
    overrides: Optional[Mapping[str, str]] = None,
    commentary: str = "",
) -> Dict[str, Any]:
    """Approve, modify or reject one record via ``StewardshipAuditLedger.apply_manual_override``.

    Raises ``KeyError`` for an unknown ``audit_id`` and ``ValueError`` for an unknown decision or override field.
    """
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    changes = dict(overrides or {})
    unknown = sorted(set(changes) - set(EDITABLE_FIELDS))
    if unknown:
        raise ValueError(f"cannot override unknown field(s): {', '.join(unknown)}")
    if decision != "modify":
        changes = {}  # approve commits the proposed values as they are; reject commits nothing
    updated = ledger.apply_manual_override(
        audit_id, steward_id, changes, commentary=commentary, review_status=DECISIONS[decision]
    )
    return updated.as_dict()
