"""Sealed original narrations. This repository stores and returns ciphertext only; the caller
holds the vault and decides who may read the text."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from cfo.core.ids import Id
from cfo.core.types import Origin
from cfo.ledger.repositories.models import PostingOriginalRow, PostingRow
from cfo.ledger.repositories.scope import ScopedRepository
from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert


class OriginalRepository(ScopedRepository):
    def put_many(self, account_id: Id, sealed: Mapping[str, bytes]) -> None:
        """Keep the first original stored for a row; a re-upload never replaces it."""
        for dedup_hash, blob in sealed.items():
            self.s.execute(
                insert(PostingOriginalRow)
                .values(
                    ledger_id=self.ledger_id,
                    account_id=account_id,
                    dedup_hash=dedup_hash,
                    ciphertext=blob,
                )
                .on_conflict_do_nothing()
            )

    def for_transactions(self, tx_ids: Iterable[Id]) -> dict[Id, bytes]:
        """Ciphertext by transaction, from its first observed posting that has one."""
        wanted = list(tx_ids)
        if not wanted:
            return {}
        q = (
            select(PostingRow.transaction_id, PostingOriginalRow.ciphertext)
            .join(
                PostingOriginalRow,
                (PostingOriginalRow.ledger_id == PostingRow.ledger_id)
                & (PostingOriginalRow.account_id == PostingRow.account_id)
                & (PostingOriginalRow.dedup_hash == PostingRow.dedup_hash),
            )
            .where(
                self.in_scope(PostingRow.ledger_id),
                PostingRow.transaction_id.in_(wanted),
                PostingRow.origin == Origin.OBSERVED.value,
            )
            .order_by(PostingRow.id)
        )
        out: dict[Id, bytes] = {}
        for tx_id, blob in self.s.execute(q):
            out.setdefault(tx_id, bytes(blob))
        return out

    def purge_orphans(self) -> int:
        """Delete originals whose row is gone (a removed statement, an ignored or deleted row), so
        removing a statement removes its readable text too."""
        alive = exists().where(
            PostingRow.ledger_id == PostingOriginalRow.ledger_id,
            PostingRow.account_id == PostingOriginalRow.account_id,
            PostingRow.dedup_hash == PostingOriginalRow.dedup_hash,
        )
        result = self.s.execute(
            delete(PostingOriginalRow).where(PostingOriginalRow.ledger_id == self.ledger_id, ~alive)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
