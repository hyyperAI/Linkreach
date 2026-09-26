# Before Changing Tests And Verification

> **Purpose:** Define the verification depth expected for different changes.
> **Read this before:** Adding tests, changing fixtures, or deciding whether a change is complete.
> **Source files:** `pytest.ini`, `tests/conftest.py`, `tests/factories.py`, `tests/`

## What breaks easily here, and why

Tests mock browser, embedding, and network behavior. A passing unit suite can miss
template initialization, subprocess behavior, Windows path handling, migrations,
and real browser state. Conversely, accidentally unmocked services can spend money
or act on LinkedIn.

## Required steps

1. Match test scope to blast radius.
2. Mock external APIs, SMTP, Playwright actions, and LLMs by default.
3. Test both success and expected failure/retry paths.
4. Run Django checks and migration drift checks.
5. Perform a focused manual UI/process smoke test for changed workflows.

## Cross-cutting rules

- tests must not contact real leads or send email;
- use factories/direct model creation and the autouse CRM bootstrap;
- do not swallow unexpected exceptions in tests;
- test persisted state and side effects, not only return strings;
- document any manual-only verification and why it cannot be automated yet.

## If you change A, you must also update B

- model → factories, DB tests, migration check;
- state transition → handler/scheduler tests and state diagram;
- view/template → authenticated client test and manual HTMX/direct-load test;
- process control → platform-specific liveness/start/stop tests;
- integration → mocked contract tests for timeout/error/idempotency.

## Tests that must pass

```powershell
uv run --no-sync python manage.py check
uv run --no-sync python manage.py makemigrations --check
uv run --no-sync pytest
```

Focused examples:

```powershell
uv run --no-sync pytest tests/dashboard
uv run --no-sync pytest tests/browser tests/tasks
uv run --no-sync pytest tests/db tests/test_reconcile.py
```

