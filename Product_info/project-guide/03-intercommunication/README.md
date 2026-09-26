# Intercommunication Index

> **Purpose:** Index how requests, processes, threads, and modules exchange work and state.
> **Read this before:** Changing asynchronous behavior, polling, task execution, or process startup.
> **Source files:** `linkreach/dashboard/views.py`, `linkreach/core/daemon.py`, `linkreach/core/scheduler.py`, `linkreach/core/bot_process.py`

- [Request flow](01-request-flow.md) — browser request through view, services, database, and template.
- [Background processes](02-background-processes.md) — dashboard, daemon, tasks, and verification thread.
- [Polling and database as message bus](03-polling-and-db-as-message-bus.md) — coordination through persisted state.
- [Subprocesses and environment variables](04-subprocesses-and-env-vars.md) — values that cross process boundaries.
- [Good patterns](05-good-patterns.md) — communication patterns worth copying.
- [Risky patterns](06-risky-patterns.md) — concurrency and coupling to handle carefully.
- [LinkedIn verification thread](07-linkedin-verification-thread.md) — exact one-shot verification sequence and limits.

