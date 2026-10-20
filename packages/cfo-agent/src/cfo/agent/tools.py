"""The agent's five tools: thin wrappers over the report layer (spec 4.6, design §5.12).

Each returns amounts as integer paise plus a preformatted Indian-grouped string, so the model
quotes figures and never computes them. Account paths are removed from what the model sees:
names are enough, and paths carry the owner's own words in a form the masker does not alias.
The docstrings are what the model reads, so they say when to call each tool.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from cfo.core.types import Scope
from cfo.ledger import reports
from cfo.ledger.repositories.db import Database

Json = dict[str, Any]
_HIDDEN = {"path", "parent_path", "binding", "account_id", "id", "transaction_id", "import_id"}


def _for_model(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _for_model(v) for k, v in value.items() if k not in _HIDDEN}
    if isinstance(value, list):
        return [_for_model(v) for v in value]
    return value


def build_tools(
    db: Database, clock: Callable[[], date], scope: Scope | None = None
) -> list[Callable[..., Json]]:
    """The tools for one ledger: every read is bounded by `scope`."""

    def read(fn: Callable[[reports.Data], Any]) -> Json:
        try:
            with db.transaction(scope) as s:
                return {"result": _for_model(fn(reports.load(s, clock())))}
        except ValueError as exc:
            return {"error": str(exc)}

    def get_net_worth(as_of: str | None = None) -> Json:
        """Net worth (what the owner owns minus what they owe), grouped into cash and savings,
        investments, deposits, other assets and what is owed, with every account's balance.

        Call this for questions about net worth, assets, debts, or account balances.

        Args:
            as_of: Optional date, YYYY-MM-DD. Defaults to today.
        """
        return read(
            lambda d: reports.balance_sheet_report(d, date.fromisoformat(as_of) if as_of else None)
        )

    def get_spending(month: str | None = None) -> Json:
        """One month's income statement: earned, spent, saved, money to and from people,
        rewards, and spending by category (categories nest, such as Food > Dining), plus a check
        that the change in net worth matches.

        Call this for how much was earned, spent or saved, or where money went in a month.

        Args:
            month: Optional month, YYYY-MM. Defaults to the current month, or the latest month
                with statements; the result states the month used.
        """
        return read(lambda d: reports.income_statement_report(d, month))

    def get_leaks(month: str | None = None) -> Json:
        """Spending that grew: each payee's spend this month against the average of the three
        months before. When the month is incomplete the reason says so.

        Call this for "where did my money leak", overspending, or unusual spending questions.

        Args:
            month: Optional month, YYYY-MM. Defaults as in get_spending.
        """
        return read(lambda d: reports.leaks_report(d, month))

    def get_safe_to_spend() -> Json:
        """How much can be spent now: cash and savings, minus the base amount the owner keeps
        aside and what is owed on credit cards, capped by the monthly allowance if one is set.
        Lists each subtraction.

        Call this for "can I afford" or "how much can I spend" questions.
        """
        return read(reports.safe_to_spend_report)

    def get_inbox() -> Json:
        """What needs the owner's attention: rows without a category, money moved to an own
        account whose other side has not been uploaded, statements the ledger disagrees with,
        and card bills due. Each item has a plain sentence.

        Call this when asked what to fix, what is missing, or whether the data is complete.
        """
        return read(reports.inbox_report)

    return [get_net_worth, get_spending, get_leaks, get_safe_to_spend, get_inbox]
