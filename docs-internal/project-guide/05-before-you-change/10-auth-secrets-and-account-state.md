# Before Changing Auth, Secrets, Or Account State

> **Purpose:** Prevent cross-user exposure, credential leaks, and unsafe LinkedIn session behavior.
> **Read this before:** Changing login, permissions, LinkedIn Account UI, credentials, cookies, or AI keys.
> **Source files:** `linkreach/settings.py:24`, `linkreach/dashboard/views.py:62`, `linkreach/dashboard/forms.py:7`, `linkreach/linkedin/models.py:22`

## What breaks easily here, and why

The dashboard is login-required but not consistently user-scoped. LinkedIn and API
credentials are sensitive database values. Verification and daemon paths can race
over one account's cookies. The AI settings form appears on an account page but
writes global SiteConfig.

## Required steps

1. Define who owns and may read/write each object.
2. Ensure saved secrets are never re-rendered, logged, exported, or placed in URLs.
3. Preserve blank-key-means-keep-existing behavior where documented.
4. Prevent concurrent verification and bot browser sessions.
5. Test session expiry, checkpoint, invalid credentials, disconnect, and reconnect.

## Cross-cutting rules

- use POST + CSRF for mutations;
- use object-level filtering before claiming multi-user safety;
- avoid plaintext secrets for production; plan encryption/key management first;
- error messages must be useful without echoing provider responses containing secrets;
- legal acceptance and contribution/privacy flags must not be silently reset.

## If you change A, you must also update B

- login URL/template → redirects, tests, branding, logout flow;
- LinkedInProfile relation → registry/daemon selection, forms, migrations, account page;
- connection status → launch, verification, polling fragment, error copy, tests;
- secret storage → Admin, forms, onboarding, deployment key management;
- user scoping → every Campaign/Deal/Lead query, export, modal, and bot selection.

## Tests that must pass

```powershell
uv run --no-sync pytest tests/dashboard/test_linkedin_account.py tests/browser/test_launch_status.py tests/cli/test_session_registry.py
uv run --no-sync python manage.py check --deploy
```

Add cross-user access tests before enabling multiple users or exposing the app beyond
a trusted local environment.

