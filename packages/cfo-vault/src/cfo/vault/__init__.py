"""Encryption at rest for the one thing the ledger keeps in the clear nowhere else: the original,
unredacted narration of a statement row. Nothing but this module knows the cipher."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("cfo.vault")

__all__ = ["FernetVault", "Vault", "generate_key", "load_vault"]


class Vault(Protocol):
    def seal(self, text: str) -> bytes: ...

    def open(self, blob: bytes) -> str | None:
        """The text, or None when this vault's key cannot open it (a lost or changed key)."""
        ...


def generate_key() -> str:
    return Fernet.generate_key().decode()


class FernetVault:
    """Authenticated encryption (AES-128-CBC with HMAC-SHA256, via Fernet)."""

    def __init__(self, key: str | bytes) -> None:
        try:
            self._f = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "the narration key is not valid; generate one with cfo.vault.generate_key()"
            ) from exc

    def seal(self, text: str) -> bytes:
        return self._f.encrypt(text.encode())

    def open(self, blob: bytes) -> str | None:
        try:
            return self._f.decrypt(bytes(blob)).decode()
        except InvalidToken:
            return None


def load_vault(env: Mapping[str, str]) -> Vault | None:
    """The vault the environment asks for, or None (originals are then simply not kept).

    `NARRATION_KEY` is the key itself. `NARRATION_KEY_FILE` names a file holding it; the file is
    created, readable by the owner only, when it does not exist yet."""
    key = (env.get("NARRATION_KEY") or "").strip()
    if key:
        return FernetVault(key)
    path = (env.get("NARRATION_KEY_FILE") or "").strip()
    if not path:
        return None
    file = Path(path)
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(generate_key())
        log.info("created a new narration key file")
    return FernetVault(file.read_text().strip())
