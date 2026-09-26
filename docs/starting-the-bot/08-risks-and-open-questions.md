# Risks And Open Questions

Things that need a decision, or at least conscious acknowledgment, before or
during implementation.

## Risk: two daemons on one LinkedIn account

The single most important failure mode this whole plan defends against. Two
`rundaemon` processes sharing one `LinkedInProfile.cookie_data` would race to
write cookies, potentially both try to act on LinkedIn "simultaneously" from
the account's perspective — which looks exactly like the kind of anomalous,
multi-session activity LinkedIn's own abuse detection is built to catch, and
could get the account checkpointed or restricted independent of anything
else in this project's design. The `select_for_update()` guard
(`03-architecture-and-process-model.md`) and UC6's explicit test
(`07-implementation-phases-and-testing.md`) exist specifically for this. If
building this incrementally, **do not ship the Start button (Phase 4) before
the race guard (Phase 3) is verified working** — the button is the risky
part, the backend guard is the safety net, ship the net first.

## Risk: hard-killing mid-LinkedIn-action

`force_kill()` is a blunt instrument. If it fires while Playwright is
mid-way through submitting a connection request or a login form, the
resulting state (partial DOM interaction, a half-submitted form) is unknown
and not something this project's `linkedin_cli` page-state machine
(`page_state.py`, `@transition` contracts) was designed to recover from —
it's designed around clean action boundaries, not "killed mid-click."
**Decision needed:** should `force_kill()` require a second, more explicit
confirmation than the cooperative Stop (e.g. typing "FORCE STOP" instead of
a plain `confirm()` dialog)? Recommend yes, but this is a product call, not
a purely technical one — flag it for review before Phase 4.

## Risk: `psutil` as a new dependency

**Confirmed: not currently installed** (not in `requirements/base.txt`, not
present in the project's `.venv` even transitively). `is_pid_alive()` is
meaningfully simpler and more robust with `psutil` — cross-platform, and it
can compare process *creation time* to rule out PID reuse, not just
existence. Without it, the `tasklist`/`os.kill(pid, 0)` fallback in
`04-backend-implementation-plan.md` works but is materially weaker against
PID reuse (existence-only) — **this weakens the Crashed vs. Running
distinction specifically on long-uptime Windows machines where PID reuse is
more likely.** Recommend adding `psutil` as a new direct dependency in
`requirements/base.txt` rather than building a hand-rolled fallback; it's
small, mature, and the de facto standard for exactly this problem. This is
a one-line addition, not a heavy dependency to justify.

## Risk: log file growth

`logs/daemon.log` is currently read in full-tail slices
(`read_log_tail(300)`) with no rotation policy visible in the audited code —
worth confirming `configure_logging()` (`core/logging.py`) doesn't already
handle this before assuming it needs fixing here; if it doesn't, that's a
pre-existing gap unrelated to this plan, not something to silently take on
as scope creep. Note it, don't fix it here, unless it's trivial.

## Open question: how does the app detect "I'm running in the Docker/managed context"?

Needs a decision before Phase 5.

**Confirmed:** `local.yml` already sets `ENABLE_VNC=true` for the Docker
service (referenced in `compose/linkedin/Dockerfile`) — but that flag means
"a VNC display is available," not "this is a managed daemon" per se; reusing
it would be piggybacking on an unrelated signal. **Confirmed:** there is no
`dashboard/context_processors.py` in this codebase — every dashboard view
builds its own context dict by hand (`active`, `breadcrumbs`, `page_title`,
etc. are all set per-view, not injected globally). So the existing
convention is explicit per-view context, not a context processor.

Recommend: add a new explicit `linkreach_MANAGED=true` env var, set only
in `local.yml`/the Dockerfile, read once in `settings.py` into a
`MANAGED_DEPLOYMENT` setting, and passed into the Monitor view's context dict
by hand — consistent with how every other dashboard view already builds its
context, not a new mechanism. Inferring "am I in Docker" from filesystem
heuristics (`/.dockerenv` existence, etc.) is fragile and this project
already fully controls its own Docker build files, so an explicit flag costs
nothing and is unambiguous.

## Open question: should Start/Stop be restricted further than `@login_required`?

Today, every dashboard view is `@login_required` with no further permission
tiers — any logged-in user can already edit any campaign, disconnect the
LinkedIn account, etc. (see `linkedin_account_action`, `campaign_delete`,
etc. — no `is_staff`/`is_superuser` checks anywhere in the audited views).
Starting/stopping a background process that opens a real browser and can
send real LinkedIn actions is a meaningfully bigger blast radius than
editing a campaign's text fields. **Decide:** should this feature introduce
the *first* privilege tier in this dashboard (e.g. `@staff_member_required`
on `bot_action`), or should it stay consistent with the existing
any-logged-in-user model for v1, matching how every other action in this
dashboard already works? Recommend staying consistent with existing
convention for v1 (this codebase's dashboard is explicitly documented as
single-operator, login-required-only) — but flag it, since it's the kind of
decision that's much cheaper to make now than to retrofit later.

## Follow-up (explicitly out of scope, noted for a future plan)

- **Auto-start on machine boot / Windows login.** Once the process-management
  primitives in this plan exist (`bot_process.start()`, clean shutdown via
  `stop_requested`), a Windows Scheduled Task or NSSM-based Windows Service
  wrapper becomes straightforward to layer on top — it would just call the
  same `start()` path (or invoke `Start-Bot.bat` directly, bypassing the
  dashboard-launch path entirely, landing in UC7's "started outside the
  dashboard" case). Worth a dedicated short plan once this feature has
  shipped and been used for a while, not before — premature to design
  auto-start before manual start/stop has proven itself stable.
- **Multiple bot instances / multi-account support.** Explicitly a v2
  concern per the rest of this project's existing one-account-per-user
  scoping (see the LinkedIn Account page's own v1 constraints). `BotProcess`
  as a singleton (`pk=1`) would need to become one row per account if that
  ever happens — noted here so the singleton design isn't mistaken for an
  oversight later, it's a deliberate v1 scoping choice matching the rest of
  the app.
