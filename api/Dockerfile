# Build context is the repository root: `docker compose build api`.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# .python-version pins 3.13 but the base image is newer, so uv installs its own Python. Keep it out
# of /root, which the unprivileged user below cannot read.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
COPY pyproject.toml uv.lock .python-version ./
COPY packages ./packages
COPY api ./api
COPY fixtures ./fixtures
RUN uv sync --frozen --no-dev --package cfo-api
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system --no-create-home cfo && mkdir /keys && chown cfo /keys
USER cfo
EXPOSE 8000
WORKDIR /app/packages/cfo-ledger
CMD ["sh", "-c", "alembic upgrade head && uvicorn cfo.api.app:create_app --factory --host 0.0.0.0 --port 8000"]
