# linkreach Custom Dashboard — Master Plan

A light/editorial, soft-white, **"linkreach"**-branded admin dashboard served at
`localhost:8000/dashboard/`, login-protected, built entirely *into* Django.

---

## 0. GOLDEN RULES (future self: read this first, never break these)

1. **ADDITIVE ONLY.** Never modify existing models, daemon, scheduler, pipeline, ML,
   tasks, or browser code. The bot must keep working exactly as it does today.
2. **Only TWO existing files may be edited, by adding lines only:**
   - `linkreach/settings.py` → add the app to `INSTALLED_APPS`
   - `linkreach/urls.py` → `include()` the dashboard urls
   Nothing else.
3. **NO new database migrations. NO new model fields. NO new tables.** Reuse existing
   models. The only write paths allowed are:
   - Campaign create/edit/delete via a standard `ModelForm` (the Admin already allows this)
   - Adding seed URLs via the **existing** `create_seed_leads()` function
4. **NO new pip packages.** Tailwind, HTMX, Chart.js all load from a CDN in the browser.
5. **Leads, Deals & ChatMessages are READ-ONLY** from the dashboard. Do NOT add
   outcome-setting or any lead editing (user decision).
6. **Names/companies are NOT stored in the DB.** `Lead` only caches
   `linkedin_url`, `public_identifier` (the handle), `country_code`, `disqualified`.
   Heavy fields (name, headline, company) are fetched live from LinkedIn and not cached.
   → The Leads table shows the **handle** (`public_identifier`), not full names.
   → NEVER call the LinkedIn API from the dashboard to enrich — that touches the
     browser/session and can disrupt the bot.
7. **The dashboard (`runserver`) and the bot (`rundaemon`) are SEPARATE processes.**
   The dashboard controls the bot by spawning/killing it as a **subprocess**, reusing the
   existing `python manage.py rundaemon` command unchanged. NEVER import `run_daemon`
   into the web process (threads + Playwright = fragile).
8. Everything lives under `/dashboard/` and requires login. **`/admin/` stays intact**
   as a fallback.
9. **Uninstall = delete `linkreach/dashboard/` + revert the 2 added lines.** Bot unaffected.

---

## 1. Confirmed product decisions

| Topic | Decision |
|---|---|
| URL | `/dashboard/` (admin stays at `/admin/`) |
| Login | Required, reuse existing superuser (`LOGIN_URL=/admin/login/`) |
| Style | Light / editorial, soft white, brand "linkreach", restrained gold accent |
| Pages | Overview · Campaigns (CRUD) · Campaign detail (+add URLs) · Leads & Deals · Monitor |
| Delete campaign | Allowed, cascade-deletes its deals |
| Demo campaign | Shown (not hidden) |
| Leads | Read-only, searchable by handle, paginated |
| Overview metrics | Connection requests sent · In conversation · Connected |
| Chart | Connects per day, last 30 days |
| Campaign form | All fields, minimalist layout |
| Bot control | Start / Stop / Restart from dashboard (subprocess) |
| Monitor | Stage tag + current campaign + chatbot-style activity feed (system actions **and** message text) + "Next up" timeline + raw-log toggle |
| Auto-refresh | HTMX polling ~5s on status/feed/log fragments |

---

## 2. The bot's REAL stages (drives the status tag + pills)

Task queue task types: `connect`, `check_pending`, `follow_up`, `email`.
Task statuses: `pending`, `running`, `completed`, `failed`.

| Status tag | Detected from |
|---|---|
| 🔑 Logging in | log: `Loading saved session` / `re-authenticating` |
| 🔍 Searching | log: `Generated N search keywords via LLM` |
| 🧠 Qualifying | log: `Strategy:` / `READY_TO_CONNECT` / `Disqualified` |
| 🤝 Connecting | running `connect` task |
| 📨 Checking invites | running `check_pending` task |
| 💬 Following up | running `follow_up` task |
| ✉️ Emailing | running `email` task |
| ☕ On a break | log: `Taking a Nm break` |
| 😴 Sleeping | log: `Queue empty — sleeping 1h` |
| ⏳ Waiting | log: `Next task in X — sleeping` |
| 🚦 Limit reached | log: `daily limit reached — slot skipped` |

Deal (lead) states: `Qualified → Ready to Connect → Pending → Connected → Completed`
(email fork: `Ready to Email → Emailed`). Outcomes: converted, not_interested,
wrong_fit, no_budget, has_solution, bad_timing, unresponsive, unknown.

`ChatMessage(deal, content, is_outgoing, creation_date, linkedin_urn)` = real AI↔prospect threads.

---

## 3. Files to ADD (all under `linkreach/dashboard/`)

```
linkreach/dashboard/__init__.py
linkreach/dashboard/apps.py              # AppConfig name="linkreach.dashboard"
linkreach/dashboard/urls.py              # 5 pages + htmx fragments + bot-control endpoints
linkreach/dashboard/views.py             # all views, @login_required
linkreach/dashboard/forms.py             # CampaignForm (ModelForm)
linkreach/dashboard/services.py          # read helpers: stats, pipeline counts, stage detect, feed, next-up
linkreach/dashboard/bot_control.py       # subprocess start/stop/restart/status + PID file + log redirect
linkreach/dashboard/templates/dashboard/base.html
linkreach/dashboard/templates/dashboard/overview.html
linkreach/dashboard/templates/dashboard/campaigns.html
linkreach/dashboard/templates/dashboard/campaign_form.html
linkreach/dashboard/templates/dashboard/campaign_detail.html
linkreach/dashboard/templates/dashboard/leads.html
linkreach/dashboard/templates/dashboard/monitor.html
linkreach/dashboard/templates/dashboard/_status.html   # htmx fragment: status banner
linkreach/dashboard/templates/dashboard/_feed.html     # htmx fragment: activity pills
linkreach/dashboard/templates/dashboard/_log.html      # htmx fragment: raw log tail
```
(~17 source files.) `APP_DIRS=True` in settings, so app-level templates are auto-found.

**Runtime files (created by bot_control, not source):**
```
logs/daemon.log     # bot stdout/stderr
data/daemon.pid     # running bot PID
```

---

## 4. Files to EDIT (only 2, additive)

**`linkreach/settings.py`** (INSTALLED_APPS starts line 23):
```python
INSTALLED_APPS = [
    ...
    "linkreach.dashboard",   # <-- ADD
]
```

**`linkreach/urls.py`** (currently only `admin/`):
```python
from django.urls import path, include
urlpatterns = [
    path("admin/", admin.site.urls),
    path("dashboard/", include("linkreach.dashboard.urls")),   # <-- ADD
    # optional: path("", RedirectView.as_view(url="/dashboard/")),
]
```

---

## 5. Data flow

- **Overview / Leads / Campaign counts:** view → ORM read (`Campaign`, `Deal`, `Lead`,
  `ActionLog`) → template. No writes.
- **Add URLs:** `campaign_detail` POST → `parse_seed_urls(text)` →
  `create_seed_leads(campaign, ids)` [EXISTING] → creates `Lead` + `QUALIFIED` `Deal`
  + updates `seed_public_ids` → show "restart bot" banner.
- **Bot control:** Monitor button POST → `bot_control.start/stop/restart`:
  - start: spawn `.venv/Scripts/python manage.py rundaemon` with
    `env["PLAYWRIGHT_BROWSERS_PATH"]=ROOT_DIR/.browsers`, stdout/stderr → `logs/daemon.log`,
    write PID → `data/daemon.pid`.
  - stop: read PID → terminate.
  - status: PID alive? + last log line + Task queue.
- **Stage detection:** `services.current_stage()` → running `Task` → stage by task_type;
  else next pending `scheduled_at` → "Waiting"; none → "Sleeping"; refine with last
  `logs/daemon.log` line keyword. Current campaign = running `Task.payload["campaign_id"]`.
- **Activity feed:** `services.activity_feed()` merges recent `ActionLog`
  (connect/follow_up) + `ChatMessage` (content, is_outgoing) + completed `Task`s,
  sorted desc, rendered as chat pills (today-focused).
- **Live updates:** `monitor.html` fragments via `hx-get` + `hx-trigger="every 5s"`.

---

## 6. Theme tokens (light / editorial)

- Background `#FAFAF8`, cards `#FFFFFF`, text `#1A1A1A`, hairline borders `#ECECEC`
- Accent (restrained gold) `#B8A06A`
- Serif headings (Playfair Display or system serif), sans body (system/Inter)
- Generous whitespace, thin rules, no heavy shadows. Quiet and expensive.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Playwright in web process | Use subprocess only (Rule 7) |
| Subprocess can't find browser | bot_control injects `PLAYWRIGHT_BROWSERS_PATH` |
| `runserver` auto-reload kills subprocess on save | run `runserver --noreload` when controlling the bot; document it |
| Two bots at once (CMD + dashboard) | bot_control checks PID before start; warn user not to also run `rundaemon` in CMD |
| SQLite write concurrency | Reads fine; only brief writes (seed/campaign). Acceptable |

---

## 8. Build phases (do in this order; test bot still works after each)

1. **Scaffold** app + `base.html` + **Overview** + **Campaigns CRUD** + **Campaign detail
   with Add-URLs** (no bot control yet).
2. **Leads & Deals** page (search + pagination).
3. **Monitor** page — stage/status + activity feed + log tail (read-only; bot still
   started from CMD).
4. **Bot control** (subprocess start/stop/restart) + wire the restart button.

The riskiest piece (bot control) is last, so everything else is verified safe first.
