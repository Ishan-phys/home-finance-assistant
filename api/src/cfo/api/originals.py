"""Reading sealed original narrations for the owner's own screens.

The text leaves here only in responses to the signed-in owner (the cockpit's transaction list and
inbox) and into local rule matching. It is not added to anything the chat tools or a model see."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from cfo.core.ids import Id
from cfo.ledger.repositories.originals import OriginalRepository
from cfo.vault import Vault
from sqlalchemy.orm import Session

Json = dict[str, Any]


def read_originals(s: Session, vault: Vault | None, tx_ids: Iterable[Id]) -> dict[Id, str]:
    """Original narrations by transaction, for those the vault can open. With no vault, or a key
    that no longer opens them, a row simply has none."""
    if vault is None:
        return {}
    out: dict[Id, str] = {}
    for tx_id, blob in OriginalRepository(s).for_transactions(tx_ids).items():
        text = vault.open(blob)
        if text is not None:
            out[tx_id] = text
    return out


def attach_originals(s: Session, vault: Vault | None, rows: list[Json], key: str) -> None:
    """Set `original` on each row (None when there is none), keyed by the row's transaction id."""
    ids = [UUID(str(r[key])) for r in rows if r.get(key)]
    found = read_originals(s, vault, ids)
    for r in rows:
        r["original"] = found.get(UUID(str(r[key]))) if r.get(key) else None
