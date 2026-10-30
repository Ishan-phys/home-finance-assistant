"""owner rules

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ledger_id", sa.Uuid(), sa.ForeignKey("ledgers.id"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("match_text", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("way", sa.String(6), nullable=False, server_default="any"),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("mode IN ('contains', 'starts_with')", name="ck_rules_mode"),
        sa.CheckConstraint("way IN ('any', 'debit', 'credit')", name="ck_rules_way"),
        sa.CheckConstraint("length(trim(match_text)) > 0", name="ck_rules_text_nonblank"),
    )
    op.create_index("ix_rules_ledger_id", "rules", ["ledger_id"])
    op.create_index("ix_rules_ledger_position", "rules", ["ledger_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_rules_ledger_position", table_name="rules")
    op.drop_index("ix_rules_ledger_id", table_name="rules")
    op.drop_table("rules")
