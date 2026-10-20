# Build context is the repository root: `docker compose build api`.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version ./
COPY packages ./packages
COPY api ./api
COPY fixtures ./fixtures
RUN uv sync --frozen --no-dev --package cfo-api
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system --no-create-home cfo
USER cfo
EXPOSE 8000
WORKDIR /app/packages/cfo-ledger
CMD ["sh", "-c", "alembic upgrade head && uvicorn cfo.api.app:create_app --factory --host 0.0.0.0 --port 8000"]
