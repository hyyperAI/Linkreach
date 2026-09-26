# Known Frontend Traps

> **Purpose:** Document implementation details that have caused or can cause visible regressions.
> **Read this before:** Editing the base shell, HTMX attributes, page scripts, sidebar, workspace, or responsive tables.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html:51`, `linkreach/dashboard/templates/dashboard/base.html:201`, `linkreach/dashboard/templates/dashboard/overview.html:137`

## Shell swaps and scripts

HTMX replaces `#oo-app`. Event listeners attached to elements inside the old shell
disappear. Global functions and listeners on `document.body` survive. Reinitialize
Lucide icons after every swap.

## Page-specific JavaScript

Chart initialization and provider-dropdown behavior live in page script blocks.
Verify direct load and HTMX navigation both initialize them; script execution during
selected fragment swaps can differ from full navigation.

## Sidebar state

Collapse state lives in `localStorage`. The collapsed logo uses a fixed crop of the
full logo asset rather than a separate icon. Asset dimension changes can break it.

## Workspace shape

Desktop workspace margins and rounded top corners create the separation from the
sidebar. Altering main width, right margin, or border-radius can reintroduce the
asymmetric “curve on one side only” problem.

## Hover movement

Cards/buttons translate by one pixel and sidebar links by two pixels. Fixed table
tracks and control dimensions are required to prevent apparent layout shift.

## Public CDN dependency

Tailwind, HTMX, Lucide, Chart.js, and fonts are loaded remotely. An offline local
install can lose layout generation, icons, charts, navigation enhancement, and fonts.

## Responsive tables

Do not squeeze all desktop columns onto mobile. Hide or move secondary country and
keyword information into the lead drawer while retaining Profile, Campaign, State,
Email, and actions.

