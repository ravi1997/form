# Contributing to Unified Form Service

Thank you for your interest in contributing! This guide covers everything you need to get started — from environment setup to submitting a pull request.

---

## Table of Contents

1. [Setting Up the Dev Environment](#1-setting-up-the-dev-environment)
2. [Coding Standards](#2-coding-standards)
3. [Branch Naming Convention](#3-branch-naming-convention)
4. [Commit Message Convention](#4-commit-message-convention)
5. [Writing and Running Tests](#5-writing-and-running-tests)
6. [Pull Request Checklist](#6-pull-request-checklist)
7. [Reporting Bugs](#7-reporting-bugs)

---

## 1. Setting Up the Dev Environment

### Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Python | 3.10+ |
| MongoDB | 6.0+ |
| Redis | 7.0+ (optional — falls back to in-memory) |
| Docker & Docker Compose | 24.0+ (for containerised setup) |

---

### Option A — Local (virtualenv)

```bash
# 1. Clone the repository
git clone <repo-url>
cd form/unified-form-service

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install dev-only tools
pip install pytest pytest-cov flake8 mypy black

# 5. Copy the environment template and fill in your values
cp .env.example .env

# 6. Start the Flask app
python app.py
```

The app will be available at `http://localhost:5000` by default.

---

### Option B — Docker Compose

```bash
cd form/unified-form-service

# Build and start all services (app + MongoDB + Redis)
docker compose up --build

# Stop all services
docker compose down
```

---

### Environment Variables

All required environment variables are documented in
[`unified-form-service/.env.example`](unified-form-service/.env.example).
Copy it to `.env` and set values appropriate for your local setup.
Critical variables:

| Variable | Purpose |
|----------|---------|
| `MONGO_URI` | Primary MongoDB connection string |
| `DB_NAME` | Form Builder database name |
| `MONGO_DB_NAME` | Form Analyser database name |
| `DATABASE_URL` | Response Gateway MongoDB URI |
| `SECRET_KEY` | Flask session / JWT signing secret |
| `FLASK_ENV` | `development` / `testing` / `production` |

---

### Seeding Demo Data

```bash
# Seed all services (builder + analyser)
python seed_all.py

# Seed builder data only
python seed.py

# Seed analyser demo data only
python seed_demo_data.py
```

---

## 2. Coding Standards

All contributions **must** comply with the rules below before a PR can be merged.

### PEP 8

All Python code must comply with [PEP 8](https://peps.python.org/pep-0008/). Use `flake8` to check:

```bash
flake8 unified-form-service/ --max-line-length=100
```

Use `black` to auto-format:

```bash
black unified-form-service/ --line-length 100
```

> **Line length**: 100 characters maximum (relaxed from PEP 8's 79 for readability in Flask route files).

---

### Type Hints

All function signatures must include type hints as per [PEP 484](https://peps.python.org/pep-0484/). Use `mypy` to validate:

```bash
mypy unified-form-service/ --ignore-missing-imports
```

**Good ✅**
```python
def get_form(form_id: str) -> dict | None:
    ...
```

**Bad ❌**
```python
def get_form(form_id):
    ...
```

---

### Docstrings

All public functions, classes, and modules **must** have docstrings following the [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings):

```python
def validate_response(payload: dict, form_schema: dict) -> tuple[bool, list[str]]:
    """Validate a form response payload against its schema.

    Args:
        payload: The raw response dictionary submitted by the user.
        form_schema: The form definition containing field types and rules.

    Returns:
        A tuple of (is_valid, list_of_error_messages). The error list is
        empty when is_valid is True.

    Raises:
        ValueError: If form_schema is missing required top-level keys.
    """
    ...
```

---

### General Guidelines

- **No bare `except`** — always catch specific exceptions.
- **No `print()` in application code** — use the structured JSON logger (`json_logger.py`).
- **No hard-coded secrets** — use environment variables via `config.py`.
- **Avoid mutable default arguments** — e.g., use `def f(items: list | None = None)` instead of `def f(items=[])`.
- **Import order**: standard library → third-party → local modules (enforced by `isort`).

---

## 3. Branch Naming Convention

Branches must be prefixed with one of the following types followed by a short, lowercase, hyphen-separated description:

| Prefix | When to use |
|--------|------------|
| `feat/` | New feature or capability |
| `fix/` | Bug fix |
| `refactor/` | Code restructuring with no behaviour change |
| `chore/` | Maintenance tasks (deps, CI, gitignore, etc.) |
| `docs/` | Documentation-only changes |
| `test/` | Adding or fixing tests |
| `perf/` | Performance improvements |

### Examples

```
feat/unified-rate-limiter
fix/jwt-expiry-edge-case
refactor/mongo-connection-sharing
chore/update-gitignore-pycache
docs/add-contributing-guide
test/response-gateway-edge-cases
```

> Branch names should be **lowercase**, use **hyphens** (not underscores), and be **concise** (≤50 characters after the prefix).

---

## 4. Commit Message Convention

This project uses the **Conventional Commits** specification
([conventionalcommits.org](https://www.conventionalcommits.org/)).

### Format

```
<type>(<optional scope>): <short description>

[optional body]

[optional footer(s)]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | A new feature (triggers a minor version bump) |
| `fix` | A bug fix (triggers a patch version bump) |
| `refactor` | A code change that neither fixes a bug nor adds a feature |
| `perf` | A code change that improves performance |
| `chore` | Changes to build process, auxiliary tools, or config files |
| `docs` | Documentation-only changes |
| `test` | Adding missing tests or correcting existing tests |
| `style` | Formatting, whitespace, missing semicolons — no logic change |
| `ci` | Changes to CI/CD configuration files and scripts |

### Scopes (common for this project)

`auth`, `builder`, `analyser`, `gateway`, `database`, `logging`,
`rate-limiter`, `validation`, `config`, `seed`, `docker`, `error-handling`

### Examples

```
feat(auth): unify JWT and API-key validation across services

Merges the previously separate auth modules from builder and gateway
into a single shared auth.py. Both JWT bearer tokens and x-api-key
header authentication are now handled centrally.

Closes #42
```

```
fix(validation): handle empty string as missing required field
```

```
chore: remove tracked __pycache__ binaries and add gitignore rules
```

### Rules

- Use the **imperative mood** in the short description: *"add"*, not *"added"* or *"adds"*.
- Keep the short description **under 72 characters**.
- **Do not end** the short description with a period.
- Reference issues in the footer: `Closes #<issue>`, `Fixes #<issue>`, `Refs #<issue>`.
- Breaking changes must include `BREAKING CHANGE:` in the footer or `!` after the type/scope:
  ```
  feat(database)!: remove SQLite support, MongoDB only
  ```

---

## 5. Writing and Running Tests

### Test Framework

This project uses **pytest**. Test files live alongside their modules in the
`unified-form-service/` directory and are named `test_<module>.py`.

### Running Tests

```bash
cd unified-form-service

# Run all tests
pytest

# Run a specific test file
pytest test_response_gateway.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=. --cov-report=term-missing

# Run only tests matching a keyword
pytest -k "rate_limiter"
```

### Writing Tests

- **Isolate external dependencies** — use `mongomock` for MongoDB and `unittest.mock`
  for HTTP calls and Redis. Never connect to a real database in tests.
- **One assertion per test** where possible. Tests should be focused and readable.
- **Name tests descriptively**: `test_<function>_<scenario>_<expected_result>`

```python
import pytest
from unittest.mock import patch, MagicMock


def test_validate_response_missing_required_field_returns_error():
    """Submitting a response without a required field should fail validation."""
    schema = {"fields": [{"id": "name", "required": True}]}
    payload = {"answers": []}

    is_valid, errors = validate_response(payload, schema)

    assert not is_valid
    assert any("name" in err for err in errors)
```

- **Test the error paths**, not just the happy path.
- **Do not use `time.sleep()`** in tests — use mocking or pytest fixtures instead.
- Tests must pass in isolation and in any order.

### Database Mocking

```python
import mongomock
import pytest


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["test_db"]
```

---

## 6. Pull Request Checklist

Before opening a PR, confirm the following:

### Code Quality
- [ ] `flake8` passes with no errors (`flake8 . --max-line-length=100`)
- [ ] `black` formatting applied (`black . --line-length 100`)
- [ ] `mypy` type-checking passes (`mypy . --ignore-missing-imports`)
- [ ] All new public functions/classes have docstrings
- [ ] No hard-coded secrets, credentials, or local file paths

### Tests
- [ ] New functionality has corresponding unit tests
- [ ] All existing tests still pass (`pytest`)
- [ ] Coverage has not decreased (run `pytest --cov`)

### Commits & Branch
- [ ] All commits follow the Conventional Commits format
- [ ] Branch is named according to the branch naming convention
- [ ] Branch is up to date with `main` (rebased or merged)

### Documentation
- [ ] `CHANGELOG.md` updated if adding a notable feature or breaking change
- [ ] Inline comments added for non-obvious logic
- [ ] `.env.example` updated if new environment variables were added

### PR Description
- [ ] PR title follows Conventional Commits format
- [ ] Description explains *what* changed and *why*
- [ ] Linked to relevant issue(s) if applicable
- [ ] Screenshots or logs attached for UI/behaviour changes

---

## 7. Reporting Bugs

### Before Reporting

1. Search existing issues to avoid duplicates.
2. Reproduce the bug on the latest `main` branch.
3. Check the structured JSON logs for error details:
   ```bash
   # Logs are written to stdout in JSON format; pipe through jq for readability
   python app.py 2>&1 | jq .
   ```

### Bug Report Template

When opening a bug report, please include:

```markdown
**Description**
A clear and concise description of what the bug is.

**Steps to Reproduce**
1. Send a POST request to `/api/forms` with payload `{...}`
2. Observe the response...

**Expected Behaviour**
What you expected to happen.

**Actual Behaviour**
What actually happened. Include full error messages and stack traces.

**Environment**
- OS: [e.g., Ubuntu 22.04]
- Python version: [e.g., 3.11.4]
- MongoDB version: [e.g., 6.0.8]
- Redis version (if applicable): [e.g., 7.0.12]
- FLASK_ENV: [development / production]

**Logs**
Paste relevant log output here (remove any sensitive information).

**Additional Context**
Any other context (screenshots, request/response payloads, etc.).
```

### Security Vulnerabilities

**Do not open a public issue for security vulnerabilities.**
Please report them privately to the repository maintainers directly.
Include a description of the vulnerability, reproduction steps, and potential impact.
