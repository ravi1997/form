# Contributing

Thank you for your interest in contributing! Please read this guide before opening issues or pull requests.

---

## Code of Conduct

Be respectful. Constructive criticism is welcome; personal attacks are not.

---

## Getting Started

1. Fork the repository.
2. Set up your local development environment — see [DEVELOPMENT.md](DEVELOPMENT.md).
3. Create a feature branch from `master`:
   ```bash
   git checkout -b feature/short-description
   ```
4. Make your changes.
5. Run the full quality checks (must all pass):
   ```bash
   make lint type-check test
   # or manually:
   ruff check .
   mypy app tests
   pytest --cov=app --cov-report=term
   ```
6. Commit using a conventional commit message (see below).
7. Push your branch and open a pull request.

---

## Branch Naming

| Type          | Pattern                       | Example                          |
|--------------|-------------------------------|----------------------------------|
| Feature       | `feature/<short-description>` | `feature/add-otp-support`        |
| Bug fix       | `fix/<short-description>`     | `fix/refresh-token-expiry`       |
| Documentation | `docs/<short-description>`    | `docs/update-architecture`       |
| Refactor      | `refactor/<short-description>`| `refactor/extract-auth-helpers`  |
| Tests         | `test/<short-description>`    | `test/add-rbac-edge-cases`       |

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`.

Examples:
```
feat(auth): add OTP second-factor support
fix(rate-limit): include Retry-After header in 429 responses
docs(architecture): document condition evaluation caches
test(rbac): add edge cases for cross-org admin scope
```

---

## Pull Request Process

1. Keep PRs focused — one logical change per PR.
2. Write or update tests for all changed behaviour.
3. Ensure all CI checks pass before requesting review.
4. Reference any related issues (`Closes #123`).
5. Fill in the PR description with:
   - **What** changed
   - **Why** it was needed
   - **How** it was implemented
   - Any **breaking changes** or migration notes

---

## Code Standards

### Python

- Target **Python 3.13**.
- Use **type hints** for all public function signatures.
- Prefer `from __future__ import annotations` in modules that reference forward types.
- Docstrings for public classes and functions are welcome but not mandatory for internal helpers.
- Keep functions short — if a function exceeds ~50 lines, consider splitting it.

### Schemas

- All request/response models live in `app/schemas/`.
- Use `SchemaModel` (from `app/schemas/common.py`) as the base — it sets Pydantic's `model_config` for the project defaults.
- Never expose internal MongoEngine documents directly; always use schema mappers.

### Tests

- New endpoints require at least one happy-path and one error-path test.
- Use the `app` and `client` fixtures from `tests/conftest.py` — they handle app creation and MongoDB teardown automatically.
- Mark tests with the appropriate pytest marker (`unit`, `integration`, `security`, `api`, `model`, `service`).

### Models

- All new `DateTimeField` defaults must use `lambda: datetime.now(timezone.utc)` (not `datetime.utcnow`).
- Declare `meta["indexes"]` explicitly for any field used in frequent queries.

---

## Dependency Policy

- Do not add runtime dependencies without discussion — keep `requirements.txt` lean.
- New test-only dependencies go in `requirements-test.txt`.
- Run `pip-audit -r requirements.txt` and ensure there are no known vulnerabilities.

---

## Reporting Issues

Before opening an issue:

1. Search existing issues.
2. Reproduce the problem locally.
3. Include:
   - Python version
   - Relevant environment variables (redact secrets)
   - Full traceback or log output
   - Minimal reproduction steps

For security vulnerabilities, do **not** open a public issue. See [SECURITY.md](SECURITY.md#responsible-disclosure).
