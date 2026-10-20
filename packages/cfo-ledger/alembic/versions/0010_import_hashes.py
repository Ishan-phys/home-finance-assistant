"""the rows each statement contained

Removing a statement used to delete rows that an overlapping or identical later statement also
contained. Each import now records every row it held, so removal keeps the rows another
statement still holds.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_hashes",
        sa.Column("ledger_id", sa.Uuid(), sa.ForeignKey("ledgers.id"), primary_key=True),
        sa.Column("import_id", sa.Uuid(), primary_key=True),
        sa.Column("dedup_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ledger_id", "import_id"],
            ["imports.ledger_id", "imports.id"],
            name="fk_import_hashes_import",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_import_hashes_account_hash", "import_hashes", ["account_id", "dedup_hash"])
    # Statements imported before this revision recorded only the rows they added.
    op.execute(
        "INSERT INTO import_hashes (ledger_id, import_id, dedup_hash, account_id) "
        "SELECT ledger_id, import_id, dedup_hash, account_id FROM postings "
        "WHERE import_id IS NOT NULL AND dedup_hash IS NOT NULL ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_index("ix_import_hashes_account_hash", table_name="import_hashes")
    op.drop_table("import_hashes")
