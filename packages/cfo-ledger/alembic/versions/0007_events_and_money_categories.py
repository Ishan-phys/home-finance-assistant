"""events, and categories for money moving between people

Adds the categories Travel, Received from others, Sent to others and Own transfer, a table of
named events, and transactions.event_id so spending can be grouped under a one-off.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE = (
    "'Income', 'Housing', 'Utilities', 'Subscriptions', 'Dining', 'Shopping', 'Health', "
    "'Transport', 'Fees', 'Investments', 'Cashback'"
)
_NEW = "'Travel', 'Received from others', 'Sent to others', 'Own transfer'"
_BEFORE = f"category IN ({_BASE}, 'Uncategorized', 'Transfer')"
_AFTER = f"category IN ({_BASE}, {_NEW}, 'Uncategorized', 'Transfer')"
_CHECKS = (
    ("transactions", "ck_transactions_category"),
    ("merchant_mappings", "ck_mappings_category"),
)


def upgrade() -> None:
    for table, name in _CHECKS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _AFTER)
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ledger_id", sa.Uuid(), sa.ForeignKey("ledgers.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("ledger_id", "id", name="uq_events_ledger_id"),
        sa.UniqueConstraint("ledger_id", "name", name="uq_events_ledger_name"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_events_name_nonblank"),
    )
    op.create_index("ix_events_ledger_id", "events", ["ledger_id"])
    op.add_column("transactions", sa.Column("event_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_transactions_event",
        "transactions",
        "events",
        ["ledger_id", "event_id"],
        ["ledger_id", "id"],
    )
    op.create_index("ix_transactions_event", "transactions", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_event", "transactions")
    op.drop_constraint("fk_transactions_event", "transactions", type_="foreignkey")
    op.drop_column("transactions", "event_id")
    op.drop_table("events")
    for table in ("transactions", "merchant_mappings"):
        op.execute(f"UPDATE {table} SET category = 'Uncategorized' WHERE category IN ({_NEW})")
    for table, name in _CHECKS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _BEFORE)
