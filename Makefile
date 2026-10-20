# Docker shortcuts. `make help` lists them.
# `make up` never rebuilds: Compose builds an image only if it does not exist yet.
# Run `make build` (or `make rebuild`) after changing code or dependencies.

COMPOSE ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help up start build rebuild down stop restart logs ps shell psql backup reset test lint

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start the stack in the background, reusing built images (builds only if missing)
	$(COMPOSE) up -d
	@echo "web: http://127.0.0.1:3000   api: http://127.0.0.1:8000"

start: up ## Alias for up

build: ## Build the images (uses the layer cache)
	$(COMPOSE) build

rebuild: ## Rebuild the images and restart the stack
	$(COMPOSE) up -d --build

down: ## Stop and remove the containers; data is kept
	$(COMPOSE) down

stop: ## Stop the containers without removing them
	$(COMPOSE) stop

restart: ## Restart the containers (after editing .env use `make up`, not this)
	$(COMPOSE) restart

logs: ## Follow the logs (make logs s=api to pick a service)
	$(COMPOSE) logs -f --tail=100 $(s)

ps: ## Show service status
	$(COMPOSE) ps

shell: ## Open a shell in the API container
	$(COMPOSE) exec api sh

psql: ## Open psql on the database
	$(COMPOSE) exec db psql -U cfo cfo

backup: ## Dump the database to backup.sql
	$(COMPOSE) exec -T db pg_dump -U cfo cfo > backup.sql
	@echo "wrote backup.sql (contains your financial data: keep it private)"

reset: ## DELETE all data (containers and the database volume)
	@printf "This deletes every ledger. Type 'yes' to continue: " && read ans && [ "$$ans" = yes ]
	$(COMPOSE) down -v

test: ## Run the Python tests
	uv run pytest -q

lint: ## Ruff, format check, strict mypy, import boundaries
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages/*/src api/src tools/check_imports.py
	uv run python tools/check_imports.py
