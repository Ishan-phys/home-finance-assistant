"""SQLAlchemy table definitions. Only the repositories import this module.

Every ledger-owned table carries a `ledger_id`, and every reference between two ledger-owned
rows is a composite foreign key that includes it, so the database itself refuses a row that
points into another ledger (spec 3.10 rule 1). A transaction is a set of postings that sums to
zero; the journal service enforces the sum, the database enforces where postings may point.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from cfo.core.ids import new_id
from cfo.core.types import (
    AccountKind,
    AccountRole,
    AccountType,
    Direction,
    Group,
    Heading,
    MappingSource,
    Origin,
)
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _in(column: str, enum: type) -> str:
    values = ", ".join(f"'{m.value}'" for m in enum)  # type: ignore[attr-defined]
    return f"{column} IN ({values})"


class Base(DeclarativeBase):
    pass


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=new_id)


def ledger_fk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("ledgers.id"), index=True)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# people, ledgers, households ---------------------------------------------------------


class PersonRow(Base):
    __tablename__ = "people"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class LedgerRow(Base):
    __tablename__ = "ledgers"
    id: Mapped[uuid.UUID] = pk()
    person_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("people.id"), unique=True)
    # keys the pseudonym tokens, so tokens do not link people across ledgers
    pseudonym_salt: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = _now()


class LedgerSettingsRow(Base):
    __tablename__ = "ledger_settings"
    __table_args__ = (
        CheckConstraint("min_cash_buffer >= 0", name="ck_ledger_settings_buffer"),
        CheckConstraint(
            "monthly_allowance IS NULL OR monthly_allowance >= 0",
            name="ck_ledger_settings_allowance",
        ),
    )
    ledger_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ledgers.id"), primary_key=True)
    min_cash_buffer: Mapped[int] = mapped_column(BigInteger, server_default="0")
    monthly_allowance: Mapped[int | None] = mapped_column(BigInteger)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HouseholdRow(Base):
    __tablename__ = "households"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class HouseholdMemberRow(Base):
    __tablename__ = "household_members"
    __table_args__ = (
        CheckConstraint("visibility IN ('full', 'balances_only')", name="ck_member_visibility"),
        CheckConstraint("until_date IS NULL OR until_date >= from_date", name="ck_member_dates"),
        # a person is in at most one household at a time
        Index(
            "uq_member_current_household",
            "person_id",
            unique=True,
            postgresql_where=text("until_date IS NULL"),
        ),
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("households.id"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("people.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), server_default="member")
    from_date: Mapped[date] = mapped_column(Date, primary_key=True)
    until_date: Mapped[date | None] = mapped_column(Date)
    visibility: Mapped[str] = mapped_column(String(16), server_default="full")


# ledger-owned -------------------------------------------------------------------------


def _ledger_ref(column: str, table: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["ledger_id", column], [f"{table}.ledger_id", f"{table}.id"], name=name
    )


class AccountRow(Base):
    """Every account in the tree: real accounts, categories and system accounts."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("ledger_id", "id", name="uq_accounts_ledger_id"),
        UniqueConstraint("ledger_id", "path", name="uq_accounts_ledger_path"),
        CheckConstraint(_in("kind", AccountKind), name="ck_accounts_kind"),
        CheckConstraint(_in("role", AccountRole), name="ck_accounts_role"),
        CheckConstraint(f"type IS NULL OR {_in('type', AccountType)}", name="ck_accounts_type"),
        CheckConstraint(f"grp IS NULL OR {_in('grp', Group)}", name="ck_accounts_group"),
        CheckConstraint(
            f"direction IS NULL OR {_in('direction', Direction)}", name="ck_accounts_direction"
        ),
        CheckConstraint(_in("heading", Heading), name="ck_accounts_heading"),
        CheckConstraint(
            "cycle_day IS NULL OR cycle_day BETWEEN 1 AND 31", name="ck_accounts_cycle"
        ),
        CheckConstraint("length(trim(display_name)) > 0", name="ck_accounts_name"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(String(32))
    grp: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(Text, server_default="")
    direction: Mapped[str | None] = mapped_column(String(8))
    heading: Mapped[str] = mapped_column(String(16), server_default="regular")
    institution: Mapped[str | None] = mapped_column(Text)
    binding: Mapped[str | None] = mapped_column(String(32))
    cycle_day: Mapped[int | None] = mapped_column(SmallInteger)
    # fingerprint of the card or account number in this account's statements (spec 4.12.2)
    statement_fingerprint: Mapped[str | None] = mapped_column(String(32))
    opened_on: Mapped[date | None] = mapped_column(Date)
    retired_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _now()


class ImportRow(Base):
    __tablename__ = "imports"
    __table_args__ = (
        UniqueConstraint("ledger_id", "id", name="uq_imports_ledger_id"),
        _ledger_ref("account_id", "accounts", "fk_imports_account"),
        Index("ix_imports_account", "account_id"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    file_name: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    rows_inserted: Mapped[int] = mapped_column(Integer)
    hashes_ignored: Mapped[int] = mapped_column(Integer)
    closing_balance: Mapped[int | None] = mapped_column(BigInteger)
    balance_as_of: Mapped[date | None] = mapped_column(Date)
    amount_due: Mapped[int | None] = mapped_column(BigInteger)
    due_date: Mapped[date | None] = mapped_column(Date)
    redaction_summary: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TransactionRow(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("ledger_id", "id", name="uq_transactions_ledger_id"),
        CheckConstraint("source IN ('import', 'manual', 'system')", name="ck_transactions_source"),
        _ledger_ref("import_id", "imports", "fk_transactions_import"),
        Index("ix_transactions_date", "posted_date"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    posted_date: Mapped[date] = mapped_column(Date)
    narration: Mapped[str] = mapped_column(Text)
    payee: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(8), server_default="import")
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = _now()


class PostingRow(Base):
    __tablename__ = "postings"
    __table_args__ = (
        CheckConstraint(_in("origin", Origin), name="ck_postings_origin"),
        CheckConstraint(
            "dedup_hash IS NULL OR origin = 'observed'", name="ck_postings_hash_observed"
        ),
        ForeignKeyConstraint(
            ["ledger_id", "transaction_id"],
            ["transactions.ledger_id", "transactions.id"],
            name="fk_postings_transaction",
            ondelete="CASCADE",
        ),
        _ledger_ref("account_id", "accounts", "fk_postings_account"),
        _ledger_ref("import_id", "imports", "fk_postings_import"),
        Index(
            "uq_postings_account_hash",
            "account_id",
            "dedup_hash",
            unique=True,
            postgresql_where=text("dedup_hash IS NOT NULL"),
        ),
        Index("ix_postings_transaction", "transaction_id"),
        Index("ix_postings_account", "account_id"),
        Index("ix_postings_import", "import_id"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    amount: Mapped[int] = mapped_column(BigInteger)  # signed paise, Beancount signs
    origin: Mapped[str] = mapped_column(String(16))
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    dedup_hash: Mapped[str | None] = mapped_column(String(64))
    units: Mapped[str | None] = mapped_column(Text)
    unit_label: Mapped[str | None] = mapped_column(Text)


class AssertionRow(Base):
    """A statement's closing balance for an account on a date."""

    __tablename__ = "assertions"
    __table_args__ = (
        _ledger_ref("account_id", "accounts", "fk_assertions_account"),
        _ledger_ref("import_id", "imports", "fk_assertions_import"),
        Index("ix_assertions_account_asof", "account_id", "as_of"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    as_of: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class ValuationRow(Base):
    """Market value of a holding or manual asset on a date. Posts nothing."""

    __tablename__ = "valuations"
    __table_args__ = (
        _ledger_ref("account_id", "accounts", "fk_valuations_account"),
        _ledger_ref("import_id", "imports", "fk_valuations_import"),
        Index("ix_valuations_account_asof", "account_id", "as_of"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    as_of: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(BigInteger)
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class ImportHashRow(Base):
    """Every statement row an import contained, including rows an earlier import had already
    brought. Removing one statement then keeps the rows another statement still holds."""

    __tablename__ = "import_hashes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ledger_id", "import_id"],
            ["imports.ledger_id", "imports.id"],
            name="fk_import_hashes_import",
            ondelete="CASCADE",
        ),
        Index("ix_import_hashes_account_hash", "account_id", "dedup_hash"),
    )
    ledger_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ledgers.id"), primary_key=True)
    import_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)


class DismissedHashRow(Base):
    """A statement row the owner ignored: a re-upload must not bring it back."""

    __tablename__ = "dismissed_hashes"
    __table_args__ = (_ledger_ref("account_id", "accounts", "fk_dismissed_account"),)
    ledger_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ledgers.id"), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), primary_key=True)


class MerchantMappingRow(Base):
    __tablename__ = "merchant_mappings"
    __table_args__ = (
        UniqueConstraint("ledger_id", "lookup_key", name="uq_mappings_ledger_key"),
        CheckConstraint(_in("source", MappingSource), name="ck_mappings_source"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    lookup_key: Mapped[str] = mapped_column(Text)
    clean_merchant: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)  # the account path
    source: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RuleRow(Base):
    """An owner rule: narration text, a match mode and direction, and the account it posts to."""

    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint("mode IN ('contains', 'starts_with')", name="ck_rules_mode"),
        CheckConstraint("way IN ('any', 'debit', 'credit')", name="ck_rules_way"),
        CheckConstraint("length(trim(match_text)) > 0", name="ck_rules_text_nonblank"),
        Index("ix_rules_ledger_position", "ledger_id", "position"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    label: Mapped[str] = mapped_column(Text)
    match_text: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(12))
    way: Mapped[str] = mapped_column(String(6), server_default="any")
    target: Mapped[str] = mapped_column(Text)  # the account path
    position: Mapped[int] = mapped_column(Integer)
    builtin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = _now()


class RedactionTermRow(Base):
    """A word or phrase the owner never wants sent to a model (their own name, family)."""

    __tablename__ = "redaction_terms"
    __table_args__ = (
        UniqueConstraint("ledger_id", "term", name="uq_redaction_terms_ledger_term"),
        CheckConstraint("length(trim(term)) > 0", name="ck_redaction_term_nonblank"),
    )
    id: Mapped[uuid.UUID] = pk()
    ledger_id: Mapped[uuid.UUID] = ledger_fk()
    term: Mapped[str] = mapped_column(Text)


class PseudonymLabelRow(Base):
    """A name the owner gave a pseudonym token, such as "landlord" for [PERSON:ab12]."""

    __tablename__ = "pseudonym_labels"
    __table_args__ = (
        CheckConstraint("length(trim(label)) > 0", name="ck_pseudonym_label_nonblank"),
    )
    ledger_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ledgers.id"), primary_key=True)
    token: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(Text)
