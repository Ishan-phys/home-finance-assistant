# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Copilot, Cursor and others) working in this
repository. Humans should start with [CONTRIBUTING.md](docs/CONTRIBUTING.md); the rules are the
same.

## What this is

AI CFO: a local-first personal finance app over a double-entry ledger. Bank statements are
redacted, parsed, categorized and journaled into PostgreSQL; pure Python computes every figure; a
Next.js cockpit shows them; a chat agent explains them. Read [docs/architecture.md](docs/architecture.md)
before a non-trivial change.

| Path | What |
| --- | --- |
| `packages/cfo-*` | Python `uv` workspace packages (core, doc, vault, redact, parse, categorize, metrics, rules, ledger, ingest, agent, testing) |
| `api/` | FastAPI app (`api/src/cfo/api/app.py` is the entry point, routes in `routes.py`) |
| `web/` | Next.js cockpit. **Read `web/AGENTS.md` first**: this Next.js version differs from your training data |
| `fixtures/` | Synthetic statements and hand-derived expected figures |
| `docs/` | User guide, development, architecture, API, migrations |

## Commands

```sh
uv sync                                   # install the Python workspace
make lint                                 # ruff, format check, strict mypy, import boundaries
make test                                 # pytest (starts a throwaway PostgreSQL via Docker)
cd web && npm run lint && npm run typecheck   # web checks
make e2e                                  # Playwright on a separate throwaway stack (port 3210)
uv run ruff format .                      # fix Python formatting
```

Run the checks for what you touched before saying a change is done, and report failures with
their output.

## Never

- **Never run `npx playwright test` against the stack on port 3000.** The browser tests truncate
  every table, and that stack holds the owner's real ledger. Use `make e2e`, which runs its own
  stack.
- **Never commit or paste real financial data**: statements, account or card numbers, names, UPI
  handles, `.env`, `backup.sql`, anything from `statements/`. Test data is synthetic
  ("Asha Rao", "Test Cafe"); generate fixtures with `fixtures/build_fixtures.py`.
- **Never run `make reset` or `docker compose down -v`** on the main stack without the owner
  asking: it deletes their ledger.
- **Never send unredacted text to a model.** Anything model-bound goes through `cfo-redact`.

## Invariants

- **Money is integer paise.** No floats for amounts, anywhere.
- **The browser never does money maths.** The API sends `{"paise", "formatted"}`; if the UI needs
  a new total, add it to the report in `packages/cfo-ledger/src/cfo/ledger/reports.py` (computed
  in `cfo-metrics`), not in TypeScript.
- **Models never do arithmetic.** Figures come from pure functions in `cfo-metrics`; the agent's
  tools return them and the model only explains.
- **Every transaction balances.** Postings sum to zero; the database rejects anything else.
- **Package boundaries are enforced.** `tools/check_imports.py` lists who may import whom. Adding
  an edge is a design decision: say so in the pull request.
- **Overview and Spending show the same month.** Both use `default_month`: the current month once
  it has statements, otherwise the latest month that does.

## Conventions

- Match the surrounding code. Python: Ruff (line length 100), strict mypy, small pure functions.
  TypeScript: the ESLint config in `web/`.
- Comments explain *why*, not *what*. Docstrings are short and plain.
- UI copy is plain, concrete English, written for someone who is not an accountant. When a page's
  behaviour changes, update its **About this page** note (the `about` prop on `PageHeader`) and
  the [user guide](docs/user-guide.md).
- Every behaviour change comes with a test: pytest for Python, Playwright in `web/e2e/` for
  user-visible flows. `fixtures/expected_results.json` is derived by hand; when you add a figure,
  derive it by hand too, and say how in its `_comment`.
- Schema changes need an Alembic migration in `packages/cfo-ledger/alembic/versions/` and a row in
  [docs/database-migrations.md](docs/database-migrations.md).
- Commit messages are imperative and say why ("Total income and expenses over all time on All
  accounts"). One idea per pull request.
