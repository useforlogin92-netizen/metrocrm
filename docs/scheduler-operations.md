# Scheduler operations and verification notes

## Current production limitation

The current APScheduler instance is started by the web application's lifespan. This is not a reliable guarantee for recurring work on a sleeping/free web service, and multiple web worker processes can each start an in-memory scheduler. A green CI run cannot prove that a job executes on time in Render.

## Safe deployment target

Run scheduled work in one dedicated, always-on worker or managed cron service, backed by the persistent PostgreSQL database. Before enabling a second scheduler, disable the web-process scheduler in a separately reviewed deployment change. Scheduled handlers must be idempotent, use durable job/run records or a PostgreSQL advisory lock, record start/end/status, and retry safely. Do not run a restore as part of a health check or scheduler verification.

## Workload status

- Backup scheduler: existing four-cycle schedule remains unchanged by this patch; backup/restore execution is intentionally not triggered.
- Lead reassignment and reminder automation: verify actual handler implementation and idempotency before registering recurring jobs. A route that suggests assignments is not itself an automatic reassignment worker.
- Render live route checks and redirects: must be verified against the deployed revision after approved deployment. Unit/CI route registration is not live verification.
