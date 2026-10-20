"""The journal service: statement rows become balanced transactions, own-account halves pair,
and the owner's corrections replace inferred postings (spec §5.3, §5.4, §5.9).

A statement tells us one side of an event for sure: the observed posting. The other side is
inferred, from a remembered mapping or the model, or is money in transit until the owner's
other account shows up. Pairing and recategorizing only ever replace inferred postings.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from cfo.core.chart import IN_TRANSIT, OPENING, REVALUATION, UNCATEGORIZED_IN, UNCATEGORIZED_OUT
from cfo.core.errors import InvalidInput, NotFoundError
from cfo.core.ids import Id, new_id
from cfo.core.types import (
    Account,
    AccountRole,
    Group,
    MerchantMapping,
    Origin,
    Posting,
    Transaction,
)
from cfo.ledger.pairing import find_pairs
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    AssertionRepository,
    ImportHashRepository,
    ImportRepository,
    ValuationRepository,
)
from cfo.ledger.repositories.transactions import JournalRepository, MappingRepository
from cfo.metrics.balances import balance
from cfo.metrics.reconcile import gaps, opening_amount
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class RowIn:
    date: date
    amount: int  # signed paise as the account sees it: negative takes money out
    narration: str  # redacted
    payee: str
    dedup_hash: str
    own_move: bool = False  # the adapter knows the other side is one of the owner's accounts
    units: str | None = None
    unit_label: str | None = None


@dataclass(frozen=True, slots=True)
class PostResult:
    inserted: int
    ignored: int
    uncategorized: int


def _usable(account: Account | None) -> bool:
    return account is not None and account.active and account.role is not AccountRole.REAL


def post_rows(
    s: Session,
    account: Account,
    import_id: Id | None,
    rows: Sequence[RowIn],
    mappings: Mapping[str, MerchantMapping],
) -> PostResult:
    """One transaction per new row: the observed posting on `account`, and an inferred counter
    posting from (in order) the adapter's own answer, a remembered mapping (the owner's wins over
    the model's, since the owner's replaces it in storage), or Uncategorized."""
    journal = JournalRepository(s)
    by_path = {a.path: a for a in AccountRepository(s).list_all(include_retired=True)}
    seen = journal.existing_hashes(account.id, (r.dedup_hash for r in rows))
    inserted = uncategorized = 0
    for r in rows:
        if r.dedup_hash in seen or r.amount == 0:
            continue
        seen.add(r.dedup_hash)
        payee = r.payee
        mapping = mappings.get(r.narration)
        target = by_path.get(mapping.label) if mapping else None
        if r.own_move:
            counter = by_path[IN_TRANSIT]
        elif mapping is not None and _usable(target):
            counter = target  # type: ignore[assignment]
            payee = mapping.clean_merchant or payee
        else:
            counter = by_path[UNCATEGORIZED_OUT if r.amount < 0 else UNCATEGORIZED_IN]
            uncategorized += 1
        journal.add(
            Transaction(
                new_id(),
                r.date,
                r.narration,
                payee,
                (
                    Posting(
                        account.id,
                        r.amount,
                        Origin.OBSERVED,
                        import_id=import_id,
                        dedup_hash=r.dedup_hash,
                        units=r.units,
                        unit_label=r.unit_label,
                    ),
                    Posting(counter.id, -r.amount, Origin.INFERRED, import_id=import_id),
                ),
                import_id=import_id,
            )
        )
        inserted += 1
    return PostResult(inserted, len(rows) - inserted, uncategorized)


def _uncategorized_ids(s: Session) -> set[Id]:
    repo = AccountRepository(s)
    return {a.id for p in (UNCATEGORIZED_OUT, UNCATEGORIZED_IN) if (a := repo.by_path(p))}


def uncategorized_rows(s: Session) -> list[tuple[str, int]]:
    """(narration, observed amount) of every transaction still waiting for a category."""
    waiting = _uncategorized_ids(s)
    out = []
    for t in JournalRepository(s).list_all(list(waiting)):
        observed = [p for p in t.postings if p.origin is Origin.OBSERVED]
        if len(observed) == 1:
            out.append((t.narration, observed[0].amount))
    return out


def apply_to_uncategorized(s: Session, mappings: Mapping[str, MerchantMapping]) -> int:
    """Give still-uncategorized transactions the category their narration now maps to."""
    waiting = _uncategorized_ids(s)
    by_path = {a.path: a for a in AccountRepository(s).list_all()}
    journal = JournalRepository(s)
    updated = 0
    for t in journal.list_all(list(waiting)):
        mapping = mappings.get(t.narration)
        target = by_path.get(mapping.label) if mapping else None
        if not _usable(target) or target is None:
            continue
        counter = next((p for p in t.postings if p.account_id in waiting), None)
        if counter is not None and counter.id is not None:
            journal.replace_posting_account(counter.id, target.id, Origin.INFERRED)
            updated += 1
    if updated:
        pair_in_transit(s)
    return updated


def pair_in_transit(s: Session) -> int:
    """Merge every pair of own-account halves in the ledger into one transaction."""
    journal = JournalRepository(s)
    pairs = find_pairs(journal.in_transit_halves())
    for out_tx, into_tx in pairs:
        journal.merge(out_tx, into_tx)
    return len(pairs)


def _load(s: Session, tx_id: Id) -> Transaction:
    tx = JournalRepository(s).get(tx_id)
    if tx is None:
        raise NotFoundError(f"unknown transaction {tx_id}")
    return tx


def _counter(tx: Transaction) -> Posting:
    observed = [p for p in tx.postings if p.origin is Origin.OBSERVED]
    others = [p for p in tx.postings if p.origin is not Origin.OBSERVED]
    if len(observed) != 1 or len(others) != 1:
        raise InvalidInput(
            "this is a movement between two of your accounts; it has no category to change"
        )
    return others[0]


def recategorize(s: Session, tx_id: Id, account_id: Id) -> int:
    """Post the transaction's other side to `account_id`, remember that for its narration, and
    apply it to every other transaction with that narration the owner has not set by hand.
    Returns how many transactions changed. Moving a row to money in transit pairs it if its
    partner is already there."""
    tx = _load(s, tx_id)
    target = AccountRepository(s).get(account_id)
    allowed = (
        target is not None
        and target.active
        and (
            target.role is AccountRole.CATEGORY
            or target.path in (IN_TRANSIT, UNCATEGORIZED_OUT, UNCATEGORIZED_IN)
        )
    )
    if not allowed or target is None:
        raise InvalidInput("pick a category, or 'Own account or investment'")
    journal = JournalRepository(s)
    # Only the row the owner touched is theirs; rows that follow the mapping stay inferred, so a
    # later correction reaches them too. Money in transit stays inferred so it can pair.
    mine = Origin.INFERRED if target.path == IN_TRANSIT else Origin.OWNER
    journal.replace_posting_account(_counter(tx).id, target.id, mine)  # type: ignore[arg-type]
    MappingRepository(s).set_owner(tx.narration, target.path, tx.payee)
    changed = 1
    for other in journal.with_narration(tx.narration):
        if other.id == tx.id:
            continue
        try:
            counter = _counter(other)
        except InvalidInput:
            continue
        if counter.origin is Origin.OWNER or counter.account_id == target.id:
            continue
        journal.replace_posting_account(counter.id, target.id, Origin.INFERRED)  # type: ignore[arg-type]
        changed += 1
    if target.path == IN_TRANSIT:
        pair_in_transit(s)
    return changed


def ignore(s: Session, tx_id: Id) -> None:
    """Drop a transaction the owner does not want (a duplicate the bank printed twice). Its
    statement rows are remembered, so a re-upload does not bring it back."""
    tx = _load(s, tx_id)
    _counter(tx)  # a paired movement between two accounts is not ignorable as one row
    journal = JournalRepository(s)
    for p in tx.postings:
        if p.origin is Origin.OBSERVED and p.dedup_hash:
            journal.dismiss(p.account_id, [p.dedup_hash])
    journal.delete(tx.id)


# reconciliation -----------------------------------------------------------------------


def record_assertion(
    s: Session, account_id: Id, as_of: date, amount: int, import_id: Id | None
) -> bool:
    """The statement says the account was `amount` on `as_of`. False when already recorded."""
    assertions = AssertionRepository(s)
    if assertions.exists(account_id, as_of, amount):
        return False
    assertions.add(account_id, as_of, amount, import_id)
    return True


def _system_tx(on: date, label: str, account_id: Id, equity_id: Id, amount: int) -> Transaction:
    return Transaction(
        new_id(),
        on,
        label,
        label,
        (Posting(account_id, amount, Origin.SYSTEM), Posting(equity_id, -amount, Origin.SYSTEM)),
        source="system",
    )


def recompute_opening(s: Session, account_id: Id) -> int | None:
    """Derive the account's opening balance from its earliest statement balance, so that
    assertion holds by construction (C6). Re-run whenever statements are added or removed.
    Accounts without statements (manual ones) keep the opening value they were given."""
    account = AccountRepository(s).get(account_id)
    if account is None or account.type is None or account.type.manual or account.binding is None:
        return None  # its opening value was given by the owner
    journal = JournalRepository(s)
    opening = AccountRepository(s).by_path(OPENING)
    if opening is None:
        raise NotFoundError("the ledger has no opening-balance account")
    touching = journal.list_all([account_id])
    for t in touching:
        if t.source == "system" and any(p.account_id == opening.id for p in t.postings):
            journal.delete(t.id)
    rest = [
        t
        for t in touching
        if not (t.source == "system" and any(p.account_id == opening.id for p in t.postings))
    ]
    assertions = AssertionRepository(s).list_all([account_id])
    if not assertions:
        return None
    earliest = min(assertions, key=lambda a: (a.as_of, str(a.id)))
    amount = opening_amount(account_id, rest, earliest)
    if amount:
        first = min((t.date for t in rest), default=earliest.as_of)
        on = min(first, earliest.as_of) - timedelta(days=1)
        journal.add(_system_tx(on, "Opening balance", account_id, opening.id, amount))
    return amount


def account_gaps(s: Session, account_id: Id) -> int:
    """How many of the account's statement balances the ledger disagrees with."""
    account = AccountRepository(s).get(account_id)
    if account is None:
        return 0
    return len(
        gaps(
            [account],
            JournalRepository(s).list_all([account_id]),
            AssertionRepository(s).list_all([account_id]),
        )
    )


def revalue(
    s: Session, account_id: Id, as_of: date, value: int, import_id: Id | None = None
) -> int:
    """A new value for a holding or a manual asset. Holdings record a valuation and post
    nothing; manual assets post the difference against Equity:Revaluation, so net worth moves
    but income does not (C3). Returns the change from the current figure."""
    account = AccountRepository(s).get(account_id)
    if account is None or account.role is not AccountRole.REAL or account.type is None:
        raise NotFoundError(f"unknown account {account_id}")
    journal = JournalRepository(s)
    current = balance(account_id, journal.list_all([account_id]), as_of)
    if account.group is Group.INVESTMENTS:
        ValuationRepository(s).add(account_id, as_of, value, import_id)
        return value - current
    if account.binding is not None:
        raise InvalidInput("this account's balance comes from its statements")
    difference = value - current
    if difference:
        equity = AccountRepository(s).by_path(REVALUATION)
        if equity is None:
            raise NotFoundError("the ledger has no revaluation account")
        journal.add(_system_tx(as_of, "Revaluation", account_id, equity.id, difference))
    return difference


# removal ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RemovalResult:
    transactions_deleted: int
    rebalanced: int


def _strip(
    s: Session, doomed: dict[Id, set[Id]], removed_import: Id | None = None
) -> tuple[int, int, set[Id]]:
    """Remove the given postings from their transactions. A transaction left without an
    observed posting goes; one that keeps another account's observed posting is balanced again
    against money in transit, so the books never go out of balance. Returns (deleted,
    rebalanced, accounts whose history changed)."""
    journal = JournalRepository(s)
    transit = AccountRepository(s).by_path(IN_TRANSIT)
    if transit is None:
        raise NotFoundError("the ledger has no money-in-transit account")
    deleted = rebalanced = 0
    touched: set[Id] = set()
    for tx_id, posting_ids in doomed.items():
        tx = journal.get(tx_id)
        if tx is None:
            continue
        touched |= {p.account_id for p in tx.postings}
        keep = [p for p in tx.postings if p.id not in posting_ids]
        if not any(p.origin is Origin.OBSERVED for p in keep):
            journal.delete(tx_id)
            deleted += 1
            continue
        journal.delete_postings([p.id for p in tx.postings if p.id in posting_ids])
        if removed_import is not None and tx.import_id == removed_import:
            # The transaction row survives (the other account's observed posting is on it), so
            # it must stop pointing at the statement that is going away.
            anchor_import = next(p.import_id for p in keep if p.origin is Origin.OBSERVED)
            journal.retag_import(tx_id, [], anchor_import)
        rest = sum(p.amount for p in keep)
        if rest:
            anchor = next(p for p in keep if p.origin is Origin.OBSERVED)
            journal.add_posting(
                tx_id, Posting(transit.id, -rest, Origin.INFERRED, import_id=anchor.import_id)
            )
            rebalanced += 1
    return deleted, rebalanced, touched


def remove_import(s: Session, import_id: Id) -> RemovalResult:
    """Undo a statement: its rows, its balances and its valuations."""
    record = ImportRepository(s).get(import_id)
    if record is None:
        raise NotFoundError(f"unknown statement {import_id}")
    journal = JournalRepository(s)
    from_import = journal.postings_from_import(import_id)
    # Rows another statement of the account also contains stay, handed over to that statement.
    held = ImportHashRepository(s).held_elsewhere(
        record.account_id,
        [p.dedup_hash for _, p in from_import if p.dedup_hash],
        import_id,
    )
    handed: dict[Id, tuple[Id, set[Id]]] = {}
    for tx_id, p in from_import:
        if p.dedup_hash and p.dedup_hash in held:
            handed[tx_id] = (held[p.dedup_hash], set())
    doomed: dict[Id, set[Id]] = defaultdict(set)
    for tx_id, p in from_import:
        if tx_id in handed:
            handed[tx_id][1].add(p.id)  # type: ignore[arg-type]
        else:
            doomed[tx_id].add(p.id)  # type: ignore[arg-type]
    for tx_id, (new_import, posting_ids) in handed.items():
        journal.retag_import(tx_id, list(posting_ids), new_import)
    deleted, rebalanced, touched = _strip(s, doomed, import_id)
    AssertionRepository(s).delete_for_import(import_id)
    ValuationRepository(s).delete_for_import(import_id)
    ImportRepository(s).delete(import_id)
    pair_in_transit(s)
    before = len(JournalRepository(s).list_all([record.account_id]))
    for account_id in touched | {record.account_id}:
        recompute_opening(s, account_id)
    after = len(JournalRepository(s).list_all([record.account_id]))
    return RemovalResult(deleted + max(0, before - after), rebalanced)


def remove_account_postings(s: Session, account_id: Id) -> None:
    """Everything on an account, so the account itself can be deleted."""
    for record in ImportRepository(s).list_all(account_id):
        remove_import(s, record.id)
    doomed: dict[Id, set[Id]] = defaultdict(set)
    for t in JournalRepository(s).list_all([account_id]):
        system = t.source == "system"
        for p in t.postings:
            if p.account_id == account_id or system:
                doomed[t.id].add(p.id)  # type: ignore[arg-type]
    _strip(s, doomed)
    AssertionRepository(s).delete_for_account(account_id)
    ValuationRepository(s).delete_for_account(account_id)
