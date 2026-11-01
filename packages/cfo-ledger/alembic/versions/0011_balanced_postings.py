"""double entry is enforced by the database

Every transaction's postings must sum to zero at commit. The check is a deferred constraint
trigger, so a write may pass through an unbalanced state inside one database transaction (pairing
moves postings between transactions) but never commit one. Rows written earlier are not
revalidated; `cfo.ledger.verify.verify_books` lists any that do not balance.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION check_transaction_balanced() RETURNS trigger AS $$
DECLARE
    ids uuid[];
    tx uuid;
    total bigint;
    n integer;
BEGIN
    IF TG_OP = 'DELETE' THEN
        ids := ARRAY[OLD.transaction_id];
    ELSIF TG_OP = 'INSERT' THEN
        ids := ARRAY[NEW.transaction_id];
    ELSE
        ids := ARRAY[OLD.transaction_id, NEW.transaction_id];
    END IF;
    FOREACH tx IN ARRAY ids LOOP
        SELECT COALESCE(SUM(amount), 0), COUNT(*) INTO total, n
        FROM postings WHERE transaction_id = tx;
        IF n > 0 AND total <> 0 THEN
            RAISE EXCEPTION 'transaction % does not balance (postings sum to %)', tx, total
                USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_FUNCTION)
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_postings_balanced AFTER INSERT OR UPDATE OR DELETE "
        "ON postings DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION check_transaction_balanced()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_postings_balanced ON postings")
    op.execute("DROP FUNCTION IF EXISTS check_transaction_balanced()")
