# Problem And Goals

## The problem, in plain terms

1. **Two processes, one memory.** The operator has to know that "the dashboard"
   and "the bot" are different programs, and start both, every session. Nothing
   in the UI explains this. A first-time user who only runs
   `Start-Dashboard.bat` will create campaigns, add leads, connect LinkedIn —
   and nothing will ever send, with no on-screen explanation why.
2. **The Monitor page's status is a guess, not a fact.** `bot_status()`
   (`linkreach/dashboard/services.py`) never checks whether a `rundaemon`
   process exists. It reads the last ~80 lines of `logs/daemon.log`, greps
   for the word "error"/"traceback"/"exception", and infers a stage
   ("Sleeping", "Working", "Needs attention") from keyword matching. Two
   concrete failure modes we've already hit:
   - The bot isn't running at all, but the log file still has an old error
     in its tail from a previous run → Monitor shows "Needs attention" when
     the honest state is "not running."
   - The bot **is** running and healthy, but hasn't logged anything
     "error"-shaped in the last 80 lines → looks fine, but so would a hung
     process that stopped writing to the log entirely (no heartbeat check
     against wall-clock time — `_last_active()` only looks at *whichever*
     timestamp is newest, DB or file, with no "but is anything still writing
     to it" check tied to whether the OS process itself is alive).
3. **No way to start, stop, or restart the bot without leaving the browser** —
   the operator has to alt-tab to a file explorer / terminal every time.

## Goals

- **G1.** One click, from the Dashboard, starts the bot — no terminal needed.
- **G2.** The Monitor page shows a status that is **verified against the
  actual OS process**, not inferred from log text. "Running" must mean a
  `rundaemon` process is confirmed alive right now.
- **G3.** The operator can stop the bot from the UI (e.g. before editing
  LinkedIn credentials, or to free the account for a manual browser session).
- **G4.** If the bot crashes, the UI says so within one status-poll interval
  (today's 5s cadence) — not "Sleeping" while a dead process's stale log sits
  there.
- **G5.** Starting is idempotent — clicking "Start" twice, or across two
  browser tabs, never launches two competing `rundaemon` processes against
  the same LinkedIn account.
- **G6.** The feature is inert (button hidden or clearly disabled with an
  explanation) in the Docker deployment, where the daemon is already the
  container's own managed process. See `08-risks-and-open-questions.md`.

## Non-goals (explicitly out of scope for this plan)

- Auto-starting the bot at machine boot / Windows login. (Could be a later,
  separate plan — Scheduled Task / Windows Service — noted as a follow-up in
  `08-risks-and-open-questions.md`, not designed here.)
- Multi-account / multi-bot orchestration. Still one LinkedIn account, one
  bot process — matches the rest of the app's current v1 scope.
- Remote start/stop (starting a bot running on a different machine than the
  dashboard). This plan assumes dashboard and bot always run on the same
  host, which is true today.
