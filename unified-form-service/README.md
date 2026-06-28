# Unified Form & Survey Microservice

This project is a consolidation of three originally separate microservices into a single, unified Flask application:
1. **Form Builder** (VCS version control, PDF generation, dynamic workflow executions)
2. **Response Gateway** (Schema ingestion and response logging gateway)
3. **Form Analyser** (Response aggregation, regression logic, trend analysis, and background schedules)

All three services run within a single Flask process, sharing standard packages and running on port `5000`.

---

## 🛠️ Environment Configuration

Set the following environment variables in your environment or a `.env` file:

```env
# General Flask Settings
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=super-secret-key-change-in-prod
JWT_SECRET=super-secret-key-change-in-prod

# Database URLs (can point to the same MongoDB instance, but separate database names)
DATABASE_URL=mongodb://localhost:27017/form_response
MONGO_URI=mongodb://localhost:27017/form_analyser
MONGO_DB_NAME=form_analyser

# Redis (for Analyser caching and webhook scheduler queues)
REDIS_URL=redis://localhost:6379/0

# Tenant Database Isolation settings
TENANT_DB_ISOLATION=false
ACTIVE_DB_LIMIT=5
DB_INACTIVE_TIMEOUT=300
```

---

## 🚀 Running the Unified Service

To start the unified service, install requirements and run `app.py`:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the unified server
python app.py
```

The unified service will start on `http://localhost:5000` and automatically spin up the background scheduler task runner.

---

## 🔍 Verification & Health Checking

Verify the status of all three mounted services:

```bash
curl http://localhost:5000/healthz
```

Expected Response:
```json
{
  "status": "ok",
  "services": {
    "builder": "running",
    "response_gateway": "running",
    "analyser": "running"
  }
}
```
