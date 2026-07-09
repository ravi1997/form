# Database Migrations and Indexes

This project does not use a traditional migration framework in the repository.

## Index management

- MongoEngine `meta` definitions create many indexes automatically
- `scripts/setup_condition_indexes.py` initializes condition-related indexes
- `scripts/init_rate_limits.py` seeds rate-limit configuration
- `app/openapi.py` attempts to ensure the monitoring stats TTL index exists at startup

## Operational note

Run index-creation scripts before routing production traffic when a new index is introduced or when deploying into an empty database.
