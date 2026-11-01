# Database migrations

Schema changes live in `packages/cfo-ledger/alembic/versions/` and are applied in order:

| Revision | Change |
| --- | --- |
| `0001` | Initial schema: accounts, valuations, transactions, transfer links, merchant mappings, obligation and income rules and instances, imports, settings |
| `0002` | Adds the `Cashback` category |
| `0003` | Owner redaction terms |
| `0004` | Pseudonym salt, account fingerprint, redaction summary, token labels |
| `0005` | The model's confidence on merchant mappings |
| `0006` | People, ledgers, households, and UUIDv7 ids. **One-way**: it keeps existing data (attached to a person named "Owner") but cannot be reversed, so back up first |
| `0007` | Events and `transactions.event_id`; the categories Travel, Received from others, Sent to others, Own transfer |
| `0008` | Spending plans, and the statement each balance came from |
| `0009` | Double-entry books: the account tree (real accounts, categories, system accounts), transactions of postings, balance assertions, valuations, setup state. **One-way and not converting**: earlier ledger data is dropped and statements are re-uploaded, so back up first |
| `0010` | Records every row each statement contained, so removing a statement keeps rows another statement also holds |
| `0011` | The database enforces double entry: a deferred trigger rejects any transaction whose postings do not sum to zero at commit |
| `0012` | Owner rules: "if the narration matches, use this category", in order |
| `0013` | Category keywords, and the starter rules for ledgers that already exist |
| `0014` | Sealed original narrations: the unredacted bank text, encrypted at rest, shown only to the owner |

Reproduce the schema on any machine:

```sh
# with Compose: nothing to do, the api service runs `alembic upgrade head`

# or against any PostgreSQL 16 database
cd packages/cfo-ledger
uv sync
export DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
uv run alembic upgrade head          # apply everything
uv run alembic current               # show the applied revision
uv run alembic downgrade -1          # step back one revision
uv run alembic upgrade head --sql    # print the SQL instead of running it
```

Adding a migration: change `packages/cfo-ledger/src/cfo/ledger/repositories/models.py`, run
`uv run alembic revision --autogenerate -m "what changed" --rev-id 000N`, review the file,
and commit it with the model change. The integration tests apply every migration to a
throwaway database, and one test walks them up and down.
