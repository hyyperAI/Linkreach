# Live Updates

> **Purpose:** Explain HTMX navigation, polling, and custom asynchronous UI behavior.
> **Read this before:** Changing live status, scripts, partial templates, history, or drawers.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html:201`, `linkreach/dashboard/templates/dashboard/monitor.html:9`, `linkreach/dashboard/templates/dashboard/linkedin_account.html:6`

## Boosted navigation

`#oo-app` has `hx-boost=true`, selects `#oo-app` from responses, replaces the outer
shell, and pushes the URL. Admin and logout links explicitly disable boosting.

After a full shell swap, JavaScript reapplies sidebar state, refreshes Lucide icons,
and scrolls to the top. Fragment swaps only refresh icons.

## Polling

- LinkedIn account status polls every 5 seconds when a profile exists.
- Monitor status and activity poll every 5 seconds.
- raw log tail loads immediately and polls every 10 seconds.

Polling endpoints return focused HTML fragments and set `hx-push-url=false`.

## Lead details drawer

`ooOpenDeal()` opens a fixed modal/drawer, renders a loading skeleton, fetches the
Deal URL with an `HX-Request` header, and inserts the partial. Escape and backdrop
click close it. Directly opening the same URL renders a full page.

Scripts embedded in swapped page content may not execute as expected because the
app shell and `oo-page-scripts` are separate swap concerns. Prefer globally defined
shell functions or HTMX lifecycle listeners for behavior needed after navigation.

