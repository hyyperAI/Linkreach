# Good Communication Patterns

> **Purpose:** Catalog reliable patterns contributors should reuse.
> **Read this before:** Designing new cross-module or asynchronous behavior.
> **Source files:** `linkreach/core/scheduler.py`, `linkreach/core/db/deals.py`, `linkreach/dashboard/views.py`, `linkreach/linkedin/browser/verify.py`

## Persist intent, then return

The dashboard starts bot or verification work quickly and redirects. Long browser
work does not block the HTTP request.

## Use one service boundary

Deal transition side effects live in `set_profile_state()`. AI provider construction
lives in `build_llm_model()`. Reuse these boundaries instead of reproducing their
logic in views or handlers.

## Resolve concrete work late

Task payloads carry campaign context; handlers choose an eligible Deal at execution
time. This avoids stale lead ids and supports queue replenishment.

## Make retries idempotent

Contact capture uses null versus non-null as a tried sentinel. Message syncing uses
LinkedIn URNs for deduplication. Deal creation has a unique campaign/lead constraint.

## Return HTML fragments for live state

HTMX polling views perform cheap reads and render the same status vocabulary used by
the full page. They do not maintain a parallel client-side state store.

## Keep expected failures explicit

Authentication, inaccessible profiles, rate limits, and external service outage
have deliberate handling. Unexpected errors should still surface and fail work.

