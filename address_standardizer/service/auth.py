"""API-key store: keys are kept only as SHA-256 digests and compared in constant time.

Entry syntax (comma- or newline-separated; ``#`` starts a comment line in files)::

    name:plaintext-key-of-at-least-16-chars
    name:sha256:<64 hex digits>          # pre-hashed: the plaintext never needs to be on the server

Several entries may share a name (key rotation). Key values must not contain commas or whitespace. Error messages
never contain key material.
"""

import hashlib
import hmac
import re
from typing import Iterable, List, Mapping, Optional, Tuple

MIN_KEY_LENGTH = 16
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class KeyStore:
    """Immutable collection of ``(name, sha256 digest)`` pairs."""

    def __init__(self, entries: Iterable[Tuple[str, bytes]]) -> None:
        self._entries: List[Tuple[str, bytes]] = list(entries)
        if not self._entries:
            raise ValueError("API key store is empty: refusing to run with authentication enabled but no keys")

    @classmethod
    def parse(cls, text: str) -> "KeyStore":
        entries: List[Tuple[str, bytes]] = []
        cleaned_lines = [line.partition("#")[0] for line in text.splitlines()]
        for raw in ",".join(cleaned_lines).split(","):
            item = raw.strip()
            if not item:
                continue
            number = len(entries) + 1
            name, sep, secret = item.partition(":")
            if not sep or not _NAME_RE.match(name) or not secret:
                raise ValueError(f"API key entry #{number} is malformed: expected name:key (name is [A-Za-z0-9_.-]{{1,64}})")
            if secret.lower().startswith("sha256:"):
                digest_hex = secret[len("sha256:"):]
                if not _HEX64_RE.match(digest_hex):
                    raise ValueError(f"API key entry #{number} has an invalid sha256 digest")
                entries.append((name, bytes.fromhex(digest_hex)))
            else:
                if len(secret) < MIN_KEY_LENGTH:
                    raise ValueError(f"API key entry #{number} is shorter than {MIN_KEY_LENGTH} characters")
                # API keys are long random tokens, not user-chosen passwords: a plain SHA-256 is the right primitive
                # (a slow password KDF would add per-request latency and no protection for a high-entropy secret).
                entries.append((name, hashlib.sha256(secret.encode("utf-8")).digest()))
        return cls(entries)

    @classmethod
    def from_config(cls, api_keys: str, api_keys_file: str) -> Optional["KeyStore"]:
        """Build the store from the env string and/or file; None when neither is configured (auth disabled)."""
        chunks: List[str] = []
        if api_keys.strip():
            chunks.append(api_keys)
        if api_keys_file:
            with open(api_keys_file, "r", encoding="utf-8") as handle:
                chunks.append(handle.read())
        if not chunks:
            return None
        return cls.parse("\n".join(chunks))

    def authenticate(self, presented: str) -> Optional[str]:
        """Return the key's name, or None. Compares against every stored digest so timing does not leak position."""
        digest = hashlib.sha256(presented.encode("utf-8")).digest()
        found: Optional[str] = None
        for name, stored in self._entries:
            if hmac.compare_digest(stored, digest):
                found = found or name
        return found

    def __len__(self) -> int:
        return len(self._entries)


def extract_api_key(headers: Mapping[str, str]) -> Optional[str]:
    """The presented credential: ``X-API-Key`` first, else ``Authorization: Bearer <key>``; None if absent."""
    key = headers.get("x-api-key", "").strip()
    if key:
        return key
    scheme, _, token = headers.get("authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() == "bearer" and token:
        return token
    return None
