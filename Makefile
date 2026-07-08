.PHONY: install test lint type-check format audit docker-build docker-up docker-down clean help

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip

help:           ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:        ## Install runtime and test/dev dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-test.txt
	$(PIP) install ruff mypy pip-audit

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

docker-build:   ## Build the Docker image
	docker build -t form-service:latest .

docker-up:      ## Start services with docker compose
	docker compose up --build -d

docker-down:    ## Stop and remove docker compose containers
	docker compose down -v

docker-logs:    ## Follow application logs from docker compose
	docker compose logs -f app

clean:          ## Remove build artifacts, caches, and coverage reports
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
	rm -rf dist build *.egg-info
