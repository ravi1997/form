# Coding Standards

- Use Python 3.13+ syntax and type hints where they clarify public APIs
- Keep route handlers thin and move business logic into services
- Use snake_case for module, function, and variable names
- Prefer small, focused modules over large catch-all files
- Run Ruff and mypy before merging

## API code

- Keep request validation in schemas
- Return schema-shaped JSON from handlers through the existing mappers
- Prefer explicit error responses over silent fallback behavior
- Keep route groups aligned with the OpenAPI blueprint structure

## Service code

- Put auth, RBAC, rate-limit, and condition logic in services, not route modules
- Use `app/utils.py` for shared runtime helpers such as `utcnow()` and `client_ip()`
- Keep stateful services thread-safe when they are used as singleton helpers

## Model code

- Define indexes explicitly when query patterns require them
- Prefer document `clean()` validation for invariants that should always hold
- Use TTL indexes for expiring operational data

## Test code

- Add regression tests for bug fixes
- Name tests after behavior, not implementation
- Keep tests close to the module or feature they protect
