# Before You Change Anything

> **Purpose:** Provide the master safety checklist and route changes to focused checklists.
> **Read this before:** Every code, schema, configuration, integration, or UI change.
> **Source files:** `CLAUDE.md:3`, `ARCHITECTURE.md`, `tests/`, `Makefile`

## What breaks easily here, and why

linkreach combines a web process, a long-running bot, browser automation,
SQLite coordination, external services, and stateful workflows. A local edit can
change eligibility for already-scheduled Tasks, skip transition side effects, expose
secrets, or start concurrent browser sessions.

## Required steps

1. Read the relevant descriptive section and focused checklist below.
2. Search for every reader and writer of fields/functions being changed.
3. Confirm local versus managed runtime behavior.
4. Update migrations, tests, `CLAUDE.md`, `ARCHITECTURE.md`, and this guide as applicable.
5. Verify the user-visible workflow, not only isolated functions.

## Cross-cutting rules

- accuracy over compatibility; migrations still must upgrade existing databases;
- unexpected errors surface; catch only expected and recoverable failures;
- keep secrets and personal data out of logs and rendered forms;
- preserve single-daemon and single-browser-per-account safety;
- do not overwrite unrelated work in the dirty working tree.

## If you change A, you must also update B

- [Data model](01-data-model.md) — schema, fields, constraints, relationships.
- [Daemon and bot](02-daemon-and-bot.md) — loop, task, process, scheduling behavior.
- [Dashboard views](03-dashboard-views.md) — routes, forms, context, imports, actions.
- [UI and styling](04-ui-and-styling.md) — templates, HTMX, tokens, interactions.
- [External integrations](05-external-integrations.md) — LinkedIn, AI, contacts, email.
- [Config and environment](06-config-and-environment.md) — settings, env vars, defaults.
- [Project conventions](07-project-conventions.md) — dependencies, errors, docs, commits.
- [Tests and verification](08-tests-and-verification.md) — verification matrix.
- [CSV import and export](09-csv-import-and-export.md) — parsing, mapping, data fidelity.
- [Auth, secrets, and account state](10-auth-secrets-and-account-state.md) — users and credentials.
- [Campaign deletion and retention](11-campaign-deletion-and-data-retention.md) — cascades and cleanup.

## Tests that must pass

Run from the repository root:

```powershell
uv run --no-sync python manage.py check
uv run --no-sync python manage.py makemigrations --check
uv run --no-sync pytest
```

On a Unix environment created by `make setup`, `make test` is the project-standard
equivalent. Add the focused commands from the selected checklist.

