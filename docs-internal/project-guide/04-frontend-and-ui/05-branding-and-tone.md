# Branding And Tone

> **Purpose:** Record names, assets, metadata, and product-writing conventions.
> **Read this before:** Changing product name, logo, favicon, metadata, navigation labels, or UI copy.
> **Source files:** `linkreach/dashboard/templates/dashboard/base.html:7`, `linkreach/dashboard/static/dashboard/img/`, `templates/admin/login.html`

The browser-facing product title is **LinkedFlow: Scale Your LinkedIn Outreach with
AI**. The current sidebar visual uses the Exop AI logo asset. The favicon and Apple
touch icon use `dashboard/img/linkedflow-favicon.png`.

This mixed naming is intentional in the current implementation but may reflect a
transition between repository name (linkreach), product experience (LinkedFlow),
and organization/brand (Exop AI). `UNVERIFIED:` there is no single checked-in brand
policy defining which name is canonical for marketing, application chrome, or docs.

UI tone should be calm and operational:

- use “Start bot”, “Verification required”, and “No email available”;
- describe what the user can do next;
- avoid internal exception names, model class names, and automation jargon;
- do not imply an external action succeeded until persisted evidence confirms it;
- use “Campaign” consistently, correcting legacy “Compaign” copy when encountered.

Meta description: “LinkedFlow helps teams import leads, manage campaigns, and scale
personalized LinkedIn outreach with AI-powered workflows.”

