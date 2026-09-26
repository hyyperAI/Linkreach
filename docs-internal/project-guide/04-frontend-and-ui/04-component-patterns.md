# Component Patterns

> **Purpose:** Define reusable HTML/CSS patterns used across the dashboard.
> **Read this before:** Creating or changing cards, buttons, tables, filters, forms, status UI, or drawers.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html:45`, `linkreach/dashboard/templates/dashboard/leads.html`, `linkreach/dashboard/templates/dashboard/_status.html`

## Surfaces

Use `.oo-surface` for a genuinely framed unit such as a metrics card, table, or
settings section. Do not nest decorative cards or wrap every page section in a card.

## Buttons and icons

Use `.oo-button` plus primary/secondary variants for commands. Use Lucide icons in
icon buttons with `title` or an accessible label. Destructive actions need red text
or border and explicit confirmation.

## Tables

Headers use muted uppercase labels; rows stay compact. Row hover uses a neutral
background and inset anchor. Action icons must have fixed dimensions so hover does
not shift columns. Missing values render meaningful text rather than blank cells.

## Forms

Labels precede inputs, helper text follows, and errors remain close to the field.
Standard inputs share 8px radius and focus ring. Password fields never prefill saved
secrets. Destructive and save actions must remain visually distinct.

## Status

Use text plus icon/dot/spinner. Never rely on color alone. Status cards should tell
the user what happened and the next safe action. The Monitor distinguishes starting,
running, stopping, stopped, unresponsive, crashed, sleeping, and failure states.

## Empty/loading/error states

Tables and drawers need stable skeletons, explicit no-data/no-results copy, and a
retry path. Do not leave an empty surface that appears broken.

