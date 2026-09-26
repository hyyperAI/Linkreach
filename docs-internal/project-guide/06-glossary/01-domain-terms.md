# Domain Terms

> **Purpose:** Define product terms in plain language.
> **Read this before:** Changing campaigns, leads, outreach workflow, email, or LinkedIn account behavior.
> **Source files:** `linkreach/core/models.py:81`, `linkreach/crm/models/lead.py:11`, `linkreach/crm/models/deal.py:55`

## A–Z

**Action log** — a persisted record of a rate-limited LinkedIn connect or follow-up action.

**Campaign** — outreach instructions and targeting context. A campaign owns Deals,
search keywords, action logs, and a trained model blob; a Lead may participate in
multiple campaigns through separate Deals.

**Contact information** — the raw LinkedIn contact overlay captured after a
connection is accepted. It is distinct from an enrichment-provider email.

**Deal** — the campaign-specific relationship between one Lead and one Campaign.
The Deal carries workflow state, outcome, summaries, attempts, and email routing.

**Disqualified Lead** — a Lead excluded across campaigns through
`Lead.disqualified=True`. This differs from an LLM rejection, which creates a
campaign-specific Failed Deal with the `wrong_fit` outcome.

**Lead** — a deduplicated LinkedIn identity, keyed by LinkedIn URL and public
identifier. It stores only durable cross-campaign identity and enrichment data.

**LinkedIn account / sender account** — the operator account represented by
`LinkedInProfile`. In v1 it is one-to-one with a Django user, while bot selection
still chooses the first active profile.

**Operator** — the person using the dashboard to configure campaigns, import
leads, connect LinkedIn, monitor automation, and review activity.

**Outcome** — a business result or closing reason attached to a Deal, such as
converted, wrong fit, no budget, or unresponsive.

**Profile summary** — a campaign-scoped JSON fact list about a Lead, generated
on demand from live LinkedIn profile data or populated with imported context.

**Task** — a persistent scheduled unit of work. It identifies an action type and
campaign, while the handler selects the concrete eligible Deal at execution time.

