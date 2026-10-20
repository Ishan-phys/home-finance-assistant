"""Small builders for the bookkeeping records, so metric tests read like the ledger they model."""

from __future__ import annotations

from datetime import date
from itertools import count
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from cfo.core.chart import SYSTEM_ACCOUNTS, SYSTEM_NAMES
from cfo.core.types import (
    Account,
    AccountKind,
    AccountRole,
    AccountType,
    Assertion,
    Direction,
    Heading,
    ImportRecord,
    Origin,
    Posting,
    Transaction,
    Valuation,
)

_ids = count(1)

OBS, INF, OWN, SYS = Origin.OBSERVED, Origin.INFERRED, Origin.OWNER, Origin.SYSTEM


def uid(n: int | UUID) -> UUID:
    """A deterministic UUID for a small integer, so tests can say account 1 and rule 2."""
    return n if isinstance(n, UUID) else UUID(int=n)


def fresh() -> UUID:
    return UUID(int=(1 << 64) + next(_ids))


def d(text: str) -> date:
    return date.fromisoformat(text)


def real(
    type: AccountType,
    name: str | None = None,
    institution: str = "HDFC",
    id: int | UUID | None = None,
    **kw: object,
) -> Account:
    label = name or type.label
    return Account(
        id=uid(id) if id is not None else fresh(),
        path=f"{type.path_root}:{institution}:{label.replace(' ', '-')}",
        kind=type.kind,
        role=AccountRole.REAL,
        display_name=label,
        type=type,
        group=type.group,
        institution=institution,
        **kw,  # type: ignore[arg-type]
    )


def category(
    path: str, direction: Direction = Direction.OUT, heading: Heading = Heading.REGULAR
) -> Account:
    return Account(
        id=uuid5(NAMESPACE_URL, path),
        path=path,
        kind=AccountKind.INCOME if direction is Direction.IN else AccountKind.EXPENSE,
        role=AccountRole.CATEGORY,
        display_name=path.rsplit(":", 1)[-1],
        description=f"{path} test category",
        direction=direction,
        heading=heading,
    )


def system(path: str) -> Account:
    """The same account object for the same path, so tests can call it freely."""
    return Account(
        id=uuid5(NAMESPACE_URL, path),
        path=path,
        kind=dict(SYSTEM_ACCOUNTS)[path],
        role=AccountRole.SYSTEM,
        display_name=SYSTEM_NAMES[path],
    )


def txn(
    day: str,
    *legs: tuple[Account, int, Origin],
    narration: str = "M",
    payee: str | None = None,
    import_id: UUID | None = None,
    source: Literal["import", "manual", "system"] = "import",
) -> Transaction:
    return Transaction(
        id=fresh(),
        date=d(day),
        narration=narration,
        payee=payee or narration,
        postings=tuple(
            Posting(account.id, amount, origin, id=fresh(), import_id=import_id)
            for account, amount, origin in legs
        ),
        source=source,
        import_id=import_id,
    )


def assertion(
    account: Account, as_of: str, amount: int, import_id: UUID | None = None
) -> Assertion:
    return Assertion(fresh(), account.id, d(as_of), amount, import_id)


def valuation(account: Account, as_of: str, amount: int) -> Valuation:
    return Valuation(fresh(), account.id, d(as_of), amount)


def imp(account: Account, period_end: str | None, **kw: object) -> ImportRecord:
    return ImportRecord(
        id=fresh(),
        account_id=account.id,
        period_end=d(period_end) if period_end else None,
        **kw,  # type: ignore[arg-type]
    )
