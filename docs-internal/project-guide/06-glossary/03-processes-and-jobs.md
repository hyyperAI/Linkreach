# Processes And Jobs

> **Purpose:** Distinguish the independently running parts of linkreach.
> **Read this before:** Changing process control, monitoring, verification, scheduling, or browser behavior.
> **Source files:** `linkreach/core/management/commands/rundaemon.py`, `linkreach/core/daemon.py`, `linkreach/core/bot_process.py`, `linkreach/linkedin/browser/verify.py`

**Dashboard server** — Django `runserver`; serves the UI and short-lived requests.

**Daemon / bot** — long-running `rundaemon` process. It owns the automation
browser, reconciles tasks, claims work, and writes process heartbeats.

**Scheduler** — database planning code in `core/scheduler.py`. It creates lazy
Task slots and recovers stale running tasks.

**Task handler** — channel-specific code that executes one claimed Task. LinkedIn
handlers live under `linkedin/tasks/`; email handling lives in `emails/tasks/`.

**Verification thread** — an in-process daemon thread launched by the dashboard
to perform first-time LinkedIn login without blocking a web request. It is not the
same process as `rundaemon` and is not persisted across a dashboard restart.

**Browser session** — `AccountSession`, which connects a `LinkedInProfile`,
campaign context, Playwright objects, cookies, and resolved active-hours timezone.

**Managed deployment** — Docker or another process-manager-owned runtime where
the dashboard must not spawn a second bot. Controlled by `linkreach_MANAGED`.

