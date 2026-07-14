
# Project Documentation — Multi-Tenant Low-Code SaaS Platform

**Purpose of this document:** complete context transfer for any LLM/agent picking up work on this project. Everything here reflects what has actually been confirmed through live inventories, discovery passes, and verification audits — not assumptions. Where something is a decision vs. an open question vs. unconfirmed, it's marked explicitly. Do not treat anything marked "unconfirmed" or "open decision" as settled fact.

---

## 1. Project Overview

A Flutter-based, multi-tenant, low-code SaaS platform, conceptually similar to Retool, Appsmith, Notion databases, React Flow builders, and Power BI dashboard editors — but fully Flutter-native. Backend is Python/Flask with MongoDB. Targets thousands of tenants at launch scale, with GDPR, HIPAA, and SOC2 compliance requirements.

**Team structure:** solo operator directing multiple AI coding agents working in parallel on a substantial pre-existing codebase, not a traditional human team. This shapes process heavily (see Section 9) — contracts between modules need to be frozen and typed before parallel agent work starts, since agents don't drift-correct ambiguity the way a human team does in standup.

**Core product concept:** three visual builders and two runtime renderers:

- **Form Builder** — drag/drop form design: nested sections, conditional visibility/branching, dynamic question types, reusable components. Output: FormSchema JSON.
- **Analytics Builder** — node-graph DAG editor: data sources, transformations, filters, aggregations, custom logic blocks as nodes; edges represent data flow. Output: DAG execution graph JSON, executed server-side.
- **Dashboard Builder** — drag/drop dashboard composition: KPI cards, tables, charts, images, custom widgets; grid or free layout. Output: DashboardSchema JSON.
- **Form Renderer** — renders published FormSchema for end users to fill out; handles conditional logic/validation at runtime.
- **Dashboard Renderer** — renders published DashboardSchema with live data, charts via `graphic`.

This document uses placeholder names only; the final product name is defined in `brand.md`.

---

## 2. Tech Stack

| Layer                   | Technology                                                                                                   | Notes                                                                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Frontend                | Flutter (Dart)                                                                                               | Targets mobile + web + desktop simultaneously                                                                                  |
| Frontend state          | Riverpod (`flutter_riverpod`)                                                                              | Confirmed real usage,`AsyncNotifier` pattern present                                                                         |
| Frontend routing        | `go_router`                                                                                                |                                                                                                                                |
| Frontend HTTP           | `dio`                                                                                                      |                                                                                                                                |
| Frontend storage        | `flutter_secure_storage` (JWT), `shared_preferences` (theme/tenant), Hive (published-form offline cache) | No`sqflite` in use                                                                                                           |
| Frontend node/canvas    | `vyuh_node_flow` (v0.27.3 confirmed in pubspec)                                                            | Used for Analytics Builder canvas                                                                                              |
| Frontend forms runtime  | `formstack` (v2.5.0 confirmed)                                                                             | Step-based rendering primitive, NOT a full conditional/nested engine — see Section 7                                          |
| Frontend charts         | `graphic` (v2.7.0 confirmed)                                                                               | Grammar-of-graphics charting library                                                                                           |
| Backend framework       | Flask (Python)                                                                                               | Hybrid: legacy monolith + newer blueprints, see Section 4.1                                                                    |
| Backend DB              | MongoDB                                                                                                      | Single shared cluster,`organization_id`-based multi-tenancy (standardized from a prior `org_id`/`organization_id` split) |
| Backend auth            | Custom JWT (`PyJWT`) + API-key auth                                                                        | See Section 4.3                                                                                                                |
| Backend background jobs | APScheduler (confirmed live for scheduled work) + Celery (confirmed live, used for Analytics DAG execution)  | RQ-style Redis helpers also present but not confirmed as the primary path                                                      |
| Backend docs            | `flasgger` (Swagger/OpenAPI), live at `/apidocs/`                                                        |                                                                                                                                |
| Backend observability   | OpenTelemetry (SDK + Flask instrumentation + OTLP exporter)                                                  |                                                                                                                                |
| Backend storage/export  | `boto3` (S3), `reportlab` (PDF)                                                                          |                                                                                                                                |
| Dev orchestration       | Docker Compose (`docker-compose.dev.yml`) via `make dev-d`                                               | See Section 4.9 for full service list                                                                                          |

---

## 3. Architecture Principles (locked decisions)

- **JSON-first design**: Forms, Analytics graphs, and Dashboards all serialize to JSON as the source of truth; the canvas/builder UI is only an editor for that JSON, never itself authoritative.
- **Separation of concerns**: Builder UI state, schema/domain state, renderer engine, and backend contract layer are kept distinct. Frontend specifically splits into three Riverpod-level stores: `SchemaStore` (persisted document), `BuilderUiStore` (ephemeral: selection/viewport/hover), `HistoryStore` (undo/redo stack, decoupled from both).
- **Plugin-based component system**: every builder supports pluggable node/field/widget types via a `PluginDescriptor`/`PluginRegistry` pattern (id, version, displayName, capabilities, defaultConfig, configSchema, runtimeBuilder). Frontend implementation confirmed built at `lib/src/core/plugin_registry.dart`, already refactored into the Form Builder's icon/behavior lookups (replacing old switch-statements).
- **Command-pattern undo/redo**: `SchemaCommand` objects (`apply()`/`invert()`) pushed to a `HistoryStore`, with command coalescing for continuous operations (e.g., one history entry per completed drag gesture, not per frame). Confirmed built and wired into the Form Builder canvas.
- **Cross-platform input abstraction**: `CanvasInputController` (`lib/src/core/canvas_input_controller.dart`) unifies touch/mouse/desktop pointer handling for canvas/drag/selection interactions — confirmed built and applied to Form Builder drop zones and selection rows.
- **Two different versioning philosophies coexist deliberately**:
  - **Forms**: git-style versioning — commits, hashes, branches, merge (`mergeBranch()`, `commitSchema()`, `activeBranch`, `commitLogs`). This was a pre-existing, deliberate product feature discovered during codebase inventory, NOT something the newer architecture work introduced — it was explicitly preserved rather than replaced.
  - **Analytics and Dashboard schemas** (new, built during this project): simple `entityVersion` optimistic-concurrency field. Save requires the client's loaded `entityVersion`; server does an atomic `find_one_and_update` with the version in the filter; mismatch returns 409 with the current server copy. (This was initially implemented as a non-atomic read-then-write — a real race condition — and was fixed in a remediation round; confirmed atomic now.)
- **Tenant isolation**: single shared MongoDB cluster, `organization_id` field on every document (standardized; a legacy `org_id` naming split existed on ~7 collections and was migrated). A `TenantScopedCollection`/`TenantScopedDatabase` wrapper injects `organization_id` from the validated JWT automatically — confirmed built, confirmed still has some bypasses in less-trafficked route handlers (partial adoption as of last verification). Tenant identity is derived ONLY from the validated JWT claim — two dangerous fallback paths (a silent `"default_org"` default, and a query-parameter fallback) were found and removed during remediation.

---

## 4. Backend Documentation

### 4.1 Codebase structure

Hybrid, not a clean single app:

- `app.py` — bootstrap; imports and reuses `builder_app.app`; registers blueprints.
- `builder_app.py` — large legacy monolith; still hosts significant live functionality (projects, dashboards routes, DAG execution wiring, audit logging).
- `blueprints/` — newer, better-organized modules: `auth_routes.py`, `analysis_routes.py`, `response_routes.py`, `form_routes.py`, `schema_routes.py`, `webhook_routes.py`.
- `routes/` — gateway-style blueprints: `forms.py`, `responses.py`, `sync.py` (named `gateway_forms`, `gateway_responses`, `gateway_sync` — intended to become a broader entry point for workspace navigation, integrations, and operational access).
- Two overlapping app styles coexist (legacy monolith + newer blueprints) — this is a known, unresolved architectural seam, not fully consolidated.
- **Important namespace inconsistency**: most routes live under `/api/v1/...`, but legacy project endpoints still appear outside that namespace. The target direction is `/api/v1/projects/...`; older project paths should be treated as legacy and removed from the product direction.

### 4.2 MongoDB collections (confirmed via live inventory)

`projects`, `forms`, `themes`, `responses`, `commits`, `token_revocations`, `users`, `api_keys`, `analysis_definitions`, `analysis_results`, `webhooks`, `tasks`, `notifications`, `upload_registry`, `lookup_materialized_views`, `workflow_runs`, `failed_workflow_runs`, `search_history`, `organizations`, `idempotency_keys`, `storage_quotas`, `update_history`, `update_queue`, `compliance_standards`, `notification_templates`, `feature_flags`, `feature_flag_overrides`, `tenant_compliance`, `compliance_records`, `compliance_audits`, `compliance_evidence`, `data_processing_records`, `audit_logs`.

Key field shapes confirmed: `forms` has `_id, project_id, organization_id, theme_id, deleted, is_public, access_policy, versions, sections, questions, encrypted_dek, updated_at`; `responses` has `_id, form_id, organization_id, status, submitted_at, answers, ai_results, updated_at`.

### 4.3 Authentication & Authorization

- Custom JWT via `AuthManager.generate_tokens()`. Access token claims: `user_id, sub, organization_id, roles, token_type, iat, jti, exp`.
- Login accepts multiple identifier types: `username`, `email`, `identifier`, `employee_id`, or `mobile`+`otp`.
- Confirmed login response envelope: `{"status": "success", "message": "...", "data": {"access_token", "refresh_token", "token_type", "expires_in": 900, "user": {...}}}`. **Not confirmed universal** — other endpoints may return bare objects; check per-endpoint.
- Token refresh: `POST /api/v1/auth/refresh` with `{"refresh_token": "..."}`, returns the same envelope.
- API-key auth exists as an alternative/parallel path (`X-API-Key` header) for integrations (e.g., webhooks) — maps to an `api_keys` document with `organization_id`.
- Role system: `superadmin`, `admin`, `editor`, `viewer`, `reviewer`, `approver`, `submitter` at the backend (`ROLE_PERMISSIONS`). Legacy role wording should be treated as invalid and replaced throughout docs and concept notes.
- Password hashing: PBKDF2-HMAC-SHA256. Originally used a static salt (a real security gap); fixed to per-user random salts with a lazy rehash-on-login migration path.
- **Regression history**: a Mongo-permissions fix intended to lock down `audit_logs` deletion (see 4.6) initially over-restricted the app's DB service account and broke login/register entirely (500 errors, `not authorized on form_analyser to execute command { find: "users", ...}`). This was identified and a fix was requested; confirm current status before assuming auth works end-to-end.
- Confirmed error response shapes are **inconsistent across the backend** — at least three different shapes seen live: `{"message": "...", "status": "error"}`, `{"error": "Invalid or expired token"}`, `{"error": "Authorization token required"}`. Frontend must parse defensively (check `message`, then `error`, then fall back to generic).

### 4.4 Tenant Isolation

- `organization_id` field, standardized (migrated from a mixed `org_id`/`organization_id` naming split — migration script exists and tested; confirmed run in the last verification, with live-read-code updated to match).
- `TenantScopedCollection`/`TenantScopedDatabase` wrapper confirmed built and used by the legacy repository layer and several route handlers — **confirmed still bypassed by other handlers in less-trafficked areas** as of the last audit; not 100% adopted.
- Per-tenant DB isolation is not part of the target product direction.
- An `X-Tenant-Workspace` header is not part of the target product direction and should be removed from the product model.
- Several originally-unscoped-by-tenant queries were found and fixed during remediation (auth revocation lookups, user lookups, analysis-definition updates — the highest-severity one, an UPDATE with no org filter, was confirmed fixed). One holdout accepted as low-risk: the `commits` collection's unique index remains `(form_id, hash)` without `organization_id`, justified because commit access is always gated by an already-org-verified `form_id` upstream.

### 4.5 Versioning

See Section 3 — two coexisting philosophies (git-style for Forms, `entityVersion` for Analytics/Dashboard). Do not conflate them or attempt to unify without an explicit decision; this was already flagged and deliberately resolved as "keep both, scoped to different data types."

### 4.6 Compliance (GDPR + HIPAA + SOC2 — all three targeted)

- **Field-level PHI encryption**: a `piiClass` field (`none|pii|phi`) added to form field definitions; fields tagged `phi` are encrypted before storage using the existing `encryption_helper.py`/`encrypted_dek` envelope-encryption pattern, extended from form-level to field-level. Confirmed implemented and tested.
- **Audit logging**: `audit_logs` collection. Coverage is a **deliberate, documented partial policy**, not full "every read and write" — after investigation, the team chose to log writes plus selected sensitive read paths only, documented in `docs/audit-logging-policy.md`. This was a conscious scope decision the prompt allowed for, not an incomplete implementation — but worth a compliance reviewer's explicit sign-off before relying on it for an actual SOC2/HIPAA audit.
- **DB-level tamper protection**: a restricted Mongo role (`app_writer_role`) confirmed created via `docker/mongo-init.js`, granting the app's service account insert-only (no update/delete) on `audit_logs`. (This is the same change that initially caused the login regression in 4.3 — confirmed re-fixed without reopening the audit-log protection gap, per the last full verification round.)
- **GDPR erasure**: `DELETE /api/v1/tenants/<org_id>/data` and a per-data-subject variant `DELETE /api/v1/tenants/<org_id>/data-subjects/<subject_id>` — confirmed via test assertions to perform a real hard-delete (`delete_many()`), not a soft-delete flag.
- **Data residency**: explicitly documented (not just left silent) as **single-region only, not yet supported for EU/regulated customers**, in `docs/data-residency.md`. This is a real, acknowledged product limitation, not an oversight.

### 4.7 Background Jobs

- APScheduler: confirmed live, used for existing scheduled analysis runs.
- Celery: confirmed live and actually wired to a running worker (verified via `docker-compose.dev.yml` worker service + `celery_worker.py`), used specifically for the new Analytics DAG execution.
- Direct threads: still used in several places (`task_manager.py`, `workflow_engine.py`, some of `app.py`/`builder_app.py`) for export jobs and workflow execution — flagged as tech debt, not consolidated, and deliberately NOT migrated during the remediation work (scoped out to avoid unnecessary risk).
- An RQ-style Redis helper (`redis_manager.py`) exists but is not confirmed as an actively-used primary path.

### 4.8 API Route Inventory (confirmed live via discovery pass)

**Canonical base for most routes**: `/api/v1/...`. **Projects specifically**: target `/api/v1/projects/...`; legacy `/api/projects` and `/projects/...` paths should be treated as deprecated surfaces. Legacy aliases also exist under `/api/...` (non-projects) and `/mahasangraha/api/v1/...` — do not build against these, they are not guaranteed maintained.

Key confirmed route families:

- **Auth**: `/api/v1/auth/{register,login,refresh,logout,request-otp,otp/verify,otp/login,accept-invite/<token>,oidc/login,oidc/callback}`
- **Forms**: `/api/v1/forms` (list/create), `/<form_id>` (+ `info,permissions,draft,clone,archive,restore,check-duplicate,public-submit,responses[...],sections[...],translations,versions/<v>,validate-design,taxonomy,sentiment,summarize,summarize-stream`)
- **Responses**: `/api/v1/responses/`, `/api/v1/responses/<response_id>`
- **Projects**: target namespace is `/api/v1/projects/...`. Legacy `/api/projects` and `/projects/...` surfaces should be removed from the product direction. Project creation requires `login_required` + role `admin` or `editor`. Project deletion is a **soft delete** (`deleted: true`), returns `{"message": "Project soft-deleted successfully"}` with a 200, not a 204.
- **Analytics graphs**: `GET|PATCH /api/v1/schemas/analytics-graphs/<id>` (legacy alias also at `/api/v1/analytics/<id>`)
- **Dashboards**: TWO separate route families confirmed — `GET|POST /api/v1/schemas/dashboards/<id>` (schema/authoring) vs. `GET|PUT|DELETE /api/v1/dashboards/<id>` plus `/canvas`, `/canvas/data`, `/data`, `/export`, `/filter-options`, `/public-token`, `/snapshots[...]`, `/widgets/<id>/data`, and unauthenticated `/dashboards/shared/<share_token>[...]`. **This distinction (authoring vs. viewing/sharing) is confirmed real and not yet reconciled with a single frontend UI** — flagged as needing a deliberate viewer-vs-builder split on the frontend.
- **Graph execution**: `POST /api/v1/executions/graphs` (returns `202` + `{"jobId": "<celery-task-id>"}`), `GET /api/v1/executions/graphs/<job_id>` (polling; no websocket/SSE alternative confirmed — polling is the only mechanism).
- **Webhooks**: `/api/v1/webhooks[...]` including `/test`, `/logs`, `/history`, and delivery-level `/retry|cancel|status|history`.
- **Tenants/compliance**: `DELETE /api/v1/tenants/<org_id>/data[-subjects/<id>]`.

### 4.9 Dev Environment

- Canonical dev command: `make dev-d` → `docker compose -f docker-compose.dev.yml up --build -d`.
- Confirmed dev ports (host → container): App `5001→5000` (note: `.env` overrides the default `5000`), MongoDB `27017`, Redis `6379`, Flower `5555`, Mongo Express `8081`, Redis Commander `8082→8081`, Mailhog `1025`/`8025`, MinIO `9000`/`9001`, Kibana `5601`, Jaeger `16686`. Celery worker has no exposed host port.
- Correct frontend dev base URL: **`http://localhost:5001/api/v1`** (and separately `http://localhost:5001/api` for Projects — see 4.1/4.8). The old hardcoded frontend value (`https://api.unifiedformservice.local/v1`) was confirmed wrong/unreachable in dev.
- Health check: `GET /healthz` → `{"status": "ok", "services": {...}}`.
- Swagger UI: `http://localhost:5001/apidocs/`, spec at `/apispec.json`.
- CORS: enabled (`flask_cors`), confirmed to explicitly allow `http://localhost:5173` in preflight — verify this matches whatever port the Flutter web dev server actually uses in your setup.
- Full dev stack also includes: minio, redis-commander, elasticsearch, flower, kibana, jaeger, mongo-express, mailhog, logstash, portainer, locust.

### 4.10 Backend Issue History (fixed, for context — don't re-investigate these)

1. Tenant fallback to `"default_org"` on missing JWT claim — removed, now hard-rejects.
2. Query-param tenant fallback in `builder_app.py` — removed.
3. Static password salt — fixed to per-user salts with rehash-on-login.
4. Multiple unscoped-by-tenant queries — fixed (see 4.4).
5. Non-atomic `entityVersion` update (race condition) — fixed to a single atomic `find_one_and_update`.
6. `org_id`/`organization_id` naming split — migrated and confirmed via live query.
7. Over-broad Mongo role restriction breaking login (side effect of audit-log lockdown) — fixed; confirmed audit-log protection still holds.
8. `PluginEngine` referenced in an early inventory as existing in the analyzer-side code — **investigated repeatedly and confirmed to NOT exist anywhere in the backend** (repo-wide case-insensitive search found nothing). Treat the earlier reference as an inventory error, not a real component.

---

## 5. Frontend Documentation

### 5.1 Codebase structure

```
lib/main.dart
lib/src/core/
  api_service.dart, design_system.dart, network.dart, router.dart, theme.dart
  plugin_registry.dart, history_store.dart, canvas_input_controller.dart
  providers/ (api_provider, auth_provider, storage_providers, theme_provider, workspace_provider)
  widgets/ (common_widgets.dart, common_widgets_formvault.dart)
lib/src/features/
  auth/, projects/, forms/, builder/ (Form Builder), gateway/, analyzer/,
  analytics/ (Analytics Builder — added), dashboard/ (Dashboard Builder — added)
```

Plus: `published_form_renderer_screen.dart`, `published_form_rule_engine.dart`, `published_form_step_compiler.dart`, `published_form_cache.dart` (Form Renderer + offline caching).

### 5.2 State management

Riverpod throughout; `AsyncNotifier` pattern confirmed for auth. Some `setState` usage remains in less-central screens. Storage key versioning/migration handling confirmed built (`StorageKeyManager.versioned()/legacy()`) for secure-storage/shared-prefs keys.

### 5.3 Core abstractions (confirmed built)

- **PluginRegistry** (`plugin_registry.dart`) — confirmed refactored into Form Builder's field/workflow icon lookups.
- **HistoryStore** (`history_store.dart`) — undo/redo with command merging; confirmed drag operations already commit one history entry per completed gesture (not per-frame — this was investigated and found to already be correctly scoped, not a gap).
- **CanvasInputController** (`canvas_input_controller.dart`) — confirmed used for Form Builder drop zones and selection rows (via `buildSelectable()` with `MouseRegion`+`GestureDetector`).

### 5.4 Design System — MAJOR ACTIVE WORK, not yet complete

Three competing systems were found coexisting:

1. **Midnight/AppTheme** — used in auth, gateway.
2. **Legacy design-system tokens** used in projects, forms, and builder modules.
3. **Default Material/package-driven** — analytics-builder, dashboard-builder, published-form (these lean on `vyuh_node_flow`/`formstack`/`graphic`'s own default styling).

**A unification project is underway** to replace all three with one canonical system, built with two density tiers (Narrative — auth/onboarding/empty-states; Functional — everything data-dense). Foundation (tokens + base components: `AppButton`, `AppCard`, `AppTextField`, `AppSectionHeader`, a stagger-reveal wrapper) was scoped but **not yet confirmed built/locked as of this writing** — check current status before assuming it exists. The visual direction and token rules belong in `design.md`; this document should only describe the product and implementation direction that the UI must support.

### 5.5 API Integration — confirmed gotchas

- **Dual base URL roots**: `/api/v1` for most things, with projects targeting `/api/v1/projects` (see 4.8). The frontend must NOT use a single shared `baseUrl` constant naively.
- **Inconsistent response envelopes**: some endpoints wrap `{"status","message","data":{...}}`, others return bare objects — check per-endpoint, don't assume uniformity.
- **Three different error shapes** from the backend (see 4.3) — needs defensive parsing.
- **`entityVersion` 409-conflict handling**: confirmed implemented for Analytics/Dashboard saves with a conflict-UI response (not silent overwrite). Forms use the commit/branch flow instead — do not apply `entityVersion` logic to Forms.
- **DAG execution polling**: `POST /api/v1/executions/graphs` request body key ambiguity — try `graphId` first (matches schema field naming); no push/websocket mechanism, polling only, suggested interval starting ~2s with backoff to ~5s after 30s.

### 5.6 Known Frontend Bugs (from visual audit — verify current status before assuming fixed)

- Mobile `RenderFlex` overflow on the Auth screen (confirmed via runtime exception, real bug).
- A pointer/hit-test interception issue on the Auth screen's Continue button caused by overlapping Flutter semantics/input layers — confirmed as the root cause of an earlier false "login is broken" diagnosis (the login flow itself works; a DOM-level click succeeds). This is still a real UX bug worth fixing even though it wasn't a backend problem.
- Session instability — user gets dropped back to `/auth` mid-navigation during route sweeps (real bug, cause not yet diagnosed).
- A CORS/preflight failure on the Projects screen's org-users fetch, leaving that section stuck in a persistent empty/failure state with no recovery path.
- `/analyzer` route was found silently resolving to `/projects` instead of rendering its own screen (real routing bug).
- **Note on the visual audit process itself**: two consecutive audit runs delivered detailed, plausible-sounding per-page reports citing specific screenshot filenames as evidence, but the screenshots folder was completely empty both times (0 files). Root cause was not yet confirmed as of the last check — leading hypothesis is the screenshot tool returns image data directly to the agent's context rather than writing files to disk. **Do not trust any screenshot-filename citation from that audit process without independently verifying the file exists.**

---

## 6. Complete Page Inventory

Full detail lives in a separate `complete-page-inventory.md` companion document; summary here:

**Confirmed existing (build quality varies):** Auth, Projects Dashboard, Forms List, Form Builder, Published Form Renderer, Analytics Builder, Dashboard Builder, Gateway (scope/purpose unclear — blueprint names suggest broader integration/sync intent than current implementation), Analyzer (intentional simulator; real backend AI endpoints for taxonomy/sentiment/summarize exist server-side with no real frontend consumer yet).

**Backend-ready, frontend missing entirely (~24 pages)** — concentrated most heavily in two areas:

- **Compliance & Admin**: Compliance Dashboard, Data Processing Records Viewer, GDPR Data Erasure Request Tool, Audit Log Viewer, Feature Flags Admin — the backend has substantially more compliance infrastructure built and tested than the frontend exposes anywhere. This is the single biggest concentration of missing-but-ready work given the GDPR/HIPAA/SOC2 target.
- **Dashboard's non-authoring surface**: Dashboard Viewer (distinct from the Builder), Export, Snapshots, Sharing (public token), and the unauthenticated Public Shared Dashboard view.

Also missing: Project Detail, Project Sharing, Form Permissions/Sections-manager/Translations/Version-History-viewer/Design-Validation-panel, Responses List/Detail (per form), Graph Execution Monitor, Workspace Switcher, Roles & Permissions overview, Notifications Center (+Templates admin), Account/Workspace/Appearance Settings, and Global Search.

**Unconfirmed/open product decisions**: Storage/Quota Panel, 404/error page handling.

**Planned product direction**:

- Global Search across projects, forms, responses, analytics, dashboards, organizations, users, and audit/activity data.
- Search visibility should be permission-filtered:
  - `superadmin` can search across the full system.
  - `admin` can search within their own organizations.
  - non-admin users should not have user search available.

---

## 7. Third-Party Package Notes (verified against actual docs, not assumed from package names)

- **`vyuh_node_flow`** — genuine, capable node-flow editor (`Node<T>`/`Port`/`Connection` model, `NodeFlowController`, pan/zoom, theming, connection validation hooks, groups, minimap, JSON-serializable graph state). Closest of the three to "React Flow for Flutter." Used close to its native API for the Analytics Builder. Young package — pin versions, isolate direct calls to one module.
- **`formstack`** — a **step-based** form renderer (`QuestionStep`/`InstructionStep`, ~20 input types), NOT a nested-section/conditional-branching engine. Its own docs list conditional logic, nested sections, auto-save, and multi-language as unsupported. Used only as a leaf-level input-widget/rendering primitive; all nested/conditional logic lives in a custom `RuleEngine` that compiles down to `formstack` steps at render time. Small package, single/small maintainer — a real dependency risk worth monitoring.
- **`graphic`** — mature grammar-of-graphics charting library (`Chart(data, variables, marks, axes, coord, transforms)`), supports interactions/selections and animation. Good for standard chart types; does NOT cover exotic types (Sankey, treemap, geo/map) — those need custom `CustomPainter` widgets as separate plugins if needed later.

---

## 8. Naming Placeholders

This document may mention placeholder names to describe current implementation artifacts, but those names are not authoritative.
- **Final product name**: defined in `brand.md`
- **Sub-product names**: use descriptive placeholders only unless `brand.md` defines otherwise

---

## 9. Development Process & Methodology Used On This Project

Given the solo-operator-plus-multiple-AI-agents structure, a specific recurring workflow has been used and should be continued:

1. **Inventory pass** (read-only, no fixes) — an agent documents actual current state of a codebase area, explicitly instructed not to guess or fill gaps with assumptions ("not found" instead of "presumably").
2. **Reconciliation** — compare inventory findings against any existing architecture doc/plan, producing explicit Matches / Conflicts (with a stated resolution or explicit "needs human decision") / Gaps / Already-built-but-unknown-to-the-doc / Recommended order of work.
3. **Completion/remediation prompts** — phased, with an explicit Definition-of-Done per phase, and decisions pre-resolved (not left open) so agents can execute without stalling.
4. **Verification audit** (read-only, separate from the agent that did the work) — checks claimed-done items against actual code with file:line citations, using VERIFIED/PARTIAL/NOT DONE/CANNOT DETERMINE status per item. Explicitly checks for the common failure pattern of "a new abstraction built but never wired into old call sites."
5. **Remediation round 2+** — targeted fixes only for what the audit found incomplete, not a full re-run.

**Standing lesson learned, worth enforcing going forward**: agents have, more than once, reported partial work as "complete" (once covering only 1 of 10 required items while still claiming full completion; another time silently omitting/garbling several items from a status table). **Any status report covering multiple checklist items should be required to show every item explicitly, in order, with no renumbering or gaps — if an item is missing from a report, treat it as unreported/unverified, not as done.**

---

## 10. Open Decisions Requiring Human Input (do not resolve these unilaterally)

1. Gateway screen implementation details beyond the broader entry-point direction.

---

## 11. Current Known Blockers / In-Progress Threads (check status before assuming resolved)

- Screenshot delivery from the visual-audit tooling is confirmed broken (two consecutive runs, zero files delivered despite detailed citations) — root cause diagnostic was requested but not yet confirmed resolved.
- The design-system Foundation prompt (Section 5.4) was written and scoped but not confirmed executed/locked as of this document.
- Session instability (drops to `/auth` mid-navigation) has not been root-caused yet.
- `TenantScopedCollection` adoption is confirmed partial, not complete, across all backend route handlers.
