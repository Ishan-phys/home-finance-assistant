"""redaction pipeline: pseudonym salt, account fingerprint, redaction summary, token labels

Ingestion now redacts personal details before parsing (spec 4.12.2). Tokens are keyed by a
per-installation salt, accounts remember the fingerprint of their card or account number so a
misplaced statement can be flagged, each import records what was redacted (counts only), and
the owner can label tokens.

Revision ID: 0004
Revises: 0003
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("pseudonym_salt", sa.LargeBinary(), nullable=True))
    op.execute(
        sa.text("UPDATE settings SET pseudonym_salt = :salt").bindparams(
            sa.bindparam("salt", os.urandom(32), type_=sa.LargeBinary())
        )
    )
    op.add_column("accounts", sa.Column("statement_fingerprint", sa.String(32), nullable=True))
    op.add_column("imports", sa.Column("redaction_summary", postgresql.JSONB(), nullable=True))
    op.create_table(
        "pseudonym_labels",
        sa.Column("token", sa.String(40), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.CheckConstraint("length(trim(label)) > 0", name="ck_pseudonym_label_nonblank"),
    )


def downgrade() -> None:
    op.drop_table("pseudonym_labels")
    op.drop_column("imports", "redaction_summary")
    op.drop_column("accounts", "statement_fingerprint")
    op.drop_column("settings", "pseudonym_salt")
