# UI Page Spec

## Page Name

Recommended page title:

**LinkedIn Account**

Subtitle:

“Connect and manage the LinkedIn account LinkedFlow uses for outreach.”

## Layout

Use the same dashboard visual language:

- main background: `#FAFAFA`
- page surface: white
- thin neutral borders
- subtle/no shadow on main cards
- compact shadcn-style controls
- Poppins for headings
- Inter for body text
- 8px-ish radius

## Page Structure

Top page header:

- Breadcrumb: Dashboard / LinkedIn Account
- Title: LinkedIn Account
- Description: Connect and monitor your LinkedIn sender account.

Main content:

1. Account status card
2. Connection setup or connected account panel
3. Safety and limits card
4. Campaign usage card
5. Recent account activity card

## Empty State

When no account exists:

Card title:

**Connect your LinkedIn account**

Body:

“LinkedFlow needs a LinkedIn account before it can send connection requests, check pending invites, or follow up with conversations.”

Primary button:

**Connect LinkedIn**

Secondary text:

“You may be asked to complete LinkedIn verification before the account becomes ready.”

## Connect Form

Fields:

- LinkedIn email or username
- LinkedIn password
- Daily connection request limit
- Daily follow-up message limit
- Legal/safety acceptance checkbox

Suggested default limits:

- connect daily limit: existing backend default or current model value
- follow-up daily limit: existing backend default or current model value

Button:

**Connect account**

Microcopy:

“LinkedFlow stores a browser session after successful login so you do not need to reconnect every run.”

## Connecting State

Show a compact progress card:

- status: Connecting
- spinner/skeleton
- message: “Checking your LinkedIn session…”
- disable duplicate submit

Do not show a blank page during browser/session work.

## Verification Required State

Card title:

**Verification required**

Badge:

Needs attention

Body:

“LinkedIn needs you to confirm this login before LinkedFlow can continue.”

Actions:

- Continue verification
- I finished verification
- Cancel

Guidance:

“Avoid repeated retries. Complete the verification first, then return here.”

## Connected State

Status card:

- green/neutral connected badge
- username/email
- detected profile name if available
- last verified/check time
- automation status

Actions:

- Reconnect
- Update credentials
- Pause
- Disconnect

Avoid making disconnect a primary button.

## Safety And Limits Card

Show:

- Connection requests today: used / limit
- Follow-ups today: used / limit
- Active hours/timezone if known
- Account status: Active or Paused

Actions:

- Edit limits

## Campaign Usage Card

Show:

- campaigns attached to this user/account
- campaign name
- pipeline status summary
- whether campaign can run from this account

For v1, this can be read-only.

## Recent Activity Card

Use `ActionLog`:

- connect actions today
- follow-up actions today
- timestamp
- campaign

If empty:

“No LinkedIn actions recorded today.”

## Responsive Behavior

Desktop:

- status/setup card left
- limits/activity cards right
- tables/cards below

Mobile:

- single column
- keep status at top
- collapse advanced details
- keep primary action visible near the top

## States To Design

- No account
- Form editing
- Connecting
- Connected
- Needs verification
- Wrong credentials
- Session expired
- Paused
- Disabled
- Rate limit reached
- Unexpected error
