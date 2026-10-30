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
from cfo.core.ids import Id
from cfo.core.money import format_inr
from cfo.core.types import (
    Account,
    AccountKind,
    AccountRole,
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
from cfo.metrics.balance_sheet import BalanceSheet, balance_sheet
from cfo.metrics.balances import balances_at
from cfo.metrics.inbox import inbox
from cfo.metrics.income_statement import CategoryLine, check_line, income_statement
from cfo.metrics.leaks import leaks
from cfo.metrics.reconcile import gaps
from cfo.metrics.safe_to_spend import safe_to_spend
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


# what needs the owner ------------------------------------------------------------------


@json_safe
def inbox_report(data: Data) -> list[Json]:
    out = []
    by_id = {t.id: t for t in data.transactions}
    for item in inbox(data.accounts, data.transactions, data.assertions, data.imports):
        who = data.name(item.account_id)
        amount = format_inr(item.amount)
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
            }
        )
    return out


@json_safe
def overview_report(data: Data) -> Json:
    now = _sheet(data, data.today)
    last_month_end = month_bounds(previous_month(month_key(data.today)))[1]
    before = _sheet(data, last_month_end)
    month = month_key(data.today)
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
            "earned": money(stmt.earned),
            "spent": money(stmt.spent),
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
    """Every account in real accounting terms: balance-sheet accounts all time, income and
    expense accounts this month."""
    start, end = month_bounds(month_key(data.today))
    all_time = balances_at(data.transactions, data.today)
    month_tx = [t for t in data.transactions if start <= t.date <= end]
    this_month = balances_at(month_tx)
    kinds = []
    for kind in AccountKind:
        source = this_month if kind in (AccountKind.INCOME, AccountKind.EXPENSE) else all_time
        totals: dict[str, int] = defaultdict(int)
        ids: dict[str, Id] = {}
        for a in data.accounts:
            if a.kind is not kind or (not a.active and source.get(a.id, 0) == 0):
                continue
            parts = a.path.split(":")
            ids[a.path] = a.id
            for i in range(1, len(parts) + 1):
                totals[":".join(parts[:i])] += source.get(a.id, 0)
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
