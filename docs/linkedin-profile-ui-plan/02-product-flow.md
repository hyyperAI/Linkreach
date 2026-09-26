# Product Flow

## Navigation

Add a new sidebar item:

**LinkedIn Account**

Suggested placement:

- Overview
- Campaigns
- Leads
- Conversations
- Monitor
- LinkedIn Account

This page is account/workspace-level, not campaign-level.

## Primary Flow: New User Connects LinkedIn

1. User opens **LinkedIn Account**.
2. Empty state explains why the account is needed.
3. User clicks **Connect LinkedIn**.
4. User enters:
   - LinkedIn email or username
   - LinkedIn password
   - daily connection limit
   - daily follow-up limit
   - legal acceptance checkbox
5. User clicks **Connect account**.
6. Backend creates or updates `LinkedInProfile`.
7. Backend starts a login/session verification attempt.
8. UI enters **Connecting** state.
9. Result is one of:
   - Connected
   - Verification required
   - Wrong credentials
   - Session/checkpoint error
   - Browser/session startup failed

## Verification Required Flow

If LinkedIn asks for verification:

1. UI shows **Verification required** state.
2. It explains what happened:
   - LinkedIn needs extra confirmation before automation can continue.
3. UI gives one clear path:
   - **Continue verification**
4. Depending on technical approach:
   - open controlled browser to LinkedIn verification page, or
   - instruct user to finish verification in their normal browser and then click **I finished verification**.
5. Backend retries session validation only after user action.
6. If successful, status changes to **Connected**.
7. If not successful, user sees specific next step.

Important: do not auto-retry repeatedly when checkpointed. The current daemon intentionally exits on checkpoint because repeated retries can harden the block.

## Connected Account Flow

Connected state should be calm and dashboard-like.

Show:

- status badge: Connected
- LinkedIn username
- detected profile name if available
- connected since or last verified time
- daily limits
- usage today
- campaigns using this account
- last activity

Primary action:

- **Reconnect**

Secondary actions:

- Update credentials
- Pause account
- Disconnect

## Session Expired Flow

If cookies expire or login is invalid:

1. Account card changes to **Session expired**.
2. Outreach is blocked for that account.
3. User clicks **Reconnect**.
4. Backend clears `cookie_data` and starts login again.
5. If successful, cookies are saved again.

## Wrong Credentials Flow

If username/password are wrong:

1. Keep account in **Not connected** or **Credentials failed** state.
2. Do not save successful session cookies.
3. Show inline field-level guidance:
   - “LinkedIn rejected these credentials. Check your email/username and password.”
4. User can edit and retry.

## Disconnect Flow

User clicks **Disconnect**.

Show confirmation:

“Disconnect this LinkedIn account? Outreach automation will stop until you reconnect.”

On confirm:

- set `active=False`, or
- clear `cookie_data`, depending on product decision.

Recommended v1 behavior:

- keep the record
- clear cookies
- set `active=False`
- preserve action logs

## Update Account Flow

User clicks **Update credentials**.

Allow:

- change LinkedIn email/username
- change password
- update daily limits
- update legal acceptance

Changing username/password should invalidate current cookies and require reconnect.
