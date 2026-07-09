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
