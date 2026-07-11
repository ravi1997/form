# API Endpoints

This is the route-level reference for the `/api/v1` surface. Every row below maps to a concrete Flask/OpenAPI handler, and the request and response schema names match the code in `app/schemas/`.

## System

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/health` | - | - | inline health payload | - |
| `GET` | `/api/v1/liveness` | - | - | inline liveness payload | - |
| `GET` | `/api/v1/readiness` | - | - | inline readiness payload | - |
| `GET` | `/api/v1/ready` | - | - | alias of readiness payload | - |
| `GET` | `/api/v1/metrics` | - | - | inline metrics payload | - |
| `POST` | `/api/v1/schemas/echo-form` | - | form schema body | echoed form schema | validation errors |

## Auth

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/auth/register` | - | `RegisterRequest` | `UserOutput` with verification required; no active session is issued | `ErrorResponse` |
| `POST` | `/api/v1/auth/login` | - | `LoginRequest` | `TokenPairResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/change-password` | - | `ChangePasswordRequest` with `AuthorizationHeader` | `ChangePasswordResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/refresh` | - | `RefreshTokenRequest` | `AccessTokenResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/logout` | - | `LogoutRequest` | `LogoutResponse` | `ErrorResponse` |
| `GET` | `/api/v1/auth/me` | - | `AuthorizationHeader` | `UserOutput` | `ErrorResponse` |
| `GET` | `/api/v1/auth/sessions` | - | `SessionListQuery` + `AuthorizationHeader` | `SessionListResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/sessions/revoke` | - | `RevokeSessionRequest` + `AuthorizationHeader` | `RevokeSessionResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/logout-all` | - | `LogoutAllSessionsRequest` + `AuthorizationHeader` | `LogoutAllSessionsResponse` | `ErrorResponse` |
| `GET` | `/api/v1/auth/admin/users/<user_uuid>/sessions` | `user_uuid` | `SessionListQuery` + `AuthorizationHeader` | `SessionListResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/admin/users/<user_uuid>/sessions/revoke` | `user_uuid` | `AdminRevokeSessionRequest` + `AuthorizationHeader` | `AdminRevokeSessionResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/admin/users/<user_uuid>/sessions/revoke-all` | `user_uuid` | `AuthorizationHeader` | `AdminRevokeAllSessionsResponse` | `ErrorResponse` |
| `GET` | `/api/v1/auth/admin/config/health` | - | `AuthorizationHeader` | `AdminConfigHealthResponse` | `ErrorResponse` |
| `GET` | `/api/v1/auth/admin/audit-logs` | - | `AdminAuditLogQuery` + `AuthorizationHeader` | `AdminAuditLogListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/auth/admin/audit-logs/search` | - | `AdminAuditLogSearchQuery` + `AuthorizationHeader` | `AdminAuditLogListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/auth/admin/users` | - | `SessionListQuery` + `AuthorizationHeader` | `UserListResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/admin/users` | - | `UserCreateInput` + `AuthorizationHeader` | `UserOutput` | `ErrorResponse` |
| `GET` | `/api/v1/auth/admin/users/<user_uuid>` | `user_uuid` | `AuthorizationHeader` | `UserOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/auth/admin/users/<user_uuid>` | `user_uuid` | `UserUpdateInput` + `AuthorizationHeader` | `UserOutput` | `ErrorResponse` |
| `POST` | `/api/v1/auth/admin/users/bulk/must-change-password` | - | `AdminBulkMustChangePasswordRequest` + `AuthorizationHeader` | `AdminBulkMustChangePasswordResponse` | `ErrorResponse` |
| `DELETE` | `/api/v1/auth/admin/users/<user_uuid>` | `user_uuid` | `AuthorizationHeader` | `MessageResponse` | `ErrorResponse` |
| `POST` | `/api/v1/auth/admin/users/<user_uuid>/verify` | `user_uuid` | `VerifyUserInput` + `AuthorizationHeader` | `UserOutput` | `ErrorResponse` |

## Organizations

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/organizations` | - | `OrganizationCreateInput` | `OrganizationOutput` | `ErrorResponse` |
| `GET` | `/api/v1/organizations` | - | `ListQuery` | `OrganizationListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/organizations/<uuid>` | `uuid` | - | `OrganizationOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/organizations/<uuid>` | `uuid` | `OrganizationUpdateInput` | `OrganizationOutput` | `ErrorResponse` |
| `DELETE` | `/api/v1/organizations/<uuid>` | `uuid` | - | `MessageResponse` | `ErrorResponse` |
| `GET` | `/api/v1/organizations/<uuid>/admins` | `uuid` | - | `OrganizationAdminsResponse` | `ErrorResponse` |
| `POST` | `/api/v1/organizations/<uuid>/admins` | `uuid` | `AddAdminInput` | `OrganizationAdminsResponse` | `ErrorResponse` |
| `DELETE` | `/api/v1/organizations/<uuid>/admins/<user_uuid>` | `uuid`, `user_uuid` | - | `OrganizationAdminsResponse` | `ErrorResponse` |
| `POST` | `/api/v1/organizations/<uuid>/invitations` | `uuid` | `InvitationInput` | `InvitationOutput` | `ErrorResponse` |
| `POST` | `/api/v1/invitations/<uuid>/accept` | `uuid` | - | `MessageResponse` | `ErrorResponse` |

## Resources

### Projects

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/projects` | - | `ProjectCreateInput` | `ProjectOutput` | `ErrorResponse` |
| `GET` | `/api/v1/projects` | - | `ListQuery` | `ProjectListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<uuid>` | `uuid` | - | `ProjectOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<uuid>` | `uuid` | `ProjectUpdateInput` | `ProjectOutput` | `ErrorResponse` |
| `DELETE` | `/api/v1/projects/<uuid>` | `uuid` | - | `MessageResponse` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<uuid>/versions` | `uuid` | `VersionCreateInput` | `VersionOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<uuid>/versions/<version_uuid>` | `uuid`, `version_uuid` | `VersionUpdateInput` | `VersionOutput` | `ErrorResponse` |

### Forms

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/projects/<project_uuid>/forms` | `project_uuid` | `FormCreateInput` | `FormOutput` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms` | `project_uuid` | `ListQuery` | `FormListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>` | `project_uuid`, `form_uuid` | - | `FormOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>` | `project_uuid`, `form_uuid` | `FormUpdateInput` | `FormOutput` | `ErrorResponse` |
| `DELETE` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>` | `project_uuid`, `form_uuid` | - | `MessageResponse` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/versions` | `project_uuid`, `form_uuid` | `VersionCreateInput` | `VersionOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/versions/<version_uuid>` | `project_uuid`, `form_uuid`, `version_uuid` | `VersionUpdateInput` | `VersionOutput` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/ui/effective` | `project_uuid`, `form_uuid` | - | `EffectiveUiConfigOutput` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/responses` | `project_uuid`, `form_uuid` | `FormResponseCreateInput` | `FormResponseOutput` | `ErrorResponse` |
| `POST` | `/api/v1/public/projects/<project_uuid>/forms/<form_uuid>/responses` | `project_uuid`, `form_uuid` | `FormResponseCreateInput` | `FormResponseOutput` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/workflow/submit` | `project_uuid`, `form_uuid` | `WorkflowActionRequest` | `WorkflowActionResponse` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/workflow/review` | `project_uuid`, `form_uuid` | `WorkflowActionRequest` | `WorkflowActionResponse` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/workflow/approve` | `project_uuid`, `form_uuid` | `WorkflowActionRequest` | `WorkflowActionResponse` | `ErrorResponse` |

### Sections

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections` | `project_uuid`, `form_uuid` | `VersionLinkQuery` + `SectionCreateInput` | `SectionOutput` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections` | `project_uuid`, `form_uuid` | `ListQuery` | `SectionListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>` | `project_uuid`, `form_uuid`, `section_uuid` | - | `SectionOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>` | `project_uuid`, `form_uuid`, `section_uuid` | `SectionUpdateInput` | `SectionOutput` | `ErrorResponse` |
| `DELETE` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>` | `project_uuid`, `form_uuid`, `section_uuid` | - | `MessageResponse` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/versions` | `project_uuid`, `form_uuid`, `section_uuid` | `VersionCreateInput` | `VersionOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/versions/<version_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `version_uuid` | `VersionUpdateInput` | `VersionOutput` | `ErrorResponse` |

### Questions

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions` | `project_uuid`, `form_uuid`, `section_uuid` | `VersionLinkQuery` + `QuestionCreateInput` | `QuestionOutput` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions` | `project_uuid`, `form_uuid`, `section_uuid` | `ListQuery` | `QuestionListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid` | - | `QuestionOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid` | `QuestionUpdateInput` | `QuestionOutput` | `ErrorResponse` |
| `DELETE` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid` | - | `MessageResponse` | `ErrorResponse` |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/versions` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid` | `VersionCreateInput` | `VersionOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/versions/<version_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid`, `version_uuid` | `VersionUpdateInput` | `VersionOutput` | `ErrorResponse` |

### Choices

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid` | `ChoiceCreateInput` | `ChoiceOutput` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid` | `ListQuery` | `ChoiceListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid`, `choice_uuid` | - | `ChoiceOutput` | `ErrorResponse` |
| `PATCH` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid`, `choice_uuid` | `ChoiceUpdateInput` | `ChoiceOutput` | `ErrorResponse` |
| `DELETE` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid`, `choice_uuid` | - | `MessageResponse` | `ErrorResponse` |

### Actions

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/actions/<action_id>/trigger` | `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid`, `action_id` | `ActionTriggerRequest` | `ActionTriggerResponse` | `ErrorResponse` |
| `GET` | `/api/v1/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>/action-executions` | `project_uuid`, `form_uuid`, `response_uuid` | `ListQuery` | `ActionExecutionListResponse` | `ErrorResponse` |

## Conditions

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/conditions/metadata` | - | - | `ConditionMetadataResponse` | - |
| `GET` | `/api/v1/conditions/operators/metadata` | - | - | operator metadata map | - |
| `POST` | `/api/v1/conditions/test` | - | `ConditionTestInput` | `ConditionTestResult` | `ErrorResponse` |
| `POST` | `/api/v1/conditions/test/batch` | - | `BatchConditionTestInput` | `BatchConditionTestResponse` | `ErrorResponse` |
| `GET` | `/api/v1/conditions/cache/metrics` | - | - | cache metrics payload | - |
| `POST` | `/api/v1/conditions/cache/invalidate/<condition_uuid>` | `condition_uuid` | - | `MessageResponse` | `ErrorResponse` |
| `GET` | `/api/v1/conditions/usage/<condition_uuid>` | `condition_uuid` | - | `ConditionUsageResponse` | `ErrorResponse` |
| `POST` | `/api/v1/conditions/impact/<condition_uuid>` | `condition_uuid` | `ConditionImpactInput` | `ConditionImpactAnalysisResponse` | `ErrorResponse` |
| `GET` | `/api/v1/conditions/monitoring/graph` | - | - | monitoring graph payload | - |
| `GET` | `/api/v1/conditions/monitoring/heatmap` | - | - | monitoring heatmap payload | - |
| `GET` | `/api/v1/conditions/monitoring/unused` | - | - | monitoring unused payload | - |
| `GET` | `/api/v1/conditions/monitoring/most-used` | - | - | monitoring most-used payload | - |
| `GET` | `/api/v1/conditions/monitoring/evaluation-stats` | - | - | monitoring stats payload | - |
| `POST` | `/api/v1/conditions/presets` | - | `PresetUpsertInput` | preset payload | `ErrorResponse` |
| `GET` | `/api/v1/conditions/presets` | - | - | preset list payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/presets/import` | - | `ImportPresetsInput` | import result payload | `ErrorResponse` |
| `GET` | `/api/v1/conditions/presets/export` | - | - | preset export payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/<condition_uuid>/approval/transition` | `condition_uuid` | `ApprovalTransitionInput` | approval state payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/<condition_uuid>/approval/rollback` | `condition_uuid` | `ActorUserInput` | approval state payload | `ErrorResponse` |
| `GET` | `/api/v1/conditions/<condition_uuid>/versions` | `condition_uuid` | - | version list payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/<condition_uuid>/versions/record` | `condition_uuid` | `VersionRecordInput` | version record payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/<condition_uuid>/versions/restore` | `condition_uuid` | `VersionRestoreInput` | restore result payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/bulk/create` | - | `BulkCreateConditionInput` | bulk create payload | `ErrorResponse` |
| `PATCH` | `/api/v1/conditions/bulk/update` | - | `BulkUpdateConditionInput` | bulk update payload | `ErrorResponse` |
| `DELETE` | `/api/v1/conditions/bulk/delete` | - | `BulkDeleteConditionInput` | bulk delete payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/bulk/validate` | - | `BulkValidateConditionInput` | bulk validate payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/bulk/test` | - | `BulkTestInput` | bulk test payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/bulk/import` | - | `BulkImportConditionsInput` | bulk import payload | `ErrorResponse` |
| `GET` | `/api/v1/conditions/bulk/export` | - | - | bulk export payload | `ErrorResponse` |
| `POST` | `/api/v1/conditions/async/evaluate` | - | `AsyncEvaluationInput` | async job payload | `ErrorResponse` |
| `GET` | `/api/v1/conditions/async/<job_id>` | `job_id` | - | async job status payload | `ErrorResponse` |

## UI templates

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/ui/theme-templates` | - | template create body | serialized theme template payload | `ErrorResponse` |
| `POST` | `/api/v1/ui/theme-templates/<template_uuid>/revisions/<revision_uuid>/publish` | `template_uuid`, `revision_uuid` | - | serialized theme template payload | `ErrorResponse` |
| `POST` | `/api/v1/ui/layout-templates` | - | template create body | serialized layout template payload | `ErrorResponse` |
| `POST` | `/api/v1/ui/layout-templates/<template_uuid>/revisions/<revision_uuid>/publish` | `template_uuid`, `revision_uuid` | - | serialized layout template payload | `ErrorResponse` |

## Rate limits

| Method | Path | Path params | Query/body | Success response | Errors |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/admin/rate-limits/configs` | - | `RateLimitCreateRequest` | `RateLimitResponse` | `ErrorResponse` |
| `GET` | `/api/v1/admin/rate-limits/configs` | - | query filters: `scope`, `target_id`, `route_pattern`, `is_active`, `page`, `per_page` | `RateLimitListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/admin/rate-limits/configs/<rule_id>` | `rule_id` | - | `RateLimitResponse` | `ErrorResponse` |
| `PATCH` | `/api/v1/admin/rate-limits/configs/<rule_id>` | `rule_id` | `RateLimitUpdateRequest` | `RateLimitResponse` | `ErrorResponse` |
| `POST` | `/api/v1/admin/rate-limits/configs/<rule_id>/toggle` | `rule_id` | - | `RateLimitResponse` | `ErrorResponse` |
| `DELETE` | `/api/v1/admin/rate-limits/configs/<rule_id>` | `rule_id` | - | `RateLimitDeleteResponse` | `ErrorResponse` |
| `POST` | `/api/v1/admin/rate-limits/configs/bulk/update` | - | `BulkRateLimitUpdateRequest` | `BulkRateLimitUpdateResponse` | `ErrorResponse` |
| `POST` | `/api/v1/admin/rate-limits/counters/reset` | - | `RateLimitResetRequest` | `RateLimitResetResponse` | `ErrorResponse` |
| `GET` | `/api/v1/admin/rate-limits/logs` | - | query filters: `user_id`, `organization_id`, `route_pattern`, `blocked`, `page`, `per_page` | `RateLimitLogsListResponse` | `ErrorResponse` |
| `GET` | `/api/v1/admin/rate-limits/status` | - | query filters: `user_id`, `organization_id`, `route_pattern` | `RateLimitStatusResponse` | `ErrorResponse` |

## Documentation coverage notes

- Nested path parameters are documented explicitly in the tables above, including deep resource trees such as `project_uuid`, `form_uuid`, `section_uuid`, `question_uuid`, `choice_uuid`, `action_id`, `response_uuid`, `version_uuid`, `rule_id`, `condition_uuid`, `template_uuid`, and `revision_uuid`.
- Response schema names are listed at the route level so the OpenAPI contract can be traced directly back to the corresponding model in `app/schemas/`.
- Where a handler returns a plain JSON payload or inline dict instead of a named schema, the table says so explicitly.
