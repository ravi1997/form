# Form-Builder Backend Rules

## 1. Multi-Tenancy & Index Management
- Do not drop primary or routing indexes (e.g. on `projects`, `forms`, `themes`) when freezing tenant databases. Only drop heavy secondary indexes (`responses`, `commits`).
- When reactivating a database, always rebuild indexes asynchronously (e.g. in a background thread) to avoid blocking the HTTP request and causing cold-start query spikes.

## 2. Non-Transactional Compensating Strategies
- Since local MongoDB instances run as standalone deployments without transaction support, do not rely solely on `start_transaction()`.
- Always wrap multi-document updates in try/except blocks with compensating rollback deletes (e.g., deleting a commit record if the matching form update matched 0 documents or threw an exception) to prevent orphaned collection states.

## 3. Upload & File Cleanup Safety
- Never delete uploaded binary assets or call cleanup routines on error paths (validation failed or merge conflict) because the user may correct other fields and resubmit the same files.
- Perform file cleanup only after successful updates, evaluating deleted files against the union of the old database state and the new request.

## 4. Resource Pruning on Inactive Tenants
- When freezing or unloading a tenant database database, invoke `gc.collect()` to force garbage collection of PyMongo cursor caches and database caches, releasing idle server-side sockets.
