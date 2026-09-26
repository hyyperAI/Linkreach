# Architecture And Process Model

## The core design decision: don't trust the OS process alone

A naive version of this feature is "save a PID file, check `tasklist` for it."
That's necessary but not sufficient — a PID can exist while the process
behind it is hung (browser wedged waiting on a LinkedIn page that never
loads, Playwright deadlocked, etc.), and on Windows a PID can be silently
**reused by a completely unrelated process** once the original exits. We
already hit a live version of this exact class of bug in this project: two
`runserver` processes ended up bound to the same port, one of them a stale
orphan, and diagnosing "which one is real" from the outside took real
digging (see the earlier troubleshooting in this session — `tasklist`
initially only showed one of the two PIDs actually listening). A bot-liveness
check that only asks "does this PID exist" is exposed to the same class of
false-positive.

**Design: combine two independent signals.**

| Signal | Source | What it proves |
|---|---|---|
| **PID liveness** | OS process table (`tasklist`/`psutil`) | The process object still exists |
| **Heartbeat freshness** | A timestamp the daemon itself writes to the DB every N seconds | The process is not just alive, but actively executing its loop |

Combining them gives a real 4-state signal instead of a boolean:

| PID alive? | Heartbeat fresh? | Real state |
|---|---|---|
| No | — | **Stopped** |
| Yes | Yes (< ~20s old) | **Running** |
| Yes | No (stale) | **Hung / unresponsive** — process exists but isn't progressing |
| No, but PID row still says "running" | — | **Crashed** — died without clean shutdown |

This maps directly onto the status states designed in
`06-monitor-status-states-reference.md`.

## Where the heartbeat lives: DB, not a bare file

Use a small dedicated table, not a loose file in `logs/`:

```python
# linkreach/core/models.py (new model)
class BotProcess(models.Model):
    """Singleton (pk=1). One row, tracking the current/last-known daemon process."""
    pid = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    stop_requested = models.BooleanField(default=False)
```

Rationale over a raw PID file:
- The Dashboard process already has a DB connection open on every request —
  no file I/O, no path-existence races, no partial-write corruption if the
  daemon dies mid-write.
- `stop_requested` becomes a clean **cooperative shutdown signal**: the
  Dashboard sets it to `True`; the daemon's own loop (`run_daemon()`'s
  `while True:`) checks it once per idle cycle and exits cleanly, closing its
  Playwright browser context and saving cookies properly first — much safer
  than a hard `taskkill` mid-navigation, which can corrupt `cookie_data` or
  leave LinkedIn thinking the session died abnormally.
- `started_by` gives the Monitor page something concrete to show ("started
  by rehan_sajid at 14:02") instead of a bare PID number.

A hard-kill fallback (`taskkill /PID <pid> /F` on Windows, `SIGKILL` on
POSIX) is still needed for the truly-hung case — see
`04-backend-implementation-plan.md`'s Stop endpoint — but cooperative
shutdown via `stop_requested` should always be tried first, with a short
timeout (e.g. 15s) before escalating to a hard kill.

## How the daemon reports its own heartbeat

`run_daemon()` already has a `Heartbeat` class (`core/daemon.py:105`) that
logs a text line every 5 minutes. Add a second, independent, much more
frequent heartbeat that writes to `BotProcess` instead of the log — e.g.
every 15s, checked at the same points the existing sleep/poll loop already
wakes up (`sleep_with_heartbeat`, the `while True:` top). This is a DB write
from *inside* the daemon process, which is exactly the kind of long-running
worker write Django's ORM already handles fine in this codebase (the daemon
does far more DB writes than this already, e.g. `Task` state transitions).

On daemon startup (`rundaemon.py:Command.handle()`, before `run_daemon()` is
called), write `BotProcess.pid = os.getpid()`, `started_at = now()`,
`started_by` (see below — passed through somehow, or left null for
terminal-launched runs), `stop_requested = False`.

On clean shutdown (whether via `stop_requested` or a normal `sys.exit()` /
`KeyboardInterrupt`), clear `pid` and `last_heartbeat_at` — or better, keep
them and add an explicit `stopped_at` field so the Monitor page can show
*when* and *by whom* it was last stopped, not just "not running."

## How the Dashboard launches the process

`subprocess.Popen([sys.executable, "manage.py", "rundaemon"], cwd=BASE_DIR,
env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": ...}, creationflags=...)` from
inside a Django view.

Windows specifics that matter:
- Use `subprocess.CREATE_NEW_PROCESS_GROUP` (and optionally
  `subprocess.DETACHED_PROCESS`) so the child survives independently of the
  Dashboard's own process tree and isn't killed if the Django dev server
  reloads (`StatReloader` restarts the parent process on `.py` changes —
  a naive child would die with it otherwise).
- Redirect the child's stdout/stderr to the existing `logs/daemon.log` file
  handle (or let the daemon's own `configure_logging()` handle file output
  as it already does) rather than piping to the parent, which would block if
  nobody reads the pipe.
- Do **not** set `--noreload`-equivalent concerns here — this is launching
  `rundaemon`, a different management command from `runserver`, so Django's
  autoreloader for the Dashboard process is irrelevant to it.

This must run **synchronously but briefly** inside the view (just the
`Popen()` call, not waiting for the process to do anything) — matches the
existing project rule already established in this codebase's LinkedIn
verification feature: *never block a request on the actual browser/daemon
work itself* (see `linkreach/linkedin/browser/verify.py` for the existing
pattern of "kick off work, return immediately, poll for status"). Starting
a subprocess is fast (milliseconds); it's what the subprocess *does* after
that (open Playwright, log in) that must never be awaited synchronously.

## Idempotency (Goal G5)

Before launching, the Start endpoint must:
1. Re-check `BotProcess` state fresh from the DB (not a cached value from
   the page's earlier load).
2. If PID is alive AND heartbeat is fresh → refuse, return "already running."
3. If PID is alive but heartbeat is stale (hung) → refuse the *start*, but
   surface a "Force stop" option instead — starting a second daemon against
   the same LinkedIn account while a hung one might still hold the browser
   session is exactly the double-process problem this whole design exists to
   prevent.
4. Only if PID is confirmed dead (or no PID recorded) → proceed to launch.

This check-then-launch has an inherent TOCTOU race if two requests hit
simultaneously (two browser tabs, both clicking Start within the same
event-loop tick). Close it with a DB-level guard: wrap the check+launch in
`transaction.atomic()` with `BotProcess.objects.select_for_update()` — SQLite
in this project's WAL/default mode still serializes writers, so this is
sufficient without extra infra.
