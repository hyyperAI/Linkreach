# Current State And Gaps

Exact audit of what exists today, file by file, so the implementation plan
isn't guessing.

## How the bot starts today

- `Start-Bot.bat` → activates `.venv`, sets `PLAYWRIGHT_BROWSERS_PATH`, runs
  `python manage.py rundaemon`.
- `linkreach/core/management/commands/rundaemon.py:Command.handle()` runs,
  in order: configure logging → `migrate --no-input` → `setup_crm()` →
  onboarding check → email-setup nudge → build an `AccountSession` for the
  first `active=True` `LinkedInProfile` → ensure newsletter subscription →
  call `linkreach.core.daemon.run_daemon(session)`, which loops forever.
- `run_daemon()` never writes a PID file, never writes a heartbeat file,
  never registers itself anywhere the Dashboard process could see. Its only
  observable output is the `logs/daemon.log` file (see
  `linkreach/core/logging.py:configure_logging` — this is presumably where
  the file handler is wired; confirm the exact path/rotation policy there
  before implementing).

## How "is it running" is inferred today

`linkreach/dashboard/services.py`:

- `LOG_PATH = BASE_DIR / "logs" / "daemon.log"` (line 21).
- `bot_status()` (line 248):
  - Reads the last 80 lines of the log, lowercases the last 40, and does
    substring checks for `"traceback"`, `"noconsole"`, `"error"`,
    `"exception"` → sets `tone="danger"`, label `"Needs attention"`, and a
    fixed message: *"The latest bot log contains an error. Review the log
    before starting another run."* This is a **static message shown whenever
    that text is anywhere in the tail**, regardless of whether the process
    that wrote it is still alive, already recovered, or was closed an hour
    ago with the terminal window shut.
  - Otherwise looks at `Task.objects.filter(status=RUNNING)` for a
    label/detail, or the next `PENDING` task's `scheduled_at` for "Waiting",
    or falls back to `_stage_from_log()` (line 229) — another keyword scan
    over the last 8 log lines ("taking a break", "searching",
    "logging in", "sleeping", ...).
  - `_last_active()` (line 210) takes the max of: last `ActionLog.created_at`,
    last `Task.completed_at`, and the log file's mtime. If that max is more
    than 12 hours old, tone flips to `"warning"`. **12 hours is the only
    staleness signal that exists anywhere** — there is no check on the order
    of seconds/minutes that would catch "the process died 30 seconds ago."
- `monitor.html` polls `monitor_status`, `monitor_feed`, `monitor_log` every
  5–10s via HTMX (`hx-trigger="every 5s"` / `"load, every 10s"`) — see
  `linkreach/dashboard/templates/dashboard/monitor.html`.

**Net effect:** the Monitor page is a *log-tail dashboard*, not a
*process-status dashboard*. It can only ever tell you what the daemon
recently *said*, never whether the daemon *exists right now*. That's the
core gap this plan closes (`03-architecture-and-process-model.md`).

## The `#oo-app` HTMX-boost inheritance trap (already hit once — must not repeat it)

`linkreach/dashboard/templates/dashboard/base.html` wraps the whole app
shell in a boosted element:

```html
<div id="oo-app" hx-boost="true" hx-target="#oo-app" hx-select="#oo-app"
     hx-swap="outerHTML transition:true" hx-push-url="true">
```

Any descendant element that declares its own `hx-get` **inherits**
`hx-target`, `hx-select`, and `hx-push-url` from this wrapper unless it
explicitly overrides them. This already broke the LinkedIn Account page's
status poller and the Monitor page's three existing pollers in exactly this
way — the fix (already applied) is `hx-target="this" hx-select="unset"
hx-push-url="false"` on every polling element. **Any new poller this feature
adds (e.g. a bot-status poller driving the Start/Stop button) must include
this trio from the start** — see `05-frontend-ui-implementation-plan.md`.

## What does not exist today and must be built

- No PID file, no heartbeat file, no any machine-readable liveness signal.
- No Django view that can launch a subprocess.
- No Django view that can terminate the bot process.
- No concept of "who started this" / "was it started from the dashboard or
  a terminal" — today's answer is always "a terminal, by hand."
- No UI control anywhere for starting/stopping — Monitor page is 100%
  read-only today (`dashboard/views.py:monitor`, `monitor_status`,
  `monitor_feed`, `monitor_log` are all plain `GET` + `@login_required`, no
  POST endpoint exists for the bot at all).
