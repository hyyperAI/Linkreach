# LinkedIn Profile UI Plan

This folder defines the product and implementation plan for a user-facing LinkedIn account/profile connection experience in LinkedFlow.

The goal is to let a user connect their LinkedIn account, handle verification states, understand whether the account is ready for outreach, and manage the account later without needing Django Admin or terminal commands.

## Files

- `01-user-perspective.md` — user goals, mental model, guidelines, and dream outcome.
- `02-product-flow.md` — end-to-end account connection, verification, connected, and recovery flows.
- `03-ui-page-spec.md` — screens, components, states, copy, and interaction recommendations.
- `04-backend-integration.md` — current backend model, required backend changes, APIs/views, and security notes.
- `05-errors-and-edge-cases.md` — likely failure modes and how the UI should communicate them.
- `06-implementation-phases.md` — practical build phases and priority order.

## Current Backend Reality

LinkedFlow already has backend concepts for LinkedIn accounts:

- `LinkedInProfile`
- one LinkedIn profile per Django `User`
- saved LinkedIn cookies in `cookie_data`
- account `active` flag
- per-account daily limits
- `legal_accepted`
- action logs per LinkedIn profile
- daemon checkpoint handling

However, the dashboard does not yet expose a polished user-facing LinkedIn account page. The current daemon path mainly runs the first active LinkedIn profile, so true multi-account sender orchestration should be treated as a later expansion.

## Strong Recommendation

Build a dedicated dashboard page named **LinkedIn Account** or **Sender Account**.

For v1, focus on one connected LinkedIn account per logged-in user:

1. Add account credentials.
2. Start verification/login.
3. Show pending verification if LinkedIn asks for a code or challenge.
4. Show connected state when cookies are valid.
5. Allow disconnect, reconnect, update credentials, and view safety limits.

Avoid building multi-sender rotation until this single-account management flow is reliable.
