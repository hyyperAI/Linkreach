# Before Changing Config And Environment

> **Purpose:** Keep configuration sources, defaults, and process handoff consistent.
> **Read this before:** Editing settings, constants, environment variables, startup scripts, or SiteConfig.
> **Source files:** `linkreach/settings.py`, `linkreach/core/conf.py`, `linkreach/core/models.py:9`, `Start-Bot.bat`, `local.yml`

## What breaks easily here, and why

Configuration is split between Python constants, Django settings, database
singletons, environment variables, campaign/profile rows, and the external
`linkedin_cli` package. A value changed in only one startup path can make dashboard
verification and daemon execution behave differently.

## Required steps

1. Identify the authoritative source and every fallback.
2. Document precedence and behavior when the value is blank.
3. Pass required values across the dashboard-to-daemon process boundary.
4. Update local scripts and managed/Docker configuration where applicable.
5. Avoid reading mutable configuration once at import time if runtime edits must apply.

## Cross-cutting rules

- secrets belong in database/env, never committed defaults;
- do not reuse an unrelated environment variable as a deployment signal;
- keep browser path consistent across dashboard and daemon;
- preserve `provider:model` as the stored AI model contract;
- active timezone `None` means no active-hours gating, not UTC.

## If you change A, you must also update B

- settings variable → deployment files, tests, runtime status UI;
- `core.conf` default → model/onboarding defaults and scheduler tests;
- SiteConfig field → migration, Admin, forms, LLM/contact client, docs;
- browser env → Start scripts, bot_process launch, settings verification path;
- managed flag → Monitor controls and deployment docs.

## Tests that must pass

```powershell
uv run --no-sync pytest tests/test_conf.py tests/test_tz_country.py tests/dashboard/test_linkedin_account.py
uv run --no-sync python manage.py check
```

Start the dashboard and bot through the same entrypoints real users use, not only
through an interactive development shell.

