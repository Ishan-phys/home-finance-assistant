"""What is private in a ledger: its redaction terms, account names, and the categories the
owner named."""

from __future__ import annotations

from cfo.core.chart import DEFAULT_CATEGORIES
from cfo.core.types import AccountRole, Group
from cfo.ledger.repositories.accounts import AccountRepository, RedactionTermRepository
from sqlalchemy.orm import Session

_FAMILY = {
    Group.LIQUID: "Liquid_Account",
    Group.OWED: "Credit_Or_Loan",
    Group.FIXED: "Fixed_Yield_Account",
    Group.INVESTMENTS: "Investment_Account",
    Group.OTHER: "Other_Asset",
}
_DEFAULT_PATHS = {c.path for c in DEFAULT_CATEGORIES}


def load_privacy_inputs(session: Session) -> dict[str, object]:
    """What a masker needs, as plain data: `terms`, `accounts` as (key, name, family,
    institution, reference), and `titles` as (key, title, family). The ledger knows what is
    private; the caller (which owns the redactor) turns it into a masker. Custom category names
    are the owner's words, so they are aliased like account names."""
    repo = AccountRepository(session)
    accounts = [
        (f"{a.id}", a.display_name, _FAMILY[a.group or Group.OTHER], institution, reference)
        for a, institution, reference in repo.private_accounts()
    ]
    titles = [
        (f"{a.id}", a.display_name, "Category")
        for a in repo.list_all(AccountRole.CATEGORY, include_retired=True)
        if a.path not in _DEFAULT_PATHS
    ]
    return {
        "terms": RedactionTermRepository(session).list_all(),
        "accounts": accounts,
        "titles": titles,
    }
