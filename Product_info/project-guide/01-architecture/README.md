# Architecture Index

> **Purpose:** Index the structural and runtime architecture of linkreach.
> **Read this before:** Choosing where new behavior belongs or changing module boundaries.
> **Source files:** `ARCHITECTURE.md`, `linkreach/`, `compose/`, `requirements/base.txt`

- [Module map](01-module-map.md) — every application module and its primary responsibility.
- [Dashboard](02-dashboard.md) — request layer, page services, forms, and templates.
- [Daemon and bot](03-daemon-and-bot.md) — worker startup, loop, task execution, and shutdown.
- [Database](04-database.md) — SQLite ownership, ORM conventions, migrations, and transaction boundaries.
- [Browser automation](05-browser-automation.md) — AccountSession, Playwright, cookies, and `linkedin_cli`.
- [External services](06-external-services.md) — AI providers, LinkedIn, contacts, enrichment, SMTP, and Hugging Face.
- [Hot paths and fragile connections](07-hot-paths-vs-fragile-seams.md) — stable paths to copy and risky boundaries to protect.
- [AI and ML pipeline](08-ai-and-ml-pipeline.md) — embeddings, qualification, summaries, and message generation.
- [Authentication, security, and secrets](09-auth-security-and-secrets.md) — access control and sensitive storage.
- [Local versus managed runtime](10-local-vs-managed-runtime.md) — Windows, Docker, and process ownership differences.

