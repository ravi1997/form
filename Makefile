.PHONY: help install install-runtime install-test dev serve worker beat test test-fast test-unit test-integration test-security test-performance test-last-failed test-parallel lint format type-check audit check build up down restart logs shell rebuild docker-build docker-up docker-down docker-logs docker-clean clean benchmark-conditions init-rate-limits setup-condition-indexes verify-audit-query-plans docker-env docker-config docker-pull docker-rebuild docker-clean-images docker-clean-volumes docker-ps docker-status docker-status-all docker-bootstrap docker-start docker-start-all docker-stop docker-stop-all docker-restart docker-reset docker-rebuild-clean docker-follow docker-logs-all docker-health docker-health-all docker-shell-app docker-shell-worker docker-shell-beat docker-shell docker-shell-all docker-log-app docker-log-worker docker-log-mongo docker-log-redis docker-dev docker-prod docker-dev-up docker-prod-up docker-up-dev docker-up-prod docker-clean-all

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest
COMPOSE ?= docker compose
MONGOSH ?= mongosh
MONGO_URI ?= mongodb://localhost:27017/form_prod
DOCKER_ENV_FILE ?= .env
DOCKER_ENV_TEMPLATE ?= .env.example

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
help:                     ## Show this help message
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z0-9_.-]+:.*?## / {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:                  ## Install runtime and test/dev dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-test.txt
	$(PIP) install ruff mypy pip-audit

install-runtime:          ## Install only runtime dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install-test:             ## Install only test/dev dependencies
	$(PIP) install -r requirements-test.txt
	$(PIP) install ruff mypy pip-audit

# -----------------------------------------------------------------------------
# Docker setup
# -----------------------------------------------------------------------------
docker-env:               ## Create .env from .env.example if missing
	@test -f $(DOCKER_ENV_FILE) || cp $(DOCKER_ENV_TEMPLATE) $(DOCKER_ENV_FILE)

docker-config:            ## Render the final compose configuration
	$(COMPOSE) config

docker-pull:              ## Pull external Docker images used by the stack
	$(COMPOSE) pull

docker-rebuild:           ## Rebuild images without cache
	$(COMPOSE) build --no-cache

docker-clean-images:      ## Remove the local service image
	docker image rm form-service:latest 2>/dev/null || true

docker-clean-volumes:     ## Remove compose resources and volumes only
	$(COMPOSE) down -v --remove-orphans

# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------
dev:                      ## Run the application locally with Flask development server
	$(PYTHON) -m flask --app app.wsgi:app run --reload --port 8000

serve:                    ## Run the production WSGI app locally with Gunicorn
	$(PYTHON) -m gunicorn --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 60 --graceful-timeout 30 --access-logfile - --error-logfile - app.wsgi:app

worker:                   ## Run the Celery worker locally
	$(PYTHON) -m celery -A app.celery.worker worker --loglevel=info

beat:                     ## Run the Celery beat scheduler locally
	$(PYTHON) -m celery -A app.celery.worker beat --loglevel=info

test:                     ## Run pytest with coverage
	$(PYTEST) --cov=app --cov-report=term --cov-report=html -q

test-fast:                ## Run tests without coverage (faster)
	$(PYTEST) -q

test-unit:                ## Run unit tests only
	$(PYTEST) -m unit -q

test-integration:         ## Run integration tests only
	$(PYTEST) -m integration -q

test-security:            ## Run security-focused tests
	$(PYTEST) -m security -q

test-performance:         ## Run performance tests only
	$(PYTEST) -m performance -q

test-last-failed:         ## Run the last failed tests
	$(PYTEST) --lf -q

test-parallel:            ## Run tests in parallel with xdist
	$(PYTEST) -n auto -q

lint:                     ## Run ruff linter
	ruff check .

format:                   ## Auto-fix formatting and linting with ruff
	ruff format .
	ruff check --fix .

type-check:               ## Run mypy type checks
	mypy app tests

audit:                    ## Scan runtime dependencies for known vulnerabilities
	pip-audit -r requirements.txt

check: lint type-check test  ## Run lint + type-check + tests (full CI check)

# -----------------------------------------------------------------------------
# Docker / Compose core
# -----------------------------------------------------------------------------
build:                    ## Build the Docker image
	$(COMPOSE) build

up:                       ## Start services with docker compose
	$(COMPOSE) up -d --build

down:                     ## Stop and remove docker compose containers and volumes
	$(COMPOSE) down -v --remove-orphans

restart:                  ## Restart the compose stack
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up -d --build

logs:                     ## Follow application logs from docker compose
	$(COMPOSE) logs -f app worker

shell:                    ## Open a shell in the app container
	$(COMPOSE) exec app sh

rebuild:                  ## Rebuild the compose stack from scratch
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

docker-ps:                ## Show compose service status
	$(COMPOSE) ps

docker-status:            ## Show compose status and recent logs
	$(COMPOSE) ps
	$(COMPOSE) logs --no-color --tail=50

docker-bootstrap:         ## Create .env, validate compose, build, and start the stack
	$(MAKE) docker-env
	$(MAKE) docker-config
	$(COMPOSE) up -d --build

docker-start:             ## Start the full stack after ensuring .env exists
	$(MAKE) docker-env
	$(COMPOSE) up -d --build

docker-start-all:         ## Start the full stack and then show status
	$(MAKE) docker-start
	$(MAKE) docker-status-all

docker-dev:               ## Start the local development stack with the override file
	$(MAKE) docker-env
	$(COMPOSE) -f docker-compose.yml -f docker-compose.override.yml up -d --build

docker-prod:              ## Start the production-style stack with the base compose file
	$(MAKE) docker-env
	$(COMPOSE) -f docker-compose.yml up -d --build

docker-dev-up:            ## Alias for docker-dev
	$(MAKE) docker-dev

docker-prod-up:           ## Alias for docker-prod
	$(MAKE) docker-prod

docker-up-dev:            ## Start the development stack and show status
	$(MAKE) docker-dev
	$(MAKE) docker-status-all

docker-up-prod:           ## Start the production stack and show status
	$(MAKE) docker-prod
	$(MAKE) docker-status-all

docker-stop:              ## Stop the full stack but keep volumes
	$(COMPOSE) stop

docker-stop-all:          ## Stop the full stack and show service status
	$(MAKE) docker-stop
	$(MAKE) docker-ps

docker-restart:           ## Restart the full stack
	$(COMPOSE) restart

docker-rebuild-clean:     ## Rebuild from scratch and restart the stack
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --build
	$(MAKE) docker-status-all

docker-reset:             ## Recreate the stack from scratch and preserve .env
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up -d --build

docker-follow:            ## Stream app and worker logs
	$(COMPOSE) logs -f app worker

docker-logs-all:          ## Stream logs for all compose services
	$(COMPOSE) logs -f

docker-status-all:        ## Show status, recent logs, and app health
	$(COMPOSE) ps
	$(COMPOSE) logs --no-color --tail=20
	-$(PYTHON) -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5); print('app healthy')"

docker-health:            ## Check compose service health and app readiness
	$(COMPOSE) ps
	-$(PYTHON) -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5); print('app healthy')"

docker-health-all:        ## Check health and show status in one command
	$(MAKE) docker-health
	$(MAKE) docker-status-all

docker-shell-app:         ## Open a shell in the app container
	$(COMPOSE) exec app sh

docker-shell-worker:      ## Open a shell in the worker container
	$(COMPOSE) exec worker sh

docker-shell-beat:        ## Open a shell in the beat container
	$(COMPOSE) exec beat sh

docker-shell:             ## Open a shell in the app container
	$(MAKE) docker-shell-app

docker-shell-all:         ## Show the shell target options
	@printf "%s\n" "Use docker-shell-app, docker-shell-worker, or docker-shell-beat"

docker-log-app:           ## Show app container logs
	$(COMPOSE) logs -f app

docker-log-worker:        ## Show worker container logs
	$(COMPOSE) logs -f worker

docker-log-mongo:         ## Show MongoDB container logs
	$(COMPOSE) logs -f mongo

docker-log-redis:         ## Show Redis container logs
	$(COMPOSE) logs -f redis

# -----------------------------------------------------------------------------
# Repo scripts
# -----------------------------------------------------------------------------
docker-build:             build
docker-up:                up
docker-down:              down
docker-logs:              logs

benchmark-conditions:     ## Benchmark condition evaluation performance
	$(PYTHON) scripts/benchmark_conditions.py

init-rate-limits:         ## Initialize default rate limit configurations
	$(PYTHON) scripts/init_rate_limits.py

setup-condition-indexes:  ## Ensure condition-related MongoDB indexes exist
	$(PYTHON) scripts/setup_condition_indexes.py

verify-audit-query-plans: ## Inspect explain plans for audit queries
	$(MONGOSH) "$(MONGO_URI)" scripts/verify_audit_query_plans.js

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
docker-clean:             ## Remove compose resources and local images
	$(COMPOSE) down -v --remove-orphans
	docker image rm form-service:latest 2>/dev/null || true

docker-clean-all:         ## Remove compose resources, local images, and the generated .env
	$(COMPOSE) down -v --remove-orphans --rmi local
	docker image rm form-service:latest 2>/dev/null || true
	rm -f $(DOCKER_ENV_FILE)

clean:                    ## Remove build artifacts, caches, and coverage reports
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
	rm -rf dist build *.egg-info
