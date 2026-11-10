# Development

How to build, test and change the code. To run and use the app, see
[Getting started](getting-started.md) and the [user guide](user-guide.md). For how the pieces fit together, see [architecture](architecture.md).

## Prerequisites

- Python 3.13 with [`uv`](https://docs.astral.sh/uv/)
- Node 22
- Docker with Compose 2.24 or later (the Python tests start a throwaway PostgreSQL through
  testcontainers, and the browser tests run against the full stack)

```sh
uv sync                          # the whole Python workspace
cp .env.example .env             # model keys are optional for development: tests use fakes
cd web && npm ci && npx playwright install chromium && cd ..
uvx pre-commit install           # optional: lint and secret checks on each commit
```

## Everyday commands

| What | Command |
| --- | --- |
| Start the app (web on 127.0.0.1:3000, API on 127.0.0.1:8000) | `make up` |
| Rebuild after changing code or dependencies | `make rebuild` |
| Python unit and integration tests | `make test` (`uv run pytest`) |
| Lint, format check, strict mypy, import boundaries | `make lint` |
| Browser tests, on a separate throwaway stack | `make e2e`, then `make e2e-down` |
| Web lint, types and build | `cd web && npm run lint && npm run typecheck && npm run build` |
| Each extractable package passes on its own | `bash tools/test_isolated.sh` |
| Ports: PostgreSQL has no host port, web and API listen on 127.0.0.1 only | `./scripts/check-ports.sh` |
| Every other target | `make help` |

To make the Python tests faster, reuse a running PostgreSQL instead of starting one each time:

```sh
CFO_TEST_DATABASE_URL=postgresql+psycopg://cfo:dev@127.0.0.1:55432/cfo uv run pytest
```

## Browser tests

The Playwright tests in `web/e2e/` empty the database before each test. `make e2e` runs them on a
second stack (project `cfo-e2e`, web on port 3210, its own volumes, no model keys), so the data in
`make up` is never touched. CI runs them the same way against a fresh stack.

Running `npx playwright test` directly targets the stack on port 3000 and **wipes it**. Only do
that on a stack with nothing you want to keep.

## Test data

- `fixtures/` holds **synthetic** statements in each bank's real file format.
  `fixtures/build_fixtures.py` regenerates them. Names are made up ("Asha Rao", "Test Cafe").
- `fixtures/expected_results.json` holds the sample ledger's figures, **derived by hand** from the
  fixtures, not copied from the engine. The acceptance test checks the engine against it.
- The acceptance run seeds merchant mappings from `fixtures/merchant_mappings.json`, so its
  figures never depend on a live model.
- Real statements belong in `statements/`, which is gitignored. Never commit one.

## Model keys

Chat and categorization need `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env` (exactly one).
Without a key, the assistant says it is unavailable and categorization is off; everything else
works. The tests never call a live model.

## Sign-in

The API needs an owner to sign in. For local work, `.env` holds one (see [Getting started](getting-started.md#step-4-set-up-your-sign-in)). The
browser tests use a fixed throwaway owner in `docker-compose.e2e.yml` (username `owner`, password
`e2e-owner-password`), and `web/e2e/global-setup.ts` signs in once and keeps the session for every
test. The Python tests set their own owner in `api/tests/conftest.py`; they never read `.env`.

In a compose file, write each `$` in the hash as `$$`. In `.env`, put the hash in single quotes.
Otherwise Compose replaces the `$` parts with nothing and every sign-in fails with a 401.

## Making a change

- Read [CONTRIBUTING.md](CONTRIBUTING.md) for the firm rules (no real data, integer paise, no
  arithmetic in models, redact before anything leaves the machine, package boundaries).
- Schema changes need an Alembic migration and a row in [database-migrations.md](database-migrations.md).
- User-visible changes update the [user guide](user-guide.md) and the page's "About this page"
  note in the web app.
- Before a pull request, run `make lint`, `make test`, the web checks and `make e2e`.

## More

- [Architecture](architecture.md): the packages, the upload pipeline, and the rules that hold
  them together
- [Database migrations](database-migrations.md): every revision and how to apply one
- [HTTP API](api.md): routes, amounts and errors
