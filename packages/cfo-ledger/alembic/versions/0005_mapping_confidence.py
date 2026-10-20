"""keep the model's confidence on merchant mappings

The System-1 categorizer returns a confidence with every label. It is stored so a later screen can
list the shakiest model labels for review. Owner mappings have none.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("merchant_mappings", sa.Column("confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("merchant_mappings", "confidence")
