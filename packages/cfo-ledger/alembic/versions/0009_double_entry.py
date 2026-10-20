"""double-entry ledger

Replaces single-row transactions with balanced transactions of postings, adds the account tree
(real accounts, categories and system accounts), balance assertions, valuations without
postings, dismissed statement rows, and setup state. Events, spending plans, obligation and
income schedules and transfer links are dropped; they come back later in a postings-shaped form.
No data is converted.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ledger data is not converted (design C1): statements are re-uploaded into the new model.
    op.execute(
        "DROP TABLE IF EXISTS transfer_links, unlinked_pairs, transactions, valuations, "
        "obligation_instances, income_instances, imports, obligation_rules, income_rules, "
        "events, spending_plans, merchant_mappings, accounts CASCADE"
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=True),
        sa.Column("grp", sa.String(length=16), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=True),
        sa.Column("heading", sa.String(length=16), server_default="regular", nullable=False),
        sa.Column("institution", sa.Text(), nullable=True),
        sa.Column("binding", sa.String(length=32), nullable=True),
        sa.Column("cycle_day", sa.SmallInteger(), nullable=True),
        sa.Column("statement_fingerprint", sa.String(length=32), nullable=True),
        sa.Column("opened_on", sa.Date(), nullable=True),
        sa.Column("retired_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN ('out', 'in')", name="ck_accounts_direction"
        ),
        sa.CheckConstraint(
            "grp IS NULL OR grp IN ('liquid', 'fixed', 'investments', 'other', 'owed')",
            name="ck_accounts_group",
        ),
        sa.CheckConstraint(
            "heading IN ('regular', 'people', 'rewards')", name="ck_accounts_heading"
        ),
        sa.CheckConstraint(
            "kind IN ('asset', 'liability', 'income', 'expense', 'equity')", name="ck_accounts_kind"
        ),
        sa.CheckConstraint("role IN ('real', 'category', 'system')", name="ck_accounts_role"),
        sa.CheckConstraint(
            "type IS NULL OR type IN ('savings', 'current', 'cash', 'credit_card', 'loan', 'fixed_deposit', 'recurring_deposit', 'mutual_fund', 'stock', 'property', 'gold')",
            name="ck_accounts_type",
        ),
        sa.CheckConstraint(
            "cycle_day IS NULL OR cycle_day BETWEEN 1 AND 31", name="ck_accounts_cycle"
        ),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="ck_accounts_name"),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_id", "id", name="uq_accounts_ledger_id"),
        sa.UniqueConstraint("ledger_id", "path", name="uq_accounts_ledger_path"),
    )
    op.create_index(op.f("ix_accounts_ledger_id"), "accounts", ["ledger_id"], unique=False)
    op.create_table(
        "merchant_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("lookup_key", sa.Text(), nullable=False),
        sa.Column("clean_merchant", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source IN ('model', 'owner')", name="ck_mappings_source"),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_id", "lookup_key", name="uq_mappings_ledger_key"),
    )
    op.create_index(
        op.f("ix_merchant_mappings_ledger_id"), "merchant_mappings", ["ledger_id"], unique=False
    )
    op.create_table(
        "dismissed_hashes",
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("dedup_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["ledger_id", "account_id"],
            ["accounts.ledger_id", "accounts.id"],
            name="fk_dismissed_account",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("ledger_id", "account_id", "dedup_hash"),
    )
    op.create_table(
        "imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("hashes_ignored", sa.Integer(), nullable=False),
        sa.Column("closing_balance", sa.BigInteger(), nullable=True),
        sa.Column("balance_as_of", sa.Date(), nullable=True),
        sa.Column("amount_due", sa.BigInteger(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("redaction_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id", "account_id"],
            ["accounts.ledger_id", "accounts.id"],
            name="fk_imports_account",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_id", "id", name="uq_imports_ledger_id"),
    )
    op.create_index("ix_imports_account", "imports", ["account_id"], unique=False)
    op.create_index(op.f("ix_imports_ledger_id"), "imports", ["ledger_id"], unique=False)
    op.create_table(
        "assertions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ledger_id", "account_id"],
            ["accounts.ledger_id", "accounts.id"],
            name="fk_assertions_account",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id", "import_id"],
            ["imports.ledger_id", "imports.id"],
            name="fk_assertions_import",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assertions_account_asof", "assertions", ["account_id", "as_of"], unique=False
    )
    op.create_index(op.f("ix_assertions_ledger_id"), "assertions", ["ledger_id"], unique=False)
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=False),
        sa.Column("payee", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=8), server_default="import", nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('import', 'manual', 'system')", name="ck_transactions_source"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id", "import_id"],
            ["imports.ledger_id", "imports.id"],
            name="fk_transactions_import",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_id", "id", name="uq_transactions_ledger_id"),
    )
    op.create_index("ix_transactions_date", "transactions", ["posted_date"], unique=False)
    op.create_index(op.f("ix_transactions_ledger_id"), "transactions", ["ledger_id"], unique=False)
    op.create_table(
        "valuations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ledger_id", "account_id"],
            ["accounts.ledger_id", "accounts.id"],
            name="fk_valuations_account",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id", "import_id"],
            ["imports.ledger_id", "imports.id"],
            name="fk_valuations_import",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_valuations_account_asof", "valuations", ["account_id", "as_of"], unique=False
    )
    op.create_index(op.f("ix_valuations_ledger_id"), "valuations", ["ledger_id"], unique=False)
    op.create_table(
        "postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.Column("dedup_hash", sa.String(length=64), nullable=True),
        sa.Column("units", sa.Text(), nullable=True),
        sa.Column("unit_label", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "dedup_hash IS NULL OR origin = 'observed'", name="ck_postings_hash_observed"
        ),
        sa.CheckConstraint(
            "origin IN ('observed', 'inferred', 'owner', 'system')", name="ck_postings_origin"
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id", "account_id"],
            ["accounts.ledger_id", "accounts.id"],
            name="fk_postings_account",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id", "import_id"],
            ["imports.ledger_id", "imports.id"],
            name="fk_postings_import",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id", "transaction_id"],
            ["transactions.ledger_id", "transactions.id"],
            name="fk_postings_transaction",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledgers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_postings_account", "postings", ["account_id"], unique=False)
    op.create_index("ix_postings_import", "postings", ["import_id"], unique=False)
    op.create_index(op.f("ix_postings_ledger_id"), "postings", ["ledger_id"], unique=False)
    op.create_index("ix_postings_transaction", "postings", ["transaction_id"], unique=False)
    op.create_index(
        "uq_postings_account_hash",
        "postings",
        ["account_id", "dedup_hash"],
        unique=True,
        postgresql_where=sa.text("dedup_hash IS NOT NULL"),
    )
    op.add_column("ledger_settings", sa.Column("monthly_allowance", sa.BigInteger(), nullable=True))
    op.add_column(
        "ledger_settings",
        sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    raise NotImplementedError("0009 cannot be reversed: the old ledger tables are gone")
