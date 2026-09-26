# Errors And Edge Cases

## Wrong Credentials

Cause:

- LinkedIn rejects username/password.

User message:

“LinkedIn rejected these credentials. Check your email or username and password, then try again.”

UI behavior:

- stay on form
- preserve username
- clear password field
- do not mark account connected

## Two-Factor Authentication Required

Cause:

- LinkedIn requests 2FA code or device confirmation.

User message:

“LinkedIn needs verification before this account can be connected.”

UI behavior:

- move to verification required state
- provide one clear next action
- do not keep retrying in the background

## Security Checkpoint

Cause:

- LinkedIn flags unusual login or automation behavior.

User message:

“LinkedIn has paused this login for a security check. Complete the check before reconnecting.”

UI behavior:

- block outreach
- show checkpoint guidance
- avoid repeated automatic retries
- allow user to retry only after they confirm completion

## Session Expired

Cause:

- saved `li_at` cookie expired or no longer valid.

User message:

“Your LinkedIn session expired. Reconnect to continue outreach.”

UI behavior:

- show reconnect action
- pause outreach for this account

## Browser Launch Failed

Cause:

- Playwright/browser dependency issue
- local environment issue
- browser process crash

User message:

“LinkedFlow could not start the LinkedIn browser session on this machine.”

UI behavior:

- show retry
- link to technical detail/log only if useful
- keep account not ready

## Account Has No Campaigns

Cause:

- `Campaign.users` does not include current user.

User message:

“This account is connected, but no campaigns are assigned to it yet.”

UI behavior:

- account can be connected
- campaign run status says not assigned

## Legal Acceptance Missing

Cause:

- `legal_accepted=False`.

User message:

“Accept the safety guidelines before automation can run.”

UI behavior:

- block automation
- show checkbox/action

## Daily Limit Reached

Cause:

- action log count meets or exceeds daily limit.

User message:

“Today’s LinkedIn action limit has been reached. LinkedFlow will resume later.”

UI behavior:

- connected but limited
- show used/limit

## Account Paused

Cause:

- user set `active=False`.

User message:

“This account is paused. Outreach will not run until you resume it.”

UI behavior:

- show resume button
- preserve credentials/cookies unless disconnect clears them

## Password Changed Outside LinkedFlow

Cause:

- LinkedIn password changed manually.

User message:

“LinkedIn requires a fresh login. Update credentials and reconnect.”

UI behavior:

- clear stale session after failed auth
- show update credentials action

## Multiple Active Accounts

Cause:

- backend can store multiple `LinkedInProfile` records across users.

V1 risk:

- daemon currently uses first active profile, so UI may imply multi-account automation that does not exist.

UI guidance:

- do not promise account rotation in v1.
- if multiple profiles exist in admin, display only current user’s profile.

## Privacy And Data Sensitivity

Sensitive items:

- LinkedIn password
- cookies in `cookie_data`
- profile identity
- outreach logs

UI should never display:

- raw cookies
- password
- full exception traceback

Admin/debug screens can expose more details, but user-facing UI should be safe and concise.
