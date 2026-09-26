# Before Changing The Daemon Or Bot

> **Purpose:** Protect task execution, process control, and LinkedIn account safety.
> **Read this before:** Editing daemon loops, handlers, scheduler, heartbeat, start/stop, or recovery.
> **Source files:** `linkreach/core/daemon.py`, `linkreach/core/scheduler.py`, `linkreach/core/bot_process.py`, `linkreach/core/management/commands/rundaemon.py`

## What breaks easily here, and why

A second daemon can perform duplicate LinkedIn actions. Blocking sleeps can hide
stop requests and stale heartbeats. Handler eligibility changes affect existing lazy
Tasks. Hard kills can interrupt browser actions and cookie persistence.

## Required steps

1. Trace startup, reconcile, claim, handler, completion/failure, and shutdown.
2. Preserve frequent heartbeat and cooperative-stop checks during waits.
3. Confirm recovery of stale Running Tasks after crashes.
4. Validate behavior with no work, future work, auth failure, checkpoint, and rate limit.
5. Test local controls and managed controls separately.

## Cross-cutting rules

- one daemon and one automation browser per sender account;
- scheduler owns Task creation;
- handlers accept `(task, session, qualifiers)`;
- unexpected failures mark the Task failed and remain visible;
- never make dashboard requests wait for the daemon operation to finish.

## If you change A, you must also update B

- heartbeat cadence → freshness/grace thresholds and Monitor copy;
- Task type → enum, scheduler, dispatch map, handler, activity UI, tests;
- eligibility query → planners, queue expectations, lifecycle docs;
- start/stop behavior → BotProcess, status service, Monitor fragments, managed mode;
- auth recovery → browser session, connection status, task failure behavior.

## Tests that must pass

```powershell
uv run --no-sync pytest tests/test_scheduler_advanced.py tests/test_schedule.py tests/test_reconcile.py tests/tasks/test_tasks.py
uv run --no-sync pytest tests/dashboard/test_linkedin_account.py tests/browser/test_launch_status.py
uv run --no-sync python manage.py check
```

Also perform a manual Start → Running → Stop → Not running Monitor smoke test without
opening a second bot process.

