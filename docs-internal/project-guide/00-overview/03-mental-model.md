# Mental Model

> **Purpose:** Give contributors a compact way to reason about the entire system.
> **Read this before:** Designing a feature that crosses dashboard, database, bot, or browser boundaries.
> **Source files:** `linkreach/core/models.py`, `linkreach/crm/models/`, `linkreach/core/scheduler.py`, `linkreach/core/daemon.py`

Think of linkreach as four cooperating layers:

1. **Control plane:** Django dashboard records intent: campaigns, imported leads,
   account settings, AI settings, bot start/stop requests, and manual queue actions.
2. **State plane:** SQLite is the durable source of truth. Models carry identities,
   workflow state, scheduled Tasks, process heartbeat, messages, and configuration.
3. **Execution plane:** `rundaemon` reconciles and claims Tasks. Handlers choose an
   eligible Deal at execution time and call LinkedIn, AI, contacts, or email services.
4. **Presentation plane:** Django templates and HTMX render database state and poll
   status fragments. The UI does not itself prove external actions succeeded.

The key distinction is **Lead versus Deal**. A Lead is a person shared across the
database. A Deal is that person's state inside one Campaign. Never place
campaign-specific state on Lead, and never treat deleting a Campaign as deleting
the person.

Tasks are intentionally lazy. They identify a campaign and action type, not a fixed
lead. A handler resolves the best eligible Deal at run time. Changing eligibility
queries can therefore alter the meaning of already-created pending Tasks.

State changes may have side effects. The canonical `set_profile_state()` path calls
the scheduler hook and captures contact information on connection. Direct queryset
updates bypass those effects and must be justified explicitly.

