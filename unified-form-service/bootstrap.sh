#!/usr/bin/env bash
# =============================================================================
#  bootstrap.sh — Unified Form Service Setup & Run Script
#
#  Usage:
#    chmod +x bootstrap.sh
#    ./bootstrap.sh [MODE]
#
#  Modes:
#    local      (default) Set up virtualenv, install deps, seed, run locally
#    docker     Build and run the full stack via Docker Compose
#    test       Install deps and run the full test suite
#    ci         Non-interactive: install deps + run tests (for CI pipelines)
#    clean      Remove virtualenv, __pycache__, and Docker containers
# =============================================================================

set -euo pipefail

# ─── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

log()     { echo -e "${CYAN}${BOLD}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}${BOLD}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}${BOLD}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}${BOLD}[ERROR]${RESET} $*"; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════════${RESET}"; \
            echo -e "${BOLD}${CYAN}  $*${RESET}"; \
            echo -e "${BOLD}${CYAN}══════════════════════════════════════════════${RESET}\n"; }

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$SCRIPT_DIR"
VENV_DIR="$SERVICE_DIR/.venv"
PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"
PYTEST="${VENV_DIR}/bin/pytest"

# ─── Mode ─────────────────────────────────────────────────────────────────────
MODE="${1:-local}"

# ─── Banner ───────────────────────────────────────────────────────────────────
echo -e ""
echo -e "${BOLD}${CYAN}"
echo -e "  ╔═══════════════════════════════════════════════╗"
echo -e "  ║        Unified Form Service Bootstrap         ║"
echo -e "  ║                                               ║"
echo -e "  ║  Mode: $(printf '%-39s' "$MODE")║"
echo -e "  ╚═══════════════════════════════════════════════╝"
echo -e "${RESET}"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

check_command() {
    command -v "$1" &>/dev/null || error "'$1' is not installed. Please install it first."
}

setup_venv() {
    header "Setting Up Python Virtual Environment"
    check_command python3

    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log "Detected Python $PYTHON_VERSION"

    if [ ! -d "$VENV_DIR" ]; then
        log "Creating virtualenv at $VENV_DIR ..."
        python3 -m venv "$VENV_DIR"
        success "Virtualenv created."
    else
        success "Virtualenv already exists at $VENV_DIR"
    fi
}

install_deps() {
    header "Installing Python Dependencies"
    log "Upgrading pip..."
    "$PIP" install --upgrade pip -q
    log "Installing requirements.txt..."
    "$PIP" install -r "$SERVICE_DIR/requirements.txt" -q
    success "All dependencies installed."
}

install_dev_deps() {
    log "Installing dev/test tools (pytest, flake8, black, isort, mypy)..."
    "$PIP" install -q pytest pytest-cov flake8 black isort mypy
    success "Dev tools installed."
}

setup_env() {
    header "Environment Configuration"
    ENV_FILE="$SERVICE_DIR/.env"
    EXAMPLE_FILE="$SERVICE_DIR/.env.example"

    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$EXAMPLE_FILE" ]; then
            cp "$EXAMPLE_FILE" "$ENV_FILE"
            success ".env created from .env.example"
            warn "Please open $ENV_FILE and update MONGO_URI, JWT_SECRET, SECRET_KEY, and REDIS_URL before running."
        else
            warn ".env.example not found. Creating minimal .env..."
            cat > "$ENV_FILE" <<EOF
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=change-me-in-production
JWT_SECRET=change-me-in-production
MONGO_URI=mongodb://localhost:27017/
DB_NAME=form_builder_db
MONGO_DB_NAME=form_analyser
DATABASE_URL=mongodb://localhost:27017/form_response
REDIS_URL=redis://localhost:6379/0
AUTH_ENABLED=False
REQUIRE_AUTH=false
EOF
            success "Minimal .env created."
        fi
    else
        success ".env already exists — skipping."
    fi
}

check_mongo() {
    log "Checking MongoDB connection..."
    if "$PYTHON" -c "
from pymongo import MongoClient
import os
uri = open('$SERVICE_DIR/.env').read()
import re
match = re.search(r'MONGO_URI=(.+)', uri)
url = match.group(1).strip() if match else 'mongodb://localhost:27017/'
c = MongoClient(url, serverSelectionTimeoutMS=2000)
c.server_info()
print('ok')
" 2>/dev/null | grep -q ok; then
        success "MongoDB is reachable."
    else
        warn "MongoDB is not reachable. Make sure it's running before starting the app."
    fi
}

check_redis() {
    log "Checking Redis connection..."
    if command -v redis-cli &>/dev/null && redis-cli ping 2>/dev/null | grep -q PONG; then
        success "Redis is reachable."
    else
        warn "Redis is not reachable. Rate limiting will fall back to in-memory mode."
    fi
}

run_lint() {
    header "Code Quality Check"
    log "Running flake8..."
    "$VENV_DIR/bin/flake8" "$SERVICE_DIR" \
        --max-line-length=120 \
        --exclude="$VENV_DIR,__pycache__,static,htmlcov" \
        --count --statistics 2>&1 || warn "flake8 reported issues (non-fatal)."
    success "Lint check complete."
}

run_tests() {
    header "Running Test Suite"
    cd "$SERVICE_DIR"

    TEST_FILES=(
        "test_response_gateway.py"
        "test_rate_limiter.py"
        "test_exception_handling.py"
        "test_more_types.py"
    )

    # Only test files that exist
    EXISTING_TESTS=()
    for f in "${TEST_FILES[@]}"; do
        [ -f "$f" ] && EXISTING_TESTS+=("$f")
    done

    if [ ${#EXISTING_TESTS[@]} -eq 0 ]; then
        warn "No test files found. Skipping."
        return
    fi

    log "Running: ${EXISTING_TESTS[*]}"
    "$PYTEST" "${EXISTING_TESTS[@]}" -v --tb=short
    success "All tests passed."
}

seed_data() {
    header "Seeding Demo Data"
    cd "$SERVICE_DIR"
    if [ -f "seed_all.py" ]; then
        log "Running seed_all.py --all ..."
        "$PYTHON" seed_all.py --all
        success "Demo data seeded."
    else
        warn "seed_all.py not found. Skipping seeding."
    fi
}

run_local() {
    header "Starting Unified Form Service (Local)"
    check_mongo
    check_redis
    log "Starting app on http://localhost:5000 ..."
    cd "$SERVICE_DIR"
    exec "$PYTHON" app.py
}

# =============================================================================
# DOCKER MODE
# =============================================================================

run_docker() {
    header "Docker Compose Stack"
    check_command docker

    cd "$SERVICE_DIR"

    # Check docker compose v2 vs v1
    if docker compose version &>/dev/null 2>&1; then
        DC="docker compose"
    elif docker-compose version &>/dev/null 2>&1; then
        DC="docker-compose"
    else
        error "Neither 'docker compose' nor 'docker-compose' found."
    fi

    log "Building Docker image..."
    $DC build

    log "Starting stack (app + MongoDB + Redis)..."
    $DC up -d

    echo ""
    success "Stack is running!"
    echo -e "  ${BOLD}App:${RESET}     http://localhost:5000"
    echo -e "  ${BOLD}Health:${RESET}  http://localhost:5000/healthz"
    echo -e "  ${BOLD}MongoDB:${RESET} mongodb://localhost:27017"
    echo -e "  ${BOLD}Redis:${RESET}   redis://localhost:6379"
    echo ""

    # Wait for app to be ready then health-check
    log "Waiting for app to be ready..."
    for i in {1..15}; do
        if curl -sf http://localhost:5000/healthz &>/dev/null; then
            success "Health check passed ✓"
            curl -s http://localhost:5000/healthz | python3 -m json.tool
            break
        fi
        sleep 2
        log "Attempt $i/15..."
    done

    echo ""
    log "To seed demo data inside the container, run:"
    echo -e "  ${BOLD}$DC exec app python seed_all.py --all${RESET}"
    echo ""
    log "To tail logs:"
    echo -e "  ${BOLD}$DC logs -f${RESET}"
    echo ""
    log "To stop the stack:"
    echo -e "  ${BOLD}$DC down${RESET}"
}

# =============================================================================
# CLEAN MODE
# =============================================================================

run_clean() {
    header "Cleaning Up"

    log "Removing Python cache files..."
    find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$SCRIPT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
    find "$SCRIPT_DIR" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find "$SCRIPT_DIR" -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
    find "$SCRIPT_DIR" -type f -name ".coverage" -delete 2>/dev/null || true
    success "Cache files removed."

    if [ -d "$VENV_DIR" ]; then
        log "Removing virtual environment..."
        rm -rf "$VENV_DIR"
        success "Virtualenv removed."
    fi

    if [ -f "$SERVICE_DIR/docker-compose.yml" ]; then
        if docker compose version &>/dev/null 2>&1; then
            log "Stopping Docker containers..."
            cd "$SERVICE_DIR" && docker compose down 2>/dev/null || true
            success "Docker containers stopped."
        fi
    fi

    success "Cleanup complete."
}

# =============================================================================
# MODE DISPATCH
# =============================================================================

case "$MODE" in

  local)
    setup_venv
    install_deps
    setup_env
    run_tests
    seed_data
    run_local
    ;;

  docker)
    setup_env
    run_docker
    ;;

  test)
    setup_venv
    install_deps
    install_dev_deps
    setup_env
    run_lint
    run_tests
    ;;

  ci)
    # Non-interactive: no venv creation, assumes python3 is on PATH
    header "CI Mode"
    log "Installing dependencies..."
    pip install -r "$SERVICE_DIR/requirements.txt" -q
    pip install -q pytest pytest-cov flake8
    setup_env
    cd "$SERVICE_DIR"
    TEST_FILES=("test_response_gateway.py" "test_rate_limiter.py" "test_exception_handling.py" "test_more_types.py")
    EXISTING=()
    for f in "${TEST_FILES[@]}"; do [ -f "$f" ] && EXISTING+=("$f"); done
    pytest "${EXISTING[@]}" -v --tb=short
    success "CI run complete."
    ;;

  clean)
    run_clean
    ;;

  *)
    echo ""
    echo -e "${BOLD}Usage:${RESET} ./bootstrap.sh [MODE]"
    echo ""
    echo -e "  ${CYAN}local${RESET}    (default) Install deps, seed data, run app locally"
    echo -e "  ${CYAN}docker${RESET}   Build and run full stack via Docker Compose"
    echo -e "  ${CYAN}test${RESET}     Install deps + run lint + full test suite"
    echo -e "  ${CYAN}ci${RESET}       Non-interactive mode for CI/CD pipelines"
    echo -e "  ${CYAN}clean${RESET}    Remove virtualenv, caches, and Docker containers"
    echo ""
    exit 1
    ;;

esac
