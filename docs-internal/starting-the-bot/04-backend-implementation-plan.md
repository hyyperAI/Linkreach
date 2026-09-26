# Backend Implementation Plan

File-by-file changes. New files marked **(new)**.

## 1. `linkreach/core/models.py`

Add the `BotProcess` model from `03-architecture-and-process-model.md`.
Migration: standard `makemigrations core` — additive only, no data migration
needed (first row is created lazily on first read via a `BotProcess.load()`
classmethod, mirroring the existing `SiteConfig.load()` singleton pattern
already used in this codebase — reuse that exact convention, don't invent a
new one).

```python
class BotProcess(models.Model):
    pid = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    stop_requested = models.BooleanField(default=False)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```

## 2. `linkreach/core/bot_process.py` **(new)**

Single module owning all process lifecycle logic — the Dashboard view layer
should not contain `subprocess`/`os.kill` calls directly, same separation of
concerns already used for `linkedin/browser/verify.py` (dashboard triggers,
a dedicated module does the actual OS-level work).

Functions to implement:

- `is_pid_alive(pid: int) -> bool` — platform-branch: `psutil.pid_exists(pid)`
  if `psutil` is already a dependency (check `requirements/base.txt` first —
  if not present, fall back to `os.kill(pid, 0)` on POSIX and a `tasklist
  /FI "PID eq {pid}"` subprocess check on Windows, matching how this session
  already diagnosed stray processes manually).
- `get_status() -> dict` — reads `BotProcess.load()`, combines with
  `is_pid_alive()`, returns one of the four states from
  `03-architecture-and-process-model.md` plus context (`started_at`,
  `started_by`, `last_heartbeat_at`, seconds-since-heartbeat).
- `start(user) -> tuple[bool, str]` — the guarded launch described in
  `03-architecture-and-process-model.md` §Idempotency. Returns
  `(started: bool, message: str)` so the view can turn it into a
  `messages.success`/`messages.error` the same way every other dashboard
  action already does (`linkedin_account_action` is the existing pattern to
  copy).
- `request_stop(user) -> tuple[bool, str]` — sets `stop_requested=True`,
  `stopped_at=None` (not yet stopped, just requested); does **not** kill
  anything itself. Cooperative shutdown only.
- `force_kill(user) -> tuple[bool, str]` — the escalation path: attempts
  `taskkill /PID {pid} /F` (Windows) or `os.kill(pid, signal.SIGKILL)`
  (POSIX), then clears `BotProcess` state. Only offered in the UI when
  status is **Hung** (see `06-monitor-status-states-reference.md`) — never
  offered as the default Stop action, to avoid casually hard-killing a
  process mid-LinkedIn-action (could leave `cookie_data` half-written, or
  worse, leave LinkedIn's own UI in a bad state that looks like automation
  to their abuse detection).

## 3. `linkreach/core/management/commands/rundaemon.py`

- On entry to `handle()`, after `_ensure_db()`, write the `BotProcess` row:
  `pid=os.getpid()`, `started_at=now()`, `stop_requested=False`,
  `stopped_at=None`. Clear any stale `last_heartbeat_at` from a previous run.
- `started_by` needs a way to travel from "who clicked Start in the
  dashboard" into this process. Simplest approach: an environment variable
  set by `bot_process.start()` when it calls `subprocess.Popen(..., env=...)`
  — e.g. `linkreach_STARTED_BY_USER_ID`. `rundaemon.py` reads it (if
  present) and resolves the `User`; if absent (started from a terminal via
  `Start-Bot.bat` the old way), `started_by` stays `null` and the UI should
  just say "started outside the dashboard" rather than guessing.
- Wrap the whole `run_daemon(session)` call so that on any exit path
  (normal return, unhandled exception, `KeyboardInterrupt`) the `BotProcess`
  row gets `pid=None`, `stopped_at=now()` — use a `try/finally`, not scattered
  updates, so this can't be missed by a future new exit path.

## 4. `linkreach/core/daemon.py`

- In `run_daemon()`'s main `while True:` loop (line ~344), add a
  heartbeat write alongside the existing text-log `Heartbeat.maybe_log()`
  call — a second, more frequent one (e.g. every 15s) that does
  `BotProcess.objects.filter(pk=1).update(last_heartbeat_at=timezone.now())`.
  Use `.update()` (not `.save()` on a fetched instance) so this is a single
  cheap `UPDATE` statement, not a full model round-trip, since it fires far
  more often than the existing 5-minute text heartbeat.
- At the same loop checkpoint, check `stop_requested`:
  ```python
  if BotProcess.objects.filter(pk=1, stop_requested=True).exists():
      logger.info("Stop requested from dashboard — shutting down cleanly")
      session.close()
      return
  ```
  Check this **every idle cycle at minimum** (the loop already wakes up
  periodically via `sleep_with_heartbeat`), so a stop request is honored
  within one sleep-slice, not only at the top of a long `sleep()` call. If
  the daemon is mid `sleep_with_heartbeat(pause, ...)` for hours (outside
  active hours), that function needs the same check added to its own
  wake-slicing loop (`HEARTBEAT_SLICE = 60` already wakes it every minute —
  piggyback the stop-check there).

## 5. `linkreach/dashboard/views.py`

Two new views, `@login_required`, POST-only for the actions (mirrors
`linkedin_account_action`'s existing pattern exactly):

```python
@login_required
def bot_action(request, action):
    from linkreach.core.bot_process import start, request_stop, force_kill
    if request.method == "POST":
        if action == "start":
            ok, msg = start(request.user)
        elif action == "stop":
            ok, msg = request_stop(request.user)
        elif action == "force-stop":
            ok, msg = force_kill(request.user)
        else:
            ok, msg = False, "Unknown action."
        (messages.success if ok else messages.error)(request, msg)
    return redirect("dashboard:monitor")
```

`monitor_status` (existing view) needs to also feed `bot_process` status
into its context so the template can render the button + badge together —
see `05-frontend-ui-implementation-plan.md`.

## 6. `linkreach/dashboard/urls.py`

```python
path("monitor/bot/<slug:action>/", views.bot_action, name="bot_action"),
```

## 7. `linkreach/dashboard/services.py`

`bot_status()` needs a real rewrite, not a patch: the log-text heuristic
(`has_error`, `_stage_from_log`) stays useful for *what stage* a confirmed-
running bot is in (searching, qualifying, sleeping — that's genuinely only
visible in the log), but the **top-level running/not-running/hung
determination must come from `bot_process.get_status()`**, not from whether
the word "error" appears in the tail. Concretely:

```python
def bot_status() -> dict:
    from linkreach.core.bot_process import get_status as process_status
    proc = process_status()  # {"state": "running"|"hung"|"crashed"|"stopped", ...}

    if proc["state"] in ("stopped", "crashed"):
        return {..., "label": "Not running", "tone": "danger" if proc["state"] == "crashed" else "neutral", ...}
    if proc["state"] == "hung":
        return {..., "label": "Unresponsive", "tone": "danger", ...}
    # proc["state"] == "running" — existing log-based stage refinement is still valid here
    ...  # existing has_error / running-task / next-task / _stage_from_log logic, unchanged
```

The existing `has_error` log-scan should be **demoted** — still shown as a
secondary "last log line had an error" note when the process state is
confirmed `running`, but it must never by itself produce "Needs attention"
when the process isn't actually running. That inversion (process-state is
the ground truth, log content is commentary) is the actual fix for the bug
this whole plan exists to solve.
