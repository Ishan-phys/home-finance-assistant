from datetime import date

from cfo.ingest.dedup import dedup_hash, hash_rows
from cfo.parse.readers import read_document
from cfo.parse.registry import ADAPTERS
from cfo.testing import FIXTURE_DIR


def d(text: str) -> date:
    return date.fromisoformat(text)


def load(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def test_occurrences_and_hash_stability() -> None:
    p = ADAPTERS["hdfc_bank"].parse(read_document("a.xls", load("hdfc_bank_sep.xls")))
    hashed = hash_rows(p.rows, account_id=1)
    twins = [h for h in hashed if h.row.date == d("2026-09-09")]
    assert [t.occurrence for t in twins] == [1, 2] and twins[0].dedup_hash != twins[1].dedup_hash
    # an overlapping later file carries the same rows with the same occurrences: same hashes
    again = hash_rows(p.rows[3:], account_id=1)
    assert {h.dedup_hash for h in again} <= {h.dedup_hash for h in hashed}
    assert dedup_hash(d("2026-09-09"), -25000, 1, "UPI-TEST CAFE-TESTCAFE-REF000009-UPI", 1) == (
        twins[0].dedup_hash
    )
    # another account never collides
    assert hash_rows(p.rows, 2)[0].dedup_hash != hashed[0].dedup_hash


def test_groww_order_twins_get_separate_occurrences() -> None:
    p = ADAPTERS["groww"].parse(read_document("o.xlsx", load("groww_mf_orders.xlsx")))
    twins = [h for h in hash_rows(p.rows, 1) if h.row.date == d("2026-08-26")]
    assert [t.occurrence for t in twins] == [1, 2]
