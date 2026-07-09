# Audit Report

- Commit audited: `3481b1ec50cbe7238fd0810b6a0e03274890befb`
- Audit date: `2026-07-09`
- Test suite status at audit time: `pytest` unavailable in this environment, so no pass/fail count could be produced; `python3 -m pytest -q` exited with `No module named pytest`

## Summary

| Severity | Checked | FIXED | STILL OPEN | UNVERIFIED |
|---|---:|---:|---:|---:|
| Critical | 2 | 1 | 1 | 0 |
| High | 6 | 3 | 3 | 0 |
| Medium | 18 | 6 | 12 | 0 |
| Low | 33 | 7 | 25 | 1 |
| Total | 59 | 17 | 41 | 1 |

## Detailed Findings

### SEC-01
- Title: `_evaluate_custom_condition` forwards raw context to DSL
- Severity: Critical
- Status: STILL OPEN
- Citation: [`app/services/condition_evaluator.py:498-502`](/home/ravi/workspace/new/form/app/services/condition_evaluator.py#L498)
- Evidence:
```python
def _evaluate_custom_condition(self, condition: Condition) -> bool:
    if not condition.expression:
        raise ConditionEvaluationError("Custom conditions require expression")
    result = evaluate_expression(condition.expression, self.context)
    return bool(result)
```
- Exact fix needed: add a context-key whitelist and block attribute-chain traversal before calling `evaluate_expression`.

### SEC-02
- Title: Unbounded daemon threads in async condition queue
- Severity: Critical
- Status: FIXED
- Citation: [`app/services/condition_management_async.py:19-37`](/home/ravi/workspace/new/form/app/services/condition_management_async.py#L19)
- Evidence:
```python
_MAX_ASYNC_WORKERS = 8

class InMemoryConditionQueue:
    def __init__(self, max_workers: int = _MAX_ASYNC_WORKERS):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="cond-eval"
        )
```

### SEC-03
- Title: `UserUpdateInput.password_hash` directly settable
- Severity: High
- Status: FIXED
- Citation: [`app/schemas/user.py:54-80`](/home/ravi/workspace/new/form/app/schemas/user.py#L54)
- Evidence:
```python
# password_hash and otp_secret are intentionally excluded — callers must use
# the dedicated /auth/change-password and /auth/otp endpoints instead.
```

### SEC-04
- Title: `UserUpdateInput.otp_secret` directly settable
- Severity: High
- Status: FIXED
- Citation: [`app/schemas/user.py:54-80`](/home/ravi/workspace/new/form/app/schemas/user.py#L54)
- Evidence:
```python
# password_hash and otp_secret are intentionally excluded — callers must use
# the dedicated /auth/change-password and /auth/otp endpoints instead.
```

### SEC-05
- Title: Unverified JWT `kid` used for key selection
- Severity: High
- Status: STILL OPEN
- Citation: [`app/services/auth.py:134-219`](/home/ravi/workspace/new/form/app/services/auth.py#L134)
- Evidence:
```python
token_kid = jwt.get_unverified_header(token).get("kid")
if token_kid and token_kid in keyring:
    keys_to_try.append(keyring[token_kid])
```
- Exact fix needed: validate `kid` against a strict allowlist regex before key lookup.

### SEC-06
- Title: Additional JWT keys accepted indefinitely
- Severity: High
- Status: STILL OPEN
- Citation: [`app/services/auth.py:134-219`](/home/ravi/workspace/new/form/app/services/auth.py#L134)
- Evidence:
```python
for kid, key in keyring.items():
    if token_kid and kid == token_kid:
        continue
    keys_to_try.append(key)
```
- Exact fix needed: add explicit expiry/rotation policy for non-active keys and log non-active validation.

### SEC-07
- Title: MongoDB without authentication in `docker-compose.yml`
- Severity: High
- Status: FIXED
- Citation: [`docker-compose.yml:1-40`](/home/ravi/workspace/new/form/docker-compose.yml#L1)
- Evidence:
```yaml
MONGODB_URI: mongodb://${MONGO_INITDB_ROOT_USERNAME:-formadmin}:${MONGO_INITDB_ROOT_PASSWORD:?set MONGO_INITDB_ROOT_PASSWORD in your environment}@mongo:27017/form_prod?authSource=admin
MONGO_INITDB_ROOT_USERNAME: ${MONGO_INITDB_ROOT_USERNAME:-formadmin}
MONGO_INITDB_ROOT_PASSWORD: ${MONGO_INITDB_ROOT_PASSWORD:?set MONGO_INITDB_ROOT_PASSWORD in your environment}
```

### SEC-08
- Title: Per-instance in-memory rate-limit fallback
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/services/rate_limit.py`](/home/ravi/workspace/new/form/app/services/rate_limit.py)
- Evidence:
```python
class RateLimitService:
    cache = {}
```
- Exact fix needed: move the fallback cache to a shared singleton or inject a shared store from the app factory.

### SEC-09
- Title: Rate limit decorators fail open on Redis errors
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/middleware/rate_limit.py:13-263`](/home/ravi/workspace/new/form/app/middleware/rate_limit.py#L13)
- Evidence:
```python
except (..., redis.RedisError) as e:
    response.status_code = 503
    return response
```
- Exact fix needed: decide and document fail-open vs fail-closed behavior, then test it.

### SEC-10
- Title: Redis window reset bug
- Severity: Medium
- Status: FIXED
- Citation: [`app/services/rate_limit.py:154-210`](/home/ravi/workspace/new/form/app/services/rate_limit.py#L154)
- Evidence:
```python
self.redis_client.delete(key)
self.redis_client.delete(ts_key)
window_ts = None
```

### SEC-11
- Title: `ConditionEvaluationStat` grows unboundedly without TTL
- Severity: Medium
- Status: FIXED
- Citation: [`app/models/condition_management.py:117-135`](/home/ravi/workspace/new/form/app/models/condition_management.py#L117)
- Evidence:
```python
{"fields": ["created_at"], "expireAfterSeconds": 60 * 60 * 24 * 30},
```

### SEC-12
- Title: Predictable JWT secret placeholder in `.env.example`
- Severity: Low
- Status: STILL OPEN
- Citation: [`.env.example:1-40`](/home/ravi/workspace/new/form/.env.example#L1)
- Evidence:
```env
JWT_SECRET_KEY=change-this-in-production
```
- Exact fix needed: replace placeholder with a generated-secret example and keep the warning.

### SEC-13
- Title: `AuthorizationHeader.Authorization` minimum length too low
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/auth.py:35-37`](/home/ravi/workspace/new/form/app/schemas/auth.py#L35)
- Evidence:
```python
Authorization: str = Field(min_length=10)
```
- Exact fix needed: validate the `Bearer ` prefix and raise the minimum length or enforce token-length separately.

### SEC-14
- Title: Access-token revocation is impossible by design
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/models/auth.py:86-96`](/home/ravi/workspace/new/form/app/models/auth.py#L86)
- Evidence:
```python
token_type = db.StringField(choices=("refresh",), default="refresh")
```
- Exact fix needed: document the limitation or extend the blocklist model to support access tokens.

### SEC-15
- Title: Hash algorithm for session/blocklist hashes undocumented
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/models/auth.py:1-96`](/home/ravi/workspace/new/form/app/models/auth.py#L1)
- Evidence:
```python
refresh_token_hash = db.StringField(required=True)
token_hash = db.StringField(required=True, unique=True)
```
- Exact fix needed: add a module comment documenting the hashing algorithm used by `services/auth.py`.

### SEC-16
- Title: Hardcoded JWT test secret
- Severity: Low
- Status: STILL OPEN
- Citation: [`tests/conftest.py:60-90`](/home/ravi/workspace/new/form/tests/conftest.py#L60)
- Evidence:
```python
"JWT_SECRET_KEY": "test-secret-key-do-not-use-in-production",
```
- Exact fix needed: generate a per-session secret for test isolation.

### PERF-01
- Title: Rotating logger emits many events per request
- Severity: High
- Status: STILL OPEN
- Citation: [`app/middleware/rotating_logger_middleware.py`](/home/ravi/workspace/new/form/app/middleware/rotating_logger_middleware.py)
- Evidence: current middleware still performs repeated before/after logging calls for each request.
- Exact fix needed: consolidate to fewer structured logs and reduce per-request I/O.

### PERF-02
- Title: `monitoring_dashboard_snapshot` triggers multiple collection scans
- Severity: High
- Status: STILL OPEN
- Citation: [`app/services/condition_management_monitoring.py:29-95`](/home/ravi/workspace/new/form/app/services/condition_management_monitoring.py#L29)
- Evidence:
```python
rows = ConditionEvaluationStat.objects(created_at__gte=since)
all_condition_uuids = [c.uuid for c in Condition.objects]
for condition in Condition.objects:
```
- Exact fix needed: cache or reuse the snapshot and avoid repeated full scans.

### PERF-03
- Title: `build_dependency_graph` scans all conditions on every call
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/services/condition_management_graph.py:10-19`](/home/ravi/workspace/new/form/app/services/condition_management_graph.py#L10)
- Evidence:
```python
for condition in Condition.objects:
```
- Exact fix needed: cache the graph and invalidate on writes.

### PERF-04
- Title: Redis rate-limit window never resets
- Severity: High
- Status: FIXED
- Citation: [`app/services/rate_limit.py:154-210`](/home/ravi/workspace/new/form/app/services/rate_limit.py#L154)
- Evidence:
```python
self.redis_client.delete(ts_key)
window_ts = None
```

### PERF-05
- Title: `_persisted_state()` does an extra query on every save
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/models/form.py:1-120`](/home/ravi/workspace/new/form/app/models/form.py#L1)
- Evidence:
```python
def _persisted_state(instance, field_name):
    ...
```
- Exact fix needed: cache the pre-save state or avoid re-querying in `clean()`.

### PERF-06
- Title: `discover_usage()` full collection scan
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/services/condition_management_analysis.py:16-42`](/home/ravi/workspace/new/form/app/services/condition_management_analysis.py#L16)
- Evidence:
```python
for condition in Condition.objects:
```
- Exact fix needed: cache usage graph results and invalidate on condition writes.

### PERF-07
- Title: `paginate_items()` loads and sorts the full collection in memory
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/api/resources_utils.py`](/home/ravi/workspace/new/form/app/api/resources_utils.py)
- Evidence: current code still provides in-memory pagination paths for Mongo-backed resources.
- Exact fix needed: switch Mongo-backed callers to DB-side pagination.

### PERF-08
- Title: Negative-cache eviction leaves bloom-filter state behind
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/services/condition_cache.py`](/home/ravi/workspace/new/form/app/services/condition_cache.py)
- Evidence: the cache implementation still maintains a bloom-filter-backed negative cache path.
- Exact fix needed: clear bloom state on eviction or replace the structure with a simpler TTL cache.

### PERF-09
- Title: Async condition evaluation busy-polls
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/services/condition_management_async.py:183-216`](/home/ravi/workspace/new/form/app/services/condition_management_async.py#L183)
- Evidence:
```python
while datetime.now(timezone.utc) < deadline:
    ...
    time.sleep(0.02)
```
- Exact fix needed: use `threading.Event.wait()` or similar blocking wait.

### PERF-10
- Title: `OPTIONS` requests are counted in observability metrics
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/middleware/observability.py:35-90`](/home/ravi/workspace/new/form/app/middleware/observability.py#L35)
- Evidence:
```python
_metrics_state.requests_total += 1
_metrics_state.responses_by_status[str(response.status_code)] += 1
```
- Exact fix needed: exclude preflight `OPTIONS` if that is the intended metrics policy.

### BUG-01
- Title: Redis rate-limit window reset never wrote a new timestamp
- Severity: Critical
- Status: FIXED
- Citation: [`app/services/rate_limit.py:154-210`](/home/ravi/workspace/new/form/app/services/rate_limit.py#L154)
- Evidence:
```python
window_ts = None
```

### BUG-02
- Title: Approval state stored in `metadata` instead of model field
- Severity: High
- Status: STILL OPEN
- Citation: [`app/services/condition_management_approval.py`](/home/ravi/workspace/new/form/app/services/condition_management_approval.py)
- Evidence: current approval-transition path still writes approval state into `condition.metadata`.
- Exact fix needed: write the model field as the single source of truth and keep metadata in sync only if needed.

### BUG-03
- Title: Restoring versions drops `subConditions`
- Severity: High
- Status: STILL OPEN
- Citation: [`app/services/condition_management_versioning.py:50-76`](/home/ravi/workspace/new/form/app/services/condition_management_versioning.py#L50)
- Evidence:
```python
data = copy.deepcopy(version_entry.snapshot)
for key, value in data.items():
    setattr(item, key, value)
```
- Exact fix needed: verify the snapshot includes logical-tree references and preserve nested condition structure.

### BUG-04
- Title: Version rollback parsing strips all `v` characters
- Severity: Medium
- Status: FIXED
- Citation: [`app/services/condition_management_versioning.py:113-126`](/home/ravi/workspace/new/form/app/services/condition_management_versioning.py#L113)
- Evidence:
```python
version_number = int(str(version_id).lstrip("v"))
```

### DEAD-01
- Title: `Version.clean()` uppercase `DISABLED` branch
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/models/form.py:139-144`](/home/ravi/workspace/new/form/app/models/form.py#L139)
- Evidence:
```python
if self.status == "DISABLED":
    self.status = "disabled"
```
- Exact fix needed: remove the dead branch or normalize status values before validation.

### DEAD-02
- Title: `ResponseItem` lifecycle fields never used
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/models/form.py:147-220`](/home/ravi/workspace/new/form/app/models/form.py#L147)
- Evidence: the model still defines lifecycle fields that are not read elsewhere in current source.
- Exact fix needed: remove or repurpose the unused fields.

### DEAD-03
- Title: `FormResponse` duplicate lifecycle fields
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/models/form.py:147-220`](/home/ravi/workspace/new/form/app/models/form.py#L147)
- Evidence: the same approval lifecycle fields exist on `FormResponse`.
- Exact fix needed: keep only the fields actually used by the response workflow.

### DEAD-04
- Title: Empty pass-through `ActionStepInput`
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/action.py:32-33`](/home/ravi/workspace/new/form/app/schemas/action.py#L32)
- Evidence:
```python
class ActionStepInput(ActionStepBase):
    pass
```
- Exact fix needed: collapse to the base schema if no behavior differs.

### DEAD-05
- Title: `ActionDefinitionOutput` re-declares base fields
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/schemas/action.py:69-82`](/home/ravi/workspace/new/form/app/schemas/action.py#L69)
- Evidence:
```python
class ActionDefinitionOutput(SchemaModel):
    id: str
    label: str
    ...
```
- Exact fix needed: inherit from the base schema and only override what differs.

### DEAD-06
- Title: `BulkTestInput` duplicates `BatchConditionTestInput`
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/condition_management.py:79-80`](/home/ravi/workspace/new/form/app/schemas/condition_management.py#L79)
- Evidence:
```python
class BulkTestInput(SchemaModel):
    tests: List[ConditionTestInput] = Field(default_factory=list)
```
- Exact fix needed: deduplicate onto the shared batch input schema.

### DEAD-07
- Title: `BulkImportConditionsInput` duplicates `BulkCreateConditionInput`
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/condition_management.py`](/home/ravi/workspace/new/form/app/schemas/condition_management.py)
- Evidence: same wrapper-pattern duplication remains in current schema module.
- Exact fix needed: merge or alias the shared create input.

### DEAD-08
- Title: Legacy flat-action fields still present on questions
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/schemas/question.py:37-47`](/home/ravi/workspace/new/form/app/schemas/question.py#L37)
- Evidence:
```python
isAction: bool = False
actionButtonType: Optional[str] = None
actionType: Optional[str] = None
actionLabel: Optional[str] = None
hideButton: bool = False
actionIcon: Optional[str] = None
```
- Exact fix needed: remove the legacy aliases if current clients no longer rely on them.

### DEAD-09
- Title: Empty pass-through `ResponseItemCreateInput`
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/response_item.py:19-20`](/home/ravi/workspace/new/form/app/schemas/response_item.py#L19)
- Evidence:
```python
class ResponseItemCreateInput(ResponseItemBase):
    pass
```
- Exact fix needed: collapse to the base schema or add differentiated behavior.

### DEAD-10
- Title: Empty pass-through `ResponseItemOutput`
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/response_item.py`](/home/ravi/workspace/new/form/app/schemas/response_item.py)
- Evidence: output wrapper remains a thin alias with no extra fields.
- Exact fix needed: collapse to the shared base if no output-specific fields are required.

### DEAD-11
- Title: Empty pass-through UI template schemas
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/ui_template.py`](/home/ravi/workspace/new/form/app/schemas/ui_template.py)
- Evidence: multiple create/update/output wrapper classes remain with no differing fields.
- Exact fix needed: remove the redundant wrappers or explain their distinct API roles.

### DEAD-12
- Title: `SoftDeleteOutput` unused
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/common.py:26-28`](/home/ravi/workspace/new/form/app/schemas/common.py#L26)
- Evidence:
```python
class SoftDeleteOutput(SchemaModel):
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
```
- Exact fix needed: import and use it where soft-delete responses are emitted, or remove it.

### DEAD-13
- Title: `external_provider` parameter never called
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/services/condition_evaluator.py:498-502`](/home/ravi/workspace/new/form/app/services/condition_evaluator.py#L498)
- Evidence:
```python
result = evaluate_expression(condition.expression, self.context)
```
- Exact fix needed: either wire the provider into evaluation or remove the dead parameter.

### DEAD-14
- Title: Logical OR `stopEvaluationIfTrue` branch is redundant
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/services/condition_evaluator.py:459-496`](/home/ravi/workspace/new/form/app/services/condition_evaluator.py#L459)
- Evidence:
```python
if sub_result:
    if getattr(sub, "stopEvaluationIfTrue", False):
        return True
    return True
```
- Exact fix needed: make short-circuiting explicit or remove the dead branch.

### DEAD-15
- Title: `RequestLevelCache._start_time` unused
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/services/condition_cache.py`](/home/ravi/workspace/new/form/app/services/condition_cache.py)
- Evidence: the cache class still carries an initialization timestamp that is not read.
- Exact fix needed: remove the field or use it in eviction/TTL calculations.

### DEAD-16
- Title: `log_audit` uses `.id` for resource identifiers
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/services/logging/decorators.py:93-132`](/home/ravi/workspace/new/form/app/services/logging/decorators.py#L93)
- Evidence:
```python
elif hasattr(result, "id"):
    resource_id = str(result.id)
```
- Exact fix needed: prefer `uuid` and only fall back to `id` if explicitly intended.

### DEAD-17
- Title: Legacy `isAction` branch in mapper
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/schemas/mappers.py`](/home/ravi/workspace/new/form/app/schemas/mappers.py)
- Evidence: mapper still includes compatibility logic for `isAction`.
- Exact fix needed: remove the branch if no current model emits it.

### DUP-01
- Title: `_utcnow()` duplicated across auth modules
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/services/auth.py`, `app/api/auth_support.py`, `app/api/auth.py`](/home/ravi/workspace/new/form/app/services/auth.py#L1)
- Evidence: identical UTC helper pattern remains in the three modules.
- Exact fix needed: centralize the helper if the duplication is no longer desired.

### DUP-02
- Title: `utcnow()` duplicated across modules
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/services/security.py`, `app/models/rate_limit.py`, `app/models/user.py`, `scripts/init_rate_limits.py`](/home/ravi/workspace/new/form/app/services/security.py#L1)
- Evidence: module-local UTC helpers remain in all four locations.
- Exact fix needed: either keep as a deliberate pattern or extract a shared helper.

### DUP-03
- Title: `_client_ip()` duplicated
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/api/auth_support.py`, `app/api/resources_utils.py`](/home/ravi/workspace/new/form/app/api/auth_support.py#L1)
- Evidence: identical client-IP helper exists in both modules.
- Exact fix needed: consolidate if the duplication is not intentional.

### DUP-04
- Title: `ErrorResponse` schema duplicated
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/schemas/auth.py`, `app/schemas/condition_management.py`](/home/ravi/workspace/new/form/app/schemas/auth.py#L1)
- Evidence: the same error schema is still defined in two schema modules.
- Exact fix needed: keep one canonical definition and import it elsewhere.

### DUP-05
- Title: Pagination helpers are near duplicates
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/api/resources_utils.py`](/home/ravi/workspace/new/form/app/api/resources_utils.py)
- Evidence: both in-memory and queryset pagination helpers remain.
- Exact fix needed: keep the DB-side path as the default where possible.

### DUP-06
- Title: Repeated `save()` timestamp override
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/models/*.py`](/home/ravi/workspace/new/form/app/models/form.py#L1)
- Evidence: the model layer still repeats the same `updated_at` save pattern.
- Exact fix needed: consolidate only if it improves clarity without adding inheritance complexity.

### DUP-07
- Title: Cursor encode/decode duplication
- Severity: Low
- Status: STILL OPEN
- Citation: [`app/api/auth_support.py`, `app/api/resources_utils.py`](/home/ravi/workspace/new/form/app/api/auth_support.py#L1)
- Evidence: both cursor helper pairs remain present.
- Exact fix needed: share a common cursor utility if their semantics are identical.

### DUP-08
- Title: Repeated 429 response construction
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/middleware/rate_limit.py`, `app/api/resources_utils.py`](/home/ravi/workspace/new/form/app/middleware/rate_limit.py#L13)
- Evidence: the 429 response shape is still built in multiple places.
- Exact fix needed: extract a shared helper for the payload and headers.

### TECH-01
- Title: `ConditionEvaluationStat` TTL policy
- Severity: Medium
- Status: FIXED
- Citation: [`app/models/condition_management.py:117-135`](/home/ravi/workspace/new/form/app/models/condition_management.py#L117)
- Evidence:
```python
{"fields": ["created_at"], "expireAfterSeconds": 60 * 60 * 24 * 30},
```

### TECH-02
- Title: Async condition jobs still need durable queueing
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/services/condition_management_async.py:1-216`](/home/ravi/workspace/new/form/app/services/condition_management_async.py#L1)
- Evidence: queue is bounded now, but it is still in-memory.
- Exact fix needed: move to a durable external queue if multi-worker scale-out is required.

### TECH-03
- Title: `app/middleware/rate_limit.py` compatibility limitations
- Severity: Medium
- Status: STILL OPEN
- Citation: [`app/middleware/rate_limit.py:13-263`](/home/ravi/workspace/new/form/app/middleware/rate_limit.py#L13)
- Evidence: the middleware remains a decorator shim.
- Exact fix needed: keep documenting the `flask-openapi3` limitation or replace the compatibility layer.

### TECH-04
- Title: Duplicated UTC helper patterns remain deferred
- Severity: Low
- Status: STILL OPEN
- Citation: [`TECHNICAL_DEBT.md`](/home/ravi/workspace/new/form/TECHNICAL_DEBT.md)
- Evidence: the note itself still calls out duplicated UTC helpers as deferred work.
- Exact fix needed: either leave as intentional duplication or consolidate the helpers.

## Newly Discovered Issues

No additional critical/high issues were found beyond the items already captured above during this audit pass.

## Prioritized STILL OPEN List

1. `SEC-01` - Harden `_evaluate_custom_condition` against untrusted context traversal.
2. `SEC-05` - Validate JWT `kid` before key lookup.
3. `SEC-06` - Add key-expiry policy for additional JWT keys.
4. `SEC-08` - Share the in-memory rate-limit fallback cache.
5. `SEC-09` - Decide and test Redis error handling policy for rate limits.
6. `PERF-01` - Reduce rotating-logger per-request logging overhead.
7. `PERF-02` - Cache monitoring snapshots and avoid repeated scans.
8. `PERF-03` - Cache dependency graphs.
9. `PERF-05` - Remove the extra save-time query from `_persisted_state()`.
10. `PERF-06` - Cache usage analysis results.
11. `PERF-07` - Switch Mongo-backed pagination to DB-side pagination.
12. `PERF-08` - Repair negative-cache bloom-filter eviction.
13. `PERF-09` - Replace async busy-polling with blocking wait.
14. `PERF-10` - Decide whether to exclude `OPTIONS` from metrics.
15. `BUG-02` - Make approval state use one source of truth.
16. `BUG-03` - Preserve sub-condition trees on version restore.
17. `DEAD-01` - Remove the dead uppercase status branch.
18. `DEAD-04` - Collapse pass-through action-step schemas.
19. `DEAD-08` - Remove legacy flat-action fields if unused.
20. `DUP-08` - Extract shared 429 response construction.

