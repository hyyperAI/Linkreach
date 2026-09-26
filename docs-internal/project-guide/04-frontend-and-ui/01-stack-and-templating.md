# Stack And Templating

> **Purpose:** Describe the frontend implementation model and asset dependencies.
> **Read this before:** Adding components, scripts, styles, pages, or dependencies.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html:1`, `linkreach/dashboard/templates/dashboard/`, `templates/admin/login.html`

The frontend is server-rendered Django, not React. It uses:

- Django template inheritance and context;
- Tailwind CSS runtime from `cdn.tailwindcss.com`;
- HTMX 1.9.12 for boosted navigation and fragment polling;
- Lucide latest from unpkg for icons;
- Chart.js 4 from jsDelivr for the overview chart;
- vanilla JavaScript for sidebar state and lead drawer behavior;
- Google-hosted Poppins and Inter fonts.

`dashboard/base.html` is the application shell. Page templates extend it and define
`content`, optional `workspace_actions`, and optional `scripts` blocks. Fragment
templates begin with `_` and are rendered both on initial pages and polling responses.

No bundler or component compiler is present. “shadcn-style” means matching its
visual and interaction language using the existing template/CSS stack; copying React
components directly would introduce an incompatible second frontend architecture.

The Admin login is a separate override under `templates/admin/login.html`. Changes
to the dashboard base do not automatically update login styling.

