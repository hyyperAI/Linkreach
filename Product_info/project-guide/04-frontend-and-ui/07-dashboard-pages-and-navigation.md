# Dashboard Pages And Navigation

> **Purpose:** Define the current information architecture and page ownership.
> **Read this before:** Adding navigation, breadcrumbs, tabs, or reorganizing pages.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html:216`, `linkreach/dashboard/urls.py:7`

## Global navigation

The left sidebar is the primary application navigation:

1. Overview
2. Campaigns
3. Leads
4. Conversations
5. Monitor
6. LinkedIn Account

Admin and Sign out sit separately in the desktop footer. The sidebar collapses to
icons at desktop sizes and becomes a horizontal strip at smaller widths.

## Workspace context

The sticky workspace header contains the sidebar toggle and shadcn-style breadcrumb.
It provides orientation, not a competing navigation system. Page title, description,
and actions live below it in a separate section. Do not add page-level tabs without
a real workflow requirement.

## Page responsibilities

- **Overview:** installation-wide metrics, chart, campaign summary, quick actions.
- **Campaigns:** campaign list and creation.
- **Campaign detail:** overview, instructions/context, campaign leads, import/manual add, filters, queue, export.
- **Leads:** cross-campaign scan/filter/export and lead detail drawer.
- **Conversations:** Deals with persisted messages and reply context.
- **Monitor:** bot control, process health, next tasks, activity, and logs.
- **LinkedIn Account:** sender credentials, verification, limits, activity, and global AI settings.

The AI settings card is currently located on a per-user account page but writes the
global SiteConfig singleton. UI copy should not imply those settings belong only to
the logged-in user.

