# Backend Integration Plan

## Existing Backend Pieces

Current model:

`linkreach.linkedin.models.LinkedInProfile`

Important fields:

- `user`
- `self_lead`
- `linkedin_username`
- `linkedin_password`
- `active`
- `connect_daily_limit`
- `follow_up_daily_limit`
- `legal_accepted`
- `cookie_data`
- `newsletter_processed`
- `contribute_to_hub`

Current session behavior:

- `AccountSession` wraps one LinkedIn profile.
- `start_browser_session(session)` launches browser/login.
- Successful login saves cookies into `cookie_data`.
- Existing cookies are reused.
- Expired cookies trigger reauthentication.

Current daemon behavior:

- main daemon picks first active LinkedIn profile.
- checkpoint errors stop the daemon.
- user is expected to clear checkpoint manually and restart.

## Required V1 Backend Additions

Add dashboard views for LinkedIn account management:

- `GET /dashboard/linkedin-account/`
- `POST /dashboard/linkedin-account/connect/`
- `POST /dashboard/linkedin-account/reconnect/`
- `POST /dashboard/linkedin-account/update/`
- `POST /dashboard/linkedin-account/pause/`
- `POST /dashboard/linkedin-account/disconnect/`
- optional: `GET /dashboard/linkedin-account/status/` for HTMX polling

## Recommended Service Layer

Create a service module such as:

`linkreach/dashboard/linkedin_account_service.py`

Responsibilities:

- get current user LinkedIn profile
- create/update profile
- clear cookies
- calculate status
- count action logs for today
- validate legal acceptance
- classify session errors into UI-safe statuses

## Status Model

The UI needs a status abstraction instead of exposing raw exceptions.

Suggested statuses:

- `not_connected`
- `connecting`
- `connected`
- `verification_required`
- `credentials_failed`
- `session_expired`
- `paused`
- `rate_limited`
- `error`

These can initially be computed from existing fields plus recent connection attempt result.

## Missing Persistence

Current model does not store:

- connection status
- last verified timestamp
- last error code
- last error message
- checkpoint URL
- verification required timestamp

Recommended model additions:

- `connection_status`
- `last_verified_at`
- `last_connection_attempt_at`
- `last_error_code`
- `last_error_message`
- `checkpoint_url`

Alternative v1 shortcut:

- derive state from `active`, `cookie_data`, and temporary messages.
- less work, but weaker UX after page refresh.

Strong recommendation:

Add persistent status fields before building the full UI.

## Verification Handling

Current checkpoint behavior exists in daemon code:

- `CheckpointChallengeError`
- `_exit_on_checkpoint`

For dashboard connection flow, do not call daemon exit logic. Instead:

1. catch checkpoint or authentication exceptions
2. save `connection_status="verification_required"`
3. save checkpoint URL if available
4. show the verification page state

## Security Considerations

Current model stores `linkedin_password` as plain text. Before exposing a polished account UI, decide whether to:

- keep current behavior for local/self-hosted v1
- encrypt stored password
- store password only temporarily for login
- rely on saved cookies after first connection

Recommended v1 minimum:

- do not display saved password
- mask password fields
- only update password when a new value is submitted
- clear cookies when username/password changes
- protect all views with `login_required`
- only allow users to manage their own profile

## Campaign Relationship

Campaigns are linked to Django users through:

`Campaign.users`

Because `LinkedInProfile.user` points to the same user, campaigns can be associated with accounts indirectly.

V1:

- show campaigns attached to the current user.

V2:

- support multiple sender accounts per workspace/campaign.
- add sender assignment UI.
- daemon should run per account or rotate eligible accounts.

## Action Usage

Use `ActionLog` for usage display:

- connect count today
- follow-up count today
- recent activity list

This aligns UI with existing backend rate limit logic.
