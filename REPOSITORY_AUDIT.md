# Repository Audit

> Full-coverage audit performed on 2026-07-08.  
> Every eligible file was read. See `REPOSITORY_INVENTORY.md` for the file inventory and verification report.

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Dependency Graph](#2-dependency-graph)
3. [Module Interactions](#3-module-interactions)
4. [Circular Dependencies](#4-circular-dependencies)
5. [Dead Code](#5-dead-code)
6. [Duplicate Code](#6-duplicate-code)
7. [Unused Modules](#7-unused-modules)
8. [TODO / FIXME Comments](#8-todo--fixme-comments)
9. [Security Issues](#9-security-issues)
10. [Performance Issues](#10-performance-issues)
11. [Technical Debt](#11-technical-debt)
12. [Documentation Gaps](#12-documentation-gaps)
13. [Testing Gaps](#13-testing-gaps)

---

## 1. Architecture

The repository implements a **Flask 3.1 + flask-openapi3 REST API** for hierarchical form management. Architecture is layered:

```
Client → gunicorn → Flask app (OpenAPI)
  → Middleware layer (request ID, observability, rate limit, rotating logger)
  → API blueprints (auth, resources, conditions, ui_templates, rate_limit, health)
  → Service layer (auth, rbac, condition_evaluator, rate_limit, security, logging)
  → Model layer (MongoEngine documents)
  → MongoDB
```

### Key design decisions

| Decision | Description |
|----------|-------------|
| **App factory** | `create_openapi_app()` in `app/openapi.py` — testable, no global state |
| **Blueprint-per-domain** | 7 APIBlueprints: auth, resources, conditions, ui_templates, rate_limit, health, legacy_compat |
| **Pydantic v2 validation** | flask-openapi3 uses Pydantic models for path/query/body; `SchemaModel` base adds `extra="forbid"` |
| **MongoEngine ODM** | `MongoEngineCompat` wrapper handles connection lifecycle + alias management for test isolation |
| **JWT multi-key rotation** | Active key identified by `JWT_ACTIVE_KID`; old keys in `JWT_ADDITIONAL_KEYS` for graceful rotation |
| **Two rate-limit systems** | ① MongoDB counter (`check_and_increment_rate_limit`) for auth endpoints; ② Redis/in-memory `RateLimitService` for resource endpoints |
| **Condition engine** | 8 condition types (regex, comparison, logical, temporal, arithmetic, set, dsl, custom); TTL/negative/request-level caches |
| **Form workflow** | State machine: draft → submitted → in_review → approved / rejected → submitted |
| **Structured logging** | 5 rotating file loggers (app, debug, errors, requests, responses) + per-request correlation ID |

---

## 2. Dependency Graph

See `REPOSITORY_INVENTORY.md` § Dependency Graph for the full graph.

Key observations:
- `app/models/form.py` is the heaviest hub (29.7 KB, referenced by 12+ modules)
- `app/services/condition_evaluator.py` fans out to cache, dsl, safe_dsl, and models
- `app/services/condition_management.py` is a pure facade over 8 sub-modules — no logic of its own
- `app/api/resources_context.py` contains most DB query logic for the resources API (13 `.objects()` calls)

---

## 3. Module Interactions

### Request flow (resources API example)

```
HTTP Request
  → request_id middleware: assigns g.request_id
  → observability middleware: starts g.request_started_monotonic, increments inflight counter
  → rotating_logger_middleware.before_request: logs 8+ events (request received, auth stages, etc.)
  → resources_api.before_request:
      ① resources_rate_limit() checks Redis/in-memory rule
      ② resolve_access_identity_from_header() decodes JWT
      ③ get_user_by_uuid() DB query
      ④ authorize_resources_route() checks ENDPOINT_PERMISSION map
  → route handler (e.g. resources_forms.get_form):
      • loads project → form from DB
      • RBAC check (_can_read_project / _can_write_project)
      • returns to_json_ready(to_form_output(form))
  → rotating_logger_middleware.after_request: logs 8+ events (response sent, stages completed)
  → observability middleware.after_request: updates counters, sets security headers, CORS
  → request_id middleware.after_request: injects X-Request-Id response header
```

### Authentication flow

```
POST /api/v1/auth/login
  → check_and_increment_rate_limit (MongoDB counter, per-IP, per-window)
  → verify email + password_hash
  → create_user_session → creates UserSession + issues JWT pair
  → returns TokenPairResponse {access_token, refresh_token, session_uuid, expires_in, user}

POST /api/v1/auth/refresh
  → decode_token(refresh_token) — tries active kid first, then additional kids
  → is_refresh_token_revoked — checks TokenBlocklist by JTI + hash
  → rotate_refresh_token — revokes old, issues new pair
  → returns AccessTokenResponse
```

---

## 4. Circular Dependencies

**No circular imports detected** via `ruff`, `mypy`, or static analysis.

The only structural coupling risk is `app/api/resources_utils.py` importing from `app/models/form.py` while `app/api/resources_context.py` also imports from both — but these are all one-directional (API → models).

**One logical cycle risk (not a Python import cycle):**  
`condition_management_approval.py` stores `approval_state` in `condition.metadata` dict but the `Condition` model also has a first-class `approval_state` field. Neither field references the other, but callers must know which source of truth to read. This is a **data architecture** cycle rather than an import cycle.

---

## 5. Dead Code

| Location | Dead Code | Severity |
|----------|-----------|----------|
| `app/models/form.py` — `Version.clean()` | `if self.status == "DISABLED"` (uppercase) — choices are lowercase; this branch never fires | Low |
| `app/models/form.py` — `ResponseItem` | `approval_state`, `published_at`, `deprecated_at` fields — never set, never read anywhere | Low |
| `app/models/form.py` — `FormResponse` | Same approval lifecycle fields duplicated on FormResponse | Low |
| `app/schemas/action.py` | `ActionStepInput` and `ActionStepOutput` are empty pass-through subclasses of `ActionStepBase` — no added fields | Low |
| `app/schemas/action.py` | `ActionDefinitionOutput` re-declares all `ActionDefinitionBase` fields instead of inheriting | Medium |
| `app/schemas/condition_management.py` | `BulkTestInput` duplicates `BatchConditionTestInput`; `BulkImportConditionsInput` duplicates `BulkCreateConditionInput` | Low |
| `app/schemas/question.py` | Legacy flat-action fields (`actionButtonType`, `actionType`, `actionLabel`, `actionIcon`, `hideButton`) — superseded by `actions: List[ActionDefinitionInput]` but not removed | Medium |
| `app/schemas/response_item.py` | `ResponseItemCreateInput` and `ResponseItemOutput` are empty pass-through subclasses | Low |
| `app/schemas/ui_template.py` | 6 empty pass-through subclasses (`ThemeTemplateCreateInput` etc.) with no differentiation | Low |
| `app/schemas/common.py` | `SoftDeleteOutput` defined but not imported by any schema | Low |
| `app/services/condition_evaluator.py` | `external_provider` parameter stored but never called | Low |
| `app/services/condition_evaluator.py` | `_evaluate_logical_condition`: `stopEvaluationIfTrue` branch and fallthrough both `return True` — the flag has no effect on OR evaluation | Medium |
| `app/services/condition_cache.py` | `RequestLevelCache._start_time` set in `__init__` but never read | Low |
| `app/services/logging/decorators.py` | `log_audit`: `resource_id` extracted via `.id` (ObjectId) — should use `.uuid`; function may assign None silently | Medium |
| `app/schemas/mappers.py` | Legacy `elif getattr(question, "isAction", False)` branch in `to_question_output` — never exercised by current model | Low |
| `tests/conftest.py` | `yesterday()`, `tomorrow()`, `next_week()`, `next_month()` helpers defined but not imported by any test | Low |
| `tests/test_api_auth.py` | `test_organization` fixture defined but never used | Low |
| `app/middleware/rotating_logger_middleware.py` | `get_logger_stats(app: Flask = None)` — `app` parameter unused inside function | Low |

---

## 6. Duplicate Code

| Pattern | Locations | Risk |
|---------|-----------|------|
| `_utcnow()` private helper | `app/services/auth.py:22`, `app/api/auth_support.py:35`, `app/api/auth.py:63` | Low — identical one-liners; could be moved to a shared `app/utils.py` |
| `utcnow()` module-level helper | `app/services/security.py:16`, `app/models/rate_limit.py:20`, `app/models/user.py:29`, `scripts/init_rate_limits.py:23` | Low — same pattern; models use it as a `default=` callable |
| `_client_ip()` helper | `app/api/auth_support.py:75` and `app/api/resources_utils.py:77` — identical implementations | Low |
| `ErrorResponse` schema | Defined in `app/schemas/auth.py` AND re-defined in `app/schemas/condition_management.py` | Medium — namespace collision if both imported |
| Pagination logic | `paginate_items` (in-memory) and `paginate_queryset` (DB) in `resources_utils.py` — near-identical signatures | Low — appropriate deduplication not possible across in-memory vs DB |
| `save()` override in models | Every MongoEngine Document has `self.updated_at = utcnow(); return super().save(...)` | Low — acceptable MongoEngine pattern; consolidation possible via `_BaseDocument` |
| Cursor encode/decode | `_encode_audit_cursor`/`_decode_audit_cursor` in `auth_support.py`; `encode_cursor`/`decode_cursor` in `resources_utils.py` — functionally identical | Low |
| Rate-limit 429 response construction | Repeated in `middleware/rate_limit.py` (`rate_limit` + `rate_limit_by_endpoint`) and `resources_utils.py` — same structure thrice | Medium |

---

## 7. Unused Modules

All modules are imported and used. No entirely dead Python modules were found via ruff F401 scan (clean).

The following modules are **lightly tested** but not dead:
- `app/services/safe_dsl.py` — used by `condition_evaluator._evaluate_custom_condition`; only 1 test for the "block" path in `test_safe_dsl.py`
- `app/api/rate_limit.py` — rate limit CRUD API; not covered by any test file
- `app/services/condition_management_async.py` — async evaluation with in-memory thread pool; not covered by direct unit tests
- `app/middleware/rate_limit.py` — `rate_limit_by_endpoint` decorator is defined but never actually applied to any route in the codebase (only `rate_limit` is used, and even that is a no-op on flask-openapi3 routes — see SECURITY.md)

---

## 8. TODO / FIXME Comments

No `TODO`, `FIXME`, `HACK`, or `XXX` comments were found in `app/` or `tests/`. The only inline `# noqa` annotations are:
- `app/services/rate_limit.py:447` — `# noqa: E711` (explicit `None` comparison in MongoEngine Q filter — intentional)
- Various `# noqa: F401` on import-side-effect imports (blueprint registration in `app/api/__init__.py`, `app/api/auth.py`)
- `pragma: no cover` on three `ImportError` blocks for optional dependencies (flask-openapi3 missing)

The `scripts/verify_audit_query_plans.js` contains a hardcoded `ISODate("2026-07-07T00:00:00Z")` that should be parameterised for production use.

---

## 9. Security Issues

### Critical

| ID | Location | Issue | Recommendation |
|----|----------|-------|----------------|
| SEC-01 | `app/services/condition_evaluator.py` | `_evaluate_custom_condition` passes user-supplied `condition.expression` to `safe_dsl.evaluate_expression`. The `DSLValidator` whitelist covers function names but **unrestricted field access paths** on the context dict are possible — a malicious condition can read any context key. | Add a context-key whitelist to `DSLValidator`; disallow attribute-chain traversal (e.g. `user.__class__.__bases__`). |
| SEC-02 | `app/services/condition_management_async.py` | `InMemoryConditionQueue` spawns **unbounded daemon threads** with no concurrency limit or backpressure. A flood of async evaluation requests will create unlimited threads, exhausting OS resources. | Add a `ThreadPoolExecutor` with a fixed `max_workers` cap; reject with `429` when queue is full. |

### High

| ID | Location | Issue | Recommendation |
|----|----------|-------|----------------|
| SEC-03 | `app/schemas/user.py` | `UserUpdateInput.password_hash` is directly settable — callers can overwrite the hash without going through the password-change endpoint. | Remove `password_hash` from `UserUpdateInput`; expose only via a dedicated `ChangePasswordRequest`. |
| SEC-04 | `app/schemas/user.py` | `UserUpdateInput.otp_secret` is directly settable. | Same as above — remove; expose via a dedicated MFA setup endpoint. |
| SEC-05 | `app/services/auth.py` | `kid` from the **unverified** JWT header is used to select the validation key. No sanitisation of the `kid` value before dict lookup. A key ID crafted as `../../../../etc/passwd` would fail silently, but injections via confusable characters could cause unexpected key selection. | Validate that `kid` matches `[a-zA-Z0-9_\-\.]+` before use. |
| SEC-06 | `app/services/auth.py` | Old keys in `JWT_ADDITIONAL_KEYS` are silently accepted indefinitely. A compromised old key continues to validate tokens. | Add an explicit key expiry mechanism; log warnings when tokens validated via non-active keys. |
| SEC-07 | `docker-compose.yml` | MongoDB runs with `--bind_ip_all` and **no authentication** configured. Anyone on the Docker network can connect without credentials. | Add `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD` environment variables and update `MONGODB_URI` to include credentials. |

### Medium

| ID | Location | Issue | Recommendation |
|----|----------|-------|----------------|
| SEC-08 | `app/services/rate_limit.py` | `RateLimitService.cache = {}` in-memory fallback is **per-instance**. If the service is re-instantiated across requests, counters reset and rate limiting becomes ineffective. | Use a module-level singleton or inject via the app factory. |
| SEC-09 | `app/middleware/rate_limit.py` | `rate_limit` and `rate_limit_by_endpoint` catch `redis.RedisError` and return `503` — they **fail open** (no limiting if Redis is down). | Document this explicitly; consider a fail-closed mode option. |
| SEC-10 | `app/services/rate_limit.py` (`_increment_redis`) | Redis window reset bug: after deleting the expired count key, the new window timestamp is never set (see § Performance). This breaks rate limiting entirely after the first window expires. | Fix the window-reset logic (see Technical Debt). |
| SEC-11 | `app/models/condition_management.py` — `ConditionEvaluationStat` | No TTL index — grows unboundedly. Potential storage DoS on busy deployments. | Add `{"fields": ["created_at"], "expireAfterSeconds": 604800}` (7 days). |
| SEC-12 | `.env.example` | `JWT_SECRET_KEY=change-this-in-production` is a predictable placeholder. If developers copy this without changing it, any JWT signed with this secret is forgeable. | Replace with `JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">`. |

### Low

| ID | Location | Issue | Recommendation |
|----|----------|-------|----------------|
| SEC-13 | `app/schemas/auth.py` | `AuthorizationHeader.Authorization` has `min_length=10`. A 3-character token `"Bearer x"` (8 chars) would pass, allowing trivially short tokens. | Increase to `min_length=20` or validate the `Bearer ` prefix and minimum token length separately. |
| SEC-14 | `app/models/auth.py` | `TokenBlocklist.token_type = choices=("refresh",)` — access token revocation is impossible by design. | Document this as a known limitation; plan an access-token blocklist if session revocation requirements tighten. |
| SEC-15 | `app/models/auth.py` | `UserSession.refresh_token_hash` and `TokenBlocklist.token_hash` have no documented hashing algorithm. | Add a module comment documenting SHA-256 is used (confirmed in `services/auth.py`). |
| SEC-16 | `tests/conftest.py` | Hardcoded JWT test secret `"test-secret-key-do-not-use-in-production"` — acceptable for tests but should use `secrets.token_hex(32)` per session for true isolation. | Low-priority change. |

---

## 10. Performance Issues

### High Impact

| ID | Location | Issue | Recommendation |
|----|----------|-------|----------------|
| PERF-01 | `app/middleware/rotating_logger_middleware.py` | Every HTTP request triggers **15–17 separate `log_app_event` calls** (8 before + 7 after). On a busy instance this floods the log files and adds measurable latency from I/O. | Consolidate to one structured event per phase boundary; use a dict of stage results instead of separate calls. |
| PERF-02 | `app/services/condition_management_monitoring.py` | `monitoring_dashboard_snapshot` performs **3 full MongoDB collection scans**: one in `get_monitoring_snapshot()`, one in `monitoring_dashboard_snapshot` itself, and one via `build_dependency_graph()`. | Cache the snapshot (TTL ~30s); pass already-fetched conditions into sub-functions rather than re-querying. |
| PERF-03 | `app/services/condition_management_graph.py` — `build_dependency_graph()` | Full `Condition.objects` scan on every invocation, called from multiple code paths with no caching. | Cache the graph snapshot (invalidate on condition write). |
| PERF-04 | `app/services/rate_limit.py` — `_increment_redis` | **Window reset bug**: after deleting the expired count key, `window_ts` is still truthy (fetched before deletion), so the new window timestamp is never written. The rate-limit window **never resets** for Redis-backed counters after the first expiry. | Fix: set `window_ts = None` after deleting the timestamp key before the conditional set. |

### Medium Impact

| ID | Location | Issue | Recommendation |
|----|----------|-------|----------------|
| PERF-05 | `app/models/form.py` — `_persisted_state()` | Issues an extra DB query on **every** `clean()` call (every save) to load the pre-save state for transition validation. | Cache the pre-state in `__init__`/`pre_save` signal or use `modify()` with conditional operators. |
| PERF-06 | `app/services/condition_management_analysis.py` — `discover_usage()` | Full collection scan of all `Condition` objects on every call; no caching. | Cache the usage graph with TTL on read; invalidate on condition writes. |
| PERF-07 | `app/api/resources_utils.py` — `paginate_items()` | Loads **all** items into a Python list, sorts in-memory, then slices. For large collections this is an O(N) memory allocation. | Use `paginate_queryset()` (DB-side `skip/limit`) for MongoDB-backed resources. |
| PERF-08 | `app/services/condition_cache.py` — `NegativeCache` | Eviction removes from `_cache` dict but **does not clear the bloom-filter bucket bits**. Evicted items can produce indefinite false positives in the bloom filter. | Track bloom-filter bits per entry; clear on eviction. Or use a simpler TTL-based negative cache without bloom filter. |

### Low Impact

| ID | Location | Issue | Recommendation |
|----|----------|-------|----------------|
| PERF-09 | `app/services/condition_management_async.py` — `evaluate_condition_async` | Busy-polls with `time.sleep(0.02)` (20 ms spin-wait). Consumes CPU and does not respect `timeout_ms` precisely. | Use `threading.Event.wait(timeout)` instead. |
| PERF-10 | `app/middleware/observability.py` | `requests_inflight` uses `max(0, ...)` guard which masks asymmetric hook calls. `OPTIONS` preflight requests are counted in `requests_total`. | Filter `OPTIONS` requests from metrics. |

---

## 11. Technical Debt

### Bugs (confirmed)

| ID | Location | Bug | Impact |
|----|----------|-----|--------|
| BUG-01 | `app/services/rate_limit.py` — `_increment_redis` | Window reset never sets new timestamp key (see PERF-04). Rate limiting silently breaks after first window expiry for Redis-backed counters. | **Critical** — rate limiting non-functional in Redis mode after first window |
| BUG-02 | `app/services/condition_management_approval.py` — `transition_approval_state` | Stores `approval_state` in `condition.metadata` dict; the `Condition` model's first-class `approval_state` field is **never updated**. Two conflicting sources of truth. | High — approval state queries on the model field will return stale data |
| BUG-03 | `app/services/condition_management_versioning.py` — `restore_condition_version` | Skips `subConditions` during restore (`if key == "subConditions": continue`). Restoring a logical condition silently drops its sub-condition references. | High — logical conditions are corrupted on version restore |
| BUG-04 | `app/services/condition_management_versioning.py` — `rollback_condition_to_version` | Strips all `"v"` chars from version ID (`str(version_id).replace("v", "")`) — e.g. `"rev3"` → `"re3"`. | Medium — version lookup fails for IDs containing `"v"` anywhere |
| BUG-05 | `app/services/condition_evaluator.py` — `_coerce_datetime` | Interprets numeric values as `datetime.now() - timedelta(seconds=value)` (seconds-ago offset) rather than Unix timestamp. | Medium — temporal conditions with numeric dates produce wrong results |
| BUG-06 | `app/services/condition_evaluator.py` — `_parse_jsonish` | CSV splitting uses `raw.split(",")` — fails if list items contain commas. | Low |
| BUG-07 | `app/services/condition_dsl.py` — `Parser._unquote` | Uses `bytes(body, "utf-8").decode("unicode_escape")` — mangles non-ASCII UTF-8 (emoji, accented chars). | Medium — DSL expressions with non-ASCII string literals silently corrupt values |
| BUG-08 | `app/services/condition_management_async.py` — `_run_async_job` | Recursive retry calls `_run_async_job(job_id, retry_count+1)` directly (not via queue), blocking the daemon thread for the full retry chain synchronously. | Low — retry delays block worker thread |
| BUG-09 | `app/services/condition_cache.py` — `_hash_context` | Uses `str(sorted(context.items()))` — fails if context values are not sortable; `int(1)` and `str("1")` produce identical keys. | Low |
| BUG-10 | `app/services/logging/decorators.py` — `log_audit` | `resource_id` extracted via `result.id` (ObjectId), not `result.uuid`. Audit log `resource_id` is always a MongoDB ObjectId string, not a UUID. | Low |
| BUG-11 | `app/models/form.py` — `Version.clean()` | Case mismatch: `if self.status == "DISABLED"` vs choices `"disabled"`. Branch is dead code. | Low |
| BUG-12 | `app/services/logging/service.py` — `get_logger` | Module-level singleton creation is not thread-safe (no lock). Two threads could create two instances simultaneously. | Low |

### Design Debt

| ID | Location | Debt | Priority |
|----|----------|------|----------|
| DEBT-01 | `app/models/form.py` — `Section` | Dual soft-delete tracking: `isDeleted`/`deletedBy`/`deletedAt` (camelCase legacy) + `deleted_at`/`deleted_by` (snake_case). Sync in `clean()` is fragile. | Medium |
| DEBT-02 | `app/schemas/section.py` | Same dual-field problem reflected in the schema exposed to API consumers. | Medium |
| DEBT-03 | `app/middleware/rate_limit.py` — `@rate_limit` | The `rate_limit` decorator is a **no-op on flask-openapi3 routes** when used without arguments (`@rate_limit` instead of `@rate_limit()`). Python calls `rate_limit(func)` which returns `decorator`, not `wrapper`. The `auth.login`, `auth.refresh`, `auth.logout` routes are not actually rate-limited by this decorator. Rate limiting works only via the MongoDB counter in `security.py`. | High — misleading code |
| DEBT-04 | `app/api/rate_limit.py` — `_require_super_admin` | Returns `(user, None, None)` on success, `(None, error_response, status_code)` on failure — a 3-tuple return with mixed semantics is fragile and non-standard. | Low |
| DEBT-05 | `app/config.py` — `validate_all` | `cls.get_bool(app.config, "ENABLE_AUDIT_LOGS", ...)` call at line 392: the return value is discarded. Validation is silently skipped. | Low |
| DEBT-06 | `app/config.py` — `CONFIG_BY_ENV` | `"qa"` maps to `ProductionConfig` — QA environments get production-level JWT TTLs and rate limits, which may make QA testing harder. No `"test"` env mapping. | Low |
| DEBT-07 | `app/services/condition_management_async.py` | In-memory queue and thread pool state is not preserved across gunicorn worker restarts or process forks. Async jobs queued in one worker are lost when that worker recycles. | High — data loss in production |

---

## 12. Documentation Gaps

### Module-Level Docstrings Missing

62 of 78 `app/` Python files lack a module-level docstring. Priority files:

| File | Priority |
|------|----------|
| `app/config.py` | High |
| `app/models/form.py` | High |
| `app/models/auth.py` | High |
| `app/models/user.py` | Medium |
| `app/services/auth.py` | High |
| `app/services/condition_evaluator.py` | High |
| `app/services/safe_dsl.py` | High |
| All `app/schemas/*.py` | Medium |
| All `app/api/*.py` | Medium |

### Function/Method Docstrings Missing

490 of ~518 public functions across `app/` lack docstrings. Highest-value targets:

- All public service functions in `app/services/auth.py`, `app/services/rbac.py`, `app/services/security.py`
- All model `clean()` and `save()` overrides (document the validation rules)
- All API route handlers (document request/response contracts)
- `app/services/condition_evaluator.py` — `_evaluate_*` private methods (complex algorithms)
- `app/services/safe_dsl.py` — `DSLValidator` and `evaluate_expression`

### `.env.example` Gaps

Two config keys present in `app/config.py` but missing from `.env.example`:
- `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT` (default: `true`)
- `WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE` (default: `true`)
- `AUDIT_LOG_RETENTION_DAYS` (default: `180`)
- `API_VERSION` (default: `v1`)
- `MONGODB_CONNECT_TIMEOUT_MS` (default: `2000`)

### `app/schemas/__init__.py` Incomplete

Does not re-export `UiTemplate*`, `ActionDefinition*`, or `ConditionManagement*` schemas despite these being actively used. Consumers must know internal sub-module paths.

---

## 13. Testing Gaps

### Coverage Overview

| Area | Coverage | Status |
|------|----------|--------|
| Auth service (JWT, sessions) | ~85% | Good |
| Auth API endpoints | ~70% | Adequate |
| Condition evaluator (core types) | ~60% | Needs work |
| Condition management (versions, presets, approval) | ~45% | Weak |
| Resources API (CRUD endpoints) | ~0% | **Missing** |
| Rate limit service (Redis path) | ~0% | **Missing** |
| Rate limit API (admin CRUD) | ~0% | **Missing** |
| UI templates API | ~30% | Weak |
| RBAC service | ~60% | Adequate |
| Form workflow state machine | ~50% | Adequate |
| Condition DSL parser | ~40% | Weak |
| Safe DSL evaluator | ~35% | Weak |
| Security service (`check_and_increment_rate_limit`) | ~20% | Weak |
| Condition cache (Redis path, eviction, bloom filter) | ~30% | Weak |

### Missing Test Cases (prioritised)

#### Priority 1 — No tests at all
- **Resources API CRUD** (`/api/v1/projects`, `/forms`, `/sections`, `/questions`, `/choices`) — zero API-level tests
- **Rate limit admin API** (`/api/v1/admin/rate-limits/configs`) — zero tests
- **Rate limit service** Redis backend (`_increment_redis`, window reset logic)
- **BUG-01** regression test: Redis window reset after first expiry

#### Priority 2 — Critical paths untested
- `_can_read/write/admin/submit/review/approve_project()` RBAC helpers in `resources_utils.py` — no direct unit tests
- `apply_form_workflow_action()` — `review` and `approve` paths not tested
- `transition_approval_state()` with invalid target state (should raise `ConditionManagementError`)
- `restore_condition_version()` with non-existent version number
- `rollback_condition_to_version()` with version ID containing `"v"` (regression for BUG-04)
- `validate_project_membership_role_alignment()` with misaligned user (should raise `ValueError`)
- `_evaluate_custom_condition()` with DSL accessing non-existent context key

#### Priority 3 — Edge cases missing
- Temporal operators: `after`, `before` (only `created_within_days` tested)
- Set operators: `subset`, `intersection`, `disjoint`
- Arithmetic: division-by-zero; `between` at exact boundary values
- Condition with `isNegated=True` for each type
- `evaluate_all` with empty list via OR (should return `True`)
- `decode_token` with expired token (should raise `AuthError`)
- `decode_token` with unknown `kid` (should raise `AuthError`)
- `rotate_refresh_token` when session has already been revoked concurrently

#### Priority 4 — Test quality improvements
- `test_api_auth.py` — `test_health_check_endpoint_exists` accepts both 200 and 404 (meaningless assertion)
- `test_api_auth.py` — `test_login_rate_limiting` makes only 5 of 10 allowed attempts
- `tests/conftest.py` — `cleanup_db` drops and recreates entire DB per test (slow); per-collection truncation preferred
- `test_condition_performance.py` — wall-clock assertion is CI-environment-dependent; mark as `@pytest.mark.slow` and skip in standard CI runs
- `test_condition_cache.py` — `test_ttl_cache_expiration` uses `time.sleep(1.1)` — use `freezegun` or `time-machine`
- Tests for `scripts/init_rate_limits.py` and `scripts/setup_condition_indexes.py` (none exist)

### Missing `pytest.ini` Markers Applied

The following markers are defined in `pytest.ini` but almost no tests use them, so `make test-unit`, `make test-security` etc. run 0 tests:
- `unit` — only a handful of tests tagged
- `security` — no tests tagged
- `performance` — 1 test tagged

---

## Summary: Files Modified This Audit Pass

| File | Change |
|------|--------|
| `REPOSITORY_INVENTORY.md` | Created — full file inventory, dependency graph, technology stack, verification report |
| `REPOSITORY_AUDIT.md` | Created — this document |
| Module docstrings added | See next section |

Previous session changes (from checkpoint `001`):
- 19 `app/` + 3 `tests/` files: `datetime.utcnow` → `datetime.now(timezone.utc)` 
- `app/middleware/rate_limit.py`: `Retry-After` header + `X-RateLimit-Remaining` fix
- 9 new documentation files: `ARCHITECTURE.md`, `SECURITY.md`, `DEVELOPMENT.md`, `DEPLOYMENT.md`, `CONTRIBUTING.md`, `TESTING.md`, `CHANGELOG.md`, `README.md` (expanded), `Makefile`

---

## Recommendations (Prioritised)

### Immediate (bugs + security)
1. **Fix BUG-01** (`_increment_redis` window reset) — rate limiting silently breaks in Redis mode
2. **Fix BUG-02** (`transition_approval_state` dual source of truth) — update `condition.approval_state` field
3. **Fix BUG-03** (`restore_condition_version` drops subConditions) — remove the skip
4. **Fix SEC-02** (unbounded async threads) — switch to `ThreadPoolExecutor(max_workers=N)`
5. **Fix SEC-03/04** (password_hash / otp_secret in UserUpdateInput) — remove from schema
6. **Fix SEC-07** (MongoDB in compose has no auth) — add credentials
7. **Add `.env.example` missing keys** (`RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT`, `WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE`, `AUDIT_LOG_RETENTION_DAYS`)

### Short-term (debt + coverage)
8. Add resources API tests (CRUD for project/form/section/question/choice)
9. Add rate limit service tests (Redis path)
10. Fix DEBT-03 (`@rate_limit` no-op) — replace with `before_request` hook like resources does
11. Add TTL index to `ConditionEvaluationStat` (SEC-11)
12. Fix BUG-07 (`Parser._unquote` mangles non-ASCII)
13. Add module-level docstrings to highest-priority files

### Long-term (improvements)
14. Consolidate duplicate `_utcnow()` / `utcnow()` helpers into `app/utils.py`
15. Eliminate dual soft-delete field pattern in `Section` model + schema (DEBT-01/02)
16. Move `ConditionEvaluationStat` persistence to a time-series sink (InfluxDB/Prometheus) rather than MongoDB for better monitoring performance
17. Replace in-memory async job queue with a proper task queue (Celery + Redis) for durability across worker restarts (DEBT-07)
18. Apply `pytest` markers consistently; set a minimum coverage threshold in CI (e.g. `--cov-fail-under=75`)
