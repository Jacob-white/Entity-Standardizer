"""Stewardship Audit Ledger and Diagnostic Explainability Engine for Phone Standardizer."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from entity_standardizer.intelligence import (
    evaluate_calling_window,
    resolve_carrier_hint,
    resolve_locality,
    resolve_timezones,
)
from entity_standardizer.models import PhoneRoutingTier, StandardizedPhone
from entity_standardizer.standardizer import standardize_phone


def explain_phone(
    raw_phone: str | None,
    country: str | None = None,
    default_country: str = "US",
    address_context: Any = None,
    utc_dt: datetime | None = None,
) -> dict[str, Any]:
    """Return a rich diagnostic & intelligence report explaining how a phone number was processed."""
    record = standardize_phone(
        raw_phone,
        country=country,
        default_country=default_country,
        address_context=address_context,
    )
    locality = resolve_locality(record.country_calling_code, record.area_code)
    timezones = resolve_timezones(record.country_iso2, record.region_code)
    carrier_hint = resolve_carrier_hint(record.country_iso2, record.national_significant_number)
    window = evaluate_calling_window(timezones, utc_dt=utc_dt)

    return {
        "record": record.to_dict(),
        "intelligence": {
            "locality": locality,
            "timezones": list(timezones),
            "carrier_hint": carrier_hint,
            "is_callable_now": window.is_callable_now,
            "local_hours": list(window.local_hours),
        },
        "explanation": {
            "healing_steps_count": len(record.healing_actions),
            "healing_actions": list(record.healing_actions),
            "risk_flags_count": len(record.risk_flags),
            "risk_flags": list(record.risk_flags),
            "confidence": record.confidence,
            "routing_tier": record.routing_tier,
            "requires_human_review": record.routing_tier != PhoneRoutingTier.AUTO_PASS,
        },
    }


class PhoneStewardshipLedger:
    """SQLite-backed audit ledger for tracking and resolving low-confidence or quarantined phone records."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._closed = False
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS phone_stewardship_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_input TEXT NOT NULL,
                    e164 TEXT,
                    country_iso2 TEXT,
                    confidence REAL NOT NULL,
                    routing_tier TEXT NOT NULL,
                    risk_flags_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    resolution_note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def record_if_flagged(self, phone: StandardizedPhone) -> int | None:
        """Log a StandardizedPhone record to the ledger if its routing tier is not AUTO_PASS."""
        if phone.routing_tier == PhoneRoutingTier.AUTO_PASS:
            return None
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO phone_stewardship_ledger (
                    raw_input, e164, country_iso2, confidence, routing_tier, risk_flags_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    phone.raw_input,
                    phone.e164,
                    phone.country_iso2,
                    phone.confidence,
                    phone.routing_tier,
                    json.dumps(list(phone.risk_flags)),
                    now_iso,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid) if cur.lastrowid is not None else None

    def list_pending(self) -> list[dict[str, Any]]:
        """Return all pending stewardship records."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, raw_input, e164, country_iso2, confidence, routing_tier, risk_flags_json, status, resolution_note
                FROM phone_stewardship_ledger
                WHERE status = 'PENDING'
                ORDER BY id ASC
                """
            ).fetchall()
        return [
            {
                "id": r[0],
                "raw_input": r[1],
                "e164": r[2],
                "country_iso2": r[3],
                "confidence": r[4],
                "routing_tier": r[5],
                "risk_flags": json.loads(r[6]),
                "status": r[7],
                "resolution_note": r[8],
            }
            for r in rows
        ]

    def resolve_entry(self, entry_id: int, status: str = "APPROVED", note: str = "") -> bool:
        """Mark a quarantined ledger record as APPROVED or REJECTED."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE phone_stewardship_ledger SET status = ?, resolution_note = ? WHERE id = ?",
                (status, note, entry_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

    def __enter__(self) -> PhoneStewardshipLedger:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

