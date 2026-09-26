# Before Changing Dashboard Views

> **Purpose:** Protect routing, authorization, mutations, fragments, and page context.
> **Read this before:** Editing dashboard URLs, views, forms, services, imports, exports, or actions.
> **Source files:** `linkreach/dashboard/urls.py`, `linkreach/dashboard/views.py`, `linkreach/dashboard/forms.py`, `linkreach/dashboard/services.py`

## What breaks easily here, and why

Views mix full-page and fragment responses, some actions control real processes, and
many querysets are installation-wide. A missing user scope can expose another user's
data; a direct state write can skip worker side effects.

## Required steps

1. Define GET versus POST and require login/CSRF appropriately.
2. Decide object ownership and scope explicitly.
3. Keep expensive browser/AI work outside the request.
4. Supply consistent `active`, breadcrumbs, page title, and descriptions.
5. Verify direct load, HTMX navigation, validation failure, and success redirect.

## Cross-cutting rules

- fragments must be cheap, read-only, and independently renderable;
- use Django forms/structured parsing for input;
- preserve filters across pagination and export;
- user-facing errors must be actionable and must not reveal secrets;
- browser and daemon work must be delegated.

## If you change A, you must also update B

- URL name/path → sidebar links, breadcrumbs, redirects, tests;
- form field → template labels/help/errors and save semantics;
- filter → queryset, querystring persistence, export, active-filter display;
- state action → transition hooks, status UI, activity feed;
- fragment context → initial full-page context and polling endpoint.

## Tests that must pass

```powershell
uv run --no-sync pytest tests/dashboard
uv run --no-sync python manage.py check
```

Use Django's test client to smoke-test the changed URL as authenticated and
unauthenticated users, including invalid POST data.

