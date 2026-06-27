# Form Builder Backend

Flask backend for a versioned form-authoring system.

## What this project does

- Creates and manages projects and forms
- Versions forms with a git-like commit / branch / merge model
- Validates submissions with calculation and conditional logic
- Supports draft response updates and conflict handling
- Generates receipt artifacts for submitted responses
- Integrates with MongoDB and S3-compatible storage such as MinIO

## Main entrypoints

- [`app.py`](app.py): Flask app, routes, request orchestration, tenant DB selection
- [`auth.py`](auth.py): password hashing, JWT issuance, auth decorators
- [`git_version_control.py`](git_version_control.py): form schema versioning logic
- [`validator.py`](validator.py): submission validation and computed fields
- [`surveyjs_translator.py`](surveyjs_translator.py): internal form schema to SurveyJS

## Local development

1. Create a Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the example environment file and adjust values:

```bash
cp .env.example .env
```

4. Start supporting services:

```bash
docker compose up -d mongodb minio
```

5. Run the app:

```bash
python app.py
```

Or use the Makefile:

```bash
make install
make run
make test
```

## Key environment variables

- `MONGO_URI`
- `DB_NAME`
- `JWT_SECRET`
- `PASSWORD_SALT`
- `TENANT_DB_ISOLATION`
- `UPLOAD_FOLDER`
- `S3_ENDPOINT_URL`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_BUCKET_NAME`

## Tests

The repository includes unit and integration-style tests at the root, for example:

- `test_auth_acl.py`
- `test_vcs_lifecycles.py`
- `test_app.py`
- `test_enterprise_features.py`

Common commands:

- `make test-auth`
- `make test-vcs`
- `make test-app`
- `make init-db`

## API examples

### Register a user

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "owner@company.com",
    "password": "securepassword123",
    "first_name": "Alice",
    "last_name": "Smith",
    "organization_name": "Alice Industries"
  }'
```

### Create a form

```bash
curl -X POST http://localhost:5000/api/forms \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Customer Feedback",
    "questions": [
      {
        "id": "q_satisfaction",
        "type": "multiple_choice",
        "title": "How satisfied are you?"
      }
    ]
  }'
```

### Submit a response

```bash
curl -X POST http://localhost:5000/api/forms/$FORM_ID/submit \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "q_satisfaction": "Very Satisfied"
  }'
```

## API reference

| Area | Common endpoints | Notes |
| --- | --- | --- |
| Auth | `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/reset-password` | JWT-based auth with access and refresh tokens |
| Org / users | `/api/org/users`, `/api/org/users/<user_id>`, `/api/org/lifecycle` | Organization management and role/state updates |
| Projects | `/api/projects`, `/api/projects/<project_id>`, `/api/projects/<project_id>/share` | Project CRUD and sharing |
| Forms | `/api/forms`, `/api/forms/<form_id>`, `/api/forms/<form_id>/publish`, `/api/forms/<form_id>/surveyjs` | Form authoring, publish, and rendering helpers |
| Versioning | `/api/forms/<form_id>/commit`, `/api/forms/<form_id>/commits`, `/api/forms/<form_id>/branches`, `/api/forms/<form_id>/diff`, `/api/forms/<form_id>/merge`, `/api/forms/<form_id>/revert` | Git-like schema lifecycle |
| Responses | `/api/forms/<form_id>/submit`, `/api/forms/<form_id>/submit-batch`, `/api/responses/<response_id>` | Submission, batch submission, and draft updates |
| Exports | `/api/forms/<form_id>/export/csv`, `/api/forms/<form_id>/export/json`, `/api/forms/<form_id>/export/async` | Generated response exports |
| Workflows | `/api/forms/<form_id>/workflows/runs`, `/api/forms/<form_id>/workflows/failed-runs`, `/api/forms/<form_id>/workflows/trigger` | Workflow execution and inspection |
| Health | `/api/health` | Liveness / basic health check |

## Notes

- `static/uploads/` is a runtime artifact directory and should not be committed.
- When `TENANT_DB_ISOLATION=true`, the app uses a per-organization database naming scheme.
