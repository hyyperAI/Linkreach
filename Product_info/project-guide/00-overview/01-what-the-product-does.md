# What The Product Does

> **Purpose:** Explain linkreach without requiring knowledge of Django or Playwright.
> **Read this before:** Product planning, onboarding, workflow, or navigation changes.
> **Source files:** `README.md:22`, `linkreach/dashboard/urls.py:7`, `linkreach/core/daemon.py:320`

linkreach is a self-hosted LinkedIn outreach workspace. An operator connects a
LinkedIn account, creates campaigns, imports or discovers LinkedIn profiles, lets
AI evaluate fit, and uses a controlled automation worker to connect or follow up.
Where a work email is available and a mailbox is configured, the workflow can
route a qualified Deal into a one-message email path instead.

The dashboard provides:

- campaign setup, CSV import, manual LinkedIn URL input, filters, and export;
- a cross-campaign Leads view and lead-details drawer;
- conversation summaries and stored messages;
- bot start/stop controls, live status, scheduled work, activity, and raw logs;
- LinkedIn account credentials, verification states, limits, and AI provider settings.

The bot provides:

- LinkedIn session startup and cookie reuse;
- search, profile enrichment, qualification, and candidate ranking;
- scheduled connection requests and acceptance checks;
- AI-assisted follow-up decisions;
- optional email enrichment and one-shot email sending.

This is presently a self-hosted, single-operator-oriented product. The schema has
some user relationships, but the dashboard does not consistently enforce
tenant-scoped queries. Do not market or extend it as multi-tenant without first
addressing the boundaries in [auth and security](../01-architecture/09-auth-security-and-secrets.md).

