# Debug Session — dashboard/linkedin-account DPAPI crash

**Session ID:** `dashboard-dpapi`
**Status:** [OPEN]
**Reported:** 2026-09-26 19:00 PKT
**Symptom:** `SecretDecryptionError` on `GET /dashboard/linkedin-account/`

## Reproduction

1. Open `http://localhost:8000/dashboard/linkedin-account/` (logged in)
2. Server returns HTTP 500 with traceback ending in `secret_fields.py:124 raise SecretDecryptionError`
3. Stack origin: `linkreach.dashboard.views.linkedin_account`
4. Other admin pages (incl. `/dashboard/`) work fine — the `core_siteconfig` secrets were wiped earlier in this session, so this is a different column.

## Observations

- `LinkedInProfile` model has **two** encrypted fields:
  - `linkedin_password = EncryptedTextField()` (no `default=""`, required)
  - `cookie_data = EncryptedJSONField(null=True, blank=True)`
- `core_siteconfig` had three DPAPI-encrypted columns that crashed on read — we blanked those via raw SQL earlier.
- Nothing has been written to `linkedin_linkedinprofile` via the current OS user yet. But the **dashboard view queries and instantiates the profile**, and Django's ORM calls `from_db_value` (which calls `reveal_secret`) for **every encrypted column** on the row — including `linkedin_password`.
- If **any** row exists in `linkedin_linkedinprofile` (even seeded by `setup_crm` or left from a prior session) with a DPAPI-encrypted `linkedin_password` written under a different Windows user, reading it triggers the same `Key not valid for use in specified state` from `CryptUnprotectData`.

## Hypotheses (falsifiable)

1. **H1 — Stale DPAPI row in `linkedin_linkedinprofile`.** `setup_crm` or a prior onboarding flow wrote at least one `LinkedInProfile` row whose `linkedin_password` was encrypted under a different Windows user. The dashboard view selects that row → `from_db_value` → `reveal_secret` → DPAPI fails → 500. *(Most likely — same root cause as the earlier `SiteConfig` crash.)*
2. **H2 — Foreign key relationship.** The view may be doing `select_related` on a model whose encrypted columns also fail. `LinkedInProfile.user` is FK to `auth.User`, which has no encrypted fields — so probably not.
3. **H3 — `cookie_data` field, not `linkedin_password`.** Both fields are encrypted. Could be either. Distinguishable by stack frames — `reveal_secret` doesn't tell us which, but `from_db_value` is per-class, so the field class tells us.
4. **H4 — Dashboard view itself does extra decryption.** Need to read `dashboard/views.py:linkedin_account` to confirm it just renders a form (no extra decrypt calls).
5. **H5 — Old Chromium session JSON.** `cookie_data` holds an encrypted JSON blob of browser storage state — if a previous daemon wrote that under a different user, the dashboard 500s on the same trigger. H1 already covers this; H5 is just naming the alternate field.

## Instrumentation plan (Step 3 — no business logic edits yet)

- Read `dashboard/views.py:linkedin_account` + the template to confirm H4.
- Read `linkedin/models.py:LinkedInProfile` migrations + count rows + dump `linkedin_password`/`cookie_data` prefixes via raw SQL — confirms H1/H3/H5.
- Add a single transient instrumentation log inside `linkedin_account` view (collapsible `# region debug-point`) that prints the row count + the lengths of `linkedin_password`/`cookie_data` BEFORE Django tries to decrypt — that's the only safe way to surface the state without triggering `from_db_value`.

## Evidence (read-only)

- 1 row in `linkedin_linkedinprofile`, id=8, user_id=10 (`admin`, superuser)
- `linkedin_password`: 389 B, `enc:v1:dpapi:AQAAANCMnd8BFdERjHoAwE_Cl-s…`
- `cookie_data`: 15,577 B, same DPAPI prefix (full Chromium storage_state)
- Both columns unreachable from this OS user → `CryptUnprotectData` → `OSError -2146893813` → `SecretDecryptionError`

## Resolution

User opted for **Option 2: delete the LinkedInProfile row** (clean install, nothing to preserve).

- `linkedin_actionlog`: 2 rows cascaded-deleted
- `linkedin_linkedinprofile`: 1 row deleted
- `auth_user`: preserved (admin login intact)
- Post-fix: `GET /dashboard/linkedin-account/` returns HTTP 302 (login redirect) — no more 500

## Cleanup

- Deleted helper scripts (`_delete_liprofile.py`, `_tables.py`)
- Debug session file kept for reference

## Status

- [RESOLVED] — fixed by removing the DPAPI-locked row; root cause was the same cross-user secret issue that hit `SiteConfig` earlier.
