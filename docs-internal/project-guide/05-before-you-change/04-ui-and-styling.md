# Before Changing UI And Styling

> **Purpose:** Preserve the dashboard's visual system, responsive behavior, and HTMX interactions.
> **Read this before:** Editing templates, CSS, JavaScript, navigation, cards, tables, forms, or charts.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html`, `linkreach/dashboard/templates/dashboard/`, `templates/admin/login.html`

## What breaks easily here, and why

The entire app shell is replaced during boosted navigation. Page scripts may not
reinitialize, Lucide icons require refresh, and workspace/sidebar geometry depends
on coordinated margins and radii. Remote CDN failure can remove core styling.

## Required steps

1. Reuse documented tokens and component classes.
2. Test direct load and navigation from another dashboard page.
3. Test sidebar expanded/collapsed and refresh persistence.
4. Test desktop, tablet, and mobile without squeezing dense tables.
5. Test keyboard focus, Escape/backdrop behavior, labels, and reduced motion.

## Cross-cutting rules

- Poppins for headings, Inter for secondary/body UI;
- `#FAFAFA` app background and white content surfaces;
- borders before shadows; 8px component radius;
- icons for familiar actions with tooltips/accessible labels;
- do not add competing in-page navigation without product need.

## If you change A, you must also update B

- base shell → every page, HTMX swap lifecycle, login consistency;
- design token → Tailwind config, CSS variables, Admin login where applicable;
- sidebar item → active context in its view and responsive/collapsed states;
- fragment markup → initial page include and post-swap icon initialization;
- chart markup/data → Chart.js initializer, empty state, responsive canvas.

## Tests that must pass

```powershell
uv run --no-sync python manage.py check
uv run --no-sync pytest tests/dashboard
```

Manually verify at approximately 1440px, 1024px, and 390px widths. Check browser
console and network errors after both direct load and HTMX navigation.

