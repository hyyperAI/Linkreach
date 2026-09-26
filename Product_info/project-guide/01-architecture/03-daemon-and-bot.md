# Daemon And Bot Architecture

> **Purpose:** Describe the long-running worker and its control lifecycle.
> **Read this before:** Changing task execution, bot controls, monitoring, startup, sleep, or shutdown.
> **Source files:** `linkreach/core/management/commands/rundaemon.py:15`, `linkreach/core/daemon.py:320`, `linkreach/core/bot_process.py:56`

`manage.py rundaemon` is the automation process. Startup performs migrations,
onboarding/config checks, browser/session setup, and reconciliation before entering
the queue loop. The daemon writes process heartbeats and checks the singleton
`BotProcess.stop_requested` flag during its loop and heartbeat-aware sleeps.

```mermaid
sequenceDiagram
    actor Operator
    participant Dashboard
    participant Control as core.bot_process
    participant DB
    participant Child as rundaemon process
    participant Daemon as run_daemon

    Operator->>Dashboard: Start bot
    Dashboard->>Control: start(user)
    Control->>DB: lock BotProcess and check status
    Control->>Child: spawn management command
    Child->>DB: register PID/start metadata
    Child->>Daemon: initialize session and run
    loop Work loop
        Daemon->>DB: heartbeat
        Daemon->>DB: reconcile and claim Task
        Daemon->>Daemon: execute handler
        Daemon->>DB: complete/fail Task
    end
    Operator->>Dashboard: Stop bot
    Dashboard->>Control: request_stop(user)
    Control->>DB: set stop_requested
    Daemon->>DB: observe request and clear process row
```

`get_status()` combines OS PID liveness, heartbeat freshness, startup/stopping
grace periods, and managed-deployment configuration. A PID alone is not proof that
the correct bot is healthy; Windows PID reuse remains possible because `psutil`
creation-time verification is not implemented.

Only one bot is modeled. `BotProcess` is a singleton and `get_first_active_profile()`
selects one LinkedIn account. Multi-account execution requires architectural work,
not merely another profile form.

