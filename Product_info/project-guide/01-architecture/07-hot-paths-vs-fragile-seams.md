# Hot Paths Versus Fragile Connections

> **Purpose:** Identify patterns worth copying and boundaries that fail easily.
> **Read this before:** Refactoring shared workflow or moving responsibilities across modules.
> **Source files:** `linkreach/core/db/deals.py:110`, `linkreach/core/scheduler.py:345`, `linkreach/dashboard/views.py:413`, `linkreach/linkedin/browser/verify.py:37`

## Hot paths: copy these patterns

- Deal transitions through `core.db.deals.set_profile_state()` when side effects matter.
- Task creation through scheduler planners, not individual action modules.
- LLM construction through `core.llm.build_llm_model()`.
- account connection display through `linkedin_account_service.account_context()`.
- external contacts contribution through one null-to-non-null write-once boundary.
- HTMX polling endpoints that render small fragments and read current DB state.

## Fragile connections: change carefully

| Connection | Why fragile |
|---|---|
| dashboard `queue_selected()` → direct Deal update | bypasses transition helper and hooks |
| dashboard verification thread → Playwright | in-memory guard disappears on server restart |
| bot start check → subprocess spawn | check/start races and PID reuse are platform-sensitive |
| Task payload → handler eligibility query | pending Tasks change meaning when query rules change |
| Campaign deletion → Deal cascade | Lead survives while campaign summaries/messages disappear with Deal |
| base template → public CDNs | app can render without assets or interaction when offline/CDN blocked |
| SiteConfig singleton → multiple users | one user's AI setting changes behavior for the whole installation |
| first active LinkedIn profile → bot | UI suggests per-user accounts, execution remains globally selected |

Before changing a fragile connection, read the corresponding checklist under
[Before you change](../05-before-you-change/README.md).

