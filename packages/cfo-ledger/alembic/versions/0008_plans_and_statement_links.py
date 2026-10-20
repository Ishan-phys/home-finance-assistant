"""spending plans, and the statement each balance came from

A spending plan holds the intended amounts: an overall monthly allowance and per-category limits,
either for one month or as a default for every month. Balances now remember the import they came
from, so removing a statement removes them too.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORIES = (
    "'', 'Income', 'Housing', 'Utilities', 'Subscriptions', 'Dining', 'Shopping', 'Health', "
    "'Transport', 'Fees', 'Investments', 'Cashback', 'Travel', 'Received from others', "
    "'Sent to others', 'Own transfer', 'Uncategorized', 'Transfer'"
)


def upgrade() -> None:
    op.create_table(
        "spending_plans",
        sa.Column("ledger_id", sa.Uuid(), sa.ForeignKey("ledgers.id"), primary_key=True),
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("category", sa.String(32), primary_key=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount >= 0", name="ck_spending_plans_amount"),
        sa.CheckConstraint(
            "month = '' OR month ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_spending_plans_month"
        ),
        sa.CheckConstraint(f"category IN ({_CATEGORIES})", name="ck_spending_plans_category"),
    )
    op.add_column("valuations", sa.Column("import_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_valuations_import",
        "valuations",
        "imports",
        ["ledger_id", "import_id"],
        ["ledger_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_valuations_import", "valuations", type_="foreignkey")
    op.drop_column("valuations", "import_id")
    op.drop_table("spending_plans")
