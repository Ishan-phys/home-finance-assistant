# Contributing

Thanks for helping. This project handles people's financial data, so a few rules are firm and the
rest is ordinary open-source etiquette.

## The firm rules

1. **Never commit real data.** No real statements, account or card numbers, names, phone numbers,
   UPI handles, `.env` files or API keys: not in code, tests, fixtures, docs, issues or screenshots.
   Real statements belong in `statements/`, which is gitignored. Test data must be synthetic
   (`fixtures/build_fixtures.py` generates the fixtures; use made-up names such as "Asha Rao").
2. **Money is integer paise.** Never use floats for amounts.
3. **Models never do arithmetic.** Every figure comes from the pure functions in `cfo-metrics`;
   the agent only calls them and explains the result.
4. **Nothing leaves the machine unredacted.** Anything sent to a model passes through `cfo-redact`.
5. **Respect package boundaries.** `tools/check_imports.py` enforces which package may import
   which. If you need a new dependency edge, say so in the pull request.

## Getting set up

You need Python 3.13 with [`uv`](https://docs.astral.sh/uv/), Node 22, and Docker (the tests start
a throwaway PostgreSQL through testcontainers).

```sh
uv sync                              # the whole workspace
cp .env.example .env                 # keys are optional for development: tests use fakes
docker compose up -d --build         # the full stack, for the browser tests and manual use
cd web && npm ci && cd ..
uvx pre-commit install              # optional: runs the lint and secret checks on each commit
```

Read the [user guide](user-guide.md) to run and use the app. The product and design documents
(PRD, HLD, LLD, TDD) are kept by the maintainers and not published; for a design question, open an
issue or discussion first and a maintainer will explain the intent.

## Before you open a pull request

CI runs all of this; run it locally first.

```sh
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/*/src api/src tools/check_imports.py
uv run python tools/check_imports.py
bash tools/test_isolated.sh          # each extractable package passes on its own
uv run pytest                        # unit and integration tests

cd web && npm run lint && npm run typecheck && npm run build
npx playwright test                  # needs the stack up; EMPTIES THE LOCAL DATABASE
```

`uv run ruff format .` fixes formatting. The browser tests wipe the database in the running stack,
so do not run them against data you want to keep.

## Making a change

- Open an issue first for anything large, or comment on an existing one.
- Keep a pull request to one idea. Add or update tests: behaviour without a test will not be merged.
- Schema changes need an Alembic migration in `packages/cfo-ledger/alembic/versions/` (see the
  README) and an update to the migration table there.
- Update the user guide and, if the behaviour is a design decision, the spec.
- Write commit messages that say why, in the imperative ("Add Axis debit card adapter").

## Adding a bank adapter

The most useful contribution. In `packages/cfo-parse`:

1. Add a **synthetic** fixture in the real file format via `fixtures/build_fixtures.py`.
   Do not copy a real statement and edit it by hand.
2. Add an adapter that declares the header it recognises and which columns carry what; adapters
   read a neutral `Document` and never call a model or compute metrics.
3. Register it in `registry.py`, add it to the catalog in `api/src/cfo/api/catalog.py`, and add a
   friendly "what to upload" line in `api/src/cfo/api/friendly.py`.
4. Add the expected results to `fixtures/expected_results.json` and tests.
5. Check redaction on narrations of that bank: leaks are bugs (see below).

## Redaction bugs

If a personal detail gets past the redactor, open an issue **describing the shape** of the
narration with the details replaced (for example `UPI/<name>/<handle>`), never the real text. If a
report would need real data to be understood, use a private security advisory instead
(see [SECURITY.md](SECURITY.md)).

## Code style

Python: `ruff` (lint and format, line length 100) and strict `mypy`. TypeScript: the ESLint config
in `web/`. Match the surrounding code. Prefer small pure functions, and explain *why* in comments,
not *what*.

## Conduct

Be kind and assume good faith. See the [Code of Conduct](CODE_OF_CONDUCT.md).
