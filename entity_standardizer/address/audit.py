"""
Exception Management & Stewardship Audit Ledger.
=================================================
Implements structured audit logging, error taxonomy, and record generation
(address_stewardship_audit_ledger) for addresses requiring manual review or
flagged as corporate formation hubs.

Provides 100% standard library SQLite persistence and SQL generation compatible
with the production PostgreSQL schema defined in Blueprint Section 1.4.3.
"""

import json
import threading
import uuid
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

from entity_standardizer.address.confidence import (
    RoutingTier,
    ConfidenceResult,
    ERR_PARSE_FAILED,
    WARN_TYPO_HEALED,
    ERR_ZIP_STATE_MISMATCH,
)

# PostgreSQL Production DDL (Blueprint Section 1.4.3)
AUDIT_LEDGER_DDL = """CREATE TABLE IF NOT EXISTS address_stewardship_audit_ledger (
    audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_id VARCHAR(64) NOT NULL,
    batch_id VARCHAR(64),
    timestamp_utc TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT clock_timestamp(),
    agent_or_system_id VARCHAR(64) NOT NULL,
    action_type VARCHAR(32) NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,
    failure_reason_codes TEXT[] NOT NULL DEFAULT '{}',
    normalized_address_key VARCHAR(256),
    building_key VARCHAR(256),
    phonetic_key VARCHAR(128),
    is_registered_agent_hub BOOLEAN NOT NULL DEFAULT FALSE,
    is_private_residence BOOLEAN NOT NULL DEFAULT FALSE,
    dpv_confirmation_code CHAR(1),
    raw_input_payload JSONB NOT NULL,
    proposed_standardized_payload JSONB NOT NULL,
    final_committed_payload JSONB NOT NULL,
    steward_commentary TEXT,
    review_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    reviewed_by VARCHAR(64),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_confidence_range CHECK (confidence_score >= 0.0000 AND confidence_score <= 1.0000),
    CONSTRAINT chk_action_type CHECK (action_type IN ('AUTO_PASS', 'AUTO_HEAL', 'MANUAL_OVERRIDE', 'REJECT_UNPARSEABLE')),
    CONSTRAINT chk_review_status CHECK (review_status IN ('PENDING', 'APPROVED', 'MODIFIED', 'REJECTED'))
);"""

SQLITE_AUDIT_LEDGER_DDL = """CREATE TABLE IF NOT EXISTS address_stewardship_audit_ledger (
    audit_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    batch_id TEXT,
    timestamp_utc TEXT NOT NULL,
    agent_or_system_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    failure_reason_codes TEXT NOT NULL,
    normalized_address_key TEXT,
    building_key TEXT,
    phonetic_key TEXT,
    is_registered_agent_hub INTEGER NOT NULL DEFAULT 0,
    is_private_residence INTEGER NOT NULL DEFAULT 0,
    dpv_confirmation_code TEXT,
    raw_input_payload TEXT NOT NULL,
    proposed_standardized_payload TEXT NOT NULL,
    final_committed_payload TEXT NOT NULL,
    steward_commentary TEXT,
    review_status TEXT NOT NULL DEFAULT 'PENDING',
    reviewed_by TEXT,
    reviewed_at TEXT
);"""

# Prior versions of a record that a steward override replaced (the ledger itself stays append-only per audit_id).
SQLITE_AUDIT_HISTORY_DDL = SQLITE_AUDIT_LEDGER_DDL.replace(
    "address_stewardship_audit_ledger", "address_stewardship_audit_history"
).replace("audit_id TEXT PRIMARY KEY,", "history_id INTEGER PRIMARY KEY AUTOINCREMENT, audit_id TEXT NOT NULL,", 1)


class ActionType:
    AUTO_PASS = "AUTO_PASS"
    AUTO_HEAL = "AUTO_HEAL"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    REJECT_UNPARSEABLE = "REJECT_UNPARSEABLE"


class ReviewStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    MODIFIED = "MODIFIED"
    REJECTED = "REJECTED"


@dataclass
class StewardshipAuditRecord:
    """Represents a row in the address_stewardship_audit_ledger."""
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    record_id: str = "REC-0"
    batch_id: Optional[str] = None
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_or_system_id: str = "address_standardizer_v1"
    action_type: str = ActionType.AUTO_PASS
    confidence_score: float = 1.0
    failure_reason_codes: List[str] = field(default_factory=list)
    normalized_address_key: Optional[str] = None
    building_key: Optional[str] = None
    phonetic_key: Optional[str] = None
    is_registered_agent_hub: bool = False
    is_private_residence: bool = False
    dpv_confirmation_code: Optional[str] = None
    raw_input_payload: Dict[str, Any] = field(default_factory=dict)
    proposed_standardized_payload: Dict[str, Any] = field(default_factory=dict)
    final_committed_payload: Dict[str, Any] = field(default_factory=dict)
    steward_commentary: Optional[str] = None
    review_status: str = ReviewStatus.PENDING
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StewardshipAuditRecord":
        """Reconstructs a StewardshipAuditRecord from a dictionary."""
        return cls(
            audit_id=d.get("audit_id") or str(uuid.uuid4()),
            record_id=d.get("record_id", "REC-0"),
            batch_id=d.get("batch_id"),
            timestamp_utc=d.get("timestamp_utc") or datetime.now(timezone.utc).isoformat(),
            agent_or_system_id=d.get("agent_or_system_id", "address_standardizer_v1"),
            action_type=d.get("action_type", ActionType.AUTO_PASS),
            confidence_score=float(d.get("confidence_score", 1.0)),
            failure_reason_codes=list(d.get("failure_reason_codes") or []),
            normalized_address_key=d.get("normalized_address_key"),
            building_key=d.get("building_key"),
            phonetic_key=d.get("phonetic_key"),
            is_registered_agent_hub=bool(d.get("is_registered_agent_hub", False)),
            is_private_residence=bool(d.get("is_private_residence", False)),
            dpv_confirmation_code=d.get("dpv_confirmation_code"),
            raw_input_payload=dict(d.get("raw_input_payload") or {}),
            proposed_standardized_payload=dict(d.get("proposed_standardized_payload") or {}),
            final_committed_payload=dict(d.get("final_committed_payload") or {}),
            steward_commentary=d.get("steward_commentary"),
            review_status=d.get("review_status", ReviewStatus.PENDING),
            reviewed_by=d.get("reviewed_by"),
            reviewed_at=d.get("reviewed_at"),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "record_id": self.record_id,
            "batch_id": self.batch_id,
            "timestamp_utc": self.timestamp_utc,
            "agent_or_system_id": self.agent_or_system_id,
            "action_type": self.action_type,
            "confidence_score": self.confidence_score,
            "failure_reason_codes": list(self.failure_reason_codes),
            "normalized_address_key": self.normalized_address_key,
            "building_key": self.building_key,
            "phonetic_key": self.phonetic_key,
            "is_registered_agent_hub": self.is_registered_agent_hub,
            "is_private_residence": self.is_private_residence,
            "dpv_confirmation_code": self.dpv_confirmation_code,
            "raw_input_payload": self.raw_input_payload,
            "proposed_standardized_payload": self.proposed_standardized_payload,
            "final_committed_payload": self.final_committed_payload,
            "steward_commentary": self.steward_commentary,
            "review_status": self.review_status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
        }

    def to_sql_insert(self) -> str:
        """Generates a PostgreSQL INSERT statement for this audit record."""
        def esc(val: Optional[str]) -> str:
            if val is None:
                return "NULL"
            escaped = str(val).replace("'", "''")
            return f"'{escaped}'"

        def json_esc(val: Dict[str, Any]) -> str:
            escaped = json.dumps(val).replace("'", "''")
            return f"'{escaped}'::jsonb"

        if self.failure_reason_codes:
            escaped_codes = [r.replace("'", "''") for r in self.failure_reason_codes]
            reasons_pg = "ARRAY[" + ", ".join(f"'{r}'" for r in escaped_codes) + "]::text[]"
        else:
            reasons_pg = "ARRAY[]::text[]"

        return (
            "INSERT INTO address_stewardship_audit_ledger (\n"
            "    audit_id, record_id, batch_id, timestamp_utc, agent_or_system_id,\n"
            "    action_type, confidence_score, failure_reason_codes,\n"
            "    normalized_address_key, building_key, phonetic_key,\n"
            "    is_registered_agent_hub, is_private_residence, dpv_confirmation_code,\n"
            "    raw_input_payload, proposed_standardized_payload, final_committed_payload,\n"
            "    steward_commentary, review_status, reviewed_by, reviewed_at\n"
            ") VALUES (\n"
            f"    {esc(self.audit_id)}::uuid, {esc(self.record_id)}, {esc(self.batch_id)}, {esc(self.timestamp_utc)}::timestamptz, {esc(self.agent_or_system_id)},\n"
            f"    {esc(self.action_type)}, {self.confidence_score:.4f}, {reasons_pg},\n"
            f"    {esc(self.normalized_address_key)}, {esc(self.building_key)}, {esc(self.phonetic_key)},\n"
            f"    {'TRUE' if self.is_registered_agent_hub else 'FALSE'}, {'TRUE' if self.is_private_residence else 'FALSE'}, {esc(self.dpv_confirmation_code)},\n"
            f"    {json_esc(self.raw_input_payload)}, {json_esc(self.proposed_standardized_payload)}, {json_esc(self.final_committed_payload)},\n"
            f"    {esc(self.steward_commentary)}, {esc(self.review_status)}, {esc(self.reviewed_by)}, "
            f"{f'{esc(self.reviewed_at)}::timestamptz' if self.reviewed_at else 'NULL'}\n"
            ");"
        )


class StewardshipAuditLedger:
    """
    Append-only audit ledger manager supporting in-memory queuing and embedded SQLite storage.
    """

    def __init__(self, db_path: Optional[str] = None, max_rows: Optional[int] = None):
        import os
        self.db_path = db_path or ":memory:"
        self._pid = os.getpid()
        # One connection is shared by all threads, so every use of it is serialized by this lock.
        self._lock = threading.RLock()
        # A private in-memory ledger would otherwise grow without bound; file-backed ledgers keep everything.
        if max_rows is None and self.db_path == ":memory:":
            raw_max = os.environ.get("ENTITY_STANDARDIZER_AUDIT_MAX_ROWS") or os.environ.get(
                "ADDRESS_STANDARDIZER_AUDIT_MAX_ROWS", "100000"
            )
            try:
                max_rows = int(raw_max)
            except ValueError:
                max_rows = 100000
        self._max_rows = max_rows if max_rows and max_rows > 0 else None
        self._inserts_since_prune = 0
        self._conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        import os
        with self._lock:
            current_pid = os.getpid()
            if current_pid != self._pid:
                self._pid = current_pid
                self._conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._init_db()
            return self._conn

    def _init_db(self):
        with self._lock, self._conn:
            try:
                self._conn.execute("PRAGMA journal_mode = WAL;")
                self._conn.execute("PRAGMA busy_timeout = 30000;")
            except Exception:
                pass
            self._conn.execute(SQLITE_AUDIT_LEDGER_DDL)
            self._conn.execute(SQLITE_AUDIT_HISTORY_DDL)

    def _prune_if_needed(self, conn: sqlite3.Connection) -> None:
        """Drop the oldest rows of a bounded (in-memory) ledger once it exceeds its cap."""
        if self._max_rows is None:
            return
        self._inserts_since_prune += 1
        if self._inserts_since_prune < 256:
            return
        self._inserts_since_prune = 0
        with conn:
            conn.execute(
                "DELETE FROM address_stewardship_audit_ledger WHERE rowid IN ("
                "SELECT rowid FROM address_stewardship_audit_ledger ORDER BY timestamp_utc ASC, rowid ASC "
                "LIMIT max(0, (SELECT count(*) FROM address_stewardship_audit_ledger) - ?))",
                (self._max_rows,),
            )
            conn.execute(
                "DELETE FROM address_stewardship_audit_history WHERE audit_id NOT IN ("
                "SELECT audit_id FROM address_stewardship_audit_ledger)"
            )

    def ensure_recorded(self, audit_record: StewardshipAuditRecord) -> StewardshipAuditRecord:
        """Idempotent append: record the entry unless a row with the same ``audit_id`` already exists.

        Batch pipelines receive audit records for results the standardizer has already logged; this makes the
        second pass a no-op instead of an error (and never overwrites the stored row).
        """
        with self._lock:
            if self.get_record(audit_record.audit_id) is None:
                return self._record_locked(audit_record, False)
            return audit_record

    def record(self, audit_record: StewardshipAuditRecord, _replace: bool = False) -> StewardshipAuditRecord:
        """Appends a new audit record to the ledger.

        The ledger is append-only per ``audit_id``: recording an existing id raises ``ValueError`` instead of
        silently overwriting history. (Steward overrides replace the current row through ``apply_manual_override``,
        which first copies the prior version to the history table.)
        """
        with self._lock:
            return self._record_locked(audit_record, _replace)

    def _record_locked(self, audit_record: StewardshipAuditRecord, _replace: bool) -> StewardshipAuditRecord:
        conn = self._get_conn()
        verb = "INSERT OR REPLACE" if _replace else "INSERT"
        try:
            with conn:
                conn.execute(
                    f"""
                    {verb} INTO address_stewardship_audit_ledger (
                        audit_id, record_id, batch_id, timestamp_utc, agent_or_system_id,
                        action_type, confidence_score, failure_reason_codes,
                        normalized_address_key, building_key, phonetic_key,
                        is_registered_agent_hub, is_private_residence, dpv_confirmation_code,
                        raw_input_payload, proposed_standardized_payload, final_committed_payload,
                        steward_commentary, review_status, reviewed_by, reviewed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        audit_record.audit_id,
                        audit_record.record_id,
                        audit_record.batch_id,
                        audit_record.timestamp_utc,
                        audit_record.agent_or_system_id,
                        audit_record.action_type,
                        audit_record.confidence_score,
                        json.dumps(audit_record.failure_reason_codes),
                        audit_record.normalized_address_key,
                        audit_record.building_key,
                        audit_record.phonetic_key,
                        1 if audit_record.is_registered_agent_hub else 0,
                        1 if audit_record.is_private_residence else 0,
                        audit_record.dpv_confirmation_code,
                        json.dumps(audit_record.raw_input_payload),
                        json.dumps(audit_record.proposed_standardized_payload),
                        json.dumps(audit_record.final_committed_payload),
                        audit_record.steward_commentary,
                        audit_record.review_status,
                        audit_record.reviewed_by,
                        audit_record.reviewed_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Audit record {audit_record.audit_id} already exists; the ledger is append-only"
            ) from exc
        self._prune_if_needed(conn)
        return audit_record

    def record_standardized_address(
        self,
        std_address: Any,
        confidence_result: ConfidenceResult,
        raw_input: Optional[Dict[str, Any]] = None,
        record_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        dpv_code: Optional[str] = None,
    ) -> StewardshipAuditRecord:
        """Constructs and appends an audit record from a standardized address result."""
        raw_payload = raw_input or {}
        std_dict = {
            "street1": std_address.street1,
            "street2": std_address.street2,
            "city": std_address.city,
            "state": std_address.state,
            "postal_code": std_address.postal_code,
            "country": std_address.country,
        }

        # Determine action_type
        if (
            std_address.address_status == "parse_failed"
            or ERR_PARSE_FAILED in confidence_result.failure_reason_codes
            or confidence_result.routing_tier == RoutingTier.MANUAL_STEWARDSHIP
        ):
            action = ActionType.REJECT_UNPARSEABLE
        elif (
            WARN_TYPO_HEALED in confidence_result.failure_reason_codes
            or ERR_ZIP_STATE_MISMATCH in confidence_result.failure_reason_codes
        ):
            action = ActionType.AUTO_HEAL
        else:
            action = ActionType.AUTO_PASS

        # Determine review_status
        if (
            confidence_result.routing_tier == RoutingTier.MANUAL_STEWARDSHIP
            or std_address.is_registered_agent_hub
            or any(c.startswith("ERR_") for c in confidence_result.failure_reason_codes)
        ):
            status = ReviewStatus.PENDING
        else:
            status = ReviewStatus.APPROVED

        audit_rec = StewardshipAuditRecord(
            record_id=record_id or f"REC-{uuid.uuid4().hex[:8]}",
            batch_id=batch_id,
            action_type=action,
            confidence_score=confidence_result.composite_score,
            failure_reason_codes=confidence_result.failure_reason_codes,
            normalized_address_key=std_address.normalized_address_key,
            building_key=std_address.building_key,
            phonetic_key=std_address.phonetic_key,
            is_registered_agent_hub=std_address.is_registered_agent_hub,
            is_private_residence=std_address.is_private_residence,
            dpv_confirmation_code=dpv_code,
            raw_input_payload=raw_payload,
            proposed_standardized_payload=std_dict,
            final_committed_payload=std_dict,
            review_status=status,
        )
        return self.record(audit_rec)

    def get_record(self, audit_id: str) -> Optional[StewardshipAuditRecord]:
        """Retrieves a single record by audit_id."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT * FROM address_stewardship_audit_ledger WHERE audit_id = ?", (audit_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def list_records(
        self,
        review_status: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[StewardshipAuditRecord]:
        """Queries audit records matching optional filters."""
        conn = self._get_conn()
        query = "SELECT * FROM address_stewardship_audit_ledger"
        params: List[Any] = []
        conditions: List[str] = []

        if review_status:
            conditions.append("review_status = ?")
            params.append(review_status)
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp_utc DESC, rowid DESC"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be >= 0")
            query += " LIMIT ?"
            params.append(limit)

        with self._lock:
            cur = conn.execute(query, tuple(params))
            return [self._row_to_record(r) for r in cur.fetchall()]

    def apply_manual_override(
        self,
        audit_id: str,
        steward_id: str,
        overrides: Dict[str, Any],
        commentary: str = "",
        review_status: str = ReviewStatus.MODIFIED,
    ) -> StewardshipAuditRecord:
        """
        Applies a data steward manual override:
        - Updates final_committed_payload
        - Signs with steward_id and reviewed_at
        - Updates action_type to MANUAL_OVERRIDE and review_status to MODIFIED

        ``review_status`` (default MODIFIED) lets the review UI record an approval (APPROVED: the proposed values are
        committed) or a rejection (REJECTED: nothing is committed, ``final_committed_payload`` is left empty).
        """
        with self._lock:
            existing = self.get_record(audit_id)
            if not existing:
                raise KeyError(f"Audit record not found: {audit_id}")

            committed = dict(existing.final_committed_payload)
            committed.update(overrides)

            # Re-run normalization in real time as specified by Blueprint Section 1.4.4 step 3
            from entity_standardizer.address.standardizer import standardize_address
            re_norm = standardize_address(
                street1=committed.get("street1"),
                street2=committed.get("street2"),
                city=committed.get("city"),
                state=committed.get("state"),
                postal_code=committed.get("postal_code"),
                country=committed.get("country"),
                finalize=False,
                use_cache=False,
            )

            final_payload = {} if review_status == ReviewStatus.REJECTED else {
                "street1": re_norm.street1,
                "street2": re_norm.street2,
                "city": re_norm.city,
                "state": re_norm.state,
                "postal_code": re_norm.postal_code,
                "country": re_norm.country,
            }

            now_utc = datetime.now(timezone.utc).isoformat()

            updated = StewardshipAuditRecord(
                audit_id=existing.audit_id,
                record_id=existing.record_id,
                batch_id=existing.batch_id,
                timestamp_utc=existing.timestamp_utc,
                agent_or_system_id=existing.agent_or_system_id,
                action_type=ActionType.MANUAL_OVERRIDE,
                confidence_score=1.0000,
                failure_reason_codes=existing.failure_reason_codes,
                normalized_address_key=re_norm.normalized_address_key,
                building_key=re_norm.building_key,
                phonetic_key=re_norm.phonetic_key,
                is_registered_agent_hub=re_norm.is_registered_agent_hub,
                is_private_residence=re_norm.is_private_residence,
                dpv_confirmation_code=existing.dpv_confirmation_code,
                raw_input_payload=existing.raw_input_payload,
                proposed_standardized_payload=existing.proposed_standardized_payload,
                final_committed_payload=final_payload,
                steward_commentary=commentary,
                review_status=review_status,
                reviewed_by=steward_id,
                reviewed_at=now_utc,
            )
            conn = self._get_conn()
            with conn:
                conn.execute(
                    "INSERT INTO address_stewardship_audit_history ("
                    "audit_id, record_id, batch_id, timestamp_utc, agent_or_system_id, action_type, confidence_score, "
                    "failure_reason_codes, normalized_address_key, building_key, phonetic_key, is_registered_agent_hub, "
                    "is_private_residence, dpv_confirmation_code, raw_input_payload, proposed_standardized_payload, "
                    "final_committed_payload, steward_commentary, review_status, reviewed_by, reviewed_at) "
                    "SELECT audit_id, record_id, batch_id, timestamp_utc, agent_or_system_id, action_type, "
                    "confidence_score, failure_reason_codes, normalized_address_key, building_key, phonetic_key, "
                    "is_registered_agent_hub, is_private_residence, dpv_confirmation_code, raw_input_payload, "
                    "proposed_standardized_payload, final_committed_payload, steward_commentary, review_status, "
                    "reviewed_by, reviewed_at FROM address_stewardship_audit_ledger WHERE audit_id = ?",
                    (audit_id,),
                )
            return self.record(updated, _replace=True)

    def history(self, audit_id: str) -> List[Dict[str, Any]]:
        """Prior versions of a record replaced by steward overrides, oldest first."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT * FROM address_stewardship_audit_history WHERE audit_id = ? ORDER BY history_id ASC",
                (audit_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def export(self, format: str = "dict") -> Union[List[Dict[str, Any]], str]:
        """Exports ledger records in 'dict', 'json', or 'sql' format."""
        records = self.list_records()
        if format == "json":
            return json.dumps([r.as_dict() for r in records], indent=2)
        elif format == "sql":
            return "\n\n".join(r.to_sql_insert() for r in records)
        return [r.as_dict() for r in records]

    def clear(self):
        """Clears all records from the ledger."""
        with self._lock:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM address_stewardship_audit_ledger")
                conn.execute("DELETE FROM address_stewardship_audit_history")
            self._inserts_since_prune = 0

    def _row_to_record(self, row: sqlite3.Row) -> StewardshipAuditRecord:
        return StewardshipAuditRecord(
            audit_id=row["audit_id"],
            record_id=row["record_id"],
            batch_id=row["batch_id"],
            timestamp_utc=row["timestamp_utc"],
            agent_or_system_id=row["agent_or_system_id"],
            action_type=row["action_type"],
            confidence_score=float(row["confidence_score"]),
            failure_reason_codes=json.loads(row["failure_reason_codes"]),
            normalized_address_key=row["normalized_address_key"],
            building_key=row["building_key"],
            phonetic_key=row["phonetic_key"],
            is_registered_agent_hub=bool(row["is_registered_agent_hub"]),
            is_private_residence=bool(row["is_private_residence"]),
            dpv_confirmation_code=row["dpv_confirmation_code"],
            raw_input_payload=json.loads(row["raw_input_payload"]),
            proposed_standardized_payload=json.loads(row["proposed_standardized_payload"]),
            final_committed_payload=json.loads(row["final_committed_payload"]),
            steward_commentary=row["steward_commentary"],
            review_status=row["review_status"],
            reviewed_by=row["reviewed_by"],
            reviewed_at=row["reviewed_at"],
        )


_DEFAULT_AUDIT_LEDGER: Optional[StewardshipAuditLedger] = None


def get_audit_ledger() -> StewardshipAuditLedger:
    """Returns the process default singleton audit ledger, initializing it lazily on first access."""
    global _DEFAULT_AUDIT_LEDGER
    if _DEFAULT_AUDIT_LEDGER is None:
        _DEFAULT_AUDIT_LEDGER = StewardshipAuditLedger()
    return _DEFAULT_AUDIT_LEDGER

