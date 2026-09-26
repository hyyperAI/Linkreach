# Before Changing CSV Import And Export

> **Purpose:** Protect lead identity, campaign association, imported context, and filtered exports.
> **Read this before:** Changing CSV upload, column mapping, manual lead input, or exports.
> **Source files:** `linkreach/dashboard/views.py:284`, `linkreach/dashboard/views.py:413`, `linkreach/dashboard/views.py:670`, `linkreach/dashboard/templates/dashboard/campaign_import_map.html`

## What breaks easily here, and why

Imports deduplicate global Leads but create campaign-specific Deals. Header mapping,
LinkedIn URL normalization, public-identifier extraction, country/email cleaning,
and summary JSON all interact. Exports contain personal data and must match active
filters.

## Required steps

1. Keep upload parsing separate from mapping confirmation and final write.
2. Validate file size/encoding, headers, LinkedIn URLs, country, and email.
3. Deduplicate within the file and against unique Lead/Deal constraints.
4. Preserve a summary of created/existing/duplicate/invalid/email-added rows.
5. Verify exports reflect the exact filtered queryset and valid CSV escaping/BOM.

## Cross-cutting rules

- never fabricate an email or profile field;
- Lead identity is global; Deal context belongs to the selected Campaign;
- imported names/companies/keywords currently live in summary context, not Lead fields;
- imported Deals begin Qualified unless product policy changes explicitly;
- treat exported files as sensitive personal data.

## If you change A, you must also update B

- accepted header alias → auto-mapping UI and tests;
- imported field → summary schema, lead drawer, keyword/display services, export;
- initial state → queue instructions, lifecycle docs, bot eligibility tests;
- filter → Leads page, campaign page, pagination, export query;
- dedup key → model constraints and conflict reporting.

## Tests that must pass

```powershell
uv run --no-sync pytest tests/dashboard
uv run --no-sync pytest tests/db
uv run --no-sync python manage.py check
```

Manually import a file with valid, duplicate, existing, malformed, missing-email,
and Unicode rows; verify the summary and filtered export contents.

