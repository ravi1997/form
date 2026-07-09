# Database Models

MongoDB is accessed through MongoEngine documents in `app/models/`.

## Main model areas

- `user.py` defines users and organizations
- `auth.py` defines sessions, token blocklists, and rate-limit counters
- `form.py` defines projects, forms, sections, questions, choices, conditions, responses, and versions
- `condition_management.py` defines presets, approvals, versions, audits, and related management state
- `rate_limit.py` defines rate-limit configuration and logging records
- `ui_template.py` defines UI templates

## Notes

- The codebase uses document collections rather than a migration-driven relational schema
- Indexes are expected to be created via model metadata or helper scripts
