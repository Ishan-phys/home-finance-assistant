# AI CFO

**New here? Start with the [setup and user guide](docs/user-guide.md).**

A local personal finance ledger and assistant, kept as double-entry books. You set up your
accounts, statements go in, Python computes every figure, and one agent explains them. See the [user guide](docs/user-guide.md) for how to run and use it.

- **Local first.** Your data lives in a PostgreSQL database on your machine. The app binds to
  `127.0.0.1` only.
- **Private by design.** Names, phone numbers, account numbers and other personal details are
  removed from every statement *before* it is stored or sent to any model. Redaction is best-effort;
  read [SECURITY.md](docs/SECURITY.md) and section 8 of the [user guide](docs/user-guide.md) before use.
- **Numbers come from code, and they agree.** Every transaction moves money between two accounts
  and adds up to zero, so net worth, the month's earned and spent, and safe-to-spend are computed
  from one set of books by tested Python. The chat agent only explains them.
- **Indian banks first.** Adapters exist for HDFC, SBI, Axis cards and Groww; adding a bank is a
  small, well-bounded contribution (see [CONTRIBUTING.md](docs/CONTRIBUTING.md)).

## Contributing

Contributions are welcome: bank adapters, redaction improvements, metrics, UI and docs. Read
[CONTRIBUTING.md](docs/CONTRIBUTING.md) first. **Never commit real statements or personal data.**

## Run it

```sh
cp .env.example .env      # add OPENAI_API_KEY or ANTHROPIC_API_KEY (either one runs both chat and categorization)
make up                   # (docker compose up -d) web on 127.0.0.1:3000, API on 127.0.0.1:8000
```

The API container applies database migrations on start. PostgreSQL publishes no host port.

On first run the app asks your name, then walks you through setup: your accounts (type,
institution, name) and your categories (each with a line on what it is for). Then you upload
statements into the accounts. Personal details are removed from every statement before anything
is stored or sent to a model.

## Database migrations

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

## Develop

```sh
uv sync                  # one workspace, Python 3.13
uv run pytest            # starts a throwaway PostgreSQL via Docker (testcontainers)
uv run ruff check . && uv run mypy packages/*/src api/src tools/check_imports.py
uv run python tools/check_imports.py   # package boundaries

# faster: reuse a running server
CFO_TEST_DATABASE_URL=postgresql+psycopg://cfo:dev@127.0.0.1:55432/cfo uv run pytest
```

`fixtures/build_fixtures.py` regenerates the synthetic statement fixtures. Real statements
belong in `statements/`, which is gitignored.

## Tests and acceptance

| What | How |
| --- | --- |
| Unit and integration (PostgreSQL), including the hand-derived expected results for the sample ledger | `uv run pytest` |
| Browser tests against the running stack (they empty the database first) | `docker compose up -d --build`, then `cd web && npx playwright install chromium && npx playwright test` |
| Ports: PostgreSQL has no host port, web and API listen on 127.0.0.1 only | `./scripts/check-ports.sh` |

The acceptance run seeds merchant mappings from `fixtures/merchant_mappings.json`, so its
figures never depend on a live model. `fixtures/expected_results.json` was derived by hand
from the fixtures. Chat needs `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`; without it the dock reports that
the assistant is unavailable and everything else works.

## Layout

A `uv` workspace of small packages under `packages/`, plus the app in `api/` and the cockpit in
`web/`. Each package declares what it may depend on, and `tools/check_imports.py` enforces it in CI.

| Package | Role |
| --- | --- |
| `cfo-core` | money, dates, domain records |
| `cfo-doc` | the neutral document form every statement is read into |
| `cfo-redact` | personal-detail redaction and prompt masking |
| `cfo-parse` | unlocking, readers, and per-bank adapters |
| `cfo-categorize` | the System-1 categorizer |
| `cfo-metrics` | pure functions over postings: balance sheet, income statement, reconciliation, safe-to-spend, inbox |
| `cfo-ledger` | schema, migrations, repositories, setup and journal services, reports |
| `cfo-ingest` | the ingestion pipeline |
| `cfo-agent` | the chat agent and its tools |
| `cfo-api` (`api/`) | the FastAPI app |

## License

[MIT](LICENSE).
