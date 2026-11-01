"""Owner rules: stored per ledger, applied to rows already in the ledger (spec 2)."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.core.chart import IN_TRANSIT
from cfo.core.errors import InvalidInput
from cfo.core.types import AccountType, MappingSource, MerchantMapping, Origin
from cfo.ledger.journal import RowIn, pair_in_transit, post_rows, recategorize
from cfo.ledger.repositories.accounts import AccountRepository, ImportRepository
from cfo.ledger.repositories.rules import RuleRepository
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.rules_service import apply_rule, preview_rule, rule_mappings
from cfo.ledger.setup import AccountInput, add_account
from cfo.ledger.verify import verify_books
from cfo.rules import MatchMode

TODAY = date(2026, 10, 20)
RENT = "UPI-[PERSON:5e31]-[VPA:19cd]-HDFC0000001-[ID:d938]-RENT"


def _setup(s):  # type: ignore[no-untyped-def]
    sav = add_account(s, AccountInput(AccountType.SAVINGS, "HDFC", "Savings"), TODAY, "hdfc_bank")
    card = add_account(s, AccountInput(AccountType.CREDIT_CARD, "HDFC", "Card"), TODAY, "hdfc_card")
    return sav, card


def _import(s, account_id):  # type: ignore[no-untyped-def]
    return ImportRepository(s).add(
        account_id, "f.csv", "0" * 64, period_start=None, period_end=date(2026, 9, 30),
        rows_inserted=0, hashes_ignored=0,
    ).id  # fmt: skip


def _row(day: str, amount: int, narration: str, h: str) -> RowIn:
    return RowIn(date.fromisoformat(day), amount, narration, narration.title(), h)


def _counter_path(s, narration: str) -> str:  # type: ignore[no-untyped-def]
    paths = {a.id: a.path for a in AccountRepository(s).list_all(include_retired=True)}
    (t,) = JournalRepository(s).with_narration(narration)
    return next(paths[p.account_id] for p in t.postings if p.origin is not Origin.OBSERVED)


def test_repository_crud_order_and_blank_rejected(database) -> None:  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        repo = RuleRepository(s)
        a = repo.add("Rent", RENT, MatchMode.CONTAINS, "debit", "Expenses:Housing")
        b = repo.add("Cred", "cred", MatchMode.CONTAINS, "any", IN_TRANSIT)
        assert [r.id for r in repo.list_all()] == [a.id, b.id]
        repo.reorder([b.id, a.id])
        assert [r.id for r in repo.list_all()] == [b.id, a.id]
        with pytest.raises(InvalidInput):
            repo.reorder([a.id])
        with pytest.raises(ValueError):
            repo.add("x", "   ", MatchMode.CONTAINS, "any", "Expenses:Housing")
        repo.update(a.id, label="Landlord")
        assert repo.get(a.id).label == "Landlord"  # type: ignore[union-attr]
        repo.delete(b.id)
        assert [r.id for r in repo.list_all()] == [a.id]


def test_apply_rule_moves_uncategorized_and_balances(database) -> None:  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        sav, _ = _setup(s)
        post_rows(s, sav, _import(s, sav.id), [_row("2026-09-02", -4500000, RENT, "h1")], {})
        rule = RuleRepository(s).add(
            "Rent", "[PERSON:5e31]", MatchMode.CONTAINS, "debit", "Expenses:Housing"
        )
        assert preview_rule(s, rule) == 1
        assert apply_rule(s, rule) == 1
        assert _counter_path(s, RENT) == "Expenses:Housing"
        assert apply_rule(s, rule) == 0
        assert verify_books(s) == []


def test_apply_rule_skips_owner_set_rows_and_owner_mappings(database) -> None:  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        sav, _ = _setup(s)
        post_rows(s, sav, _import(s, sav.id), [_row("2026-09-02", -100, "UPI-SHOP-A", "h1"),
                                               _row("2026-09-03", -100, "UPI-SHOP-B", "h2")], {})  # fmt: skip
        housing = AccountRepository(s).by_path("Expenses:Housing")
        fitness_free = AccountRepository(s).by_path("Expenses:Shopping")
        (b,) = JournalRepository(s).with_narration("UPI-SHOP-B")
        recategorize(s, b.id, fitness_free.id)  # the owner chose Shopping by hand
        rule = RuleRepository(s).add("Shops", "UPI-SHOP", MatchMode.CONTAINS, "any", housing.path)
        assert apply_rule(s, rule) == 1
        assert _counter_path(s, "UPI-SHOP-A") == "Expenses:Housing"
        assert _counter_path(s, "UPI-SHOP-B") == "Expenses:Shopping"


def test_rule_mappings_beats_model_but_not_owner() -> None:
    from cfo.core.ids import new_id
    from cfo.rules import Rule

    rule = Rule(new_id(), "Rent", "rent", MatchMode.CONTAINS, "any", "Expenses:Housing", 0)
    known = {
        "A RENT": MerchantMapping("A RENT", "x", "Expenses:Shopping", MappingSource.MODEL),
        "B RENT": MerchantMapping("B RENT", "x", "Expenses:Shopping", MappingSource.OWNER),
    }
    out = rule_mappings([rule], {"A RENT": "debit", "B RENT": "debit", "C": "debit"}, known)
    assert set(out) == {"A RENT"} and out["A RENT"].label == "Expenses:Housing"


def test_transfer_rule_pairs_card_payment_out_of_spending(database) -> None:  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        sav, card = _setup(s)
        post_rows(
            s,
            sav,
            _import(s, sav.id),
            [_row("2026-09-02", -500000, "UPI-CRED CLUB-PAYMENT ON CRED", "h1")],
            {},
        )
        post_rows(
            s, card, _import(s, card.id), [_row("2026-09-03", 500000, "PAYMENT RECEIVED", "h2")], {}
        )
        rule = RuleRepository(s).add(
            "Card bill", "cred club", MatchMode.CONTAINS, "debit", IN_TRANSIT
        )
        card_rule = RuleRepository(s).add(
            "Card bill in", "payment received", MatchMode.CONTAINS, "credit", IN_TRANSIT
        )
        apply_rule(s, rule)
        apply_rule(s, card_rule)
        pair_in_transit(s)
        txs = JournalRepository(s).list_all()
        assert len(txs) == 1 and {p.account_id for p in txs[0].postings} == {sav.id, card.id}
        assert verify_books(s) == []


def test_starter_rules_seed_once_and_deleted_ones_stay_deleted(database) -> None:  # type: ignore[no-untyped-def]
    from cfo.ledger.rules_service import STARTER_RULES, keyword_rules, seed_starter_rules

    with database.transaction() as s:
        assert seed_starter_rules(s) == len(STARTER_RULES)
        assert seed_starter_rules(s) == 0
        repo = RuleRepository(s)
        for r in repo.list_all():
            repo.delete(r.id)
        assert repo.list_all() == []
        assert keyword_rules(s) == []


def test_keywords_become_lowest_priority_rules(database) -> None:  # type: ignore[no-untyped-def]
    from cfo.ledger.rules_service import active_rules
    from cfo.ledger.setup import edit_category

    with database.transaction() as s:
        grooming = AccountRepository(s).by_path("Expenses:Grooming")
        edit_category(s, grooming.id, keywords=" haircut, Spa ,spa, massage")
        assert AccountRepository(s).by_path("Expenses:Grooming").keywords == "haircut, Spa, massage"
        owner = RuleRepository(s).add("Mine", "haircut", MatchMode.CONTAINS, "any", "Expenses:Fees")
        rules = active_rules(s)
        assert rules[0].id == owner.id and {r.match_text for r in rules[1:]} == {
            "haircut",
            "Spa",
            "massage",
        }
        assert all(r.way == "debit" and r.target == "Expenses:Grooming" for r in rules[1:])
