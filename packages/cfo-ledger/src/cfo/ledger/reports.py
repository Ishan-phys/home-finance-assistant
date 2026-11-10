"""Read-side reports: load the ledger once, call the pure metrics, and shape plain JSON.

HTTP routes and the chat tools both read through here, so the cockpit and the assistant always
show the same numbers. Every amount is `{"paise": int, "formatted": "₹1,00,000.00"}`, so a
client or a model quotes figures without converting.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import wraps
from typing import Any
from uuid import UUID

from cfo.core.chart import DEFAULT_CATEGORIES, IN_TRANSIT
from cfo.core.dates import month_bounds, month_key, previous_month
from cfo.core.errors import NotFoundError
from cfo.core.ids import Id
from cfo.core.money import format_inr
from cfo.core.types import (
    Account,
    AccountKind,
    AccountRole,
    AccountType,
    Assertion,
    Direction,
    Group,
    ImportRecord,
    Origin,
    Transaction,
    Valuation,
)
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    AssertionRepository,
    ImportRepository,
    LedgerSettings,
    SettingsRepository,
    ValuationRepository,
)
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.metrics.activity import account_activity, ranks
from cfo.metrics.balance_sheet import BalanceSheet, balance_sheet
from cfo.metrics.balances import balances_at
from cfo.metrics.card_payments import card_choices, payable_amount
from cfo.metrics.inbox import inbox
from cfo.metrics.income_statement import CategoryLine, check_line, income_statement
from cfo.metrics.leaks import leaks
from cfo.metrics.reconcile import gaps
from cfo.metrics.recurring import recurring_payments
from cfo.metrics.safe_to_spend import safe_to_spend
from cfo.metrics.search import by_month, find_flows, largest_first, latest_first
from cfo.metrics.trend import category_moves, mean, monthly_trend
from sqlalchemy.orm import Session

Json = dict[str, Any]

GROUP_ORDER = (Group.LIQUID, Group.INVESTMENTS, Group.FIXED, Group.OTHER, Group.OWED)
GROUP_LABELS = {
    Group.LIQUID: "Cash and savings",
    Group.INVESTMENTS: "Investments",
    Group.FIXED: "Deposits",
    Group.OTHER: "Other assets",
    Group.OWED: "What I owe",
}
KIND_LABELS = {
    AccountKind.ASSET: "Assets",
    AccountKind.LIABILITY: "Liabilities",
    AccountKind.INCOME: "Income",
    AccountKind.EXPENSE: "Expenses",
    AccountKind.EQUITY: "Equity",
}
_DEFAULT_PATHS = {c.path for c in DEFAULT_CATEGORIES}


def plain(value: Any) -> Any:
    """JSON-safe: ids become strings, dates ISO strings, tuples lists. A model client serializes
    tool results with the standard library, which rejects a UUID."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    return value


def json_safe[T](fn: Callable[..., T]) -> Callable[..., T]:
    """Every report returns plain JSON, whoever reads it: the API, the cockpit, or a model."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return plain(fn(*args, **kwargs))  # type: ignore[no-any-return]

    return wrapper


def money(paise: int) -> Json:
    return {"paise": paise, "formatted": format_inr(paise)}


def day(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


@dataclass(frozen=True, slots=True)
class Data:
    accounts: list[Account]
    transactions: list[Transaction]
    assertions: list[Assertion]
    valuations: list[Valuation]
    imports: list[ImportRecord]
    statements: list[Json]  # import history rows, with file names
    settings: LedgerSettings
    today: date

    def account(self, account_id: Id | None) -> Account | None:
        return next((a for a in self.accounts if a.id == account_id), None)

    def name(self, account_id: Id | None) -> str:
        found = self.account(account_id)
        return found.display_name if found else "?"


def load(session: Session, today: date) -> Data:
    """Everything the reports need, in one scoped read."""
    return Data(
        accounts=AccountRepository(session).list_all(include_retired=True),
        transactions=JournalRepository(session).list_all(),
        assertions=AssertionRepository(session).list_all(),
        valuations=ValuationRepository(session).list_all(),
        imports=ImportRepository(session).list_all(),
        statements=ImportRepository(session).history(),
        settings=SettingsRepository(session).get(),
        today=today,
    )


def _sheet(data: Data, as_of: date) -> BalanceSheet:
    return balance_sheet(data.accounts, data.transactions, data.valuations, as_of)


def account_json(a: Account, balance: int | None = None) -> Json:
    out: Json = {
        "id": a.id,
        "path": a.path,
        "name": a.display_name,
        "kind": a.kind.value,
        "role": a.role.value,
        "type": a.type.value if a.type else None,
        "type_label": a.type.label if a.type else None,
        "group": a.group.value if a.group else None,
        "institution": a.institution,
        "binding": a.binding,
        "manual": bool(a.type and a.type.manual),
        "description": a.description,
        "keywords": a.keywords,
        "direction": a.direction.value if a.direction else None,
        "heading": a.heading.value,
        "retired": not a.active,
    }
    if balance is not None:
        out["balance"] = money(balance)
    return out


# money: the balance sheet --------------------------------------------------------------


@json_safe
def balance_sheet_report(data: Data, as_of: date | None = None) -> Json:
    when = as_of or data.today
    sheet = _sheet(data, when)
    groups = []
    for g in GROUP_ORDER:
        lines = [line for line in sheet.lines if line.group is g]
        accounts = []
        for line in lines:
            a = data.account(line.account_id)
            if a is None:
                continue
            row = account_json(a, line.balance)
            if line.market is not None:
                row |= {
                    "cost": money(line.cost),
                    "market": money(line.market),
                    "unrealized": money(line.unrealized),
                }
            accounts.append(row)
        groups.append(
            {
                "group": g.value,
                "label": GROUP_LABELS[g],
                "total": money(sheet.groups[g]),
                "accounts": accounts,
            }
        )
    return {"as_of": when, "net_worth": money(sheet.total), "groups": groups}


# where it went: the income statement ---------------------------------------------------


def default_month(data: Data) -> str:
    """This month if anything happened in it, else the latest month with imported rows."""
    current = month_key(data.today)
    months = {month_key(t.date) for t in data.transactions if t.source == "import"}
    if not months or current in months:
        return current
    return max(months)


def _tree(lines: Sequence[CategoryLine], kind: AccountKind) -> list[Json]:
    nodes: dict[str, Json] = {}
    roots: list[Json] = []
    for line in sorted((x for x in lines if x.kind is kind), key=lambda x: x.path):
        node: Json = {
            "path": line.path,
            "name": line.name,
            "account_id": line.account_id,
            "amount": money(line.amount),
            "depth": line.depth,
            "children": [],
        }
        nodes[line.path] = node
        parent = nodes.get(line.path.rsplit(":", 1)[0])
        (parent["children"] if parent else roots).append(node)
    for node in nodes.values():
        node["children"].sort(key=lambda n: -n["amount"]["paise"])
    return sorted(roots, key=lambda n: -n["amount"]["paise"])


@json_safe
def income_statement_report(data: Data, month: str | None = None) -> Json:
    chosen = month or default_month(data)
    start, end = month_bounds(chosen)
    stmt = income_statement(data.accounts, data.transactions, start, end)
    check = check_line(_sheet(data, start - timedelta(days=1)), _sheet(data, end), stmt)
    return {
        "month": chosen,
        "start": start,
        "end": end,
        "earned": money(stmt.earned),
        "spent": money(stmt.spent),
        "net_in": money(stmt.net_in),
        "net_out": money(stmt.net_out),
        "saved": money(stmt.saved),
        "rewards": money(stmt.rewards),
        "people_in": money(stmt.people_in),
        "people_out": money(stmt.people_out),
        "revaluation": money(stmt.revaluation),
        "check": {
            "change_in_net_worth": money(check.change_in_net_worth),
            "saved": money(check.saved),
            "revaluation": money(check.revaluation),
            "opening": money(check.opening),
            "unrealized_change": money(check.unrealized_change),
            "explained": money(check.explained),
            "ok": check.ok,
        },
        "categories": {
            "out": _tree(stmt.categories, AccountKind.EXPENSE),
            "in": _tree(stmt.categories, AccountKind.INCOME),
        },
    }


def _spent_this_month(data: Data) -> int:
    start, end = month_bounds(month_key(data.today))
    return income_statement(data.accounts, data.transactions, start, end).spent


@json_safe
def safe_to_spend_report(data: Data) -> Json:
    s = safe_to_spend(
        _sheet(data, data.today),
        data.settings.min_cash_buffer,
        data.settings.monthly_allowance,
        _spent_this_month(data),
    )
    subtractions = [
        {"label": "Base amount kept aside", "amount": money(s.kept_aside)},
        {"label": "Owed on credit cards", "amount": money(s.owed_on_cards)},
    ]
    return {
        "amount": money(s.amount),
        "liquid": money(s.liquid),
        "kept_aside": money(s.kept_aside),
        "owed_on_cards": money(s.owed_on_cards),
        "available": money(s.available),
        "monthly_allowance": None
        if data.settings.monthly_allowance is None
        else money(data.settings.monthly_allowance),
        "allowance_remaining": None
        if s.allowance_remaining is None
        else money(s.allowance_remaining),
        "subtractions": subtractions,
    }


def _month_complete(data: Data, month: str) -> bool:
    _, end = month_bounds(month)
    if end >= data.today:
        return False
    return not gaps(data.accounts, data.transactions, data.assertions)


@json_safe
def leaks_report(data: Data, month: str | None = None) -> Json:
    chosen = month or default_month(data)
    r = leaks(data.accounts, data.transactions, chosen, complete=_month_complete(data, chosen))
    rows = [
        {
            "category": data.name(x.account_id),
            "payee": x.payee,
            "current": money(x.current),
            "baseline_avg": money(x.baseline_avg),
            "variance": money(x.variance),
            "count": x.count,
        }
        for x in (r.variance or ())
        if x.variance > 0
    ]
    current = [
        {
            "category": data.name(x.account_id),
            "payee": x.payee,
            "amount": money(x.amount),
            "count": x.count,
        }
        for x in r.current[:10]
    ]
    return {
        "month": chosen,
        "current": current,
        "complete": r.complete,
        "baseline_months": r.baseline_months,
        "reason": r.variance_reason,
        "rows": rows,
    }


def _movement(change: int | None, pct: int | None) -> Json | None:
    """A change worded for quoting: which way, by how much, and by what percent."""
    if change is None:
        return None
    return {
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
        "amount": money(abs(change)),
        "percent": None if pct is None else f"{abs(pct)}%",
    }


@json_safe
def trend_report(data: Data, months: int = 6) -> Json:
    """Month by month: money in, out and saved, the savings rate, how spending moved against the
    month before, the average of the complete months, and which categories drove the latest
    complete month, each against the month before it. Only months with imported statements are
    listed. A month still in progress is shown but never compared: three days of spending set
    against a whole month would read as a collapse."""
    if not 2 <= months <= 12:
        raise ValueError("months must be between 2 and 12")
    keys = sorted({month_key(t.date) for t in data.transactions if t.source == "import"})[-months:]
    if not keys:
        return {"months": [], "average": None, "categories": None}
    lines = monthly_trend(data.accounts, data.transactions, keys)
    partial = {k for k in keys if month_bounds(k)[1] >= data.today}
    complete = [x for x in lines if x.month not in partial]
    rows = [
        {
            "month": x.month,
            "complete": x.month not in partial,
            "net_in": money(x.net_in),
            "net_out": money(x.net_out),
            "saved": money(x.saved),
            "savings_rate": None if x.savings_rate is None else f"{x.savings_rate}%",
            "net_out_vs_previous": _movement(x.net_out_change, x.net_out_change_pct)
            if i and x.month not in partial and keys[i - 1] not in partial
            else None,
            "compared_with": keys[i - 1] if i else None,
            "note": "month in progress: figures so far, not comparable"
            if x.month in partial
            else None,
        }
        for i, x in enumerate(lines)
    ]
    latest = complete[-1].month if complete else keys[-1]
    return {
        "months": rows,
        "average": None
        if not complete
        else {
            "months_counted": len(complete),
            "net_in": money(mean([x.net_in for x in complete])),
            "net_out": money(mean([x.net_out for x in complete])),
            "saved": money(mean([x.saved for x in complete])),
        },
        "categories": {
            "month": latest,
            "compared_with": previous_month(latest),
            "rows": [
                {
                    "category": c.name,
                    "amount": money(c.amount),
                    "share_of_spending": None if c.share is None else f"{c.share}%",
                    "previous": money(c.previous_amount),
                    "vs_previous": _movement(c.change, c.change_pct),
                }
                for c in category_moves(data.accounts, data.transactions, latest)[:8]
            ],
        },
    }


# which account, which payee: activity, search and regular payments ---------------------

_BANK = {AccountType.SAVINGS, AccountType.CURRENT}
ACCOUNT_KINDS = ("all", "bank", "credit_card", "loan")


def _kind_of(a: Account) -> str:
    if a.type in _BANK:
        return "bank"
    if a.type is AccountType.CREDIT_CARD:
        return "credit_card"
    if a.type is AccountType.LOAN:
        return "loan"
    return "other"


def _type_label(a: Account | None) -> str | None:
    """What kind of account this is, in words the model can use ("Credit card"). The model sees
    only a stand-in name, which would otherwise be all it knew."""
    return a.type.label if a and a.type else None


def _day(label: str, text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{label} must be a date as YYYY-MM-DD, not {text!r}") from None


def _span(
    data: Data, month: str | None, start: str | None, end: str | None, *, whole: bool
) -> tuple[date | None, date | None]:
    """The period asked for. A month, or a start and/or end date; with neither, the default
    month, or (`whole`) no limit at all. Raises ValueError for a bad or backwards range."""
    if month and (start or end):
        raise ValueError("give a month, or a start and end date, not both")
    if month:
        return month_bounds(month)
    if start or end:
        first = _day("start", start) if start else None
        last = _day("end", end) if end else None
        if first and last and first > last:
            raise ValueError("start must not be after end")
        return first, last
    return (None, None) if whole else month_bounds(default_month(data))


def _period_json(data: Data, start: date | None, end: date | None) -> Json:
    dates = [t.date for t in data.transactions]
    first = start or (min(dates) if dates else None)
    last = end or data.today
    return {
        "start": first,
        "end": last,
        # A period that reaches today is still filling up: never present it as a full total.
        "in_progress": last >= data.today,
    }


def _movement_row(data: Data, f: Any) -> Json:
    a = data.account(f.account_id)
    return {
        "date": f.date,
        "payee": f.payee,
        "amount": money(abs(f.amount)),
        "direction": "out" if f.out else "in",
        "account": a.display_name if a else "?",
        "account_type": _type_label(a),
        "category": f.counterpart.display_name if f.counterpart else None,
    }


@json_safe
def account_activity_report(
    data: Data,
    month: str | None = None,
    start: str | None = None,
    end: str | None = None,
    kind: str = "all",
) -> Json:
    """What each bank account, card or loan spent, paid out, received and moved, ranked."""
    if kind not in ACCOUNT_KINDS:
        raise ValueError(f"kind must be one of {', '.join(ACCOUNT_KINDS)}")
    first, last = _span(data, month, start, end, whole=False)
    if first is None or last is None:  # a half-open range: fill the missing side
        dates = [t.date for t in data.transactions]
        first = first or (min(dates) if dates else data.today)
        last = last or data.today
    real = [
        a
        for a in data.accounts
        if a.role is AccountRole.REAL and (kind == "all" or _kind_of(a) == kind)
    ]
    by_id = {a.id: a for a in real}
    active = {
        x.account_id: x for x in account_activity(data.accounts, data.transactions, first, last)
    }
    rows_in = [active[i] for i in by_id if i in active]
    rank = {
        key: ranks({x.account_id: getattr(x, key) for x in rows_in})
        for key in ("spending", "total_out", "payments")
    }
    rows = [
        {
            "account": by_id[x.account_id].display_name,
            "account_type": _type_label(by_id[x.account_id]),
            "spending": money(x.spending),
            "sent_to_people": money(x.people_out),
            "moved_to_own_accounts": money(x.transfers_out),
            "total_out": money(x.total_out),
            "payments": x.payments,
            "income": money(x.income),
            "received_from_people": money(x.people_in),
            "moved_from_own_accounts": money(x.transfers_in),
            "refunds": money(x.refunds),
            "total_in": money(x.total_in),
            "transactions": x.transactions,
            "rank_by_spending": rank["spending"].get(x.account_id),
            "rank_by_total_out": rank["total_out"].get(x.account_id),
            "rank_by_payments": rank["payments"].get(x.account_id),
        }
        for x in sorted(rows_in, key=lambda x: (-x.spending, -x.total_out, str(x.account_id)))
    ]
    top = {
        key: [r["account"] for r in rows if r[f"rank_by_{key}"] == 1]
        for key in ("spending", "total_out", "payments")
    }
    return {
        "period": _period_json(data, first, last),
        "kind": kind,
        "accounts": rows,
        "top": top,  # ties list every account that shares the top rank
        "totals": {
            "spending": money(sum(x.spending for x in rows_in)),
            "total_out": money(sum(x.total_out for x in rows_in)),
            "total_in": money(sum(x.total_in for x in rows_in)),
        },
        "no_activity": [a.display_name for a in real if a.id not in active],
    }


@json_safe
def transactions_search_report(
    data: Data,
    text: str | None = None,
    month: str | None = None,
    start: str | None = None,
    end: str | None = None,
    direction: str = "out",
    category: str | None = None,
    account: str | None = None,
    sort: str = "amount",
    limit: int = 10,
    include_transfers: bool = False,
) -> Json:
    """Movements matching a payee text, category and/or account over a period, with the total,
    a month-by-month split and the largest or latest few."""
    if direction not in ("out", "in", "any"):
        raise ValueError("direction must be out, in or any")
    if sort not in ("amount", "date"):
        raise ValueError("sort must be amount or date")
    if not 1 <= limit <= 25:
        raise ValueError("limit must be between 1 and 25")
    first, last = _span(data, month, start, end, whole=True)
    ids = None
    if account:
        wanted = account.strip().casefold()
        ids = {
            a.id
            for a in data.accounts
            if a.role is AccountRole.REAL and wanted in a.display_name.casefold()
        }
        if not ids:
            known = ", ".join(a.display_name for a in data.accounts if a.role is AccountRole.REAL)
            raise ValueError(f"no account matches {account!r}; the accounts are: {known}")
    matches = find_flows(
        data.accounts,
        data.transactions,
        first,
        last,
        text=text,
        direction=direction,  # type: ignore[arg-type]
        category=category,
        account_ids=ids,
        include_transfers=include_transfers,
    )
    ordered = largest_first(matches) if sort == "amount" else latest_first(matches)
    return {
        "period": _period_json(data, first, last) if (first or last) else "all statements",
        "filters": {
            "text": text,
            "category": category,
            "account": account,
            "direction": direction,
            "transfers_between_own_accounts": include_transfers,
        },
        "count": len(matches),
        "total": money(sum(abs(f.amount) for f in matches)),
        "by_month": [
            {"month": m, "total": money(total), "count": n}
            for m, total, n in by_month(matches)[-12:]
        ],
        "rows": [_movement_row(data, f) for f in ordered[:limit]],
        "truncated": len(matches) > limit,
        "note": "Refunds and money received are listed with direction in; they are not netted off.",
    }


@json_safe
def recurring_payments_report(data: Data, months: int = 6) -> Json:
    """Payees that show up in at least three of the last complete months, with their usual
    monthly amount."""
    if not 3 <= months <= 12:
        raise ValueError("months must be between 3 and 12")
    keys = sorted({month_key(t.date) for t in data.transactions if t.source == "import"})
    complete = [k for k in keys if month_bounds(k)[1] < data.today][-months:]
    if len(complete) < 3:
        return {
            "months_looked_at": complete,
            "payments": [],
            "note": "Regular payments need at least three complete months of statements.",
        }
    found = recurring_payments(data.accounts, data.transactions, complete)
    return {
        "months_looked_at": complete,
        "payments": [
            {
                "payee": r.payee,
                "category": r.category,
                "months_seen": r.months_seen,
                "usual_monthly_amount": money(r.average_monthly),
                "latest_month_amount": money(r.latest_amount),
                "last_paid": r.last_date,
                "steady": r.steady,
            }
            for r in found[:12]
        ],
        "regular_total_per_month": money(sum(r.average_monthly for r in found)),
    }


# what needs the owner ------------------------------------------------------------------


@json_safe
def inbox_report(data: Data) -> list[Json]:
    out = []
    by_id = {t.id: t for t in data.transactions}
    for item in inbox(data.accounts, data.transactions, data.assertions, data.imports):
        who = data.name(item.account_id)
        amount = format_inr(item.amount)
        pay_card = False
        if item.kind == "uncategorized":
            t = by_id[item.transaction_id] if item.transaction_id else None
            text = f"{amount} · {t.payee if t else ''} on {who} needs a category"
            action = "categorize"
        elif item.kind == "unpaired":
            t = by_id.get(item.transaction_id) if item.transaction_id else None
            left = t is not None and any(
                p.amount < 0 and p.origin is Origin.OBSERVED for p in t.postings
            )
            text = (
                f"{amount} left {who} for an account of yours; upload the other side"
                if left
                else f"{amount} arrived in {who} from an account of yours; upload the other side"
            )
            action = "pair"
            pay_card = left and t is not None and payable_amount(data.accounts, t) is not None
        elif item.kind == "gap":
            gap = next(
                g
                for g in gaps(data.accounts, data.transactions, data.assertions)
                if g.account_id == item.account_id and g.as_of == item.date
            )
            way = "short of" if gap.difference > 0 else "more than"
            text = f"{who} is {amount} {way} its statement on {day(item.date)}; upload the missing statement"
            action = "upload"
        else:
            if item.due is not None and item.due != item.amount:
                text = (
                    f"{amount} of the {format_inr(item.due)} {who} bill is still due on "
                    f"{day(item.date)}"
                )
            else:
                text = f"{who} bill of {amount} is due on {day(item.date)}"
            action = "upload"
        out.append(
            {
                "kind": item.kind,
                "amount": money(item.amount),
                "date": item.date,
                "account": {"id": item.account_id, "name": who} if item.account_id else None,
                "transaction_id": item.transaction_id,
                "text": text,
                "action": action,
                "pay_card": pay_card,
            }
        )
    return out


@json_safe
def card_options_report(data: Data, tx_id: Id) -> Json:
    """The cards a bank row could have paid, likeliest first. Empty when it cannot be a card
    payment, so the cockpit offers nothing there."""
    tx = next((t for t in data.transactions if t.id == tx_id), None)
    if tx is None:
        raise NotFoundError(f"unknown transaction {tx_id}")
    amount = payable_amount(data.accounts, tx)
    return {
        "amount": money(amount) if amount is not None else None,
        "cards": [
            {
                "id": c.account_id,
                "name": data.name(c.account_id),
                "owed": money(c.owed),
                "suggested": c.suggested,
                "current": c.current,
            }
            for c in card_choices(data.accounts, data.transactions, data.imports, tx)
        ],
    }


@json_safe
def overview_report(data: Data) -> Json:
    now = _sheet(data, data.today)
    last_month_end = month_bounds(previous_month(month_key(data.today)))[1]
    before = _sheet(data, last_month_end)
    month = default_month(data)
    start, end = month_bounds(month)
    stmt = income_statement(data.accounts, data.transactions, start, end)
    items = inbox_report(data)
    return {
        "as_of": data.today,
        "net_worth": {
            "total": money(now.total),
            "change_since_last_month": money(now.total - before.total),
        },
        "this_month": {
            "month": month,
            "net_in": money(stmt.net_in),
            "net_out": money(stmt.net_out),
            "saved": money(stmt.saved),
        },
        "safe_to_spend": safe_to_spend_report(data),
        "inbox": {"count": len(items), "top": items[:3]},
    }


# transactions --------------------------------------------------------------------------


def _side(data: Data, account_id: Id) -> Json:
    a = data.account(account_id)
    return {
        "id": account_id,
        "name": a.display_name if a else "?",
        "kind": a.kind.value if a else None,
        "role": a.role.value if a else None,
    }


def transaction_json(data: Data, t: Transaction) -> Json:
    negative = min(t.postings, key=lambda p: (p.amount, str(p.account_id)))
    positive = max(t.postings, key=lambda p: (p.amount, str(p.account_id)))
    counter = [p for p in t.postings if p.origin is not Origin.OBSERVED]
    category = None
    if len(counter) == 1:
        a = data.account(counter[0].account_id)
        if a is not None and a.role is not AccountRole.REAL and a.path != IN_TRANSIT:
            category = {
                "id": a.id,
                "name": a.display_name,
                "path": a.path,
                "uncategorized": a.role is AccountRole.SYSTEM,
            }
    paid_card = None
    if len(counter) == 1 and counter[0].origin is Origin.OWNER:
        card = data.account(counter[0].account_id)
        if card is not None and card.role is AccountRole.REAL:
            paid_card = {"id": card.id, "name": card.display_name}  # waiting for its statement
    return {
        "id": t.id,
        "date": t.date,
        "narration": t.narration,
        "payee": t.payee,
        "source": t.source,
        "amount": money(sum(p.amount for p in t.postings if p.amount > 0)),
        "from": _side(data, negative.account_id),
        "to": _side(data, positive.account_id),
        "category": category,
        "card_payment": paid_card,
        "editable": len([p for p in t.postings if p.origin is Origin.OBSERVED]) == 1
        and len(counter) == 1,
        "postings": [
            {
                "account_id": p.account_id,
                "account": data.name(p.account_id),
                "path": data.account(p.account_id).path if data.account(p.account_id) else "?",  # type: ignore[union-attr]
                "amount": money(p.amount),
                "origin": p.origin.value,
            }
            for p in t.postings
        ],
    }


@json_safe
def transactions_report(
    data: Data,
    *,
    account_id: Id | None = None,
    category_id: Id | None = None,
    month: str | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list[Json]:
    bounds = month_bounds(month) if month else None
    needle = q.lower().strip() if q else None
    rows = []
    for t in sorted(data.transactions, key=lambda x: (x.date, str(x.id)), reverse=True):
        touched = {p.account_id for p in t.postings}
        if account_id and account_id not in touched:
            continue
        if category_id and category_id not in touched:
            continue
        if bounds and not bounds[0] <= t.date <= bounds[1]:
            continue
        if needle and needle not in t.narration.lower() and needle not in t.payee.lower():
            continue
        rows.append(transaction_json(data, t))
        if len(rows) >= limit:
            break
    return rows


@json_safe
def account_report(data: Data, account_id: Id) -> Json:
    account = data.account(account_id)
    if account is None:
        return {}
    mine = sorted(
        (t for t in data.transactions if any(p.account_id == account_id for p in t.postings)),
        key=lambda x: (x.date, str(x.id)),
    )
    running, register = 0, []
    for t in mine:
        change = sum(p.amount for p in t.postings if p.account_id == account_id)
        running += change
        register.append(
            transaction_json(data, t) | {"change": money(change), "running": money(running)}
        )
    register.reverse()
    sheet = _sheet(data, data.today)
    line = next((x for x in sheet.lines if x.account_id == account_id), None)
    bad = {
        (g.account_id, g.as_of): g for g in gaps(data.accounts, data.transactions, data.assertions)
    }
    statements = []
    for st in data.statements:
        if st["account_id"] != account_id:
            continue
        as_of = date.fromisoformat(st["balance_as_of"]) if st["balance_as_of"] else None
        gap = bad.get((account_id, as_of)) if as_of else None
        statements.append(
            st
            | {
                "import_id": st["id"],
                "assertion_ok": gap is None,
                "difference": money(gap.difference) if gap else None,
            }
        )
    out: Json = {
        "account": account_json(account, line.balance if line else running),
        "register": register,
        "statements": statements,
    }
    if line is not None and line.market is not None:
        out["holdings"] = {
            "cost": money(line.cost),
            "market": money(line.market),
            "unrealized": money(line.unrealized),
        }
    return out


# the books ------------------------------------------------------------------------------


@json_safe
def accounts_tree_report(data: Data) -> Json:
    """Every account in real accounting terms, each totalled over all time up to today."""
    all_time = balances_at(data.transactions, data.today)
    kinds = []
    for kind in AccountKind:
        totals: dict[str, int] = defaultdict(int)
        ids: dict[str, Id] = {}
        for a in data.accounts:
            if a.kind is not kind or (not a.active and all_time.get(a.id, 0) == 0):
                continue
            parts = a.path.split(":")
            ids[a.path] = a.id
            for i in range(1, len(parts) + 1):
                totals[":".join(parts[:i])] += all_time.get(a.id, 0)
        nodes: dict[str, Json] = {}
        root: Json = {}
        for path in sorted(totals):
            found = data.account(ids.get(path))
            node: Json = {
                "path": path,
                "name": found.display_name if found else path.rsplit(":", 1)[-1],
                "account_id": ids.get(path),
                "balance": money(totals[path]),
                "children": [],
            }
            nodes[path] = node
            parent = nodes.get(path.rsplit(":", 1)[0]) if ":" in path else None
            if parent is not None:
                parent["children"].append(node)
            else:
                root = node
        kinds.append(
            {
                "kind": kind.value,
                "label": KIND_LABELS[kind],
                "total": root.get("balance", money(0)),
                "nodes": root.get("children", []),
            }
        )
    return {"as_of": data.today, "kinds": kinds}


@json_safe
def categories_report(data: Data) -> Json:
    start, end = month_bounds(month_key(data.today))
    used: dict[Id, int] = defaultdict(int)
    month: dict[Id, int] = defaultdict(int)
    for t in data.transactions:
        for p in t.postings:
            used[p.account_id] += 1
            if start <= t.date <= end:
                month[p.account_id] += p.amount
    transit = next((a for a in data.accounts if a.path == IN_TRANSIT), None)
    out: Json = {
        "out": [],
        "in": [],
        "own_move": {
            "id": transit.id if transit else None,
            "name": "Own account or investment",
            "description": "Money moved between your own accounts, card bill payments and investments",
        },
    }
    for a in sorted(data.accounts, key=lambda x: x.path):
        if a.role is not AccountRole.CATEGORY:
            continue
        natural = month[a.id] if a.kind is AccountKind.EXPENSE else -month[a.id]
        parent = a.path.rsplit(":", 1)[0]
        out["in" if a.direction is Direction.IN else "out"].append(
            account_json(a)
            | {
                "parent_path": parent if parent.count(":") else None,
                "this_month": money(natural),
                "used": used[a.id],
                "default": a.path in _DEFAULT_PATHS,
            }
        )
    return out


_TOKEN = re.compile(r"\[[A-Z_]+:[0-9a-f]{4}\]")


@json_safe
def privacy_tokens(data: Data, labels: dict[str, str]) -> list[Json]:
    """Every pseudonym token in the ledger, how often it appears, and its label if any."""
    counts: dict[str, int] = {}
    for t in data.transactions:
        for token in _TOKEN.findall(t.narration):
            counts[token] = counts.get(token, 0) + 1
    return [
        {"token": token, "count": n, "label": labels.get(token)}
        for token, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
