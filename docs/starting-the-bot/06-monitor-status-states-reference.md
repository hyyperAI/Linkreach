# Monitor Status States — Reference

The authoritative state machine the Monitor page must render, and every use
case it has to handle correctly. This is the spec the frontend/backend plans
in `04-` and `05-` implement against.

## The state machine

```
                 ┌─────────────┐
   Start clicked │             │ heartbeat confirmed fresh
        ─────────▶  STARTING   ├──────────────────────────▶  RUNNING
                 │             │                                 │
                 └─────────────┘                                 │
                                                heartbeat goes    │ Stop clicked
                                                stale, PID alive  │ (cooperative)
                                                        ┌─────────┘
                                                        ▼
   PID disappears  ┌──────────────┐   Force stop    ┌─────────────┐
   without a clean │              │◀────────────────┤  UNRESPONSIVE│
   stopped_at      │   CRASHED    │                 │   (HUNG)    │
   ◀───────────────┤              │                 └─────────────┘
                    └──────┬───────┘
                           │ Start clicked (restart)
                           ▼
                    back to STARTING

   PID disappears WITH a clean stopped_at recorded → STOPPED (not "crashed")
```

Five distinct states, not the current two (`good`/`danger`). Each maps to a
concrete, testable condition:

| State | Condition | `tone` |
|---|---|---|
| **Not running / Stopped** | No PID recorded, or PID dead, AND `stopped_at` is set (clean exit) | neutral |
| **Starting** | `start()` was just called; no heartbeat yet, or heartbeat < one poll-interval old and PID freshly recorded | info (blue) |
| **Running** | PID alive AND `last_heartbeat_at` within the freshness window (heartbeat interval × ~2, e.g. 30s if heartbeat writes every 15s) | good (green) |
| **Unresponsive / Hung** | PID alive AND `last_heartbeat_at` older than the freshness window | danger (amber, not red — it might still recover) |
| **Crashed** | PID dead AND `stopped_at` is **not** set (died without the clean-shutdown `finally` block running) | danger (red) |

## Every use case the UI must get right

### UC1 — Fresh install, bot never started
No `BotProcess` row content (or a freshly-created empty singleton). Must
render as **Not running**, not as an error. First-time message: *"The bot
hasn't been started yet."* + Start button.

### UC2 — Operator clicks Start
Immediate feedback: state flips to **Starting** on the very next render
(the `start()` call sets this optimistically before the subprocess has done
anything real — don't wait for a heartbeat to show *some* reaction to the
click). Button becomes hidden/disabled. Within ~15–30s (first heartbeat),
state transitions to **Running** on its own via the existing 5s poll — no
manual refresh needed.

### UC3 — Bot running normally (idle, waiting, or working a task)
State is **Running**. The existing stage sub-label (`Sleeping`, `Waiting`,
`Working` / `Searching` / `Qualifying` / etc. from today's `_stage_from_log`
keyword scan) is still shown *underneath* the Running state as detail text —
that part of the current implementation is genuinely useful and should be
kept, just demoted from "the whole answer" to "extra detail once we already
know it's alive."

### UC4 — Bot crashes (uncaught exception, Python-level crash, killed by OS OOM, etc.)
No clean `finally` ran, so `stopped_at` is never set. PID stops existing.
Next poll after the crash: **Crashed**, tone red, with the last log tail
shown (this is where the *existing* log-error-scan becomes genuinely useful
context — "here's what it was doing when it died" — rather than being the
sole source of truth). Start button reappears, labeled to imply restart
("Start bot" is fine — no need for a separate "Restart" label, the meaning
is the same action).

### UC5 — Bot hangs (process alive, stuck)
E.g. Playwright waiting forever on a page that never resolves, or a deadlock.
PID still alive, but no heartbeat write for 30+ seconds. State:
**Unresponsive**. This is the state this whole plan exists to make visible —
today this looks *identical* to "Sleeping" (a healthy idle state), which is
actively misleading. UI must visually distinguish it clearly (amber +
explicit "not responding" text) and offer **Force stop** as the recovery
path, not the gentle Stop (a cooperative `stop_requested` flag is useless
against a process that's stopped checking its own flags).

### UC6 — Two browser tabs, race to click Start
Tab A clicks Start. Tab B (also on Monitor, maybe from a phone browser or a
second monitor) clicks Start within the same second, before Tab A's poll has
refreshed Tab B's view. Backend's `select_for_update()` guard (per
`03-architecture-and-process-model.md`) ensures only one `subprocess.Popen`
actually fires; Tab B's request sees `BotProcess` already in `Starting`/
`Running` and gets the "already running" message instead of launching a
second daemon. **This must be tested explicitly** — it's the one failure
mode (two daemons on one LinkedIn account) that risks getting the account
flagged by LinkedIn, not just a UI glitch.

### UC7 — Bot started the old way (`Start-Bot.bat`, terminal, not the dashboard button)
Must still be detected correctly — the heartbeat-writing code added to
`rundaemon.py` (`04-backend-implementation-plan.md` §3) runs regardless of
*how* the command was launched, not only when launched via the new
subprocess path. State shows **Running**, `started_by` is `None`/blank
(no dashboard user attached), UI shows *"Started outside the dashboard"*
instead of a username. The Stop button must still work in this case too —
cooperative shutdown via `stop_requested` doesn't care who started the
process.

### UC8 — Operator clicks Stop
State immediately reflects the *request* (e.g. a transient "Stopping…"
label) even though the process itself may take a few seconds to notice
`stop_requested` and exit its current loop iteration. Once the daemon's
`finally` block runs, `stopped_at` is set and state settles to **Stopped**.
If the daemon doesn't notice within a generous timeout (e.g. 60s — much
longer than one loop iteration should ever take), the UI should suggest
**Force stop** as a fallback, since a stop request that isn't honored within
a minute is itself a sign of a hang.

### UC9 — Dashboard process restarts (Django autoreload) while bot keeps running
Because `BotProcess` lives in the DB, not in Django in-memory state, this is
a non-event — the Monitor page on the *new* Dashboard process instance reads
the same DB row and shows the correct, unaffected **Running** state
immediately. This is the concrete payoff of choosing DB-backed heartbeat over
an in-process Python variable — call this out as a smoke test in
`07-implementation-phases-and-testing.md`.

### UC10 — Machine reboots without a clean shutdown
The bot process is gone (OS killed everything), but `stopped_at` was never
set because nothing ran the clean-exit path. On the next Monitor page load
after reboot, this correctly resolves to **Crashed**, not silently to
**Stopped** — which is the honest answer (it didn't shut down cleanly, even
though "the whole machine turned off" is a more benign reason than an actual
bug). Don't special-case this to look like a clean stop; an operator who
doesn't know the machine rebooted should still see a signal that something
ended abnormally.

### UC11 — LinkedIn account gets Disconnected/Paused while the bot is running
These are **independent** states — the LinkedIn Account page's
`connection_status` and the Monitor page's bot process state answer
different questions ("is this account signed in" vs "is the automation
process alive"). Disconnecting the account does not, by itself, stop the
daemon process — the daemon will simply fail its next LinkedIn-touching
task and that failure will show up in the task log, while the bot process
itself is still very much "Running." **Document this distinction visibly**
in both places (a short cross-reference note on each page) so operators
don't confuse "bot process running" with "outreach actually happening" —
they're related but not the same fact, and conflating them was part of the
original confusion this whole plan is responding to.

### UC12 — Docker/managed deployment
Per `08-risks-and-open-questions.md`: state display becomes purely
informational (no Start/Stop controls), sourced from whatever health signal
the managed container already exposes (or, if none exists yet, from the same
heartbeat mechanism — the daemon writes its heartbeat regardless of how it
was launched, so the *display* logic doesn't actually need to change between
Docker and local; only the *controls* need to be hidden).
