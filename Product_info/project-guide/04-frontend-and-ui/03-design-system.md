# Design System

> **Purpose:** Record the current visual tokens and hierarchy.
> **Read this before:** Styling pages, components, charts, login, or responsive layouts.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html:22`, `templates/admin/login.html:19`

## Color

| Token | Value | Use |
|---|---|---|
| background / paper | `#FAFAFA` | application and sidebar background |
| card | `#FFFFFF` | workspace and component surfaces |
| ink | `#09090B` | primary text and primary controls |
| muted | `#71717A` | secondary text |
| hair | `#E4E4E7` | borders and separators |
| hover | `#F4F4F5` | neutral hover and selection |

Red is reserved for destructive actions and failures. Workflow badges may use
restrained status tones, but readable labels must carry meaning without color.

## Typography

- Poppins: headings, brand/primary display text, and editable title fields.
- Inter: body, controls, tables, metadata, and supporting copy.
- no negative letter spacing; primary headings use moderate size and weight.

## Shape and spacing

- component radius: generally `0.5rem` (8px);
- larger framed surfaces/workspace corners: `0.75rem` to `1rem`;
- controls: approximately 40px minimum height;
- use compact table rows and 4/8px-derived spacing increments;
- page content remains fluid; avoid reinstating a global max-width wrapper.

## Elevation

Surfaces use a thin border and subtle shadow. Strong elevation is reserved for the
lead drawer, dropdown-like overlays, and transient floating UI. Hover elevation is
small and paired with a border/background change. Do not apply heavy shadows to
every section.

## Motion

Interactions use 140–220ms transitions. The shell honors `prefers-reduced-motion`
by reducing animation and removing hover movement.

