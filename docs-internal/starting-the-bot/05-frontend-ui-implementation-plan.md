# Frontend UI Implementation Plan

## Where the control goes

Top of the Monitor page, directly in the existing status banner
(`dashboard/templates/dashboard/_status.html`, included by `monitor.html` at
line 9) — not a separate section. The operator's first question on this page
is "is it on," and the button to change that should sit right next to the
answer, not below three other cards. This also matches the LinkedIn Account
page's own pattern: one status card, action buttons directly inside it (see
`_linkedin_status.html`, already built).

## Visual states (reuses existing design tokens — no new CSS system)

Reuse the exact chip/tone convention already established on
`_linkedin_status.html` (`.oo-chip` + border/bg/text color trio) and
`_status.html` (the `tone == 'danger'|'warning'` branching already in
`monitor.html`'s banner). Add one more tone bucket, `neutral`, for "stopped
but not an error" (today's code only has `good`/`warning`/`danger` — see
`bot_status()`'s `tone` variable, `services.py` line 265).

| State | Chip color | Icon | Primary button shown |
|---|---|---|---|
| Not running | gray/neutral (`border-hair bg-zinc-50 text-ink/70`) | `power-off` | **Start bot** |
| Starting | sky/blue, pulsing dot (matches `verifying` state on LinkedIn page) | `loader-2` (spin) | *(button hidden — mid-action)* |
| Running (idle/working/waiting — existing stage labels apply) | emerald/green, same as today's `good` tone | existing per-stage icon, unchanged | **Stop bot** (secondary style) |
| Unresponsive / Hung | amber | `triangle-alert` | **Force stop** (danger style) + explanatory text |
| Crashed | red (today's `danger` tone, but now driven by process state, not log text) | `triangle-alert` | **Start bot** (restart) |

## The button + confirmation

```html
{% if bot.state == 'not_running' or bot.state == 'crashed' %}
  <form method="post" action="{% url 'dashboard:bot_action' 'start' %}">
    {% csrf_token %}
    <button class="oo-button oo-button-primary">Start bot</button>
  </form>
{% elif bot.state == 'running' %}
  <form method="post" action="{% url 'dashboard:bot_action' 'stop' %}"
        onsubmit="return confirm('Stop the bot? In-progress LinkedIn actions will finish, then it will shut down cleanly.');">
    {% csrf_token %}
    <button class="oo-button oo-button-secondary">Stop bot</button>
  </form>
{% elif bot.state == 'hung' %}
  <form method="post" action="{% url 'dashboard:bot_action' 'force-stop' %}"
        onsubmit="return confirm('The bot isn\'t responding. Force-stopping may interrupt an in-progress LinkedIn action. Continue?');">
    {% csrf_token %}
    <button class="oo-button text-red-700 hover:bg-red-50">Force stop</button>
  </form>
{% endif %}
```

A plain `confirm()` is consistent with existing dashboard patterns — nothing
here currently uses a styled modal for confirmations (campaign delete, lead
disqualify, etc. — check those views for the actual current convention before
building; if a modal pattern exists there, mirror it instead of introducing
`confirm()` as a new one-off).

## HTMX wiring — do not repeat the inheritance bug

The status banner is already polled: `_status.html` is included inside a
`div hx-get="{% url 'dashboard:monitor_status' %}" hx-trigger="every 5s"` at
`monitor.html` line 9 — **already fixed** (as of this session) to include
`hx-target="this" hx-select="unset" hx-push-url="false"`, per the `#oo-app`
boost-inheritance trap documented in `02-current-state-and-gaps.md`. Because
the Start/Stop button lives *inside* this same polled fragment, it
automatically gets these same safe overrides for free — **do not** give the
button its own separate `hx-get`/`hx-post` polling loop; let it be a plain
`<form method="post">` (full-page redirect on submit, like every other
dashboard action today) so it inherits nothing new to get wrong. Only the
*status display* needs to be live-polled; the *action* can be a normal POST.

## Button state during "Starting"

Between clicking Start and the next 5s poll confirming a heartbeat, the
button should not be clickable again (prevents the double-launch race noted
in `03-architecture-and-process-model.md` even before the backend's own
DB-level guard kicks in — defense in depth, not a replacement for it). Two
options, pick the simpler one to build first:
1. **Server-truth only (recommended for v1):** rely on the 5s poll. Right
   after a successful Start POST and redirect back to Monitor, `bot.state`
   is already `starting` (set optimistically by the `start()` call before
   returning) — so the very next render already shows the disabled/hidden
   button state. No extra JS needed.
2. **Optimistic client-side disable:** add `hx-disabled-elt="this"` (a
   built-in htmx attribute) to the form's submit button for extra safety
   against a double-click in the ~200ms before the redirect completes.
   Nice-to-have, not required for v1.

## Explaining "why can't I see the browser window" inline

The bot runs a **visible, headed** Chrome window (`BROWSER_HEADLESS = False`
in `linkedin_cli/conf.py`) — when started from the dashboard via a detached
subprocess, that window will still pop up on the operator's desktop (same
machine), which can be surprising the first time ("I clicked a button in my
browser tab, why did a totally different Chrome window just open?"). Add one
line of copy under the Start button, shown once in the "Starting" state:

> *A separate Chrome window will open on this computer — that's the bot
> signing in to LinkedIn. Don't close it.*

This mirrors the copy already written for the LinkedIn Account page's
"Start verification" flow (`_linkedin_status.html`) — reuse the same
sentence structure so the two features feel like one consistent product,
not two different explanations for the same underlying fact.

## Docker/non-local scoping in the UI

Per `08-risks-and-open-questions.md`, if the app detects it's running in the
Docker/managed context (see that doc for the detection approach), the
Start/Stop button should not appear at all — replace it with a plain
sentence: *"This bot runs as part of the managed container and starts
automatically."* Don't show a disabled button with no explanation; that
reads as broken, not as "not applicable here."
