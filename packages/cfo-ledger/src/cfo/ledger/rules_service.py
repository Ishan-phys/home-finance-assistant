"""Applying owner rules: to the rows of an upload, and to rows already in the ledger.

Authority, highest first: the owner's change to one transaction, an owner mapping of that exact
narration, rules by position, then the model. A rule therefore never touches a row the owner set
by hand or a narration the owner mapped, and it beats a mapping only the model made.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from cfo.core.chart import IN_TRANSIT
from cfo.core.errors import InvalidInput
from cfo.core.ids import Id, new_id
from cfo.core.types import (
    Account,
    AccountRole,
    Direction,
    MappingSource,
    MerchantMapping,
    Origin,
    Posting,
    Scope,
)
from cfo.ledger.journal import _counter, _usable, pair_in_transit
from cfo.ledger.repositories.accounts import AccountRepository
from cfo.ledger.repositories.rules import RuleRepository
from cfo.ledger.repositories.transactions import JournalRepository, MappingRepository
from cfo.rules import MatchMode, Rule, first_match
from cfo.rules import Way as RuleWay
from sqlalchemy.orm import Session

Way = Literal["debit", "credit"]


def rule_mappings(
    rules: Sequence[Rule],
    wanted: Mapping[str, Way],
    known: Mapping[str, MerchantMapping],
) -> dict[str, MerchantMapping]:
    """Mappings for the narrations in `wanted` that a rule matches, except those the owner has
    already mapped. Not stored: a rule is looked up again each time, so editing it takes effect."""
    out: dict[str, MerchantMapping] = {}
    for narration, way in wanted.items():
        mapped = known.get(narration)
        if mapped is not None and mapped.source is MappingSource.OWNER:
            continue
        rule = first_match(rules, narration, way)
        if rule is not None:
            out[narration] = MerchantMapping(
                narration, rule.label, rule.target, MappingSource.OWNER
            )
    return out


def _candidates(
    s: Session, rule: Rule, originals: Mapping[Id, str] | None
) -> list[tuple[Id, Posting]]:
    """Transactions the rule would move: one observed side, a counter side the owner did not set,
    a narration the owner has not mapped, and text the rule matches."""
    journal = JournalRepository(s)
    txs = journal.list_all()
    owned = {
        k
        for k, m in MappingRepository(s).get_many({t.narration for t in txs}).items()
        if m.source is MappingSource.OWNER
    }
    out = []
    for t in txs:
        if t.narration in owned:
            continue
        try:
            counter = _counter(t)
        except InvalidInput:
            continue  # a movement between two of the owner's accounts
        if counter.origin is Origin.OWNER:
            continue
        observed = next(p for p in t.postings if p.origin is Origin.OBSERVED)
        way: Way = "debit" if observed.amount < 0 else "credit"
        text = (originals or {}).get(t.id) or t.narration
        if first_match([rule], text, way) is not None:
            out.append((t.id, counter))
    return out


def preview_rule(s: Session, rule: Rule, originals: Mapping[Id, str] | None = None) -> int:
    """How many existing transactions applying the rule would move."""
    target = _target(s, rule)
    return sum(1 for _, c in _candidates(s, rule, originals) if c.account_id != target.id)


def apply_rule(s: Session, rule: Rule, originals: Mapping[Id, str] | None = None) -> int:
    """Post the matching transactions' other side to the rule's account. Only the counter-posting
    changes (same amount, so the transaction still balances). Returns how many changed."""
    target = _target(s, rule)
    journal = JournalRepository(s)
    changed = 0
    for _, counter in _candidates(s, rule, originals):
        if counter.account_id == target.id or counter.id is None:
            continue
        journal.replace_posting_account(counter.id, target.id, Origin.INFERRED)
        changed += 1
    if changed:
        pair_in_transit(s)
    return changed


def _target(s: Session, rule: Rule) -> Account:
    target = AccountRepository(s).by_path(rule.target)
    if target is None or not _usable(target):
        raise InvalidInput("this rule points at a category that is retired or missing")
    return target


# Starter rules: card bill payments are transfers (never spending), cashback is a reward.
# Editable and deletable like any rule. Not shipped: anything naming a service that is also used
# for other payments (CRED pays rent and bills too), so the owner adds those from their own rows.
STARTER_RULES: tuple[tuple[str, str, RuleWay, str], ...] = (
    ("Card bill payment", "BPPY CC PAYMENT", "any", IN_TRANSIT),
    ("Card bill payment", "CREDIT CARD PAYMENT", "any", IN_TRANSIT),
    ("Card bill payment", "CC PAYMENT", "any", IN_TRANSIT),
    ("Card bill payment", "MB/IB PAYMENT", "any", IN_TRANSIT),
    ("Card bill payment", "PAYMENT RECEIVED", "credit", IN_TRANSIT),
    ("Card cashback", "CASHBACK", "any", "Income:Rewards"),
)

KEYWORD_POSITION = 1_000_000  # keyword rules run after every owner rule


def seed_starter_rules(s: Session, scope: Scope | None = None) -> int:
    """Give a new ledger the starter rules. Does nothing once the ledger has any rule, so rules
    the owner deleted stay deleted."""
    repo = RuleRepository(s, scope)
    if repo.list_all():
        return 0
    for label, text, way, target in STARTER_RULES:
        repo.add(label, text, MatchMode.CONTAINS, way, target, builtin=True)
    return len(STARTER_RULES)


def keyword_rules(s: Session) -> list[Rule]:
    """The owner's per-category keywords as the lowest-priority rules. Not stored: they follow
    whatever the keywords say now."""
    out: list[Rule] = []
    for a in AccountRepository(s).list_all(AccountRole.CATEGORY):
        way: RuleWay = "credit" if a.direction is Direction.IN else "debit"
        for word in [w.strip() for w in a.keywords.split(",") if w.strip()]:
            out.append(
                Rule(
                    new_id(),
                    a.display_name,
                    word,
                    MatchMode.CONTAINS,
                    way,
                    a.path,
                    KEYWORD_POSITION + len(out),
                )  # fmt: skip
            )
    return out


def active_rules(s: Session) -> list[Rule]:
    """The owner's rules, then keyword rules: what an upload or a retry matches against."""
    return [*RuleRepository(s).list_all(), *keyword_rules(s)]
