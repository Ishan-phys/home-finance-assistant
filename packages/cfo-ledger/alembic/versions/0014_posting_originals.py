"""sealed original narrations

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "posting_originals",
        sa.Column("ledger_id", sa.Uuid(), sa.ForeignKey("ledgers.id"), primary_key=True),
        sa.Column("account_id", sa.Uuid(), primary_key=True),
        sa.Column("dedup_hash", sa.String(64), primary_key=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("posting_originals")
