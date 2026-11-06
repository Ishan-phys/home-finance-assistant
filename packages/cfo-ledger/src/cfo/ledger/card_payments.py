"""Paying a credit card from a bank row, before the card's statement shows the payment.

The owner says which card a row of money leaving a bank account paid. The row's other side moves
from a guess (a category, money in transit) to that card's liability, so the card owes less at
once and the transaction still sums to zero. When the card's own statement later shows the same
payment, that line replaces the recorded one (`adopt_card_payments`). Until then the owner can
put the row back exactly as it was (`undo_card_payment`)."""

from __future__ import annotations

from dataclasses import dataclass

from cfo.core.chart import IN_TRANSIT
from cfo.core.errors import ConflictError, InvalidInput, NotFoundError
from cfo.core.ids import Id
from cfo.core.types import Account, AccountRole, AccountType, Origin
from cfo.ledger.journal import _counter, _usable
from cfo.ledger.pairing import Half, find_card_matches
from cfo.ledger.repositories.accounts import AccountRepository
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.metrics.card_payments import payable_amount
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class Previous:
    """What the row's other side was, so a mistaken pick can be put back exactly."""

    account_id: Id
    origin: Origin


@dataclass(frozen=True, slots=True)
class CardPaid:
    previous: Previous
    matched: bool  # the card's statement already had this payment, so it cannot be undone


def _is_card(account: Account | None) -> bool:
    return (
        account is not None
        and account.role is AccountRole.REAL
        and account.type is AccountType.CREDIT_CARD
    )


def pay_card(s: Session, tx_id: Id, card_id: Id) -> CardPaid:
    """Record a bank row as a payment to `card_id`. Choosing a different card moves it."""
    journal = JournalRepository(s)
    tx = journal.get(tx_id)
    if tx is None:
        raise NotFoundError(f"unknown transaction {tx_id}")
    accounts = AccountRepository(s).list_all(include_retired=True)
    if payable_amount(accounts, tx) is None:
        raise InvalidInput("only money that left a bank or cash account can pay a card")
    card = next((a for a in accounts if a.id == card_id), None)
    if card is None or not _is_card(card) or not card.active:
        raise InvalidInput("pick one of your credit cards")
    counter = _counter(tx)
    previous = Previous(counter.account_id, counter.origin)
    if counter.account_id != card.id:
        journal.replace_posting_account(counter.id, card.id, Origin.OWNER)  # type: ignore[arg-type]
    adopt_card_payments(s)
    after = journal.get(tx_id)
    matched = after is not None and sum(p.origin is Origin.OBSERVED for p in after.postings) == 2
    return CardPaid(previous, matched)


def undo_card_payment(s: Session, tx_id: Id, account_id: Id, origin: Origin) -> None:
    """Put the other side back as it was before `pay_card`. Refused once the card's statement
    has matched the payment, because then it is a confirmed movement between two accounts."""
    from cfo.ledger.journal import pair_in_transit  # noqa: PLC0415

    journal = JournalRepository(s)
    tx = journal.get(tx_id)
    if tx is None:
        raise NotFoundError(f"unknown transaction {tx_id}")
    accounts = {a.id: a for a in AccountRepository(s).list_all(include_retired=True)}
    others = [p for p in tx.postings if p.origin is not Origin.OBSERVED]
    if (
        len(others) != 1
        or others[0].origin is not Origin.OWNER
        or not _is_card(accounts.get(others[0].account_id))
    ):
        raise ConflictError("this payment is already matched with the card's statement")
    target = accounts.get(account_id)
    if origin not in (Origin.INFERRED, Origin.OWNER) or not (
        _usable(target) or (_is_card(target) and target is not None and target.active)
    ):
        raise InvalidInput("that is not somewhere this payment can go back to")
    journal.replace_posting_account(others[0].id, account_id, origin)  # type: ignore[arg-type]
    if target is not None and target.path == IN_TRANSIT:
        pair_in_transit(s)


def adopt_card_payments(s: Session) -> int:
    """Match each payment recorded against a card with that card's statement line for it, and
    keep one transaction with both sides observed. Returns how many were matched."""
    accounts = AccountRepository(s).list_all(include_retired=True)
    cards = {a.id for a in accounts if _is_card(a)}
    transit = next((a.id for a in accounts if a.path == IN_TRANSIT), None)
    if not cards or transit is None:
        return 0
    journal = JournalRepository(s)
    recorded: list[Half] = []
    lines: list[Half] = []
    card_of: dict[Id, Id] = {}
    for t in journal.list_all(list(cards)):
        if len(t.postings) != 2:
            continue
        a, b = t.postings
        for mine, other in ((a, b), (b, a)):
            if mine.account_id not in cards or mine.amount <= 0:
                continue
            half = Half(t.id, mine.account_id, t.date, mine.amount)
            if (
                mine.origin is Origin.OWNER
                and other.origin is Origin.OBSERVED
                and other.account_id not in cards
            ):
                recorded.append(half)
            elif (
                mine.origin is Origin.OBSERVED
                and other.account_id == transit
                and other.origin is Origin.INFERRED
            ):
                lines.append(half)
                card_of[t.id] = mine.account_id
    pairs = find_card_matches(recorded, lines)
    for recorded_tx, line_tx in pairs:
        journal.adopt_statement_line(recorded_tx, line_tx, card_of[line_tx])
    return len(pairs)
