# Before Changing Campaign Deletion Or Data Retention

> **Purpose:** Prevent accidental loss of shared lead data or misleading cleanup behavior.
> **Read this before:** Editing campaign delete, lead cleanup, cascade rules, or privacy erasure.
> **Source files:** `linkreach/dashboard/views.py:225`, `linkreach/core/models.py:81`, `linkreach/crm/models/deal.py:63`, `linkreach/chat/models.py:21`

## What breaks easily here, and why

Deleting a Campaign removes Deals and messages but leaves Leads. That is deliberate:
Leads are global and may be reused. A cleanup that deletes Leads can cascade into
other campaigns. Conversely, retaining orphan Leads preserves personal/contact data.

## Required steps

1. Draw the exact cascade graph before editing foreign keys or delete code.
2. Determine whether the operation is campaign cleanup, orphan cleanup, or full data erasure.
3. Count affected Campaigns, Deals, Messages, Leads, Tasks, logs, and external contributions.
4. Require explicit confirmation for destructive UI actions.
5. Add rollback/backup guidance for any bulk cleanup command.

## Cross-cutting rules

- never equate Campaign deletion with Lead deletion;
- do not delete a Lead referenced by another Deal;
- consider embeddings, contact_info, api_email, and external contribution history;
- process and Task rows may reference campaign ids in JSON rather than foreign keys;
- deletions must be auditable in UI copy even if no permanent audit model exists yet.

## If you change A, you must also update B

- Campaign cascade → Deal/message/action/search tests and user confirmation copy;
- Lead deletion → every campaign relationship and contact/privacy behavior;
- Task retention → scheduler recovery and Monitor history assumptions;
- external erasure → contacts-service contract and legal documentation;
- cleanup policy → this guide, privacy notice, Admin/CLI tooling.

## Tests that must pass

```powershell
uv run --no-sync pytest tests/db tests/dashboard tests/test_reconcile.py
uv run --no-sync python manage.py check
```

Create two campaigns sharing one Lead, delete one campaign, and verify the Lead and
other campaign Deal survive while the deleted campaign's Deal/messages do not.

