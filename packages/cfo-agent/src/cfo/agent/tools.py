"""The agent's nine tools: thin wrappers over the report layer (spec 4.6, design §5.12).

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
    db: Database,
    clock: Callable[[], date],
    scope: Scope | None = None,
    unalias: Callable[[str], str] | None = None,
) -> list[Callable[..., Json]]:
    """The tools for one ledger: every read is bounded by `scope`. The model only ever sees
    account names as aliases, so an account it asks for comes back as one: `unalias` turns it
    into the real name before it is looked up."""
    real_name = unalias or (lambda text: text)

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

    def get_trend(months: int = 6) -> Json:
        """How money moved over the last several months: for each month, money in, money out,
        saved and the savings rate, how spending changed against the month before, the average of
        the complete months, and which categories drove the latest month (each with its share of
        spending and its change against the month before). A month still in progress is marked
        not complete.

        Call this for "how am I doing", trends, savings rate, whether spending is rising, what
        changed, or any question that needs a comparison between months. Pair it with
        get_spending or get_leaks to explain a change.

        Args:
            months: How many months back to look, from 2 to 12. Defaults to 6.
        """
        return read(lambda d: reports.trend_report(d, months))

    def get_account_activity(
        month: str | None = None,
        start: str | None = None,
        end: str | None = None,
        kind: str = "all",
    ) -> Json:
        """What each bank account, credit card or loan did over a period: spending, money sent to
        people, money moved to the owner's own accounts (such as a card bill payment), total
        paid out, number of payments, income and money received, with each account's type and
        its rank. The result also names which account ranks first.

        Call this for "which credit card had the most spending", "which bank account made the
        most payments", "how much came into my savings account", or any comparison between the
        owner's accounts or cards. Card bill payments are moves between own accounts, not
        spending; the result keeps them apart.

        Args:
            month: Optional month, YYYY-MM. Do not combine with start or end.
            start: Optional first day, YYYY-MM-DD.
            end: Optional last day, YYYY-MM-DD. With neither month nor dates, the latest month
                with statements is used; the result states the period.
            kind: "all" (default), "bank" (savings and current), "credit_card" or "loan".
        """
        return read(lambda d: reports.account_activity_report(d, month, start, end, kind))

    def find_transactions(
        text: str | None = None,
        category: str | None = None,
        account: str | None = None,
        month: str | None = None,
        start: str | None = None,
        end: str | None = None,
        direction: str = "out",
        sort: str = "amount",
        limit: int = 10,
        include_transfers: bool = False,
    ) -> Json:
        """Find movements by payee, category, account and period: the count, the total, a
        month-by-month split and the largest or latest few. Transfers between the owner's own
        accounts are left out unless asked for.

        Call this for "how much did I spend on Swiggy", "how much on food in the last three
        months", "my biggest expenses", "what did I pay from my credit card", "what came into
        my savings", or to look at the latest transactions.

        Args:
            text: Optional text to find in the payee, such as "swiggy".
            category: Optional category, such as "Food" or "Dining"; its sub-categories count.
            account: Optional account, named as it appeared in an earlier result.
            month: Optional month, YYYY-MM. Do not combine with start or end.
            start: Optional first day, YYYY-MM-DD.
            end: Optional last day, YYYY-MM-DD. With no period at all, every statement is used.
            direction: "out" (money leaving, the default), "in" (money arriving) or "any".
            sort: "amount" (largest first, the default) or "date" (latest first).
            limit: How many rows to list, 1 to 25. Defaults to 10. The count and total always
                cover every match.
            include_transfers: True to include moves between the owner's own accounts.
        """
        return read(
            lambda d: reports.transactions_search_report(
                d,
                text,
                month,
                start,
                end,
                direction,
                category,
                real_name(account) if account else None,
                sort,
                limit,
                include_transfers,
            )
        )

    def get_recurring_payments(months: int = 6) -> Json:
        """Payments that come back month after month, such as rent, subscriptions and EMIs: each
        payee seen in at least three of the last complete months, with its usual monthly amount
        and whether it is steady, plus the total of all of them per month.

        Call this for subscriptions, regular or fixed costs, what is committed each month, or
        what could be cancelled. It cannot tell a subscription from any other habit.

        Args:
            months: How many complete months to look at, 3 to 12. Defaults to 6.
        """
        return read(lambda d: reports.recurring_payments_report(d, months))

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

    return [
        get_net_worth,
        get_spending,
        get_trend,
        get_account_activity,
        find_transactions,
        get_recurring_payments,
        get_leaks,
        get_safe_to_spend,
        get_inbox,
    ]
