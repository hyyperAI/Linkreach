# Implementation Phases

## Phase 1 — Planning And Backend Status Foundation

Goal:

Make the account state understandable and persistent.

Tasks:

- Add persistent status fields to `LinkedInProfile`, or create a related `LinkedInAccountStatus` model.
- Add service functions to calculate account readiness.
- Add dashboard route for LinkedIn Account page.
- Add sidebar navigation item.
- Add read-only account status page.

Deliverable:

User can open the page and see whether their current LinkedIn account exists and whether it is active.

## Phase 2 — Connect And Update Credentials

Goal:

Let user create or update their LinkedIn account from dashboard.

Tasks:

- Build connect form.
- Create/update `LinkedInProfile` for `request.user`.
- Add legal acceptance checkbox.
- Add daily limit fields.
- Mask password handling.
- Clear cookies when credentials change.

Deliverable:

User can add LinkedIn credentials and see account saved in dashboard.

## Phase 3 — Login Verification Flow

Goal:

Turn saved credentials into a verified browser session.

Tasks:

- Add a controlled “Connect account” action that attempts session startup.
- Catch authentication errors.
- Catch checkpoint/verification errors.
- Save status result.
- Show connecting, connected, or verification required state.
- Do not auto-retry checkpointed accounts.

Deliverable:

User can connect account and receive clear outcome.

## Phase 4 — Account Health Dashboard

Goal:

Make the connected account useful after setup.

Tasks:

- Show connected status.
- Show daily limits and usage.
- Show recent action logs.
- Show assigned campaigns.
- Show last verified/check time.

Deliverable:

User understands whether the LinkedIn account is ready for outreach.

## Phase 5 — Account Actions

Goal:

Let user manage the account safely.

Tasks:

- Reconnect
- Pause
- Resume
- Update credentials
- Disconnect
- Confirm destructive or disabling actions

Deliverable:

User can recover from expired sessions or intentionally stop automation.

## Phase 6 — Multi-Account V2

Goal:

Support multiple sender accounts and campaign-level sender assignment.

Tasks:

- Decide workspace/team account model.
- Replace one-to-one user profile limitation if needed.
- Add sender account list.
- Add campaign sender assignment.
- Update daemon to run per account or rotate accounts.
- Add per-account health, usage, and checkpoint state.

Deliverable:

LinkedFlow can operate as a multi-sender LinkedIn outreach system.

## High Priority

- LinkedIn Account page route and sidebar item.
- Read-only current account status.
- Connect/update form.
- Verification required state.
- Reconnect flow.
- Error handling for wrong credentials and checkpoints.

## Medium Priority

- Usage cards from `ActionLog`.
- Assigned campaigns card.
- Pause/resume.
- Persistent last error and last verified fields.
- HTMX polling while connecting.

## Low Priority

- Multi-account sender assignment.
- Account health score.
- Browser session diagnostics panel.
- Team-level permissions.
- Advanced notification settings.
