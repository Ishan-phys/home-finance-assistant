"""people, ledgers, households, and UUID identifiers (spec 3.10)

Every ledger-owned table gains a `ledger_id`, every reference between ledger-owned rows becomes a
composite foreign key that includes it, and integer identifiers become UUIDs so ledgers from
different installations can later be imported together.

Existing data is kept: when any exists, it is attached to one person named "Owner" with one ledger,
and every row's relationships are preserved by mapping each old integer id to a new UUID. The
pseudonym salt moves from the settings table onto the ledger. This migration is one-way: integer
ids cannot be rebuilt from UUIDs, so `downgrade` refuses; restore from a backup instead.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# table -> {fk column: referenced table}; every table here has an integer `id`
FKS: dict[str, dict[str, str]] = {
    "accounts": {},
    "obligation_rules": {"account_id": "accounts", "source_account_id": "accounts"},
    "income_rules": {"account_id": "accounts"},
    "obligation_instances": {"rule_id": "obligation_rules"},
    "income_instances": {"rule_id": "income_rules"},
    "imports": {"account_id": "accounts", "obligation_rule_id": "obligation_rules"},
    "valuations": {"account_id": "accounts"},
    "transactions": {
        "account_id": "accounts",
        "obligation_instance_id": "obligation_instances",
        "income_instance_id": "income_instances",
        "import_id": "imports",
    },
    "transfer_links": {"debit_tx_id": "transactions", "credit_tx_id": "transactions"},
    "unlinked_pairs": {"low_tx_id": "transactions", "high_tx_id": "transactions"},
    "merchant_mappings": {},
    "redaction_terms": {},
}
LEDGER_OWNED = [t for t in FKS if t not in ("transfer_links", "unlinked_pairs")] + [
    "pseudonym_labels"
]


def upgrade() -> None:
    # 1. the new tables -------------------------------------------------------------
    op.create_table(
        "people",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "ledgers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("people.id"), nullable=False, unique=True),
        sa.Column("pseudonym_salt", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "ledger_settings",
        sa.Column("ledger_id", sa.Uuid(), sa.ForeignKey("ledgers.id"), primary_key=True),
        sa.Column("min_cash_buffer", sa.BigInteger(), server_default="0", nullable=False),
        sa.CheckConstraint("min_cash_buffer >= 0", name="ck_ledger_settings_buffer"),
    )
    op.create_table(
        "households",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "household_members",
        sa.Column("household_id", sa.Uuid(), sa.ForeignKey("households.id"), primary_key=True),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("people.id"), primary_key=True),
        sa.Column("role", sa.String(32), server_default="member", nullable=False),
        sa.Column("from_date", sa.Date(), primary_key=True),
        sa.Column("until_date", sa.Date(), nullable=True),
        sa.Column("visibility", sa.String(16), server_default="full", nullable=False),
        sa.CheckConstraint("visibility IN ('full', 'balances_only')", name="ck_member_visibility"),
        sa.CheckConstraint("until_date IS NULL OR until_date >= from_date", name="ck_member_dates"),
    )
    op.create_index(
        "uq_member_current_household",
        "household_members",
        ["person_id"],
        unique=True,
        postgresql_where=sa.text("until_date IS NULL"),
    )

    # 2. one person and ledger for any data that already exists ------------------------
    op.execute(
        """
        INSERT INTO people (id, name)
        SELECT gen_random_uuid(), 'Owner'
        WHERE EXISTS (SELECT 1 FROM accounts) OR EXISTS (SELECT 1 FROM redaction_terms)
           OR EXISTS (SELECT 1 FROM merchant_mappings) OR EXISTS (SELECT 1 FROM pseudonym_labels)
        """
    )
    op.execute(
        """
        INSERT INTO ledgers (id, person_id, pseudonym_salt)
        SELECT gen_random_uuid(), p.id,
               COALESCE((SELECT pseudonym_salt FROM settings WHERE id = 1),
                        decode(md5(random()::text || clock_timestamp()::text), 'hex')
                        || decode(md5(clock_timestamp()::text || random()::text), 'hex'))
        FROM people p
        """
    )
    op.execute(
        """
        INSERT INTO ledger_settings (ledger_id, min_cash_buffer)
        SELECT l.id, COALESCE((SELECT min_cash_buffer FROM settings WHERE id = 1), 0) FROM ledgers l
        """
    )

    # 3. ledger_id on every owned table (the single ledger, when there is one) -----------
    for table in LEDGER_OWNED:
        op.add_column(table, sa.Column("ledger_id", sa.Uuid(), nullable=True))
        op.execute(f"UPDATE {table} SET ledger_id = (SELECT id FROM ledgers LIMIT 1)")
        op.alter_column(table, "ledger_id", nullable=False)

    # 4. map every old integer id to a new UUID, and every reference with it ---------------
    for table in FKS:
        op.execute(f"ALTER TABLE {table} ADD COLUMN uid uuid NOT NULL DEFAULT gen_random_uuid()")
    for table, refs in FKS.items():
        for col, target in refs.items():
            op.execute(f"ALTER TABLE {table} ADD COLUMN {col}_u uuid")
            op.execute(
                f"UPDATE {table} SET {col}_u = t.uid FROM {target} t WHERE {table}.{col} = t.id"
            )
    # DROP COLUMN ... CASCADE removes the old keys, foreign keys, indexes, and checks on them
    for table, refs in FKS.items():
        for col in refs:
            op.execute(f"ALTER TABLE {table} DROP COLUMN {col} CASCADE")
    for table in FKS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN id CASCADE")
    for table, refs in FKS.items():
        op.execute(f"ALTER TABLE {table} RENAME COLUMN uid TO id")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
        op.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id)")
        for col in refs:
            op.execute(f"ALTER TABLE {table} RENAME COLUMN {col}_u TO {col}")
    for table, col in [
        ("obligation_rules", "account_id"),
        ("income_rules", "account_id"),
        ("obligation_instances", "rule_id"),
        ("income_instances", "rule_id"),
        ("imports", "account_id"),
        ("valuations", "account_id"),
        ("transactions", "account_id"),
        ("transfer_links", "debit_tx_id"),
        ("transfer_links", "credit_tx_id"),
        ("unlinked_pairs", "low_tx_id"),
        ("unlinked_pairs", "high_tx_id"),
    ]:
        op.alter_column(table, col, nullable=False)

    # unlinked pairs are stored low < high, and UUID order differs from integer order
    op.execute(
        """
        UPDATE unlinked_pairs SET low_tx_id = LEAST(low_tx_id, high_tx_id),
                                  high_tx_id = GREATEST(low_tx_id, high_tx_id)
        """
    )

    # 5. the constraints and indexes the models declare --------------------------------
    for table in LEDGER_OWNED:
        op.create_foreign_key(f"fk_{table}_ledger", table, "ledgers", ["ledger_id"], ["id"])
        if table != "pseudonym_labels":  # its primary key leads with ledger_id
            op.create_index(f"ix_{table}_ledger_id", table, ["ledger_id"])
    for table, name in [
        ("accounts", "uq_accounts_ledger_id"),
        ("imports", "uq_imports_ledger_id"),
        ("transactions", "uq_transactions_ledger_id"),
        ("obligation_rules", "uq_obligation_rules_ledger_id"),
        ("obligation_instances", "uq_obligation_instances_ledger_id"),
        ("income_rules", "uq_income_rules_ledger_id"),
        ("income_instances", "uq_income_instances_ledger_id"),
    ]:
        op.create_unique_constraint(name, table, ["ledger_id", "id"])

    def composite(table: str, name: str, cols: list[str], target: str) -> None:
        op.create_foreign_key(name, table, target, ["ledger_id", *cols], ["ledger_id", "id"])

    composite("imports", "fk_imports_account", ["account_id"], "accounts")
    composite("imports", "fk_imports_rule", ["obligation_rule_id"], "obligation_rules")
    composite("valuations", "fk_valuations_account", ["account_id"], "accounts")
    composite("transactions", "fk_transactions_account", ["account_id"], "accounts")
    composite(
        "transactions",
        "fk_transactions_obligation",
        ["obligation_instance_id"],
        "obligation_instances",
    )
    composite("transactions", "fk_transactions_income", ["income_instance_id"], "income_instances")
    composite("transactions", "fk_transactions_import", ["import_id"], "imports")
    composite("obligation_rules", "fk_obligation_rules_account", ["account_id"], "accounts")
    composite("obligation_rules", "fk_obligation_rules_source", ["source_account_id"], "accounts")
    composite("income_rules", "fk_income_rules_account", ["account_id"], "accounts")
    composite(
        "obligation_instances", "fk_obligation_instances_rule", ["rule_id"], "obligation_rules"
    )
    composite("income_instances", "fk_income_instances_rule", ["rule_id"], "income_rules")
    for col in ("debit_tx_id", "credit_tx_id"):
        op.create_foreign_key(
            f"fk_transfer_links_{col}", "transfer_links", "transactions", [col], ["id"]
        )
    for col in ("low_tx_id", "high_tx_id"):
        op.create_foreign_key(
            f"fk_unlinked_pairs_{col}", "unlinked_pairs", "transactions", [col], ["id"]
        )

    op.create_index("ix_imports_account", "imports", ["account_id"])
    op.create_index("ix_valuations_account_asof", "valuations", ["account_id", "as_of"])
    op.create_index("ix_transactions_account_date", "transactions", ["account_id", "posted_date"])
    op.create_unique_constraint(
        "uq_transactions_account_hash", "transactions", ["account_id", "dedup_hash"]
    )
    op.create_index(
        "uq_transactions_obligation_instance",
        "transactions",
        ["obligation_instance_id"],
        unique=True,
        postgresql_where=sa.text("obligation_instance_id IS NOT NULL"),
    )
    op.create_index(
        "uq_transactions_income_instance",
        "transactions",
        ["income_instance_id"],
        unique=True,
        postgresql_where=sa.text("income_instance_id IS NOT NULL"),
    )
    op.create_unique_constraint(
        "uq_obligation_instance", "obligation_instances", ["rule_id", "scheduled_date"]
    )
    op.create_unique_constraint(
        "uq_income_instance", "income_instances", ["rule_id", "scheduled_date"]
    )
    op.create_index(
        "uq_obligation_rules_card_statement",
        "obligation_rules",
        ["source_account_id", "source_period_end"],
        unique=True,
        postgresql_where=sa.text("source = 'card_statement'"),
    )
    op.create_check_constraint(
        "ck_transfer_distinct", "transfer_links", "debit_tx_id <> credit_tx_id"
    )
    op.create_unique_constraint("uq_transfer_debit", "transfer_links", ["debit_tx_id"])
    op.create_unique_constraint("uq_transfer_credit", "transfer_links", ["credit_tx_id"])
    op.create_check_constraint("ck_unlinked_ordered", "unlinked_pairs", "low_tx_id < high_tx_id")
    op.create_unique_constraint("uq_unlinked_pair", "unlinked_pairs", ["low_tx_id", "high_tx_id"])

    # keys that were global become per-ledger
    op.drop_constraint("merchant_mappings_lookup_key_key", "merchant_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_mappings_ledger_key", "merchant_mappings", ["ledger_id", "lookup_key"]
    )
    op.drop_constraint("redaction_terms_term_key", "redaction_terms", type_="unique")
    op.create_unique_constraint(
        "uq_redaction_terms_ledger_term", "redaction_terms", ["ledger_id", "term"]
    )
    op.drop_constraint("pseudonym_labels_pkey", "pseudonym_labels", type_="primary")
    op.create_primary_key("pseudonym_labels_pkey", "pseudonym_labels", ["ledger_id", "token"])

    # 6. the single settings row has moved onto the ledger ---------------------------------
    op.drop_table("settings")


def downgrade() -> None:
    raise NotImplementedError(
        "0006 is one-way: integer ids cannot be rebuilt from UUIDs. Restore from a backup taken "
        "before upgrading."
    )
