# User Perspective

## Who This Page Is For

The primary user is an operator or founder who wants LinkedFlow to run LinkedIn outreach from their own LinkedIn account.

They may not understand browser cookies, daemon sessions, Playwright, or checkpoints. They only need to know:

- Is my LinkedIn account connected?
- Is it safe and ready to run outreach?
- Does LinkedFlow need anything from me?
- What happens if LinkedIn asks for verification?
- How do I change, disconnect, or reconnect my account?

## Dream Outcome

The ideal experience:

1. User signs in to LinkedFlow.
2. User opens **LinkedIn Account** from the sidebar.
3. User adds their LinkedIn email or username and password.
4. LinkedFlow starts a connection attempt.
5. If LinkedIn accepts the login, the account becomes **Connected**.
6. If LinkedIn asks for two-factor authentication, checkpoint, or identity verification, LinkedFlow clearly says what is needed.
7. User completes the required verification.
8. LinkedFlow confirms that the account is ready.
9. User can later return to the page to see status, limits, last activity, connection health, and account controls.

The user should never feel like the product silently failed.

## User Guidelines

The page should speak in plain product language:

- Use **Connect LinkedIn** instead of “create LinkedInProfile record”.
- Use **Verification required** instead of “CheckpointChallengeError”.
- Use **Session expired** instead of “cookie invalid”.
- Use **Reconnect account** instead of “reauthenticate”.

The page should be transparent without being scary:

- Tell the user LinkedFlow uses their account for outreach automation.
- Tell the user LinkedIn may ask for verification.
- Tell the user not to retry repeatedly if the account is checkpointed.
- Tell the user that daily limits help keep activity controlled.

The page should avoid:

- Technical stack details.
- Long warning blocks.
- Hiding broken states.
- Letting users click “start outreach” when the account is not ready.

## What The User Needs To See After Connection

Once connected, the page should show:

- Account identity: LinkedIn username/email and, when available, detected public profile name.
- Status: Connected, Needs verification, Session expired, Disabled, Error.
- Outreach readiness: Ready, Not ready, Limited today, Paused.
- Daily limits: connection requests and follow-up messages.
- Today’s usage: actions used today versus daily limits.
- Last checked time.
- Connected campaigns.
- Actions:
  - Reconnect
  - Update credentials
  - Disconnect
  - Pause automation
  - Resume automation

## What We Need To Understand Before Going Further

Before implementation, confirm these decisions:

- Should v1 support only one LinkedIn account per logged-in user?
- Should the dashboard support multiple sender accounts later?
- Should passwords continue to be stored, or should we move toward browser-session-only connection?
- Will verification happen inside an embedded/local browser session, or will the UI instruct the user to complete verification in a real browser?
- Should non-staff users be allowed to log in and manage accounts, or is this still admin-only?
- What legal/safety copy is required before enabling automation?
