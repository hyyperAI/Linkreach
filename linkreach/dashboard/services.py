"""Read-only query helpers for the dashboard.

Everything here only *reads* from existing models — no writes, no migrations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from linkreach.chat.models import ChatMessage, ConversationEvent
from linkreach.core.models import Campaign, Task
from linkreach.crm.models import Deal, DealState
from linkreach.linkedin.models import ActionLog

# Where the bot's console output is mirrored (created in Phase 4 / when the bot is
# launched with output redirected here). Read-only from the dashboard's side.
LOG_PATH = Path(settings.BASE_DIR) / "logs" / "daemon.log"

# task_type -> (human label, icon) for status tags and the "next up" list.
STAGE_BY_TASK = {
    "connect": ("Connecting", "🤝"),
    "check_pending": ("Checking invites", "📨"),
    "follow_up": ("Following up", "💬"),
    "email": ("Emailing", "✉️"),
    "manual_message": ("Manual reply", "✍️"),
    "custom_first_message": ("Sending campaign opener", "send"),
}


def overview_stats(user=None) -> dict:
    """Top-line numbers for the Overview page."""
    action_logs = ActionLog.objects.all()
    campaigns = Campaign.objects.all()
    deals = Deal.objects.all()
    if user is not None:
        action_logs = action_logs.filter(campaign__users=user)
        campaigns = campaigns.filter(users=user)
        deals = deals.filter(campaign__users=user)

    connects_sent = action_logs.filter(
        action_type=ActionLog.ActionType.CONNECT,
    ).distinct().count()
    active_campaigns = campaigns.annotate(num_deals=Count("deals")).filter(
        status=Campaign.Status.ACTIVE,
        num_deals__gt=0,
    ).distinct().count()
    qualified = deals.filter(state=DealState.QUALIFIED).distinct().count()
    pending = deals.filter(state=DealState.PENDING).distinct().count()
    failed = deals.filter(state=DealState.FAILED).distinct().count()
    connected = deals.filter(
        state__in=[DealState.CONNECTED, DealState.COMPLETED]
    ).distinct().count()
    # "In conversation" = deals that have at least one chat message exchanged.
    in_conversation = (
        deals.filter(messages__isnull=False).distinct().count()
    )
    return {
        "connects_sent": connects_sent,
        "active_campaigns": active_campaigns,
        "qualified": qualified,
        "pending": pending,
        "failed": failed,
        "in_conversation": in_conversation,
        "connected": connected,
    }


def campaign_action_summary(campaign) -> dict:
    """Human-friendly next step for a campaign detail header."""
    counts = dict(
        Deal.objects.filter(campaign=campaign)
        .values_list("state")
        .annotate(n=Count("id"))
    )
    has_account = campaign.users.exists()
    qualified = counts.get(DealState.QUALIFIED, 0)
    ready = counts.get(DealState.READY_TO_CONNECT, 0)
    pending = counts.get(DealState.PENDING, 0)
    connected = counts.get(DealState.CONNECTED, 0)
    failed = counts.get(DealState.FAILED, 0)

    if campaign.status == Campaign.Status.DRAFT:
        return {
            "tone": "action",
            "label": "Start when ready",
            "text": "This campaign is in Draft. Review the setup, then start it from the campaign header.",
            "metric": "Draft",
        }
    if campaign.status == Campaign.Status.PAUSED:
        return {
            "tone": "muted",
            "label": "Campaign paused",
            "text": "Queued work is preserved and will continue after you start the campaign again.",
            "metric": "Paused",
        }

    if campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED:
        delivered = Deal.objects.filter(
            campaign=campaign,
            custom_message_status=Deal.CustomMessageStatus.SENT,
        ).count()
        failed_messages = Deal.objects.filter(
            campaign=campaign,
            custom_message_status=Deal.CustomMessageStatus.FAILED,
        ).count()
        if failed_messages:
            return {
                "tone": "danger",
                "label": "Messages need review",
                "text": "One or more personalized openers could not be delivered. Review the row errors before retrying.",
                "metric": f"{failed_messages} failed",
            }
        if qualified:
            return {
                "tone": "action",
                "label": "Review and start",
                "text": "Review each imported opener, then start the approved connection workflow.",
                "metric": f"{qualified} to review",
            }
        if delivered:
            return {
                "tone": "good",
                "label": "Personalized outreach active",
                "text": "Imported openers were sent after connection acceptance. AI follow-up can now continue.",
                "metric": f"{delivered} sent",
            }

    if not has_account:
        return {
            "tone": "danger",
            "label": "Account missing",
            "text": "Attach a LinkedIn account before this campaign can run.",
            "metric": "No runner",
        }
    if qualified:
        return {
            "tone": "action",
            "label": "Ready to queue",
            "text": "Qualified leads are waiting. Select the best ones and queue them for connection.",
            "metric": f"{qualified} qualified",
        }
    if ready:
        return {
            "tone": "good",
            "label": "Queued",
            "text": "Leads are ready for the bot to send connection requests.",
            "metric": f"{ready} ready",
        }
    if pending:
        return {
            "tone": "good",
            "label": "Invites pending",
            "text": "Connection requests are out. Watch for accepts and replies.",
            "metric": f"{pending} pending",
        }
    if connected:
        return {
            "tone": "good",
            "label": "Conversations next",
            "text": "Connected leads are available for follow-up and conversation review.",
            "metric": f"{connected} connected",
        }
    if failed and sum(counts.values()) == failed:
        return {
            "tone": "muted",
            "label": "No active leads",
            "text": "Add profiles or broaden the campaign target to start outreach.",
            "metric": "Empty campaign",
        }
    return {
        "tone": "muted",
        "label": "Review campaign",
        "text": "Check the pipeline and add profiles when you are ready to continue.",
        "metric": f"{sum(counts.values())} leads",
    }


def conversations(user=None) -> list:
    """Deals that have at least one chat message (matches the Overview
    'In conversation' stat), newest activity first. Each deal is annotated
    with ``last_msg``, ``last_incoming`` (bool — was the latest message *from*
    the lead, i.e. awaiting our reply), and ``msg_count``.
    """
    deals = Deal.objects.filter(messages__isnull=False)
    if user is not None:
        deals = deals.filter(campaign__users=user)
    deals = (
        deals
        .select_related("lead", "campaign")
        .annotate(msg_count=Count("messages", distinct=True))
        .distinct()
    )
    out = []
    for d in deals:
        last = d.messages.order_by("-creation_date").first()
        d.last_msg = last
        d.last_incoming = bool(last and not last.is_outgoing)
        d.display_name = deal_display_name(d)
        out.append(d)
    # Most recent message first.
    out.sort(key=lambda d: d.last_msg.creation_date if d.last_msg else d.update_date,
             reverse=True)
    return out


def latest_manual_task(deal) -> dict:
    task = (
        Task.objects.filter(
            task_type=Task.TaskType.MANUAL_MESSAGE,
            payload__deal_id=deal.pk,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if task is None:
        return {"state": "", "label": "", "error": "", "task": None}
    payload = task.payload or {}
    error = payload.get("manual_error") or ""
    if task.status == Task.Status.PENDING:
        state, label = "queued", "Queued"
    elif task.status == Task.Status.RUNNING:
        state, label = "sending", "Sending"
    elif task.status == Task.Status.COMPLETED:
        state, label = "sent", "Sent"
    elif task.status == Task.Status.FAILED:
        state, label = "failed", "Failed"
    else:
        state, label = task.status, task.get_status_display()
    return {"state": state, "label": label, "error": error, "task": task}


def _manual_task_timeline_items(deal) -> list[dict]:
    tasks = Task.objects.filter(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status__in=[Task.Status.PENDING, Task.Status.RUNNING],
        payload__deal_id=deal.pk,
    ).order_by("created_at", "id")
    items = []
    for task in tasks:
        payload = task.payload or {}
        body = payload.get("message") or ""
        if not body:
            continue
        if ChatMessage.objects.filter(deal=deal, is_outgoing=True, content=body).exists():
            continue
        status = "Sending" if task.status == Task.Status.RUNNING else "Queued"
        items.append({
            "kind": "pending_manual",
            "sort_at": task.started_at or task.created_at,
            "task": task,
            "content": body,
            "status_label": status,
        })
    return items


def conversation_timeline(deal) -> list[dict]:
    items = []
    for msg in deal.messages.select_related("owner", "initiated_by").order_by("creation_date", "pk"):
        items.append({
            "kind": "message",
            "sort_at": msg.creation_date,
            "message": msg,
        })
    for event in deal.conversation_events.select_related("created_by").order_by("created_at", "pk"):
        label = (
            "Manual mode started"
            if event.event_type == ConversationEvent.EventType.MANUAL_MODE_STARTED
            else "AI auto-reply resumed"
        )
        if event.created_by_id and event.event_type == ConversationEvent.EventType.MANUAL_MODE_STARTED:
            label = f"{label} by you"
        items.append({
            "kind": "event",
            "sort_at": event.created_at,
            "event": event,
            "label": label,
        })
    items.extend(_manual_task_timeline_items(deal))
    return sorted(items, key=lambda item: (item["sort_at"] or timezone.now(), 0 if item["kind"] == "event" else 1))


def has_duplicate_manual_task(deal, body: str) -> bool:
    return Task.objects.filter(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status__in=[Task.Status.PENDING, Task.Status.RUNNING],
        payload__deal_id=deal.pk,
        payload__message=body,
    ).exists()


def conversation_detail_context(deal) -> dict:
    import_fields = deal_import_fields(deal)
    custom_import_fields = (
        deal.profile_summary.get("custom_import_fields", {})
        if isinstance(deal.profile_summary, dict)
        else {}
    )
    return {
        "deal": deal,
        "lead": deal.lead,
        "name": deal_display_name(deal),
        "email_status": email_status(deal.lead),
        "email": lead_email(deal.lead),
        "keywords": deal_keywords(deal, limit=5),
        "state_tone": state_tone(deal.state),
        "import_fields": import_fields,
        "custom_import_fields": custom_import_fields,
        "profile_facts": summary_facts(deal.profile_summary),
        "chat_facts": summary_facts(deal.chat_summary),
        "timeline_items": conversation_timeline(deal),
        "manual_task": latest_manual_task(deal),
    }


def connects_last_30_days(user=None) -> tuple[list[str], list[int]]:
    """Daily connection-request counts for the last 30 days (for the chart)."""
    today = timezone.localdate()
    start = today - timedelta(days=29)
    buckets = {start + timedelta(days=i): 0 for i in range(30)}

    rows = ActionLog.objects.filter(
        action_type=ActionLog.ActionType.CONNECT,
        created_at__date__gte=start,
    )
    if user is not None:
        rows = rows.filter(campaign__users=user)
    rows = rows.distinct().values_list("created_at", flat=True)
    for dt in rows:
        d = timezone.localtime(dt).date()
        if d in buckets:
            buckets[d] += 1

    labels = [d.strftime("%b %d") for d in buckets]
    data = list(buckets.values())
    return labels, data


def pipeline_counts(campaign) -> list[tuple[str, int]]:
    """Count of deals per funnel state for one campaign, in funnel order."""
    rows = (
        Deal.objects.filter(campaign=campaign)
        .values("state")
        .annotate(n=Count("id"))
    )
    by_state = {r["state"]: r["n"] for r in rows}
    return [(label, by_state.get(value, 0)) for value, label in DealState.choices]


def campaign_status_badge(campaign) -> dict:
    labels = {
        Campaign.Status.DRAFT: "Draft",
        Campaign.Status.ACTIVE: "Active",
        Campaign.Status.PAUSED: "Paused",
    }
    tones = {
        Campaign.Status.DRAFT: "border-hair bg-paper text-muted",
        Campaign.Status.ACTIVE: "border-emerald-200 bg-emerald-50 text-emerald-700",
        Campaign.Status.PAUSED: "border-amber-200 bg-amber-50 text-amber-700",
    }
    return {
        "label": labels.get(campaign.status, campaign.status.title()),
        "class": tones.get(campaign.status, "border-hair bg-paper text-muted"),
    }


def deal_state_badge(deal) -> dict:
    """Presentation-only state label with CSV-specific profile failure wording."""
    if (
        deal.campaign.outreach_mode == Campaign.OutreachMode.CSV_PERSONALIZED
        and deal.state == DealState.FAILED
        and _csv_profile_unavailable_reason(deal.reason)
    ):
        return {
            "label": "Profile unavailable",
            "class": "border-red-200 bg-red-50 text-red-700",
            "title": deal.reason or "LinkedIn profile could not be reached.",
        }
    return {
        "label": deal.get_state_display(),
        "class": "border-hair bg-paper text-ink",
        "title": deal.reason if deal.state == DealState.FAILED and deal.reason else "",
    }


def _csv_profile_unavailable_reason(reason: str) -> bool:
    if not reason:
        return True
    text = reason.lower()
    return any(
        marker in text
        for marker in (
            "profile inaccessible",
            "profile unavailable",
            "profile not found",
            "unreachable",
            "could not open profile",
            "no connect button",
            "linkedin access blocked",
            "skipprofile",
        )
    )


# ---------------------------------------------------------------------------
# Monitor (read-only): status, next-up, activity feed, raw log
# ---------------------------------------------------------------------------

def log_exists() -> bool:
    return LOG_PATH.exists()


def read_log_tail(n: int = 300) -> list[str]:
    """Last ``n`` lines of the bot log file (empty if it doesn't exist yet)."""
    if not LOG_PATH.exists():
        return []
    try:
        with LOG_PATH.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()[-n:]
    except OSError:
        return []


def _campaign_name(campaign_id) -> str:
    if not campaign_id:
        return ""
    return (
        Campaign.objects.filter(pk=campaign_id)
        .values_list("name", flat=True)
        .first()
        or ""
    )


def _last_active() -> datetime | None:
    """Best-effort 'last seen' timestamp inferred from DB + log file."""
    times: list[datetime] = []
    a = ActionLog.objects.order_by("-created_at").values_list("created_at", flat=True).first()
    if a:
        times.append(a)
    t = (
        Task.objects.exclude(completed_at=None)
        .order_by("-completed_at")
        .values_list("completed_at", flat=True)
        .first()
    )
    if t:
        times.append(t)
    if LOG_PATH.exists():
        times.append(datetime.fromtimestamp(LOG_PATH.stat().st_mtime, tz=dt_timezone.utc))
    return max(times) if times else None


def _stage_from_log():
    """Refine the status tag from the most recent log lines when idle."""
    for line in reversed(read_log_tail(8)):
        l = line.lower()
        if "taking a" in l and "break" in l:
            return ("On a break", "☕")
        if "search keywords" in l or "searching" in l:
            return ("Searching", "🔍")
        if "loading saved session" in l or "re-authenticat" in l or "logging in" in l:
            return ("Logging in", "🔑")
        if "strategy:" in l or "ready_to_connect" in l or "qualif" in l:
            return ("Qualifying", "🧠")
        if "daily limit reached" in l:
            return ("Limit reached", "🚦")
        if "sleeping" in l:
            return ("Sleeping", "😴")
    return None


def _issue_from_log_text(log_text: str) -> str:
    log_text = log_text.lower()
    if "rate_limit_exceeded" in log_text or "status_code: 429" in log_text:
        if "groq" in log_text:
            return "The last run stopped because Groq hit its daily token rate limit. Wait for the provider reset window or switch the configured model/API key."
        return "The last run stopped because the LLM provider hit a rate limit. Wait for the reset window or switch the configured model/API key."
    if "llm api error" in log_text:
        return "The last run stopped because the LLM provider returned an API error. Check the configured model and API key."
    if "traceback" in log_text or "exception" in log_text or "error" in log_text:
        return "The last run stopped with an error. Review the raw log below for details."
    return ""


def bot_status() -> dict:
    """Current bot status, grounded in process liveness before log text."""
    now = timezone.now()
    from linkreach.core.bot_process import get_status as process_status

    proc = process_status()
    log_tail = read_log_tail(80)
    log_text = "\n".join(log_tail[-40:]).lower()
    has_error = (
        "traceback" in log_text
        or "noconsole" in log_text
        or "error" in log_text
        or "exception" in log_text
    )
    log_issue = _issue_from_log_text(log_text)
    running = (
        Task.objects.filter(status=Task.Status.RUNNING).order_by("-started_at").first()
    )
    detail = proc.get("detail") or ""
    campaign = ""
    issue = ""
    tone = proc.get("tone", "neutral")
    label = proc.get("label", "Not running")
    icon = "power-off"
    last_active = proc.get("last_heartbeat_at") or _last_active()

    if proc["state"] in {"not_running", "starting", "stopping", "hung", "crashed"}:
        if proc["state"] == "starting":
            icon = "loader-2"
        elif proc["state"] == "stopping":
            icon = "pause-circle"
        elif proc["state"] in {"hung", "crashed"}:
            icon = "triangle-alert"
            issue = proc["detail"]
        else:
            icon = "power-off"
        if proc["state"] == "not_running" and has_error:
            detail = log_issue or "Stopped. The latest log still contains an older error."
    elif running:
        label, icon = STAGE_BY_TASK.get(running.task_type, ("Working", "⚙️"))
        campaign = _campaign_name((running.payload or {}).get("campaign_id"))
        if has_error:
            issue = log_issue or "The bot is running, but the latest log contains an error. Review the raw log."
    else:
        nxt = Task.objects.pending().first()
        if nxt and nxt.scheduled_at and nxt.scheduled_at > now:
            label, icon = ("Waiting", "⏳")
            stage = STAGE_BY_TASK.get(nxt.task_type, ("task", ""))[0].lower()
            detail = f"next {stage} · {timezone.localtime(nxt.scheduled_at).strftime('%b %d, %H:%M')}"
            campaign = _campaign_name((nxt.payload or {}).get("campaign_id"))
        else:
            label, icon = ("Sleeping", "😴")
        refined = _stage_from_log()
        if refined:
            label, icon = refined

    if last_active and now - last_active > timedelta(hours=12) and tone not in {"danger", "warning"}:
        tone = "warning"
        if not detail:
            detail = "no recent activity"

    return {
        "label": label,
        "icon": icon,
        "detail": detail,
        "campaign": campaign,
        "last_active": last_active,
        "issue": issue,
        "tone": tone,
        "log_exists": LOG_PATH.exists(),
        "state": proc["state"],
        "process": proc,
    }


def next_up(limit: int = 6) -> list[dict]:
    rows = Task.objects.pending().filter(scheduled_at__gte=timezone.now())[:limit]
    out = []
    for t in rows:
        label, icon = STAGE_BY_TASK.get(t.task_type, (t.task_type, "•"))
        out.append({
            "label": label,
            "icon": icon,
            "when": t.scheduled_at,
            "campaign": _campaign_name((t.payload or {}).get("campaign_id")),
        })
    return out


def activity_feed(limit: int = 60, user=None) -> list[dict]:
    """Merged, newest-first feed of messages + bot actions for the chat view."""
    items: list[dict] = []

    msgs = ChatMessage.objects.select_related("deal__lead")
    if user is not None:
        msgs = msgs.filter(deal__campaign__users=user)
    msgs = msgs.distinct().order_by("-creation_date")[:limit]
    for m in msgs:
        who = m.deal.lead.public_identifier if (m.deal_id and m.deal.lead_id) else "lead"
        items.append({
            "kind": "message",
            "when": m.creation_date,
            "outgoing": m.is_outgoing,
            "who": who,
            "text": m.content,
        })

    action_labels = {"connect": "Sent connection request", "follow_up": "Sent a follow-up"}
    action_icons = {"connect": "🤝", "follow_up": "💬"}
    logs = ActionLog.objects.select_related("campaign")
    if user is not None:
        logs = logs.filter(campaign__users=user)
    logs = logs.distinct().order_by("-created_at")[:limit]
    for a in logs:
        items.append({
            "kind": "action",
            "when": a.created_at,
            "icon": action_icons.get(a.action_type, "•"),
            "text": action_labels.get(a.action_type, a.action_type),
            "who": a.campaign.name if a.campaign_id else "",
        })

    items.sort(key=lambda x: x["when"], reverse=True)
    return items[:limit]


# ---------------------------------------------------------------------------
# Lead detail helpers (profile/chat summaries, name, email)
# ---------------------------------------------------------------------------

def summary_facts(blob) -> list[str]:
    """Normalize a profile_summary / chat_summary blob into a list of fact strings.

    Stored shape is ``{"facts": [...]}`` but we tolerate a bare list or None.
    """
    if not blob:
        return []
    facts = blob.get("facts") if isinstance(blob, dict) else blob
    if not isinstance(facts, list):
        return []
    return [str(f).strip() for f in facts if str(f).strip()]


def summary_preview(blob, n_facts: int = 2, max_chars: int = 90) -> str:
    facts = summary_facts(blob)
    if not facts:
        return ""
    text = " · ".join(facts[:n_facts])
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def deal_summary_preview(deal, max_chars: int = 110) -> str:
    """Short 'who is this' blurb for table rows. Prefers the conversation-time
    profile_summary facts; falls back to the AI's qualification ``reason`` (which
    most leads have well before any summary exists)."""
    preview = summary_preview(deal.profile_summary)
    if preview:
        return preview
    reason = (deal.reason or "").replace("\n", " ").strip()
    if not reason:
        return ""
    return reason if len(reason) <= max_chars else reason[: max_chars - 1].rstrip() + "…"


KEYWORD_STOPWORDS = {
    "about", "across", "after", "against", "also", "and", "are", "based",
    "because", "been", "being", "build", "but", "can", "chief", "company",
    "current", "customer", "does", "established", "executive", "focused",
    "from", "has", "have", "help", "into", "large", "lead", "not", "our",
    "profile", "rather", "senior", "should", "startup", "startups", "than",
    "that", "the", "their", "this", "with", "would",
}


def deal_keywords(deal, limit: int = 3) -> dict:
    """Compact scan keywords for a lead row, derived from existing summaries."""
    facts = summary_facts(deal.profile_summary)
    text = " ".join(facts[:3]) or (deal.reason or "")
    candidates: list[str] = []

    preferred = [
        ("AI", (" ai ", "artificial intelligence")),
        ("SaaS", ("saas", "software")),
        ("Founder", ("founder", "co-founder", "ceo")),
        ("B2B", ("b2b", "enterprise")),
        ("Growth", ("growth", "marketing", "revenue")),
        ("Product", ("product", "platform")),
        ("Sales", ("sales", "commercial", "revenue")),
        ("Engineering", ("engineering", "technical", "cto")),
        ("Fintech", ("fintech", "finance")),
        ("Healthcare", ("healthcare", "health")),
    ]
    haystack = f" {text.lower()} "
    for label, needles in preferred:
        if any(needle in haystack for needle in needles):
            candidates.append(label)

    if len(candidates) < limit:
        import re

        words = re.findall(r"\b[A-Za-z][A-Za-z+-]{3,}\b", text)
        for word in words:
            clean = word.strip("-+").lower()
            if clean in KEYWORD_STOPWORDS:
                continue
            label = clean.upper() if clean in {"ai", "b2b"} else clean.title()
            if label not in candidates:
                candidates.append(label)
            if len(candidates) >= limit + 3:
                break

    return {
        "visible": candidates[:limit],
        "extra": max(len(candidates) - limit, 0),
        "all": candidates,
    }


def state_tone(state: str) -> str:
    if state in {DealState.QUALIFIED, DealState.READY_TO_EMAIL, DealState.READY_TO_CONNECT}:
        return "action"
    if state in {DealState.PENDING, DealState.EMAILED}:
        return "waiting"
    if state in {DealState.CONNECTED, DealState.COMPLETED}:
        return "good"
    if state == DealState.FAILED:
        return "danger"
    return "muted"


def email_status(lead) -> dict:
    email = lead_email(lead)
    return {
        "email": email,
        "available": bool(email),
        "label": "Available" if email else "No email",
    }


def deal_import_fields(deal) -> dict:
    blob = deal.profile_summary if isinstance(deal.profile_summary, dict) else {}
    fields = blob.get("import_fields") or {}
    return fields if isinstance(fields, dict) else {}


def deal_display_name(deal) -> str:
    fields = deal_import_fields(deal)
    first = (fields.get("first_name") or fields.get("First Name") or "").strip()
    last = (fields.get("last_name") or fields.get("Last Name") or "").strip()
    full_name = " ".join(part for part in [first, last] if part).strip()
    if full_name:
        return full_name
    return pretty_name(deal.lead.public_identifier) or deal.lead.public_identifier


def pretty_name(handle: str) -> str:
    """Cosmetic name from a LinkedIn handle, e.g. 'david-gordon' -> 'David Gordon'."""
    if not handle:
        return ""
    base = handle.replace("-", " ").replace("_", " ").replace(".", " ")
    return base.title().strip()


def lead_email(lead) -> str:
    """Best known email for a lead (enrichment result or scraped contact info)."""
    if lead.api_email:
        return lead.api_email
    ci = lead.contact_info
    if isinstance(ci, dict):
        if ci.get("email"):
            return ci["email"]
        emails = ci.get("emails")
        if isinstance(emails, list) and emails:
            return emails[0]
    return ""
