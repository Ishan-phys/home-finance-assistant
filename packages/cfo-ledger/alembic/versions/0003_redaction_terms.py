"""owner-set redaction terms

Words or phrases (the owner's name, family names) replaced with [REDACTED] before any text
goes to the model. Stored in the clear until iteration 4 encrypts sensitive fields.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redaction_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.CheckConstraint("length(trim(term)) > 0", name="ck_redaction_term_nonblank"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term"),
    )


def downgrade() -> None:
    op.drop_table("redaction_terms")
