# Contributing

## Expectations

- Keep code, tests, and docs in the same change when behavior changes
- Add regression tests for bug fixes
- Run the relevant verification commands before opening a PR

## Suggested process

1. Create a focused branch.
2. Make the smallest correct code change.
3. Update the documentation that reflects the changed behavior.
4. Run targeted tests and quality checks.
5. Summarize the behavioral change and validation in the PR.

## When to update docs

- when a route is added, renamed, or removed
- when configuration defaults or validation rules change
- when auth or RBAC behavior changes
- when operational behavior changes, such as logging or rate limiting
- when background job behavior changes

## Review standard

- favor evidence over assumptions
- update README only as an index, not as the sole source of detail
- prefer focused commits when the change naturally separates into code, docs, and tests
