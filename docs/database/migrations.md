# Database Migrations and Indexes

This project does not use a traditional migration framework in the repository. Schema changes are handled by code changes plus explicit index initialization where needed.

## Index management

- MongoEngine `meta` definitions create many indexes automatically
- `scripts/setup_condition_indexes.py` initializes condition-related indexes
- `scripts/init_rate_limits.py` seeds rate-limit configuration
- `app/openapi.py` attempts to ensure the monitoring stats TTL index exists at startup

## Collections with special index behavior

- `user_sessions` indexes session UUID, user UUID, active flag, last-seen timestamp, refresh JTI, and refresh token hash
- `rate_limit_counters` uses a unique compound key plus a TTL index
- `session_audit_logs` uses several query-friendly indexes plus a TTL index
- `token_blocklist` uses TTL expiration on `expires_at`
- `condition_evaluation_stats` is retained with a TTL index

## Operational note

Run index-creation scripts before routing production traffic when a new index is introduced or when deploying into an empty database.
