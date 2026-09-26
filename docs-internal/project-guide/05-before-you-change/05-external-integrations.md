# Before Changing External Integrations

> **Purpose:** Prevent unsafe or incompatible changes to network-dependent services.
> **Read this before:** Modifying LinkedIn, AI, BetterContact, contacts hub, SMTP, or model-kit integrations.
> **Source files:** `linkreach/core/llm.py`, `linkreach/contacts/service.py`, `linkreach/emails/bettercontact.py`, `linkreach/emails/sender.py`, `linkreach/linkedin/ml/hub.py`

## What breaks easily here, and why

Providers differ in authentication, base URL, response shape, retry behavior, and
cost. LinkedIn behavior depends on an external package and changing private UI/API.
Retries can duplicate paid lookups, emails, or LinkedIn actions.

## Required steps

1. Define timeout, expected failures, retries, and idempotency.
2. Mock all network calls in automated tests.
3. Validate credentials without exposing them.
4. Preserve provider/model/base URL mapping and existing saved configuration.
5. Confirm outage behavior does not move state incorrectly.

## Cross-cutting rules

- never log API keys, cookies, passwords, email bodies, or raw contact data;
- one-shot actions require durable evidence before retry;
- contacts contribution remains best effort and privacy-gated;
- OpenAI-compatible providers require explicit base URL;
- use `linkedin_cli` for platform mechanics rather than duplicating them here.

## If you change A, you must also update B

- AI provider → builder, form dropdown/presets, validation, onboarding, tests;
- LinkedIn package API → launch/session/task call sites and pinned compatibility docs;
- enrichment result → Lead fields, route state, UI email indicator, exports;
- SMTP behavior → Mailbox validation, daily caps, Deal audit fields;
- contacts payload → privacy gate, server contract, provenance tests.

## Tests that must pass

```powershell
uv run --no-sync pytest tests/test_llm.py tests/contacts tests/emails tests/api tests/browser
uv run --no-sync python manage.py check
```

Use provider sandbox/test credentials only for an opt-in manual smoke test; never
make the standard test suite call a live service.

