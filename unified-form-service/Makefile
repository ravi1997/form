# =============================================================================
#  unified-form-service — Makefile
#  Run from within the unified-form-service/ directory
#  Usage: make <target>
# =============================================================================

PYTHON       := python3
VENV_DIR     := ../venv
PIP          := $(VENV_DIR)/bin/pip
PYTEST       := $(VENV_DIR)/bin/pytest

# Detect active venv python if available
PYTHON_BIN   := $(shell which python3)

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
venv: ## Create Python virtual environment (one level up)
	@echo "→ Creating virtual environment at $(VENV_DIR)..."
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "✓ Virtualenv created."

.PHONY: install
install: ## Install all Python dependencies from requirements.txt
	@echo "→ Installing dependencies..."
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	@echo "✓ Dependencies installed."

.PHONY: install-dev
install-dev: install ## Install dependencies + dev/test extras (pytest, black, flake8)
	@echo "→ Installing dev tools..."
	$(PYTHON) -m pip install pytest pytest-cov flake8 black isort mypy
	@echo "✓ Dev dependencies installed."

.PHONY: env
env: ## Copy .env.example → .env (only if .env doesn't exist)
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✓ .env created — please fill in your values."; \
	else \
		echo "! .env already exists, skipping."; \
	fi

# ─── Running the App ───────────────────────────────────────────────────────────
.PHONY: run
run: ## Start the unified Flask application (http://localhost:5000)
	@echo "→ Starting unified-form-service on http://localhost:5000 ..."
	$(PYTHON) app.py

.PHONY: run-dev
run-dev: ## Start with debug/hot-reload mode
	@echo "→ Starting in development mode..."
	FLASK_ENV=development FLASK_DEBUG=1 $(PYTHON) app.py

# ─── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker-build
docker-build: ## Build the Docker image
	@echo "→ Building Docker image..."
	docker build -t unified-form-service:latest .

.PHONY: docker-up
docker-up: ## Start all services (app + MongoDB + Redis) via Docker Compose
	@echo "→ Starting Docker Compose stack..."
	docker compose up --build -d
	@echo "✓ Stack running → http://localhost:5000"

.PHONY: docker-down
docker-down: ## Stop and remove all Docker Compose containers
	@echo "→ Stopping Docker Compose stack..."
	docker compose down

.PHONY: docker-logs
docker-logs: ## Tail logs from running Docker Compose stack
	docker compose logs -f

.PHONY: docker-restart
docker-restart: docker-down docker-up ## Restart the full Docker stack

# ─── Testing ───────────────────────────────────────────────────────────────────
.PHONY: test
test: ## Run all unified-service tests
	@echo "→ Running all tests..."
	$(PYTHON) -m pytest \
		test_response_gateway.py \
		test_rate_limiter.py \
		test_exception_handling.py \
		test_more_types.py \
		-v

.PHONY: test-cov
test-cov: ## Run tests with HTML coverage report
	@echo "→ Running tests with coverage..."
	$(PYTHON) -m pytest \
		test_response_gateway.py test_rate_limiter.py \
		test_exception_handling.py test_more_types.py \
		--cov=. --cov-report=term-missing --cov-report=html
	@echo "✓ Coverage report at htmlcov/index.html"

.PHONY: test-watch
test-watch: ## Run tests in watch mode (requires pytest-watch)
	$(PYTHON) -m pytest_watch -- \
		test_response_gateway.py test_rate_limiter.py \
		test_exception_handling.py test_more_types.py -v

# ─── Database Seeding ──────────────────────────────────────────────────────────
.PHONY: seed
seed: ## Seed all demo data (builder themes/forms/users + analyser responses)
	@echo "→ Seeding all demo data..."
	$(PYTHON) seed_all.py --all

.PHONY: seed-builder
seed-builder: ## Seed only form builder data (themes, forms, users, orgs)
	@echo "→ Seeding builder data..."
	$(PYTHON) seed_all.py --builder

.PHONY: seed-analyser
seed-analyser: ## Seed only analyser demo responses (200 realistic responses)
	@echo "→ Seeding analyser demo responses..."
	$(PYTHON) seed_all.py --analyser

# ─── Code Quality ──────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Lint code with flake8
	@echo "→ Running flake8..."
	$(PYTHON) -m flake8 . \
		--max-line-length=120 \
		--exclude=venv,__pycache__,static,htmlcov
	@echo "✓ Linting complete."

.PHONY: format
format: ## Auto-format code with black + isort
	@echo "→ Formatting with black..."
	$(PYTHON) -m black . --line-length=120 --exclude="venv|static|htmlcov"
	@echo "→ Sorting imports with isort..."
	$(PYTHON) -m isort . --profile=black
	@echo "✓ Formatting complete."

.PHONY: typecheck
typecheck: ## Run mypy static type checker
	@echo "→ Running mypy..."
	$(PYTHON) -m mypy . --ignore-missing-imports --exclude venv
	@echo "✓ Type check complete."

# ─── Health Check ──────────────────────────────────────────────────────────────
.PHONY: health
health: ## Ping /healthz to verify the service is running
	@echo "→ Checking health at http://localhost:5000/healthz ..."
	@curl -sf http://localhost:5000/healthz | $(PYTHON) -m json.tool \
		|| echo "✗ Service not reachable."

# ─── Cleanup ───────────────────────────────────────────────────────────────────
.PHONY: clean
clean: ## Remove Python caches, test artefacts, and coverage reports
	@echo "→ Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name ".coverage" -delete 2>/dev/null; true
	@echo "✓ Cleanup done."

# ─── All-in-one ────────────────────────────────────────────────────────────────
.PHONY: setup
setup: install env ## First-time setup: install deps and create .env
	@echo ""
	@echo "✓ Setup complete! Next steps:"
	@echo "  1. Edit .env with your MongoDB URI, JWT secret, Redis URL, etc."
	@echo "  2. make run          → Start the app locally"
	@echo "  3. make seed         → Seed demo data"
	@echo "  4. make test         → Run tests"
	@echo "  5. make docker-up    → Run full stack via Docker"
	@echo ""
