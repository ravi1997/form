# Development Guide

## Prerequisites

- Python 3.13+
- MongoDB 6+ (for real runs) or mongomock (for tests)
- Redis (optional — rate limiting falls back to in-memory without it)

## Local setup

```bash
# 1. Clone and enter the repository
git clone <repo-url>
cd form

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install all dependencies (runtime + dev/test)
pip install -r requirements.txt -r requirements-test.txt
pip install ruff mypy pip-audit

# 4. Copy the example env file and edit as needed
cp .env.example .env
# At minimum set JWT_SECRET_KEY for anything beyond unit tests.

# 5. Run tests (uses mongomock — no MongoDB required)
pytest -q --cov=app --cov-report=term

# 6. Start the development server (requires MongoDB)
flask --app app.wsgi:app run --reload --port 8000
# or with gunicorn:
gunicorn --bind 0.0.0.0:8000 --reload app.wsgi:app
```

### Using the Makefile

The project ships with a `Makefile` for common tasks:

```bash
make install     # install runtime + test dependencies
make test        # run pytest with coverage
make lint        # ruff check
make type-check  # mypy
make format      # ruff format (auto-fix)
make audit       # pip-audit vulnerability scan
make docker-build
make docker-up   # docker compose up --build -d
make docker-down
make clean       # remove __pycache__, .coverage, etc.
```

CI runs the same core checks and additionally enforces `ruff format --check .`
before linting, plus `pip-audit -r requirements.txt`.

---

## Running with Docker Compose

```bash
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET_KEY
export JWT_SECRET_KEY='your-secret-here'
docker compose up --build
```

The service listens on `http://localhost:8000`. MongoDB data is persisted in the `mongo_data` Docker volume.

---

## Environment Variables

See `.env.example` for the full list with comments. The most important ones for local development:

| Variable            | Default               | Notes                                      |
|--------------------|-----------------------|--------------------------------------------|
| `APP_ENV`           | `development`        | `development` / `production`               |
| `MONGODB_URI`       | `mongodb://localhost:27017/form_dev` | Local MongoDB URI        |
| `MONGODB_DB`        | `form_dev`           |                                            |
| `JWT_SECRET_KEY`    | *(auto-generated warning)* | Required in production              |
| `JWT_ACTIVE_KID`    | `v1`                 | Key ID for token signing                   |
| `LOG_LEVEL`         | `INFO`               | `DEBUG` for verbose local logs             |
| `LOG_DIR`           | `logs`               | Relative or absolute path                  |

Full documentation: see `ARCHITECTURE.md` and `.env.example`.

---

## Running Tests

```bash
# All tests (uses mongomock — no real MongoDB needed)
pytest -q

# With coverage report
pytest --cov=app --cov-report=term

# Specific test file
pytest tests/test_api_auth.py -v

# Run by marker
pytest -m unit
pytest -m security
pytest -m integration
```

Test markers are defined in `pytest.ini`. See `TESTING.md` for the full test strategy.

---

## Code Style

The project uses:

- **[Ruff](https://docs.astral.sh/ruff/)** for linting and formatting
- **[Mypy](https://mypy.readthedocs.io/)** for type checking (lenient config — see `mypy.ini`)

Run before every commit:

```bash
ruff check .          # lint
ruff format --check .  # format validation in CI
ruff format .         # format
mypy app tests        # type check
pytest -q --cov=app --cov-report=term
```

Or use `make lint type-check format`.

The CI pipeline mirrors these commands and also runs `ruff format --check .` explicitly before linting.

---

## Adding a New API Endpoint

1. Add the route handler to the appropriate `app/api/resources_*.py` module (or create a new one).
2. Define request/response schemas in `app/schemas/` (Pydantic v2 `BaseModel` subclassing `SchemaModel`).
3. Add mappers in `app/schemas/mappers.py` if a new model→schema conversion is needed.
4. Register the permission in `app/api/resources_utils.py:ENDPOINT_PERMISSION` if it's a resource endpoint.
5. Write tests in `tests/` following the naming convention `test_<domain>.py`.
6. Update `ARCHITECTURE.md` if the endpoint introduces a new component.

---

## Adding a New MongoDB Model

1. Define the `mongoengine.Document` subclass in `app/models/<domain>.py`.
2. Export it from `app/models/__init__.py` if needed.
3. Add it to `tests/conftest.py:_ensure_test_indexes()` so test runs initialise its indexes.
4. Document the new collection in `ARCHITECTURE.md`.
5. Run `python scripts/setup_condition_indexes.py` (or create an equivalent script) if custom indexes are needed.

---

## Debugging

### Structured logs

All application events are logged as JSON lines in `logs/`. Use `jq` to parse them:

```bash
# Follow app events in real time
tail -f logs/app.log | jq '.'

# Find all errors for a request
jq 'select(.request_id == "abc-123")' logs/errors.log

# Find all slow responses
jq 'select(.duration_ms > 200)' logs/responses.log
```

### Debug log level

```bash
LOG_LEVEL=DEBUG gunicorn --bind 0.0.0.0:8000 app.wsgi:app
```

This enables the `debug.log` output with detailed trace entries for each JWT decode, DB query, and RBAC check.

### Metrics endpoint

```bash
curl http://localhost:8000/api/v1/metrics | jq '.'
```

Returns uptime, total requests, inflight count, average duration, and status code breakdown.

---

## IDE Recommendations

- **VS Code** with the Python and Pylance extensions.
- Enable `ruff` as the default formatter (`.vscode/settings.json`):

```json
{
  "python.analysis.typeCheckingMode": "basic",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true
  }
}
```

- **PyCharm**: configure the project interpreter to use `.venv/bin/python`, enable ruff as an external tool.
