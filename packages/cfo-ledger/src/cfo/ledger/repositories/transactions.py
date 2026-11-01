"""The journal (transactions and their postings) and remembered categorizations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from cfo.core.chart import IN_TRANSIT
from cfo.core.ids import Id, new_id
from cfo.core.types import MappingSource, MerchantMapping, Origin, Posting, Transaction
from cfo.ledger.pairing import Half
from cfo.ledger.repositories.db import rowcount
from cfo.ledger.repositories.models import (
    AccountRow,
    DismissedHashRow,
    MerchantMappingRow,
    PostingRow,
    TransactionRow,
)
from cfo.ledger.repositories.scope import ScopedRepository
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert


def _posting(r: PostingRow) -> Posting:
    return Posting(
        account_id=r.account_id,
        amount=r.amount,
        origin=Origin(r.origin),
        id=r.id,
        import_id=r.import_id,
        dedup_hash=r.dedup_hash,
        units=r.units,
        unit_label=r.unit_label,
    )


class JournalRepository(ScopedRepository):
    def add(self, tx: Transaction) -> Transaction:
        """Store a balanced transaction. The caller built it, so it already sums to zero."""
        self.s.add(
            TransactionRow(
                id=tx.id,
                ledger_id=self.ledger_id,
                posted_date=tx.date,
                narration=tx.narration,
                payee=tx.payee,
                source=tx.source,
                import_id=tx.import_id,
            )
        )
        self.s.flush()
        for p in tx.postings:
            self._add_posting(tx.id, p)
        self.s.flush()
        return tx

    def _add_posting(self, tx_id: Id, p: Posting) -> Id:
        row = PostingRow(
            id=p.id or new_id(),
            ledger_id=self.ledger_id,
            transaction_id=tx_id,
            account_id=p.account_id,
            amount=p.amount,
            origin=p.origin.value,
            import_id=p.import_id,
            dedup_hash=p.dedup_hash,
            units=p.units,
            unit_label=p.unit_label,
        )
        self.s.add(row)
        return row.id

    def add_posting(self, tx_id: Id, posting: Posting) -> Id:
        """Add one posting to an existing transaction; the caller keeps it balanced."""
        posting_id = self._add_posting(tx_id, posting)
        self.s.flush()
        return posting_id

    def _load(self, rows: Sequence[TransactionRow]) -> list[Transaction]:
        if not rows:
            return []
        ids = [r.id for r in rows]
        by_tx: dict[Id, list[Posting]] = defaultdict(list)
        q = select(PostingRow).where(PostingRow.transaction_id.in_(ids)).order_by(PostingRow.id)
        for p in self.s.scalars(q):
            by_tx[p.transaction_id].append(_posting(p))
        return [
            Transaction(
                id=r.id,
                date=r.posted_date,
                narration=r.narration,
                payee=r.payee,
                postings=tuple(by_tx[r.id]),
                source=r.source,  # type: ignore[arg-type]
                import_id=r.import_id,
            )
            for r in rows
            if by_tx[r.id]
        ]

    def get(self, tx_id: Id) -> Transaction | None:
        row = self.s.scalars(
            select(TransactionRow).where(
                TransactionRow.id == tx_id, self.in_scope(TransactionRow.ledger_id)
            )
        ).first()
        found = self._load([row]) if row else []
        return found[0] if found else None

    def list_all(self, account_ids: Sequence[Id] | None = None) -> list[Transaction]:
        """Every transaction in scope, or those touching any of `account_ids`, oldest first."""
        q = select(TransactionRow).where(self.in_scope(TransactionRow.ledger_id))
        if account_ids is not None:
            touching = select(PostingRow.transaction_id).where(
                PostingRow.account_id.in_(list(account_ids))
            )
            q = q.where(TransactionRow.id.in_(touching))
        rows = list(self.s.scalars(q.order_by(TransactionRow.posted_date, TransactionRow.id)))
        return self._load(rows)

    def with_narration(self, narration: str) -> list[Transaction]:
        q = select(TransactionRow).where(
            self.in_scope(TransactionRow.ledger_id), TransactionRow.narration == narration
        )
        return self._load(
            list(self.s.scalars(q.order_by(TransactionRow.posted_date, TransactionRow.id)))
        )

    def existing_hashes(self, account_id: Id, hashes: Iterable[str]) -> set[str]:
        """Hashes already stored for the account, or dismissed by the owner."""
        wanted = list(hashes)
        if not wanted:
            return set()
        stored = self.s.scalars(
            select(PostingRow.dedup_hash).where(
                PostingRow.account_id == account_id,
                self.in_scope(PostingRow.ledger_id),
                PostingRow.dedup_hash.in_(wanted),
            )
        )
        dismissed = self.s.scalars(
            select(DismissedHashRow.dedup_hash).where(
                DismissedHashRow.account_id == account_id,
                self.in_scope(DismissedHashRow.ledger_id),
                DismissedHashRow.dedup_hash.in_(wanted),
            )
        )
        return {h for h in stored if h} | set(dismissed)

    def dismiss(self, account_id: Id, hashes: Iterable[str]) -> None:
        for h in hashes:
            self.s.execute(
                insert(DismissedHashRow)
                .values(ledger_id=self.ledger_id, account_id=account_id, dedup_hash=h)
                .on_conflict_do_nothing()
            )
        self.s.flush()

    def replace_posting_account(self, posting_id: Id, account_id: Id, origin: Origin) -> None:
        self.s.execute(
            update(PostingRow)
            .where(PostingRow.id == posting_id, PostingRow.ledger_id == self.ledger_id)
            .values(account_id=account_id, origin=origin.value)
        )
        self.s.flush()

    def delete(self, tx_id: Id) -> None:
        self.s.execute(
            delete(TransactionRow).where(
                TransactionRow.id == tx_id, TransactionRow.ledger_id == self.ledger_id
            )
        )
        self.s.flush()

    def postings_from_import(self, import_id: Id) -> list[tuple[Id, Posting]]:
        """(transaction id, posting) for every posting the import created."""
        rows = self.s.scalars(
            select(PostingRow).where(
                PostingRow.import_id == import_id, self.in_scope(PostingRow.ledger_id)
            )
        )
        return [(r.transaction_id, _posting(r)) for r in rows]

    def retag_import(self, tx_id: Id, posting_ids: Sequence[Id], import_id: Id | None) -> None:
        """Hand postings (and the transaction, if it was the same import's) to another import."""
        if posting_ids:
            self.s.execute(
                update(PostingRow)
                .where(PostingRow.id.in_(list(posting_ids)), PostingRow.ledger_id == self.ledger_id)
                .values(import_id=import_id)
            )
        self.s.execute(
            update(TransactionRow)
            .where(TransactionRow.id == tx_id, TransactionRow.ledger_id == self.ledger_id)
            .values(import_id=import_id)
        )
        self.s.flush()

    def delete_postings(self, posting_ids: Sequence[Id]) -> None:
        if posting_ids:
            self.s.execute(
                delete(PostingRow).where(
                    PostingRow.id.in_(list(posting_ids)), PostingRow.ledger_id == self.ledger_id
                )
            )
            self.s.flush()

    def move_postings(self, from_account: Id, to_account: Id) -> int:
        """Re-point every posting on one account to another (a category merge)."""
        result = self.s.execute(
            update(PostingRow)
            .where(PostingRow.account_id == from_account, PostingRow.ledger_id == self.ledger_id)
            .values(account_id=to_account)
        )
        self.s.flush()
        return rowcount(result)

    def in_transit_halves(self) -> list[Half]:
        """Transactions of one observed posting whose other side is money in transit, waiting
        for the owner's other account to show up."""
        transit = select(AccountRow.id).where(
            AccountRow.path == IN_TRANSIT, self.in_scope(AccountRow.ledger_id)
        )
        candidates = select(PostingRow.transaction_id).where(
            PostingRow.account_id.in_(transit), PostingRow.origin == Origin.INFERRED.value
        )
        rows = list(
            self.s.scalars(
                select(TransactionRow).where(
                    TransactionRow.id.in_(candidates), self.in_scope(TransactionRow.ledger_id)
                )
            )
        )
        transit_ids = set(self.s.scalars(transit))
        halves = []
        for t in self._load(rows):
            observed = [p for p in t.postings if p.origin is Origin.OBSERVED]
            waiting = [p for p in t.postings if p.account_id in transit_ids]
            if len(t.postings) == 2 and len(observed) == 1 and len(waiting) == 1:
                halves.append(Half(t.id, observed[0].account_id, t.date, waiting[0].amount))
        return halves

    def merge(self, keep_tx: Id, other_tx: Id) -> None:
        """Two halves become one event: `other`'s observed posting moves into `keep`, both
        money-in-transit postings go, and `other` is deleted. Their sum is unchanged."""
        transit = select(AccountRow.id).where(
            AccountRow.path == IN_TRANSIT, AccountRow.ledger_id == self.ledger_id
        )
        self.s.execute(
            delete(PostingRow).where(
                PostingRow.transaction_id.in_([keep_tx, other_tx]),
                PostingRow.account_id.in_(transit),
                PostingRow.ledger_id == self.ledger_id,
            )
        )
        self.s.execute(
            update(PostingRow)
            .where(PostingRow.transaction_id == other_tx, PostingRow.ledger_id == self.ledger_id)
            .values(transaction_id=keep_tx)
        )
        self.delete(other_tx)


def _mapping(r: MerchantMappingRow) -> MerchantMapping:
    return MerchantMapping(
        r.lookup_key, r.clean_merchant, r.label, MappingSource(r.source), r.confidence
    )


class MappingRepository(ScopedRepository):
    def get_many(self, keys: Iterable[str]) -> dict[str, MerchantMapping]:
        wanted = list(keys)
        if not wanted:
            return {}
        rows = self.s.scalars(
            select(MerchantMappingRow).where(
                self.in_scope(MerchantMappingRow.ledger_id),
                MerchantMappingRow.lookup_key.in_(wanted),
            )
        )
        return {r.lookup_key: _mapping(r) for r in rows}

    def save_model(self, mappings: Iterable[MerchantMapping]) -> None:
        """Store model categorizations. An owner mapping is never replaced."""
        for m in mappings:
            stmt = insert(MerchantMappingRow).values(
                id=new_id(),
                ledger_id=self.ledger_id,
                lookup_key=m.lookup_key,
                clean_merchant=m.clean_merchant,
                label=m.label,
                source=MappingSource.MODEL.value,
                confidence=m.confidence,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[MerchantMappingRow.ledger_id, MerchantMappingRow.lookup_key],
                set_={
                    "clean_merchant": stmt.excluded.clean_merchant,
                    "label": stmt.excluded.label,
                    "confidence": stmt.excluded.confidence,
                },
                where=MerchantMappingRow.source == MappingSource.MODEL.value,
            )
            self.s.execute(stmt)

    def list_owner(self) -> list[MerchantMapping]:
        """Every mapping the owner made, oldest change first."""
        rows = self.s.scalars(
            select(MerchantMappingRow)
            .where(
                self.in_scope(MerchantMappingRow.ledger_id),
                MerchantMappingRow.source == MappingSource.OWNER.value,
            )
            .order_by(MerchantMappingRow.updated_at, MerchantMappingRow.id)
        )
        return [_mapping(r) for r in rows]

    def set_owner(self, lookup_key: str, label: str, clean_merchant: str) -> MerchantMapping:
        stmt = insert(MerchantMappingRow).values(
            id=new_id(),
            ledger_id=self.ledger_id,
            lookup_key=lookup_key,
            clean_merchant=clean_merchant,
            label=label,
            source=MappingSource.OWNER.value,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[MerchantMappingRow.ledger_id, MerchantMappingRow.lookup_key],
            set_={
                "clean_merchant": stmt.excluded.clean_merchant,
                "label": stmt.excluded.label,
                "source": MappingSource.OWNER.value,
                "confidence": None,
            },
        )
        self.s.execute(stmt)
        return MerchantMapping(lookup_key, clean_merchant, label, MappingSource.OWNER)

    def repoint(self, from_label: str, to_label: str) -> int:
        """Move every remembered mapping from one account path to another (a category merge)."""
        result = self.s.execute(
            update(MerchantMappingRow)
            .where(
                MerchantMappingRow.ledger_id == self.ledger_id,
                MerchantMappingRow.label == from_label,
            )
            .values(label=to_label)
        )
        return rowcount(result)

    def forget(self, label: str) -> None:
        """Drop the mappings that point at a deleted category."""
        self.s.execute(
            delete(MerchantMappingRow).where(
                MerchantMappingRow.ledger_id == self.ledger_id, MerchantMappingRow.label == label
            )
        )
