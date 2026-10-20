## What and why

<!-- What changes, and why. Link the issue. -->

## Checklist

- [ ] No real statements, names, account numbers, keys or other personal data (code, tests, fixtures, docs, screenshots)
- [ ] Tests added or updated, and `uv run pytest` passes
- [ ] `ruff check`, `ruff format --check`, `mypy` and `tools/check_imports.py` pass
- [ ] Web changes: `npm run lint`, `npm run typecheck`, `npm run build` pass (and Playwright if the UI changed)
- [ ] Schema change has an Alembic migration and the README migration table is updated
- [ ] User guide and spec updated if behaviour changed
