"""Accounts, statements (imports), balance assertions, valuations, and ledger settings."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from cfo.core.ids import Id
from cfo.core.types import (
    Account,
    AccountKind,
    AccountRole,
    AccountType,
    Assertion,
    Direction,
    Group,
    Heading,
    ImportRecord,
    Valuation,
)
from cfo.ledger.repositories.models import (
    AccountRow,
    AssertionRow,
    ImportHashRow,
    ImportRow,
    LedgerRow,
    LedgerSettingsRow,
    PostingRow,
    PseudonymLabelRow,
    RedactionTermRow,
    ValuationRow,
)
from cfo.ledger.repositories.scope import ScopedRepository
from sqlalchemy import delete, func, select, update


def _account(r: AccountRow) -> Account:
    return Account(
        id=r.id,
        path=r.path,
        kind=AccountKind(r.kind),
        role=AccountRole(r.role),
        display_name=r.display_name,
        type=AccountType(r.type) if r.type else None,
        group=Group(r.grp) if r.grp else None,
        description=r.description,
        keywords=r.keywords or "",
        direction=Direction(r.direction) if r.direction else None,
        heading=Heading(r.heading),
        institution=r.institution,
        binding=r.binding,
        cycle_day=r.cycle_day,
        statement_fingerprint=r.statement_fingerprint,
        opened_on=r.opened_on,
        retired_on=r.retired_on,
    )


@dataclass(frozen=True, slots=True)
class AccountUsage:
    postings: int
    imports: int


_FIELDS = {
    "display_name": "display_name",
    "institution": "institution",
    "cycle_day": "cycle_day",
    "description": "description",
    "keywords": "keywords",
    "statement_fingerprint": "statement_fingerprint",
    "binding": "binding",
    "retired_on": "retired_on",
}


class AccountRepository(ScopedRepository):
    def add(self, account: Account) -> Account:
        row = AccountRow(
            id=account.id,
            ledger_id=self.ledger_id,
            path=account.path,
            kind=account.kind.value,
            role=account.role.value,
            display_name=account.display_name,
            type=account.type.value if account.type else None,
            grp=account.group.value if account.group else None,
            description=account.description,
            keywords=account.keywords,
            direction=account.direction.value if account.direction else None,
            heading=account.heading.value,
            institution=account.institution,
            binding=account.binding,
            cycle_day=account.cycle_day,
            statement_fingerprint=account.statement_fingerprint,
            opened_on=account.opened_on,
            retired_on=account.retired_on,
        )
        self.s.add(row)
        self.s.flush()
        return _account(row)

    def _scoped(self) -> Any:
        return select(AccountRow).where(self.in_scope(AccountRow.ledger_id))

    def get(self, account_id: Id) -> Account | None:
        row = self.s.scalars(self._scoped().where(AccountRow.id == account_id)).first()
        return _account(row) if row else None

    def by_path(self, path: str) -> Account | None:
        """The account at `path` in the write ledger."""
        row = self.s.scalars(
            select(AccountRow).where(
                AccountRow.ledger_id == self.ledger_id, AccountRow.path == path
            )
        ).first()
        return _account(row) if row else None

    def list_all(
        self, role: AccountRole | None = None, include_retired: bool = False
    ) -> list[Account]:
        q = self._scoped()
        if role is not None:
            q = q.where(AccountRow.role == role.value)
        if not include_retired:
            q = q.where(AccountRow.retired_on.is_(None))
        return [_account(r) for r in self.s.scalars(q.order_by(AccountRow.path, AccountRow.id))]

    def private_accounts(self) -> list[tuple[Account, str | None, str | None]]:
        """Real accounts with the private strings masking aliases (spec 9.1): the account and
        its institution name."""
        return [(a, a.institution, None) for a in self.list_all(AccountRole.REAL)]

    def update(self, account_id: Id, **fields: Any) -> Account:
        values = {_FIELDS[k]: v for k, v in fields.items()}
        self.s.execute(
            update(AccountRow)
            .where(AccountRow.id == account_id, AccountRow.ledger_id == self.ledger_id)
            .values(**values)
        )
        self.s.flush()
        found = self.get(account_id)
        if found is None:
            raise KeyError(account_id)
        return found

    def set_fingerprint(self, account_id: Id, fingerprint: str) -> None:
        self.update(account_id, statement_fingerprint=fingerprint)

    def retire(self, account_id: Id, on: date) -> None:
        self.update(account_id, retired_on=on)

    def usage(self, account_id: Id) -> AccountUsage:
        postings = self.s.scalar(
            select(func.count())
            .select_from(PostingRow)
            .where(PostingRow.account_id == account_id, self.in_scope(PostingRow.ledger_id))
        )
        imports = self.s.scalar(
            select(func.count())
            .select_from(ImportRow)
            .where(ImportRow.account_id == account_id, self.in_scope(ImportRow.ledger_id))
        )
        return AccountUsage(int(postings or 0), int(imports or 0))

    def delete(self, account_id: Id) -> None:
        self.s.execute(
            delete(AccountRow).where(
                AccountRow.id == account_id, AccountRow.ledger_id == self.ledger_id
            )
        )
        self.s.flush()


class ImportRepository(ScopedRepository):
    def add(
        self,
        account_id: Id,
        file_name: str,
        file_sha256: str,
        *,
        period_start: date | None,
        period_end: date | None,
        rows_inserted: int,
        hashes_ignored: int,
        closing_balance: int | None = None,
        balance_as_of: date | None = None,
        amount_due: int | None = None,
        due_date: date | None = None,
        redaction_summary: dict[str, int] | None = None,
    ) -> ImportRecord:
        row = ImportRow(
            ledger_id=self.ledger_id,
            account_id=account_id,
            file_name=file_name,
            file_sha256=file_sha256,
            period_start=period_start,
            period_end=period_end,
            rows_inserted=rows_inserted,
            hashes_ignored=hashes_ignored,
            closing_balance=closing_balance,
            balance_as_of=balance_as_of,
            amount_due=amount_due,
            due_date=due_date,
            redaction_summary=redaction_summary,
        )
        self.s.add(row)
        self.s.flush()
        return self._domain(row)

    def get(self, import_id: Id) -> ImportRecord | None:
        row = self.s.scalars(
            select(ImportRow).where(ImportRow.id == import_id, self.in_scope(ImportRow.ledger_id))
        ).first()
        return self._domain(row) if row else None

    def list_all(self, account_id: Id | None = None) -> list[ImportRecord]:
        q = select(ImportRow).where(self.in_scope(ImportRow.ledger_id))
        if account_id is not None:
            q = q.where(ImportRow.account_id == account_id)
        return [self._domain(r) for r in self.s.scalars(q.order_by(ImportRow.id))]

    def history(self) -> list[dict[str, Any]]:
        """Import history, newest first, with dates as ISO strings."""

        def iso(d: date | None) -> str | None:
            return d.isoformat() if d else None

        rows = self.s.scalars(
            select(ImportRow)
            .where(self.in_scope(ImportRow.ledger_id))
            .order_by(ImportRow.id.desc())
        )
        return [
            {
                "id": r.id,
                "account_id": r.account_id,
                "file_name": r.file_name,
                "period_start": iso(r.period_start),
                "period_end": iso(r.period_end),
                "rows_inserted": r.rows_inserted,
                "hashes_ignored": r.hashes_ignored,
                "imported_at": r.imported_at.isoformat(),
                "closing_balance_paise": r.closing_balance,
                "balance_as_of": iso(r.balance_as_of),
                "amount_due_paise": r.amount_due,
                "due_date": iso(r.due_date),
                "redaction_summary": r.redaction_summary or {},
            }
            for r in rows
        ]

    def set_counts(self, import_id: Id, rows_inserted: int, hashes_ignored: int) -> None:
        self.s.execute(
            update(ImportRow)
            .where(ImportRow.id == import_id, ImportRow.ledger_id == self.ledger_id)
            .values(rows_inserted=rows_inserted, hashes_ignored=hashes_ignored)
        )

    def delete(self, import_id: Id) -> None:
        self.s.execute(
            delete(ImportRow).where(
                ImportRow.id == import_id, ImportRow.ledger_id == self.ledger_id
            )
        )
        self.s.flush()

    @staticmethod
    def _domain(r: ImportRow) -> ImportRecord:
        return ImportRecord(
            id=r.id,
            account_id=r.account_id,
            period_end=r.period_end,
            amount_due=r.amount_due,
            due_date=r.due_date,
            closing_balance=r.closing_balance,
            balance_as_of=r.balance_as_of,
        )


class ImportHashRepository(ScopedRepository):
    def add(self, import_id: Id, account_id: Id, hashes: Sequence[str]) -> None:
        for h in dict.fromkeys(hashes):
            self.s.add(
                ImportHashRow(
                    ledger_id=self.ledger_id,
                    import_id=import_id,
                    dedup_hash=h,
                    account_id=account_id,
                )
            )
        self.s.flush()

    def held_elsewhere(self, account_id: Id, hashes: Sequence[str], import_id: Id) -> dict[str, Id]:
        """Of these rows, which another import of the account also contains, and which import."""
        if not hashes:
            return {}
        rows = self.s.execute(
            select(ImportHashRow.dedup_hash, ImportHashRow.import_id)
            .where(
                ImportHashRow.account_id == account_id,
                ImportHashRow.import_id != import_id,
                ImportHashRow.dedup_hash.in_(list(hashes)),
                self.in_scope(ImportHashRow.ledger_id),
            )
            .order_by(ImportHashRow.import_id)
        )
        return {h: i for h, i in rows}

    def same_file(self, account_id: Id, sha256: str) -> bool:
        return (
            self.s.scalars(
                select(ImportRow.id)
                .where(
                    ImportRow.account_id == account_id,
                    ImportRow.file_sha256 == sha256,
                    self.in_scope(ImportRow.ledger_id),
                )
                .limit(1)
            ).first()
            is not None
        )


class _Snapshots(ScopedRepository):
    """Shared shape of assertions and valuations: an amount for an account on a date."""

    model: Any
    record: Any

    def add(self, account_id: Id, as_of: date, amount: int, import_id: Id | None) -> Any:
        row = self.model(
            ledger_id=self.ledger_id,
            account_id=account_id,
            as_of=as_of,
            amount=amount,
            import_id=import_id,
        )
        self.s.add(row)
        self.s.flush()
        return self.record(row.id, row.account_id, row.as_of, row.amount, row.import_id)

    def list_all(self, account_ids: Sequence[Id] | None = None) -> list[Any]:
        q = select(self.model).where(self.in_scope(self.model.ledger_id))
        if account_ids is not None:
            q = q.where(self.model.account_id.in_(list(account_ids)))
        rows = self.s.scalars(q.order_by(self.model.as_of, self.model.id))
        return [self.record(r.id, r.account_id, r.as_of, r.amount, r.import_id) for r in rows]

    def exists(self, account_id: Id, as_of: date, amount: int) -> bool:
        q = select(self.model.id).where(
            self.in_scope(self.model.ledger_id),
            self.model.account_id == account_id,
            self.model.as_of == as_of,
            self.model.amount == amount,
        )
        return self.s.scalars(q.limit(1)).first() is not None

    def delete_for_import(self, import_id: Id) -> int:
        result = self.s.execute(
            delete(self.model).where(
                self.model.import_id == import_id, self.model.ledger_id == self.ledger_id
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def delete_for_account(self, account_id: Id) -> None:
        self.s.execute(
            delete(self.model).where(
                self.model.account_id == account_id, self.model.ledger_id == self.ledger_id
            )
        )


class AssertionRepository(_Snapshots):
    model = AssertionRow
    record = Assertion

    def add(self, account_id: Id, as_of: date, amount: int, import_id: Id | None) -> Assertion:
        return super().add(account_id, as_of, amount, import_id)  # type: ignore[no-any-return]

    def list_all(self, account_ids: Sequence[Id] | None = None) -> list[Assertion]:
        return super().list_all(account_ids)


class ValuationRepository(_Snapshots):
    model = ValuationRow
    record = Valuation

    def add(self, account_id: Id, as_of: date, amount: int, import_id: Id | None) -> Valuation:
        return super().add(account_id, as_of, amount, import_id)  # type: ignore[no-any-return]

    def list_all(self, account_ids: Sequence[Id] | None = None) -> list[Valuation]:
        return super().list_all(account_ids)


@dataclass(frozen=True, slots=True)
class LedgerSettings:
    min_cash_buffer: int  # the base amount kept aside
    monthly_allowance: int | None
    setup_completed_at: datetime | None


class SettingsRepository(ScopedRepository):
    def get(self) -> LedgerSettings:
        """Across several ledgers (a household view) amounts are summed; setup is complete only
        when every ledger has completed it."""
        rows = list(
            self.s.scalars(
                select(LedgerSettingsRow).where(self.in_scope(LedgerSettingsRow.ledger_id))
            )
        )
        allowances = [r.monthly_allowance for r in rows if r.monthly_allowance is not None]
        done = [r.setup_completed_at for r in rows]
        return LedgerSettings(
            min_cash_buffer=sum(r.min_cash_buffer for r in rows),
            monthly_allowance=sum(allowances) if allowances else None,
            setup_completed_at=None if not done or None in done else max(d for d in done if d),
        )

    def update(self, **fields: Any) -> LedgerSettings:
        allowed = {"min_cash_buffer", "monthly_allowance", "setup_completed_at"}
        unknown = set(fields) - allowed
        if unknown:
            raise KeyError(", ".join(sorted(unknown)))
        row = self.s.get(LedgerSettingsRow, self.ledger_id)
        if row is None:
            row = LedgerSettingsRow(ledger_id=self.ledger_id, min_cash_buffer=0)
            self.s.add(row)
        for k, v in fields.items():
            setattr(row, k, v)
        self.s.flush()
        return self.get()

    def salt(self) -> bytes:
        """The ledger's pseudonym salt. It keys the tokens that stand in for names and numbers,
        so it never changes once data has been imported."""
        salt = self.s.scalars(
            select(LedgerRow.pseudonym_salt).where(LedgerRow.id == self.ledger_id)
        ).one()
        return bytes(salt)


class RedactionTermRepository(ScopedRepository):
    def list_all(self) -> list[str]:
        return list(
            self.s.scalars(
                select(RedactionTermRow.term)
                .where(self.in_scope(RedactionTermRow.ledger_id))
                .order_by(RedactionTermRow.id)
            )
        )

    def replace(self, terms: Sequence[str]) -> list[str]:
        """Set the full list: trimmed, blank and duplicate (case-insensitive) entries dropped."""
        seen: set[str] = set()
        keep: list[str] = []
        for t in terms:
            t = t.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                keep.append(t)
        self.s.execute(delete(RedactionTermRow).where(RedactionTermRow.ledger_id == self.ledger_id))
        self.s.flush()
        for t in keep:
            self.s.add(RedactionTermRow(ledger_id=self.ledger_id, term=t))
        self.s.flush()
        return keep


class PseudonymLabelRepository(ScopedRepository):
    def all(self) -> dict[str, str]:
        return {
            r.token: r.label
            for r in self.s.scalars(
                select(PseudonymLabelRow).where(self.in_scope(PseudonymLabelRow.ledger_id))
            )
        }

    def set(self, token: str, label: str) -> None:
        """Set or clear (blank label) the name shown for a token."""
        label = label.strip()
        row = self.s.get(PseudonymLabelRow, (self.ledger_id, token))
        if not label:
            if row is not None:
                self.s.delete(row)
        elif row is None:
            self.s.add(PseudonymLabelRow(ledger_id=self.ledger_id, token=token, label=label))
        else:
            row.label = label
        self.s.flush()
