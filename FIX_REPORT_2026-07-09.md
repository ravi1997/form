# Fix Report
- Audited commit: `3481b1ec50cbe7238fd0810b6a0e03274890befb`
- Date: `2026-07-09`
- Final pytest: `339 passed, 0 failed`

## Items

| ID | Action | File/line | Pytest result | Reason |
|---|---|---|---|---|
| SEC-06 | FIXED | [app/config.py](./app/config.py), [app/services/auth.py](./app/services/auth.py) | `339 passed` | |
| SEC-09 | FIXED | [app/middleware/rate_limit.py](./app/middleware/rate_limit.py), [tests/test_rate_limit_service.py](./tests/test_rate_limit_service.py) | `339 passed` | |
| PERF-01 | DEFERRED | [app/middleware/rotating_logger_middleware.py](./app/middleware/rotating_logger_middleware.py) | `339 passed` | Low-confidence refactor with no direct behavioral bug, and the middleware already has broad per-request logging coverage that would need coordinated logging-policy review. |
| PERF-02 | FIXED | [app/services/condition_management_monitoring.py:47-124](./app/services/condition_management_monitoring.py#L47) | `339 passed` | |
| PERF-03 | FIXED | [app/services/condition_management_graph.py:11-29](./app/services/condition_management_graph.py#L11) | `339 passed` | |
| PERF-05 | FIXED | [app/models/form.py:100-111](./app/models/form.py#L100) | `339 passed` | |
| PERF-06 | FIXED | [app/services/condition_management_analysis.py:18-54](./app/services/condition_management_analysis.py#L18) | `339 passed` | |
| PERF-07 | DEFERRED | [app/api/resources_utils.py](./app/api/resources_utils.py) | `339 passed` | Switching all Mongo-backed pagination callers to DB-side pagination touches several resource endpoints and response shapes, so it was deferred to avoid scope creep in this pass. |
| PERF-08 | DEFERRED | [app/services/condition_cache.py](./app/services/condition_cache.py) | `339 passed` | The negative-cache bloom-filter behavior needs a structural redesign or replacement, and I did not have a safe minimal change that preserved the current cache semantics. |
| BUG-02 | FIXED | [app/services/condition_management_approval.py:38-106](./app/services/condition_management_approval.py#L38) | `339 passed` | |
| BUG-03 | DEFERRED | [app/services/condition_management_versioning.py](./app/services/condition_management_versioning.py) | `339 passed` | I did not find a regression test that proved the sub-condition tree loss path end to end, and changing version restore logic without that confirmation risked breaking existing restore semantics. |
| DEAD-04 | DEFERRED | [app/schemas/action.py:32-33](./app/schemas/action.py#L32) | `339 passed` | This is a low-value schema cleanup and collapsing it would be purely stylistic with no behavioral gain. |
| DEAD-05 | DEFERRED | [app/schemas/action.py:69-82](./app/schemas/action.py#L69) | `339 passed` | The duplicate action-definition output schema is still serving API compatibility, and merging it would require checking every downstream consumer. |
| DEAD-08 | DEFERRED | [app/schemas/question.py:37-47](./app/schemas/question.py#L37) | `339 passed` | The flat action aliases are legacy compatibility fields, so removing them now would need a broader client-contract audit than this pass allows. |
| DEAD-09 | DEFERRED | [app/schemas/response_item.py:19-20](./app/schemas/response_item.py#L19) | `339 passed` | This wrapper is redundant but harmless, and collapsing it would not materially improve behavior. |
| DEAD-10 | DEFERRED | [app/schemas/response_item.py](./app/schemas/response_item.py) | `339 passed` | I did not have a distinct output-specific behavior to preserve, so the wrapper was left in place rather than guessed away. |
| DEAD-11 | DEFERRED | [app/schemas/ui_template.py](./app/schemas/ui_template.py) | `339 passed` | These template wrappers are thin aliases, but I did not verify that every API consumer can absorb a schema flattening safely. |
| DEAD-12 | DEFERRED | [app/schemas/common.py:26-28](./app/schemas/common.py#L26) | `339 passed` | The soft-delete output type may still be intended for future or external use, and I did not have a proven unused call path to justify removal. |
| DEAD-13 | DEFERRED | [app/services/condition_evaluator.py:498-502](./app/services/condition_evaluator.py#L498) | `339 passed` | I could not confirm the `external_provider` parameter is dead across all evaluator entry points, so I left it untouched. |
| DEAD-14 | DEFERRED | [app/services/condition_evaluator.py:459-496](./app/services/condition_evaluator.py#L459) | `339 passed` | The branch is redundant but harmless, and changing the short-circuit logic would be a readability-only cleanup with no functional win. |
| DEAD-16 | DEFERRED | [app/services/logging/decorators.py:93-132](./app/services/logging/decorators.py#L93) | `339 passed` | The resource-id fallback to `.id` may still be needed for non-UUID models, so I did not narrow it without a broader audit. |
| DEAD-17 | DEFERRED | [app/schemas/mappers.py](./app/schemas/mappers.py) | `339 passed` | The `isAction` mapper branch is legacy compatibility logic and removing it would require a full contract sweep I did not perform here. |
| DUP-01 | DEFERRED | [app/services/auth.py](./app/services/auth.py), [app/api/auth_support.py](./app/api/auth_support.py), [app/api/auth.py](./app/api/auth.py) | `339 passed` | Centralizing the UTC helper would add an extra shared dependency across auth modules without a clear runtime benefit. |
| DUP-02 | DEFERRED | [app/services/security.py](./app/services/security.py), [app/models/rate_limit.py](./app/models/rate_limit.py), [app/models/user.py](./app/models/user.py), [scripts/init_rate_limits.py](./scripts/init_rate_limits.py) | `339 passed` | The duplicated UTC helper is a small local pattern across separate runtime and script entry points, and consolidating it would not remove meaningful risk. |
| DUP-03 | DEFERRED | [app/api/auth_support.py](./app/api/auth_support.py), [app/api/resources_utils.py](./app/api/resources_utils.py) | `339 passed` | The client-IP helper is tiny and context-specific, so a shared utility would add indirection for little gain. |
| DUP-04 | DEFERRED | [app/schemas/auth.py](./app/schemas/auth.py), [app/schemas/condition_management.py](./app/schemas/condition_management.py) | `339 passed` | I did not want to collapse the duplicate error schema without checking every import site and schema export path. |
| DUP-05 | DEFERRED | [app/api/resources_utils.py](./app/api/resources_utils.py) | `339 passed` | The pagination helpers are already split by data source, and unifying them would blur the in-memory versus queryset behavior. |
| DUP-06 | DEFERRED | [app/models/form.py](./app/models/form.py) | `339 passed` | Repeated `updated_at` save overrides are intentionally simple per model, and extracting inheritance just for that pattern would add complexity. |
| DUP-07 | DEFERRED | [app/api/auth_support.py](./app/api/auth_support.py), [app/api/resources_utils.py](./app/api/resources_utils.py) | `339 passed` | The cursor helpers are similar but not proven identical enough to merge safely without validating all pagination call sites. |
| DUP-08 | DEFERRED | [app/middleware/rate_limit.py](./app/middleware/rate_limit.py), [app/api/resources_utils.py](./app/api/resources_utils.py) | `339 passed` | The 429 responses are built in separate layers with slightly different context, so I left them separate instead of forcing a shared helper. |
| TECH-02 | DEFERRED | [app/services/condition_management_async.py](./app/services/condition_management_async.py) | `339 passed` | Moving the async queue to durable infrastructure is an architectural decision that depends on deployment scope outside this pass. |
| TECH-03 | DEFERRED | [app/middleware/rate_limit.py](./app/middleware/rate_limit.py) | `339 passed` | The middleware compatibility shim is still needed for current OpenAPI integration constraints, so replacing it would be a broader compatibility project. |
| TECH-04 | DEFERRED | [TECHNICAL_DEBT.md](./TECHNICAL_DEBT.md) | `339 passed` | I did not have a code change to make here, and the remaining guidance is documentation-level debt rather than a contained fix. |

## Notes

- `SEC-01`, `SEC-05`, `SEC-08`, `SEC-12`, `SEC-13`, `SEC-14`, `SEC-15`, `SEC-16`, `DEAD-01`, `PERF-10` were already verified in the earlier pass and remain green under the final `pytest` run.
- `PERF-02`, `PERF-03`, `PERF-05`, `PERF-06`, and `BUG-02` were the only additional code changes made in this continuation.
