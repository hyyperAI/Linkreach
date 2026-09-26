# Implementation Phases And Testing

Suggested build order — each phase should be shippable and tested on its own
before starting the next, same discipline as
`docs/linkedin-profile-ui-plan/06-implementation-phases.md` used for the
LinkedIn Account page.

## Phase 1 — Heartbeat foundation (no UI yet)

**Goal:** the daemon can be truthfully asked "are you alive" from the DB,
with zero UI changes.

Tasks:
- Add `BotProcess` model + migration.
- Wire heartbeat writes into `run_daemon()`'s loop.
- Wire PID/`started_at`/`stopped_at` lifecycle into `rundaemon.py`
  (`try/finally` around `run_daemon()`).
- Add `linkreach/core/bot_process.py` with `is_pid_alive()` and
  `get_status()` only (no `start()`/`stop()` yet).

**Test manually:** start the bot the old way (`Start-Bot.bat`). Open
`manage.py shell` and confirm `BotProcess.load()` shows a live PID and a
heartbeat timestamp that updates every ~15s. Kill the terminal window
(simulating a crash) and confirm `is_pid_alive()` correctly flips to `False`
within one heartbeat interval, while `stopped_at` stays `None` (proving the
crash-vs-clean-stop distinction actually works before any UI depends on it).

**Automated tests:** unit tests for `is_pid_alive()` (mock a real PID —
e.g. the test process's own `os.getpid()` — and a definitely-dead one, e.g.
`99999999`), and for `get_status()`'s four-state logic using a frozen clock
(`freezegun` or Django's own `time_machine`/`override` patterns already used
elsewhere in this test suite — check `tests/conftest.py` for the existing
convention before picking a new one).

## Phase 2 — Rewrite `bot_status()` to use the new signal

**Goal:** Monitor page tells the truth, still with zero new buttons.

Tasks:
- Rewrite `services.py:bot_status()` per `04-backend-implementation-plan.md`
  §7 — process state is ground truth, log-text stays as secondary detail.
- Update `_status.html` template for the new state set (5 states, not 2).

**Test manually:** reproduce the exact bug that started this plan — stop the
bot, leave an old error in `daemon.log`'s tail, reload Monitor. Must now show
**Not running**, not "Needs attention." Then start the bot again and confirm
it correctly flips to **Running** once the first heartbeat lands.

**Automated tests:** `tests/dashboard/` — extend or create
`test_monitor.py` covering each of the 5 states rendering the right label/
tone, driven by directly manipulating `BotProcess` rows in the test DB (no
real subprocess needed for this phase).

## Phase 3 — Start/Stop backend

**Goal:** `bot_process.start()`, `request_stop()`, `force_kill()` work, with
the idempotency guard, but still no UI button — drive them via
`manage.py shell` or a temporary test-only view first.

Tasks:
- Implement `start()` with the `select_for_update()` race guard.
- Implement `request_stop()`.
- Wire `stop_requested` checking into `run_daemon()`'s loop (including the
  long-sleep wake-slicing path, per `04-` §4).
- Implement `force_kill()` (Windows `taskkill`, POSIX `SIGKILL`).

**Test manually:**
- Click-equivalent start → confirm exactly one `rundaemon` process exists
  (`tasklist`/`ps`), confirm `BotProcess` matches.
- Call `start()` twice in immediate succession (e.g. two shell calls,
  or a small script firing two requests concurrently with threads) → confirm
  only one subprocess was actually spawned.
- Call `request_stop()` on a running bot → confirm it exits within one loop
  iteration and `stopped_at` gets set; confirm the browser closed cleanly
  (no orphaned Chrome process left behind — check `tasklist` for
  `chrome.exe` separately from the Python process).
- Kill the daemon process manually mid-run (simulate crash) → confirm
  `force_kill()` on an already-dead PID doesn't error, and `get_status()`
  correctly shows **Crashed** afterward.

**Automated tests:** these are the highest-value tests in the whole feature
and the hardest to make fast/reliable — consider using a trivial dummy
subprocess (e.g. `python -c "import time; time.sleep(30)"`) in place of the
real `rundaemon` command for the race/idempotency tests, since the real
command needs a fully configured `SiteConfig`/`LinkedInProfile`/Playwright
environment that shouldn't be a prerequisite for testing process-management
logic. Save one or two tests that actually launch real `rundaemon` for a
manual/CI-optional smoke test, not the default suite.

## Phase 4 — UI: Start/Stop button + full state display

**Goal:** everything in `05-frontend-ui-implementation-plan.md`, wired to
the Phase 3 backend.

Tasks:
- Add `bot_action` view + URL.
- Update `_status.html` with the state-conditional buttons.
- Add the "browser window will open" explanatory copy.
- Confirm the `hx-target="this" hx-select="unset" hx-push-url="false"` trio
  is present (it already is, on the existing poller this button lives
  inside — just don't remove it).

**Test manually (this is the actual end-to-end test of the whole plan):**
1. Fresh dashboard, bot not running → Monitor shows **Not running** +
   Start button.
2. Click Start → button disappears/disables, state shows **Starting**
   within the same page, **Running** within ~30s, no manual refresh.
3. A real Chrome window opens on the desktop — confirm the explanatory copy
   was shown beforehand, not after (surprise avoidance is the actual UX
   goal here, verify it lands before the window pops up).
4. Click Stop → confirm the running task (if any) finishes, browser closes,
   state returns to **Not running** within a reasonable window, log shows a
   clean shutdown line.
5. Open two browser tabs on Monitor, click Start in both quickly → confirm
   only one bot process, second click's message says "already running/
   starting," not a silent no-op and not an error.
6. Restart the Dashboard's own `runserver` process (or trigger Django's
   autoreload by touching a `.py` file) while the bot is running
   independently → confirm Monitor still shows **Running** immediately on
   the next page load (proves UC9 from `06-`).

## Phase 5 — Docker/managed-mode scoping

Per `08-risks-and-open-questions.md` — detect the managed-container case and
hide the controls, showing the informational sentence instead. Test in an
actual `docker compose -f local.yml up` run, not just by reading the code —
confirm the Monitor page in that environment shows the right
(controls-hidden) variant.
