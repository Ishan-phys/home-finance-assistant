"""Data migrations on a database that already holds a ledger."""

from __future__ import annotations

import os
import uuid

from alembic import command
from cfo.testing.pg import alembic_config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_0013_gives_existing_ledgers_starter_rules_once(pg_url: str, admin_engine) -> None:  # type: ignore[no-untyped-def]
    name = f"mig_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(pg_url).set(database=name).render_as_string(hide_password=False)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        cfg = alembic_config(url)
        command.upgrade(cfg, "0012")
        engine = create_engine(url)
        with_rules, without = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as c:
            for name_, lid in (("A", with_rules), ("B", without)):
                person = uuid.uuid4()
                c.execute(
                    text("INSERT INTO people (id, name) VALUES (:i, :n)"), {"i": person, "n": name_}
                )
                c.execute(
                    text("INSERT INTO ledgers (id, person_id, pseudonym_salt) VALUES (:l, :p, :s)"),
                    {"l": lid, "p": person, "s": b"x" * 32},
                )
            c.execute(
                text(
                    "INSERT INTO rules (id, ledger_id, label, match_text, mode, way, target,"
                    " position) VALUES (:i, :l, 'mine', 'x', 'contains', 'any', 'Expenses:Fees', 0)"
                ),
                {"i": uuid.uuid4(), "l": with_rules},
            )
        command.upgrade(cfg, "0013")
        with engine.connect() as c:
            counts = dict(
                c.execute(text("SELECT ledger_id, count(*) FROM rules GROUP BY ledger_id")).all()
            )
            keywords = c.execute(
                text("SELECT count(*) FROM accounts WHERE keywords IS NULL")
            ).scalar()
        assert counts[with_rules] == 1  # a ledger that already had rules is left alone
        assert counts[without] == 6 and keywords == 0
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
