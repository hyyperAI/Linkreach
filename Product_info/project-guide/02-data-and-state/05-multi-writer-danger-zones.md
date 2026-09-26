# Multi-Writer Danger Zones

> **Purpose:** Identify state that can be written from multiple code paths.
> **Read this before:** Changing state fields, bulk updates, imports, bot controls, or account verification.
> **Source files:** `linkreach/core/db/deals.py`, `linkreach/dashboard/views.py`, `linkreach/core/bot_process.py`, `linkreach/linkedin/browser/launch.py`

| State | Writers | Risk |
|---|---|---|
| `Deal.state` | transition helper, qualification, task handlers, email handler, dashboard queue/import | direct writes can skip scheduler/contact side effects |
| `Lead.urn` / `country_code` | live profile reads and discovery/import | stale or conflicting identifiers can violate uniqueness |
| `Lead.contact_info` | Connected transition and follow-up retry | null is a retry sentinel; replacing it changes idempotency |
| `Lead.api_email` | contacts resolve, BetterContact, CSV import | source/provenance and email-route state can drift |
| `Deal.profile_summary` | AI materialization and CSV import context | different JSON shapes must remain readable by UI/agents |
| `Deal.chat_summary` | chat synchronization | outgoing messages must stay excluded from lead facts |
| `LinkedInProfile.cookie_data` | verification thread and daemon session | concurrent browsers can overwrite cookies |
| `connection_status` | account views and browser launch/verification | a crash can leave stale `verifying` without cleanup |
| `BotProcess` | dashboard process-control and daemon lifecycle | stale PID/heartbeat can misreport or allow unsafe restart |
| `Task.status` | daemon claim/complete/fail and stale recovery | concurrent workers can double-handle work if single-daemon invariant breaks |
| `SiteConfig` | Admin, onboarding, LinkedIn Account AI form | global settings affect all users and worker runs |

Use transactions where check-and-write must be atomic. Treat queryset `update()` as
a low-level write that bypasses model and service behavior. Document any new writer
here and in the relevant state-machine file.

