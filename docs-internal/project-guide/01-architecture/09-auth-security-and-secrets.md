# Authentication, Security, And Secrets

> **Purpose:** Record the current access-control and secret-storage reality.
> **Read this before:** Authentication, user management, hosting, credentials, API settings, or multi-user work.
> **Source files:** `linkreach/settings.py:24`, `linkreach/dashboard/views.py:38`, `linkreach/core/models.py:9`, `linkreach/linkedin/models.py:31`

## Current behavior

- Dashboard pages use `@login_required`; login is Django Admin login.
- There is no dashboard role or object-level permission layer.
- many Campaign, Deal, and Lead queries are global rather than scoped to `request.user`.
- `Campaign.users` exists but is not consistently used for authorization.
- `LinkedInProfile` is one-to-one with a Django user.
- the LinkedIn password, LLM API key, BetterContact key, contact token, mailbox
  password, and cookies are stored in the local database without application-level encryption.
- settings currently contain a development secret key, `DEBUG=True`, and `ALLOWED_HOSTS=['*']`.

This is acceptable only for a trusted, local/self-hosted development context. It is
not production-safe internet-facing configuration.

## Security boundaries

Never render stored secrets back into forms. The AI form uses a blank password field
to mean “keep the saved key.” Preserve that convention. Never include credentials,
cookies, contact details, or raw conversation content in logs.

Before claiming multi-user support, enforce user-scoped querysets, object ownership,
privileged bot controls, per-user configuration where needed, encrypted secret
storage, production settings, and tests for cross-user access.

