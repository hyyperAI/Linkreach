# Starting The Bot — Planning Docs

This folder plans a single feature: **let the operator start (and stop) the LinkedIn
automation bot from the Dashboard**, and make the **Monitor page tell the truth**
about whether it's actually running.

This is a plan, not an implementation. Nothing in `linkreach/` is changed by
these documents. Follow `06-implementation-phases-and-testing.md` when building it.

## Why this exists

Today, two separate processes make up the running app:

- **Dashboard** — `manage.py runserver` / `Start-Dashboard.bat`
- **Bot** — `manage.py rundaemon` / `Start-Bot.bat`

Starting one never starts the other. The operator has to remember to
double-click both `.bat` files every session, and the Monitor page's "is it
running" signal is inferred from log text, not from an actual process check —
so it can say "Needs attention" when the bot isn't running at all, or look
idle when it's mid-crash. See `02-current-state-and-gaps.md` for the exact
mechanism and why it's misleading.

## Files in this folder

| File | Covers |
|---|---|
| `01-problem-and-goals.md` | What's broken today, in plain terms, and what "done" looks like |
| `02-current-state-and-gaps.md` | Line-by-line audit of the existing Monitor/daemon code and exactly where it's wrong |
| `03-architecture-and-process-model.md` | The technical approach: how the dashboard will launch, track, and detect the bot process |
| `04-backend-implementation-plan.md` | File-by-file backend changes |
| `05-frontend-ui-implementation-plan.md` | Monitor page UI: the Start/Stop button, visual states, HTMX wiring |
| `06-monitor-status-states-reference.md` | The exact status state machine + every use case the UI must handle |
| `07-implementation-phases-and-testing.md` | Suggested build order + how to test each phase |
| `08-risks-and-open-questions.md` | Safety considerations, platform scoping (Docker vs local Windows), things that need a decision before building |

## Scope note — this only applies to local/self-hosted runs

In the Docker deployment (`local.yml`, `compose/linkedin/`), there is **one**
container running `rundaemon` as its main process, managed by Docker's own
`restart: unless-stopped` policy — not by the Django dashboard. A "Start Bot"
button launching a *second* daemon process from inside that container would
conflict with it (two processes fighting over the same LinkedIn account/browser
profile). This plan is scoped to the **local Windows two-process setup**
(`Start-Dashboard.bat` + `Start-Bot.bat`) only. See `08-risks-and-open-questions.md`
for how the code should detect and refuse to double-run in the Docker case.
