# System Diagram

> **Purpose:** Show the main runtime components and information flow.
> **Read this before:** Cross-module changes or integration work.
> **Source files:** `linkreach/urls.py`, `linkreach/core/daemon.py`, `linkreach/core/scheduler.py`, `linkreach/linkedin/browser/session.py`

```mermaid
flowchart LR
    Operator[Outreach operator] -->|HTTPS/local browser| Dashboard[Django dashboard]
    Dashboard -->|reads and writes| DB[(SQLite database)]
    Dashboard -->|start / stop request| BotControl[Bot process control]
    Dashboard -->|verification request| Verify[LinkedIn verification thread]
    BotControl --> Daemon[rundaemon process]
    Daemon -->|heartbeat and task state| DB
    Daemon --> Scheduler[Scheduler and task handlers]
    Scheduler --> DB
    Verify --> Session[AccountSession + Playwright]
    Daemon --> Session
    Session --> LinkedIn[LinkedIn UI and Voyager API]
    Scheduler --> LLM[Configured AI provider]
    Scheduler --> Contacts[Contacts hub / BetterContact]
    Scheduler --> SMTP[SMTP mailbox]
    LinkedIn -->|profiles, status, messages| DB
    LLM -->|qualification, facts, drafts| DB
    Contacts -->|email or contribution result| DB
    SMTP -->|send result| DB
```

```mermaid
flowchart TD
    Lead[Lead: one LinkedIn identity] --> D1[Deal in Campaign A]
    Lead --> D2[Deal in Campaign B]
    CampaignA[Campaign A] --> D1
    CampaignB[Campaign B] --> D2
    D1 --> MessagesA[Chat messages and summaries]
    D2 --> MessagesB[Independent state and summaries]
```

The dashboard and daemon are separate processes in local development. They
coordinate through the database and log file; they do not share Python memory.
The verification thread is an exception: it lives inside the dashboard process.

