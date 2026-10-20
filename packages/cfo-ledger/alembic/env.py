import os

from alembic import context
from cfo.ledger.repositories.models import Base
from sqlalchemy import create_engine, pool

target_metadata = Base.metadata


def _url() -> str:
    return os.environ.get("DATABASE_URL") or context.config.get_main_option("sqlalchemy.url") or ""


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
