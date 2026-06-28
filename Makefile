# =============================================================================
#  unified-form-service — Makefile
#  Usage: make <target>
# =============================================================================

PYTHON       := python3
VENV_DIR     := venv
PIP          := $(VENV_DIR)/bin/pip
PYTEST       := $(VENV_DIR)/bin/pytest
FLASK_APP    := unified-form-service/app.py
SERVICE_DIR  := unified-form-service
BUILDER_DIR  := form-builder

# Detect OS for open-browser command
UNAME := $(shell uname)
ifeq ($(UNAME), Darwin)
    OPEN := open
else
    OPEN := xdg-open
endif

.DEFAULT_GOAL := help

# ─── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "  ╔════════════════════════════════════════╗"
	@echo "  ║    unified-form-service  —  Makefile   ║"
	@echo "  ╚════════════════════════════════════════╝"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ─── Environment Setup ─────────────────────────────────────────────────────────
.PHONY: venv
venv: ## Create Python virtual environment
	@echo "→ Creating virtual environment..."
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "✓ Virtualenv created at $(VENV_DIR)/"

.PHONY: install
install: venv ## Install all Python dependencies
	@echo "→ Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r $(SERVICE_DIR)/requirements.txt
	@echo "✓ Dependencies installed."

.PHONY: install-dev
install-dev: install ## Install dependencies + dev/test extras
	@echo "→ Installing dev dependencies..."
	$(PIP) install pytest pytest-cov flake8 black isort mypy
	@echo "✓ Dev dependencies installed."

.PHONY: env
env: ## Copy .env.example to .env (only if .env doesn't exist)
	@if [ ! -f $(SERVICE_DIR)/.env ]; then \
		cp $(SERVICE_DIR)/.env.example $(SERVICE_DIR)/.env; \
		echo "✓ .env created from .env.example — please fill in your values."; \
	else \
		echo "! .env already exists, skipping."; \
	fi

# ─── Running the App ───────────────────────────────────────────────────────────
.PHONY: run
run: ## Start the unified Flask application
	@echo "→ Starting unified-form-service on http://localhost:5000 ..."
	cd $(SERVICE_DIR) && $(PYTHON) app.py

.PHONY: run-dev
run-dev: ## Start with hot-reload (Flask debug mode)
	@echo "→ Starting in development/debug mode..."
	cd $(SERVICE_DIR) && FLASK_ENV=development FLASK_DEBUG=1 $(PYTHON) app.py

# ─── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker-build
docker-build: ## Build the Docker image
	@echo "→ Building Docker image..."
	docker build -t unified-form-service:latest $(SERVICE_DIR)/

.PHONY: docker-up
docker-up: ## Start all services via Docker Compose (app + MongoDB + Redis)
	@echo "→ Starting Docker Compose stack..."
	docker compose -f $(SERVICE_DIR)/docker-compose.yml up --build -d
	@echo "✓ Stack running. App → http://localhost:5000"

.PHONY: docker-down
docker-down: ## Stop and remove Docker Compose containers
	@echo "→ Stopping Docker Compose stack..."
	docker compose -f $(SERVICE_DIR)/docker-compose.yml down

.PHONY: docker-logs
docker-logs: ## Tail logs from Docker Compose stack
	docker compose -f $(SERVICE_DIR)/docker-compose.yml logs -f

.PHONY: docker-restart
docker-restart: docker-down docker-up ## Restart all Docker containers

# ─── Testing ───────────────────────────────────────────────────────────────────
.PHONY: test
test: ## Run all tests (builder + unified service)
	@echo "→ Running unified-form-service tests..."
	cd $(SERVICE_DIR) && $(PYTEST) \
		test_response_gateway.py \
		test_rate_limiter.py \
		test_exception_handling.py \
		test_more_types.py \
		-v
	@echo ""
	@echo "→ Running form-builder tests..."
	cd $(BUILDER_DIR) && $(PYTEST) -v

.PHONY: test-service
test-service: ## Run only unified-service tests
	cd $(SERVICE_DIR) && $(PYTEST) \
		test_response_gateway.py \
		test_rate_limiter.py \
		test_exception_handling.py \
		test_more_types.py \
		-v

.PHONY: test-builder
test-builder: ## Run only form-builder tests
	cd $(BUILDER_DIR) && $(PYTEST) -v

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	@echo "→ Running tests with coverage..."
	cd $(SERVICE_DIR) && $(PYTEST) \
		test_response_gateway.py test_rate_limiter.py \
		test_exception_handling.py test_more_types.py \
		--cov=. --cov-report=term-missing --cov-report=html
	@echo "✓ Coverage report at $(SERVICE_DIR)/htmlcov/index.html"

# ─── Database Seeding ──────────────────────────────────────────────────────────
.PHONY: seed
seed: ## Seed all data (builder + analyser)
	@echo "→ Seeding all demo data..."
	cd $(SERVICE_DIR) && $(PYTHON) seed_all.py --all

.PHONY: seed-builder
seed-builder: ## Seed only form builder data (themes, forms, users)
	@echo "→ Seeding builder data..."
	cd $(SERVICE_DIR) && $(PYTHON) seed_all.py --builder

.PHONY: seed-analyser
seed-analyser: ## Seed only analyser demo responses (200 fake responses)
	@echo "→ Seeding analyser demo responses..."
	cd $(SERVICE_DIR) && $(PYTHON) seed_all.py --analyser

# ─── Code Quality ──────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Run flake8 linter on unified-form-service
	@echo "→ Running flake8..."
	$(VENV_DIR)/bin/flake8 $(SERVICE_DIR) \
		--max-line-length=120 \
		--exclude=$(SERVICE_DIR)/venv,$(SERVICE_DIR)/__pycache__,$(SERVICE_DIR)/static
	@echo "✓ Linting complete."

.PHONY: format
format: ## Auto-format code with black + isort
	@echo "→ Running black formatter..."
	$(VENV_DIR)/bin/black $(SERVICE_DIR) --line-length=120 \
		--exclude="$(SERVICE_DIR)/venv|$(SERVICE_DIR)/static"
	@echo "→ Running isort..."
	$(VENV_DIR)/bin/isort $(SERVICE_DIR) --profile=black
	@echo "✓ Formatting complete."

.PHONY: typecheck
typecheck: ## Run mypy type checker
	@echo "→ Running mypy..."
	$(VENV_DIR)/bin/mypy $(SERVICE_DIR) \
		--ignore-missing-imports \
		--exclude '$(SERVICE_DIR)/venv'
	@echo "✓ Type check complete."

# ─── Health Check ──────────────────────────────────────────────────────────────
.PHONY: health
health: ## Hit the /healthz endpoint to verify service is running
	@echo "→ Checking service health..."
	@curl -sf http://localhost:5000/healthz | $(PYTHON) -m json.tool \
		|| echo "✗ Service not reachable at http://localhost:5000"

# ─── Git ───────────────────────────────────────────────────────────────────────
.PHONY: log
log: ## Show recent git log
	git log --oneline -20

.PHONY: status
status: ## Show git status
	git status

# ─── Cleanup ───────────────────────────────────────────────────────────────────
.PHONY: clean
clean: ## Remove Python cache files and build artifacts
	@echo "→ Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
	find . -type f -name "*.pyo" -delete 2>/dev/null; true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null; true
	@echo "✓ Cleanup done."

.PHONY: clean-venv
clean-venv: ## Remove the virtual environment
	@echo "→ Removing virtual environment..."
	rm -rf $(VENV_DIR)
	@echo "✓ Virtualenv removed."

# ─── All-in-one ────────────────────────────────────────────────────────────────
.PHONY: setup
setup: install env ## Full first-time setup (venv + deps + .env)
	@echo ""
	@echo "✓ Setup complete! Next steps:"
	@echo "  1. Edit $(SERVICE_DIR)/.env with your MongoDB URI, JWT secret, etc."
	@echo "  2. make run         → Start the app"
	@echo "  3. make seed        → Seed demo data"
	@echo "  4. make test        → Run tests"
	@echo "  5. make docker-up   → Run via Docker"
	@echo ""
