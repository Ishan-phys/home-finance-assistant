"""category keywords, and starter rules for ledgers that already exist

Revision ID: 0013
Revises: 0012
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (label, text, way, target path): copied here so the migration never changes with the app
_STARTER = (
    ("Card bill payment", "BPPY CC PAYMENT", "any", "Assets:InTransit"),
    ("Card bill payment", "CREDIT CARD PAYMENT", "any", "Assets:InTransit"),
    ("Card bill payment", "CC PAYMENT", "any", "Assets:InTransit"),
    ("Card bill payment", "MB/IB PAYMENT", "any", "Assets:InTransit"),
    ("Card bill payment", "PAYMENT RECEIVED", "credit", "Assets:InTransit"),
    ("Card cashback", "CASHBACK", "any", "Income:Rewards"),
)


def upgrade() -> None:
    op.add_column("accounts", sa.Column("keywords", sa.Text(), nullable=False, server_default=""))
    bind = op.get_bind()
    ledgers = (
        bind.execute(
            sa.text(
                "SELECT l.id FROM ledgers l WHERE NOT EXISTS (SELECT 1 FROM rules r WHERE r.ledger_id = l.id)"
            )
        )
        .scalars()
        .all()
    )
    for ledger_id in ledgers:
        for position, (label, text, way, target) in enumerate(_STARTER):
            bind.execute(
                sa.text(
                    "INSERT INTO rules (id, ledger_id, label, match_text, mode, way, target,"
                    " position, builtin) VALUES (:id, :ledger, :label, :text, 'contains', :way,"
                    " :target, :position, true)"
                ),
                {
                    "id": uuid.uuid4(),
                    "ledger": ledger_id,
                    "label": label,
                    "text": text,
                    "way": way,
                    "target": target,
                    "position": position,
                },
            )


def downgrade() -> None:
    op.execute("DELETE FROM rules WHERE builtin")
    op.drop_column("accounts", "keywords")
