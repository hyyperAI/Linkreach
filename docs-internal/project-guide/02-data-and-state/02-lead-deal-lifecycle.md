# Lead And Deal Lifecycle

> **Purpose:** Define the implemented outreach state machine and routing rules.
> **Read this before:** Changing Deal states, qualification, email routing, connection, follow-up, or outcomes.
> **Source files:** `linkreach/crm/models/deal.py:6`, `linkreach/core/db/deals.py:110`, `linkreach/linkedin/pipeline/qualify.py:44`

```mermaid
stateDiagram-v2
    [*] --> Discovered: Lead created/imported
    Discovered --> Qualified: LLM accepts or manual import
    Discovered --> Failed: LLM rejects (wrong_fit Deal)
    Qualified --> ReadyToEmail: email route hit
    ReadyToEmail --> Emailed: email task sends once
    Qualified --> ReadyToConnect: GP confidence or manual queue
    ReadyToConnect --> Pending: connection request sent
    Pending --> Pending: not accepted / backoff increased
    Pending --> Connected: LinkedIn reports first degree
    Connected --> Connected: follow-up sends or waits
    Connected --> Completed: agent closes conversation
    Qualified --> Failed: operational or policy failure
    ReadyToConnect --> Failed: repeated unreachable profile
    Pending --> Failed: unrecoverable failure
    Connected --> Failed: unrecoverable failure
```

The email and LinkedIn paths are mutually expressed by state. A Deal with
`READY_TO_EMAIL` is not eligible for the connect pool. Sending sets `EMAILED`, which
is a Layer-1 resting state until a human supplies an outcome.

`Lead.disqualified=True` is permanent across campaigns. An LLM rejection is only a
Failed Deal in that campaign. Do not conflate them.

The canonical transition helper is `set_profile_state()`. It writes reason/outcome,
calls `on_deal_state_entered()`, and captures contact information on first Connected.
The dashboard's manual queue currently performs a direct Qualified → Ready to
Connect queryset update because no transition side effect is required for that edge.

