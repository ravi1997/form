# Architecture Decisions

## Current decisions

- Flask + flask-openapi3 is the HTTP layer
- MongoDB is the system of record
- Redis is used for Celery and distributed rate-limiting support
- Celery handles async condition workloads
- MongoEngine documents model the application state

## Reasoning

- The stack favors straightforward operational deployment over a heavier service mesh or relational schema
- The API exposes schema-validated endpoints directly from the Flask application
- The worker process can scale independently from the API

## Notable tradeoffs

- Access tokens are not blocklisted individually to keep revocation mechanics simple and short-lived
- In-memory rate limiting exists as a last resort but is not distributed
- The docs favor one canonical tree rather than repeated information in multiple root-level markdown files
- UI templates are versioned through revisions instead of mutable inline blobs
