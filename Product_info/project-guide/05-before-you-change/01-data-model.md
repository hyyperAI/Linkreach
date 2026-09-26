# Before Changing A Data Model

> **Purpose:** Prevent unsafe schema, relationship, and state-storage changes.
> **Read this before:** Editing any Django model, field, constraint, manager, or migration.
> **Source files:** `linkreach/core/models.py`, `linkreach/crm/models/`, `linkreach/linkedin/models.py`, `linkreach/emails/models.py`, `linkreach/chat/models.py`

## What breaks easily here, and why

Fields double as workflow signals: `contact_info=None` means retry, Deal state routes
channels, email timestamps enforce caps, and singleton rows assume `pk=1`. Foreign
key changes can delete shared leads or retain records unexpectedly.

## Required steps

1. Find every field reader/writer, including templates, exports, Admin, and tests.
2. Decide null/blank/default and upgrade behavior for existing rows.
3. Create a migration; review generated operations manually.
4. Preserve or deliberately replace uniqueness and deletion rules.
5. Add factories/fixtures and migration-safe tests.

## Cross-cutting rules

- campaign-specific values belong on Deal, cross-campaign identity on Lead;
- secrets and personal data need explicit storage/display decisions;
- do not change embedding format or model blob compatibility silently;
- direct queryset updates bypass `save()` and hooks.

## If you change A, you must also update B

- model field → migrations, Admin, forms, services, exports, factories, docs;
- Deal state choices → scheduler, handlers, filters, badges, pipeline counts, tests;
- foreign key `on_delete` → deletion docs and deletion tests;
- SiteConfig → onboarding, AI/settings forms, validation, singleton tests;
- LinkedInProfile status → launch/verification code, account fragments, tests.

## Tests that must pass

```powershell
uv run --no-sync python manage.py check
uv run --no-sync python manage.py makemigrations --check
uv run --no-sync python manage.py migrate --plan
uv run --no-sync pytest tests/db tests/test_reconcile.py tests/dashboard
```

