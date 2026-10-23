"""Per-key tenant isolation (opt-in): a cache key namespace and a separate audit ledger per API key name.

The namespace and ledger are carried in context variables, which FastAPI/Starlette propagate into the threadpool
workers that run the standardization, so the engine itself needs no tenant parameter.
"""

import os
import threading
from typing import Dict, Optional, Tuple

from address_standardizer.audit import LEDGER_OVERRIDE, StewardshipAuditLedger
from address_standardizer.cache import CACHE_NAMESPACE


class Tenancy:
    def __init__(self, enabled: bool, audit_dir: str = "") -> None:
        self.enabled = enabled
        self.audit_dir = audit_dir
        self._ledgers: Dict[str, StewardshipAuditLedger] = {}
        self._lock = threading.Lock()

    def ledger_for(self, name: str) -> StewardshipAuditLedger:
        """The tenant's ledger: in-memory, or ``<audit_dir>/<name>.db`` when a directory is configured.

        Names come from the validated key store ([A-Za-z0-9_.-], at most 64 chars), so they are safe file names.
        """
        with self._lock:
            ledger = self._ledgers.get(name)
            if ledger is None:
                path = os.path.join(self.audit_dir, name + ".db") if self.audit_dir else None
                ledger = StewardshipAuditLedger(db_path=path)
                self._ledgers[name] = ledger
            return ledger

    def enter(self, name: Optional[str]) -> Optional[Tuple[object, object]]:
        """Activate the tenant for the current context; returns tokens for :meth:`exit` (None when inactive)."""
        if not self.enabled or name is None:
            return None
        return CACHE_NAMESPACE.set(name), LEDGER_OVERRIDE.set(self.ledger_for(name))

    def exit(self, tokens: Optional[Tuple[object, object]]) -> None:
        if tokens is not None:
            CACHE_NAMESPACE.reset(tokens[0])  # type: ignore[arg-type]
            LEDGER_OVERRIDE.reset(tokens[1])  # type: ignore[arg-type]
