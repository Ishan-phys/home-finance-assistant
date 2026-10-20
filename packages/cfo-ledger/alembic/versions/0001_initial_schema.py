"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-03 20:18:16.867500

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Initial schema (spec 4.7). Everything is stored in the clear until iteration 4."""
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subtype", sa.String(length=32), nullable=False),
        sa.Column("binding", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("institution", sa.Text(), nullable=True),
        sa.Column("account_reference", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.Date(), nullable=True),
        sa.Column("cycle_day", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subtype IN ('checking', 'savings', 'cash', 'credit_card', 'loan', 'fixed_deposit', 'recurring_deposit', 'mutual_fund', 'stock', 'brokerage', 'property', 'gold')",
            name="ck_accounts_subtype",
        ),
        sa.CheckConstraint(
            "cycle_day IS NULL OR cycle_day BETWEEN 1 AND 31", name="ck_accounts_cycle"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "merchant_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lookup_key", sa.Text(), nullable=False),
        sa.Column("clean_merchant", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("category <> 'Transfer'", name="ck_mappings_not_transfer"),
        sa.CheckConstraint(
            "category IN ('Income', 'Housing', 'Utilities', 'Subscriptions', 'Dining', 'Shopping', 'Health', 'Transport', 'Fees', 'Investments', 'Uncategorized', 'Transfer')",
            name="ck_mappings_category",
        ),
        sa.CheckConstraint("source IN ('model', 'owner')", name="ck_mappings_source"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lookup_key"),
    )
    op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("min_cash_buffer", sa.BigInteger(), server_default="0", nullable=False),
        sa.CheckConstraint("id = 1", name="ck_settings_single_row"),
        sa.CheckConstraint("min_cash_buffer >= 0", name="ck_settings_buffer"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "income_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_day", sa.SmallInteger(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'one_off' AND due_date IS NOT NULL AND due_day IS NULL AND start_date IS NULL) OR (kind = 'monthly' AND due_day BETWEEN 1 AND 31 AND start_date IS NOT NULL AND due_date IS NULL)",
            name="ck_income_rules_shape",
        ),
        sa.CheckConstraint("kind IN ('one_off', 'monthly')", name="ck_income_rules_kind"),
        sa.CheckConstraint("amount > 0", name="ck_income_rules_amount"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "obligation_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_day", sa.SmallInteger(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=16), server_default="manual", nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=True),
        sa.Column("source_period_end", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'one_off' AND due_date IS NOT NULL AND due_day IS NULL AND start_date IS NULL) OR (kind = 'monthly' AND due_day BETWEEN 1 AND 31 AND start_date IS NOT NULL AND due_date IS NULL)",
            name="ck_obligation_rules_shape",
        ),
        sa.CheckConstraint("kind IN ('one_off', 'monthly')", name="ck_obligation_rules_kind"),
        sa.CheckConstraint(
            "source IN ('manual', 'card_statement')", name="ck_obligation_rules_source"
        ),
        sa.CheckConstraint("amount > 0", name="ck_obligation_rules_amount"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_obligation_rules_card_statement",
        "obligation_rules",
        ["source_account_id", "source_period_end"],
        unique=True,
        postgresql_where=sa.text("source = 'card_statement'"),
    )
    op.create_table(
        "valuations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_valuations_account_asof", "valuations", ["account_id", "as_of"], unique=False
    )
    op.create_table(
        "imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("hashes_ignored", sa.Integer(), nullable=False),
        sa.Column("amount_due", sa.BigInteger(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("obligation_rule_id", sa.Integer(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["obligation_rule_id"],
            ["obligation_rules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imports_account", "imports", ["account_id"], unique=False)
    op.create_table(
        "income_instances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="expected", nullable=False),
        sa.CheckConstraint(
            "state IN ('expected', 'received', 'skipped', 'cancelled')",
            name="ck_income_instances_state",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["income_rules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "scheduled_date", name="uq_income_instance"),
    )
    op.create_index(
        "ix_income_instances_date", "income_instances", ["scheduled_date"], unique=False
    )
    op.create_table(
        "obligation_instances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="pending", nullable=False),
        sa.CheckConstraint(
            "state IN ('pending', 'paid', 'skipped', 'cancelled')",
            name="ck_obligation_instances_state",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["obligation_rules.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "scheduled_date", name="uq_obligation_instance"),
    )
    op.create_index(
        "ix_obligation_instances_date", "obligation_instances", ["scheduled_date"], unique=False
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("clean_merchant", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("dedup_hash", sa.String(length=64), nullable=False),
        sa.Column("obligation_instance_id", sa.Integer(), nullable=True),
        sa.Column("income_instance_id", sa.Integer(), nullable=True),
        sa.Column("import_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('Income', 'Housing', 'Utilities', 'Subscriptions', 'Dining', 'Shopping', 'Health', 'Transport', 'Fees', 'Investments', 'Uncategorized', 'Transfer')",
            name="ck_transactions_category",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["imports.id"],
        ),
        sa.ForeignKeyConstraint(
            ["income_instance_id"],
            ["income_instances.id"],
        ),
        sa.ForeignKeyConstraint(
            ["obligation_instance_id"],
            ["obligation_instances.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "dedup_hash", name="uq_transactions_account_hash"),
    )
    op.create_index(
        "ix_transactions_account_date", "transactions", ["account_id", "posted_date"], unique=False
    )
    op.create_index("ix_transactions_date", "transactions", ["posted_date"], unique=False)
    op.create_index(
        "uq_transactions_income_instance",
        "transactions",
        ["income_instance_id"],
        unique=True,
        postgresql_where=sa.text("income_instance_id IS NOT NULL"),
    )
    op.create_index(
        "uq_transactions_obligation_instance",
        "transactions",
        ["obligation_instance_id"],
        unique=True,
        postgresql_where=sa.text("obligation_instance_id IS NOT NULL"),
    )
    op.create_table(
        "transfer_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debit_tx_id", sa.Integer(), nullable=False),
        sa.Column("credit_tx_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("debit_tx_id <> credit_tx_id", name="ck_transfer_distinct"),
        sa.ForeignKeyConstraint(
            ["credit_tx_id"],
            ["transactions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["debit_tx_id"],
            ["transactions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credit_tx_id", name="uq_transfer_credit"),
        sa.UniqueConstraint("debit_tx_id", name="uq_transfer_debit"),
    )
    op.create_table(
        "unlinked_pairs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("low_tx_id", sa.Integer(), nullable=False),
        sa.Column("high_tx_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("low_tx_id < high_tx_id", name="ck_unlinked_ordered"),
        sa.ForeignKeyConstraint(
            ["high_tx_id"],
            ["transactions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["low_tx_id"],
            ["transactions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("low_tx_id", "high_tx_id", name="uq_unlinked_pair"),
    )
    op.execute("INSERT INTO settings (id, min_cash_buffer) VALUES (1, 0)")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("unlinked_pairs")
    op.drop_table("transfer_links")
    op.drop_index(
        "uq_transactions_obligation_instance",
        table_name="transactions",
        postgresql_where=sa.text("obligation_instance_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_transactions_income_instance",
        table_name="transactions",
        postgresql_where=sa.text("income_instance_id IS NOT NULL"),
    )
    op.drop_index("ix_transactions_date", table_name="transactions")
    op.drop_index("ix_transactions_account_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_obligation_instances_date", table_name="obligation_instances")
    op.drop_table("obligation_instances")
    op.drop_index("ix_income_instances_date", table_name="income_instances")
    op.drop_table("income_instances")
    op.drop_index("ix_imports_account", table_name="imports")
    op.drop_table("imports")
    op.drop_index("ix_valuations_account_asof", table_name="valuations")
    op.drop_table("valuations")
    op.drop_index(
        "uq_obligation_rules_card_statement",
        table_name="obligation_rules",
        postgresql_where=sa.text("source = 'card_statement'"),
    )
    op.drop_table("obligation_rules")
    op.drop_table("income_rules")
    op.drop_table("settings")
    op.drop_table("merchant_mappings")
    op.drop_table("accounts")
