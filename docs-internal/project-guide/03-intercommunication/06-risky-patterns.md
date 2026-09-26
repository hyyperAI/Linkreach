# Risky Communication Patterns

> **Purpose:** Explain patterns that can cause races, stale UI, duplicate actions, or hidden side effects.
> **Read this before:** Adding concurrency, direct writes, polling, or another process.
> **Source files:** `linkreach/dashboard/views.py:646`, `linkreach/linkedin/browser/verify.py:26`, `linkreach/core/bot_process.py:21`, `linkreach/core/models.py:96`

## Direct state writes

`QuerySet.update()` is fast but bypasses `save()` and transition hooks. It is only
safe when no hook should run. Adding a hook later requires auditing every direct writer.

## In-memory concurrency guards

The verification `_running` set protects only one Django process. It does not guard
against another runserver worker, reload, daemon, or machine.

## PID-only checks

`tasklist`/`os.kill(pid, 0)` proves a PID exists, not that it is the original daemon.
Heartbeat freshness reduces but does not eliminate PID-reuse ambiguity.

## Multiple daemons

Task claiming uses a query followed by state mutation, not a distributed lease with
`select_for_update(skip_locked=True)`. The system relies on one-daemon operation.
Starting a second daemon can duplicate LinkedIn actions.

## Global mutable configuration

`SiteConfig` and `BotProcess` are singleton records. A form shown on a per-user page
still changes installation-wide behavior.

## Log-derived status

Monitor presentation still uses daemon log content for stage/issue detail. Log text
is observational and can be stale or changed by copy edits; process state must come
from BotProcess and durable rows.

