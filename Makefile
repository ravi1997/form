.PHONY: help install dev test test-fast test-unit test-security lint format type-check audit check build up down restart logs shell rebuild docker-build docker-clean clean

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip
COMPOSE ?= docker compose

help:           ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:        ## Install runtime and test/dev dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-test.txt
	$(PIP) install ruff mypy pip-audit

dev:            ## Run the application locally with Flask development server
	$(PYTHON) -m flask --app app.wsgi:app run --reload --port 8000

test:           ## Run pytest with coverage
	$(PYTHON) -m pytest --cov=app --cov-report=term --cov-report=html -q

test-fast:      ## Run tests without coverage (faster)
	$(PYTHON) -m pytest -q

test-unit:      ## Run unit tests only
	$(PYTHON) -m pytest -m unit -q

test-security:  ## Run security-focused tests
	$(PYTHON) -m pytest -m security -q

lint:           ## Run ruff linter
	ruff check .

format:         ## Auto-fix formatting and linting with ruff
	ruff format .
	ruff check --fix .

type-check:     ## Run mypy type checks
	mypy app tests

audit:          ## Scan runtime dependencies for known vulnerabilities
	pip-audit -r requirements.txt

check: lint type-check test  ## Run lint + type-check + tests (full CI check)

build:          ## Build the Docker image
	$(COMPOSE) build

up:             ## Start services with docker compose
	$(COMPOSE) up -d --build

down:           ## Stop and remove docker compose containers and volumes
	$(COMPOSE) down -v --remove-orphans

restart:        ## Restart the compose stack
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up -d --build

logs:           ## Follow application logs from docker compose
	$(COMPOSE) logs -f app worker

shell:          ## Open a shell in the app container
	$(COMPOSE) exec app sh

rebuild:        ## Rebuild the compose stack from scratch
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

docker-build:   build
docker-up:      up
docker-down:    down
docker-logs:    logs
docker-clean:   ## Remove compose resources and local images
	$(COMPOSE) down -v --remove-orphans
	docker image rm form-service:latest 2>/dev/null || true

clean:          ## Remove build artifacts, caches, and coverage reports
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
	rm -rf dist build *.egg-info
