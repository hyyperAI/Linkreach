# Data And State Index

> **Purpose:** Index persistent models, state machines, writers, and deletion behavior.
> **Read this before:** Any model, workflow, import, queue, or lifecycle change.
> **Source files:** `linkreach/core/models.py`, `linkreach/crm/models/`, `linkreach/linkedin/models.py`

- [Data models](01-data-models.md) — fields, relationships, invariants, and ownership.
- [Lead and Deal lifecycle](02-lead-deal-lifecycle.md) — campaign workflow state machine.
- [Connection status](03-connection-status.md) — LinkedIn account verification state machine.
- [Bot process state](04-bot-process-state.md) — process-control state machine.
- [Multi-writer danger zones](05-multi-writer-danger-zones.md) — fields written by more than one path.
- [Email, contact, and conversation data](06-email-contact-and-conversation-data.md) — sensitive communication state.
- [Deletion, cascades, and retention](07-deletion-cascades-and-retention.md) — what is removed and what survives.

