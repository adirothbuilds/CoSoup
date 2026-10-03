SHELL := /bin/bash
.DEFAULT_GOAL := help
PYTHON ?= .venv/bin/python
PYTHON_BOOTSTRAP ?= python3.12
NPM ?= npm
PRIVATE_ROOT ?= /srv/stock-scanner
COMPOSE_ENV ?= $(PRIVATE_ROOT)/compose.env
COMPOSE_PROJECT ?= stock-scanner
TIMEZONE ?= UTC
SERVICE ?=
BUILD_FLAGS ?=
COMPOSE = docker compose --project-name "$(COMPOSE_PROJECT)" --env-file "$(COMPOSE_ENV)" -f apps/server/deploy/compose.yaml -f apps/web/deploy/compose.yaml

.PHONY: help install typecheck build web-dev ios-start ios-export ios-build test test-python test-client test-e2e docker-build init migrate deploy up down restart status logs config seed-schedules codex-build codex-start
help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; print "Stock Scanner commands:"} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
install: ## Install pinned Python and JS dependencies for development
	$(PYTHON_BOOTSTRAP) -m venv .venv
	$(PYTHON) -m pip install -r apps/server/requirements.txt
	$(NPM) ci --ignore-scripts --no-audit --no-fund
typecheck: ## Check web, iOS and shared TypeScript contracts
	$(NPM) run typecheck
build: ## Build the production React web application
	$(NPM) run build
web-dev: ## Run web development server with a same-origin API proxy
	$(NPM) run dev -w @stock-scanner/web
ios-start: ## Start Expo on the local LAN; does not start the home scheduler
	$(NPM) run start -w @stock-scanner/mobile
ios-export: ## Bundle iOS JS/assets locally without signing or a paid service
	EXPO_NO_TELEMETRY=1 $(NPM) run mobile:export
ios-build: ## Build/run the native iOS app locally on a Mac with Xcode
	$(NPM) run ios -w @stock-scanner/mobile
test-python: ## Run scanner and server unit tests
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m unittest discover -s apps/server/tests -v
test-client: ## Test shared contracts and browser transport
	$(NPM) test
test: typecheck test-python test-client ## Run all unit and contract checks
test-e2e: ## Run functional browser tests against a private test API
	$(NPM) run test:e2e
docker-build: ## Build server and web images; Codex is a separate optional target
	$(COMPOSE) build $(BUILD_FLAGS) api web
init: ## Initialize private host files outside Git without overwriting existing values
	$(PYTHON) -m apps.server init --root "$(PRIVATE_ROOT)" --timezone "$(TIMEZONE)"
migrate: ## Apply explicit schema bootstrap/role grants using the admin service
	$(COMPOSE) up -d postgres
	$(COMPOSE) run --rm migrate
deploy: docker-build ## Build, migrate, then start the persistent Docker services
	$(MAKE) migrate COMPOSE_ENV="$(COMPOSE_ENV)" COMPOSE_PROJECT="$(COMPOSE_PROJECT)"
	$(COMPOSE) up -d --no-build --wait
up: ## Start previously built services and wait for health
	$(COMPOSE) up -d --no-build --wait
down: ## Stop services while retaining private data (no volume deletion)
	$(COMPOSE) down
restart: ## Recreate services to apply changed private configuration
	$(COMPOSE) up -d --no-build --force-recreate $(SERVICE)
status: ## Show container status
	$(COMPOSE) ps
logs: ## Follow bounded container logs; optionally SERVICE=scheduler
	$(COMPOSE) logs --tail 100 --follow $(SERVICE)
config: ## Validate Compose without printing interpolated configuration
	$(COMPOSE) config --quiet
seed-schedules: ## Prepare disabled daily/weekly/archive/backup schedules
	$(COMPOSE) run --rm migrate seed-schedules
codex-build: ## Build the optional dedicated Codex CLI image
	$(COMPOSE) --profile codex build codex-worker
codex-start: ## Start Codex after private auth and host sandbox verification
	$(COMPOSE) --profile codex up -d --no-build codex-worker
