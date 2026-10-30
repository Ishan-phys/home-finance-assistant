"""Setup: every ledger's system accounts and default categories, the owner's real accounts,
and categories the owner defines (spec §3, §5.0). Statements can only be added once the ledger
has a real account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from cfo.core.chart import (
    DEFAULT_CATEGORIES,
    OPENING,
    SYSTEM_ACCOUNTS,
    SYSTEM_NAMES,
    real_account_path,
    slug,
)
from cfo.core.errors import CategoryInUse, ConflictError, InvalidInput, NotFoundError, SetupRequired
from cfo.core.ids import Id, new_id
from cfo.core.types import (
    Account,
    AccountKind,
    AccountRole,
    AccountType,
    Direction,
    Heading,
    Origin,
    Posting,
    Scope,
    Transaction,
)
from cfo.ledger.repositories.accounts import AccountRepository, SettingsRepository
from cfo.ledger.repositories.rules import RuleRepository
from cfo.ledger.repositories.transactions import JournalRepository, MappingRepository
from sqlalchemy.orm import Session

MAX_DESCRIPTION = 200
MAX_NAME = 60


def create_ledger_defaults(s: Session, scope: Scope | None = None) -> None:
    """The five system accounts and the default categories. Safe to run again."""
    repo = AccountRepository(s, scope)
    for path, kind in SYSTEM_ACCOUNTS:
        if repo.by_path(path) is None:
            repo.add(Account(new_id(), path, kind, AccountRole.SYSTEM, SYSTEM_NAMES[path]))
    for c in DEFAULT_CATEGORIES:
        if repo.by_path(c.path) is None:
            kind = AccountKind.INCOME if c.direction is Direction.IN else AccountKind.EXPENSE
            repo.add(
                Account(
                    new_id(),
                    c.path,
                    kind,
                    AccountRole.CATEGORY,
                    c.name,
                    description=c.description,
                    direction=c.direction,
                    heading=c.heading,
                )
            )


def _text(value: str, what: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise InvalidInput(f"{what} cannot be blank")
    if len(cleaned) > limit:
        raise InvalidInput(f"{what} must be at most {limit} characters")
    return cleaned


# real accounts ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountInput:
    type: AccountType
    institution: str
    name: str
    cycle_day: int | None = None
    opening_value: int | None = None  # manual accounts: what it is worth on opening_date
    opening_date: date | None = None


def _free_path(repo: AccountRepository, path: str) -> str:
    candidate, n = path, 1
    while repo.by_path(candidate) is not None:
        n += 1
        candidate = f"{path}-{n}"
    return candidate


def post_opening(s: Session, account: Account, on: date, amount: int) -> None:
    """Opening value of an account, against Equity:Opening."""
    if amount == 0:
        return
    opening = AccountRepository(s).by_path(OPENING)
    if opening is None:
        raise NotFoundError("the ledger has no opening-balance account")
    JournalRepository(s).add(
        Transaction(
            new_id(),
            on,
            "Opening balance",
            "Opening balance",
            (
                Posting(account.id, amount, Origin.SYSTEM),
                Posting(opening.id, -amount, Origin.SYSTEM),
            ),
            source="system",
        )
    )


def add_account(s: Session, inp: AccountInput, today: date, binding: str | None = None) -> Account:
    name = _text(inp.name, "the account name", MAX_NAME)
    institution = _text(inp.institution, "the institution", MAX_NAME)
    create_ledger_defaults(s)  # a ledger from before the double-entry upgrade has none yet
    if inp.cycle_day is not None and not 1 <= inp.cycle_day <= 31:
        raise InvalidInput("the statement day must be between 1 and 31")
    if inp.type.manual and (inp.opening_value is None or inp.opening_date is None):
        raise InvalidInput(f"a {inp.type.label.lower()} needs its current value and a date")
    repo = AccountRepository(s)
    account = repo.add(
        Account(
            new_id(),
            _free_path(repo, real_account_path(inp.type, institution, name)),
            inp.type.kind,
            AccountRole.REAL,
            name,
            type=inp.type,
            group=inp.type.group,
            institution=institution,
            binding=None if inp.type.manual else binding,
            cycle_day=inp.cycle_day,
            opened_on=today,
        )
    )
    if account.binding is None and inp.opening_value is not None and inp.opening_date is not None:
        post_opening(s, account, inp.opening_date, inp.opening_value)
    return account


def _real(s: Session, account_id: Id) -> Account:
    account = AccountRepository(s).get(account_id)
    if account is None or account.role is not AccountRole.REAL:
        raise NotFoundError(f"unknown account {account_id}")
    return account


def edit_account(
    s: Session,
    account_id: Id,
    *,
    name: str | None = None,
    institution: str | None = None,
    cycle_day: int | None = None,
) -> Account:
    _real(s, account_id)
    fields: dict[str, object] = {}
    if name is not None:
        fields["display_name"] = _text(name, "the account name", MAX_NAME)
    if institution is not None:
        fields["institution"] = _text(institution, "the institution", MAX_NAME)
    if cycle_day is not None:
        if not 1 <= cycle_day <= 31:
            raise InvalidInput("the statement day must be between 1 and 31")
        fields["cycle_day"] = cycle_day
    return AccountRepository(s).update(account_id, **fields)


def delete_account(s: Session, account_id: Id) -> None:
    """Delete an account with everything on it. Movements it shared with another account stay
    on that account, waiting on money in transit."""
    from cfo.ledger.journal import remove_account_postings  # noqa: PLC0415  (journal imports setup)

    _real(s, account_id)
    remove_account_postings(s, account_id)
    AccountRepository(s).delete(account_id)


# categories ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CategoryInput:
    name: str
    direction: Direction
    description: str
    parent_id: Id | None = None


def _category(s: Session, account_id: Id) -> Account:
    account = AccountRepository(s).get(account_id)
    if account is None:
        raise NotFoundError(f"unknown category {account_id}")
    if account.role is not AccountRole.CATEGORY:
        raise InvalidInput("only categories can be changed here")
    return account


def add_category(s: Session, inp: CategoryInput) -> Account:
    name = _text(inp.name, "the category name", MAX_NAME)
    description = _text(inp.description, "the description", MAX_DESCRIPTION)
    root = "Income" if inp.direction is Direction.IN else "Expenses"
    heading = Heading.REGULAR
    if inp.parent_id is not None:
        parent = _category(s, inp.parent_id)
        if parent.direction is not inp.direction:
            raise InvalidInput("a category sits under a category of the same direction")
        root, heading = parent.path, parent.heading
    path = f"{root}:{slug(name)}"
    repo = AccountRepository(s)
    clash = repo.by_path(path) or next(
        (
            a
            for a in repo.list_all(AccountRole.CATEGORY, include_retired=True)
            if a.path.lower() == path.lower()
        ),
        None,
    )
    if clash is not None:
        raise ConflictError(f"a category called {name} already exists")
    kind = AccountKind.INCOME if inp.direction is Direction.IN else AccountKind.EXPENSE
    return repo.add(
        Account(
            new_id(),
            path,
            kind,
            AccountRole.CATEGORY,
            name,
            description=description,
            direction=inp.direction,
            heading=heading,
        )
    )


def edit_category(
    s: Session, account_id: Id, *, name: str | None = None, description: str | None = None
) -> Account:
    """Rename or redescribe a category. The path stays, so history and mappings are kept."""
    _category(s, account_id)
    fields: dict[str, object] = {}
    if name is not None:
        fields["display_name"] = _text(name, "the category name", MAX_NAME)
    if description is not None:
        fields["description"] = _text(description, "the description", MAX_DESCRIPTION)
    return AccountRepository(s).update(account_id, **fields)


def _active_children(s: Session, account: Account) -> list[Account]:
    prefix = account.path + ":"
    return [
        a for a in AccountRepository(s).list_all(AccountRole.CATEGORY) if a.path.startswith(prefix)
    ]


def retire_category(s: Session, account_id: Id, today: date) -> None:
    account = _category(s, account_id)
    if _active_children(s, account):
        raise ConflictError("retire or merge the categories under it first")
    # What was remembered for it would keep these rows uncategorized for good, because a known
    # description is never sent to the categorizer again.
    MappingRepository(s).forget(account.path)
    RuleRepository(s).delete_targeting(account.path)
    AccountRepository(s).retire(account_id, today)


def merge_category(s: Session, from_id: Id, into_id: Id, today: date) -> int:
    """Move every posting and remembered mapping of one category into another, then retire it.
    Returns the number of postings moved."""
    source, target = _category(s, from_id), _category(s, into_id)
    if source.id == target.id:
        raise InvalidInput("pick a different category to merge into")
    if source.direction is not target.direction:
        raise InvalidInput("money-in and money-out categories cannot be merged")
    if not target.active:
        raise InvalidInput("cannot merge into a retired category")
    if _active_children(s, source):
        raise ConflictError("merge or retire the categories under it first")
    moved = JournalRepository(s).move_postings(source.id, target.id)
    MappingRepository(s).repoint(source.path, target.path)
    RuleRepository(s).repoint(source.path, target.path)
    AccountRepository(s).retire(source.id, today)
    return moved


def delete_category(s: Session, account_id: Id) -> None:
    account = _category(s, account_id)
    if AccountRepository(s).usage(account_id).postings:
        raise CategoryInUse(f"{account.display_name} has transactions")
    if _active_children(s, account):
        raise ConflictError("delete the categories under it first")
    MappingRepository(s).forget(account.path)
    AccountRepository(s).delete(account_id)


# setup state --------------------------------------------------------------------------


def is_set_up(s: Session) -> bool:
    """A ledger is set up once it has a real account to put statements on (C8)."""
    return bool(AccountRepository(s).list_all(AccountRole.REAL))


def complete_setup(s: Session, now: datetime) -> None:
    if not is_set_up(s):
        raise SetupRequired("add an account before finishing setup")
    SettingsRepository(s).update(setup_completed_at=now)
