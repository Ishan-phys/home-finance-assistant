"""add the Cashback category

Card cashback and rewards credits are not income. The category check constraints on
transactions and merchant mappings gain 'Cashback'.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE = (
    "'Income', 'Housing', 'Utilities', 'Subscriptions', 'Dining', 'Shopping', 'Health', "
    "'Transport', 'Fees', 'Investments'"
)
_BEFORE = f"category IN ({_BASE}, 'Uncategorized', 'Transfer')"
_AFTER = f"category IN ({_BASE}, 'Cashback', 'Uncategorized', 'Transfer')"

_CHECKS = (
    ("transactions", "ck_transactions_category"),
    ("merchant_mappings", "ck_mappings_category"),
)


def upgrade() -> None:
    for table, name in _CHECKS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _AFTER)


def downgrade() -> None:
    # Rows already categorized Cashback cannot satisfy the older constraint.
    for table in ("transactions", "merchant_mappings"):
        op.execute(f"UPDATE {table} SET category = 'Uncategorized' WHERE category = 'Cashback'")
    for table, name in _CHECKS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _BEFORE)
