# linkreach/core/scheduler.py
"""Per-type 24h planner with Poisson-spaced lazy task slots.

The daemon's task queue is *lazy*: each row carries only ``task_type``,
``campaign_id``, and ``scheduled_at``. The handler resolves a concrete
target (lead/deal) at execution time via a single eligibility query.

This module is the only place that creates ``Task`` rows. The pipeline
moves forward in three layers:

1. **Per-type planner** — ``plan_connect_window``,
   ``plan_follow_up_window``, ``plan_check_pending_window``. Each one,
   when no PENDING task of its type exists for a campaign, computes the
   right slot count ``n`` for the next 24h, inserts one row that fires
   immediately, and Poisson-spaces the remaining ``n - 1`` rows across
   the working portion of the window. The leading immediate slot kills
   the cold-start ramp (without it the first action would sit ``T/n``
   away on average — ~72 min for a 20/day campaign).

2. **State-transition hook** — ``on_deal_state_entered(deal)`` updates
   ``deal.next_check_pending_at`` for PENDING transitions. A CONNECTED
   transition in a reviewed CSV-personalized campaign queues its exact
   imported opener; other CONNECTED deals remain planner-owned.

3. **Reconcile** — ``reconcile(session)``. Recovers stale RUNNING tasks
   and calls each planner per campaign. The daemon invokes it on startup
   and whenever the queue has no ready task.
"""
from __future__ import annotations

import datetime
import logging
import random
from datetime import datetime as Datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from linkreach.core.conf import (
    ACTIVE_END_HOUR,
    ACTIVE_START_HOUR,
    CAMPAIGN_CONFIG,
    CHECK_PENDING_DAILY_CAP,
    ENABLE_ACTIVE_HOURS,
)
from linkreach.crm.models import DealState
from linkreach.core.models import Task

logger = logging.getLogger(__name__)


AUTOMATION_TASK_TYPES = (
    Task.TaskType.CONNECT,
    Task.TaskType.CHECK_PENDING,
    Task.TaskType.FOLLOW_UP,
    Task.TaskType.EMAIL,
    Task.TaskType.CUSTOM_FIRST_MESSAGE,
)


def _campaign_active(campaign) -> bool:
    from linkreach.core.models import Campaign

    return campaign.status == Campaign.Status.ACTIVE


# ── Working-hours arithmetic ──────────────────────────────────────────


def _working_intervals(start, end, tz_name) -> list[tuple]:
    """Return ``[(s, e), ...]`` UTC datetimes for the working portions of
    ``[start, end]``. The whole window ``[(start, end)]`` is returned —
    i.e. no gating — when ``ENABLE_ACTIVE_HOURS`` is False or ``tz_name`` is
    None (timezone not resolved, e.g. unknown profile country)."""
    if not ENABLE_ACTIVE_HOURS or tz_name is None:
        return [(start, end)]

    tz = ZoneInfo(tz_name)
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)

    intervals: list[tuple] = []
    day = local_start.date()
    last_day = local_end.date()
    while day <= last_day:
        day_active_start = Datetime(
            day.year, day.month, day.day, ACTIVE_START_HOUR, tzinfo=tz,
        )
        day_active_end = Datetime(
            day.year, day.month, day.day, ACTIVE_END_HOUR, tzinfo=tz,
        )
        s = max(day_active_start, local_start)
        e = min(day_active_end, local_end)
        if e > s:
            intervals.append((s, e))
        day = day + timedelta(days=1)
    return intervals


def working_seconds_in_window(start, end, tz_name) -> float:
    """Sum of seconds inside ``[ACTIVE_START_HOUR, ACTIVE_END_HOUR]`` between
    ``start`` and ``end``. Returns ``(end - start).total_seconds()`` when
    active hours are disabled or ``tz_name`` is None (no gating)."""
    if not ENABLE_ACTIVE_HOURS or tz_name is None:
        return max(0.0, (end - start).total_seconds())
    return sum((e - s).total_seconds() for s, e in _working_intervals(start, end, tz_name))


def poisson_slot_times(now, n: int, tz_name, horizon_hours: float = 24) -> list:
    """Return ``n`` strictly-increasing timestamps inside the working
    portion of ``[now, now + horizon_hours]``.

    Implementation: sample ``n`` uniform positions in ``[0, T)`` (working
    seconds) and sort. This is the order-statistic representation of a
    conditional Poisson process given ``n`` arrivals in the window —
    same distribution as exponential inter-arrival sampling, but
    guarantees exactly ``n`` slots without overshoot. Mean spacing in
    working time is ``T / (n + 1)``.
    """
    if n <= 0:
        return []

    end = now + timedelta(hours=horizon_hours)
    intervals = _working_intervals(now, end, tz_name)
    total = sum((e - s).total_seconds() for s, e in intervals)
    if total <= 0:
        return []

    positions = sorted(random.uniform(0, total) for _ in range(n))

    times: list = []
    cursor_interval = 0
    cursor_offset = 0.0  # working-seconds consumed before the current interval
    for pos in positions:
        while cursor_interval < len(intervals):
            s, e = intervals[cursor_interval]
            dur = (e - s).total_seconds()
            if pos < cursor_offset + dur:
                times.append(s + timedelta(seconds=pos - cursor_offset))
                break
            cursor_offset += dur
            cursor_interval += 1
    return times


# ── Per-type planners ─────────────────────────────────────────────────


def _has_pending(task_type: "Task.TaskType", campaign_id: int) -> bool:
    return Task.objects.filter(
        task_type=task_type,
        status=Task.Status.PENDING,
        payload__campaign_id=campaign_id,
    ).exists()


def _create_lazy_slots(task_type: "Task.TaskType", campaign_id: int, times: list) -> int:
    if not times:
        return 0
    Task.objects.bulk_create([
        Task(
            task_type=task_type,
            scheduled_at=t,
            payload={"campaign_id": campaign_id},
        )
        for t in times
    ])
    return len(times)


def _plan_slots(task_type: "Task.TaskType", campaign_id: int, n: int, tz_name) -> int:
    """Schedule *n* lazy slots: one fires immediately, the remaining
    ``n - 1`` are Poisson-spaced across the next 24h working window
    (``tz_name`` defines that window's local hours; None → full 24h).

    The leading immediate slot is intentional — without it the first
    action of a freshly-planned window would sit ``T/n`` away on average
    (the mean of a single ``Exp(n/T)`` draw). That cold-start ramp made
    `make run` feel dead for ~an hour on a 20/day campaign.
    """
    if n <= 0:
        return 0
    now = timezone.now()
    times = [now] + poisson_slot_times(now, n - 1, tz_name)
    return _create_lazy_slots(task_type, campaign_id, times)


def plan_connect_window(session, campaign) -> int:
    """Plan the next 24h of connect slots for *campaign*. No-op when a
    PENDING connect task already exists for the campaign.

    Only the daily limit is consulted — LinkedIn's own weekly ceiling
    surfaces at the handler boundary via ``ReachedConnectionLimit``.
    """
    if not _campaign_active(campaign) or _has_pending(Task.TaskType.CONNECT, campaign.pk):
        return 0

    profile = session.linkedin_profile
    n = max(0, profile.connect_daily_limit - profile._daily_count("connect"))

    if campaign.is_freemium:
        n = int(n * campaign.action_fraction)

    created = _plan_slots(Task.TaskType.CONNECT, campaign.pk, n, session.active_timezone)
    if created:
        logger.info(
            "[%s] planned %d connect slots over next 24h — 1 fires now, "
            "%d Poisson-spaced (daily=%d)",
            campaign, created, max(0, created - 1), profile.connect_daily_limit,
        )
    return created


def plan_follow_up_window(session, campaign) -> int:
    """Plan the next 24h of follow-up slots for *campaign*. No-op when a
    PENDING follow-up task already exists for the campaign."""
    if not _campaign_active(campaign) or _has_pending(Task.TaskType.FOLLOW_UP, campaign.pk):
        return 0

    profile = session.linkedin_profile
    daily_remaining = max(0, profile.follow_up_daily_limit - profile._daily_count("follow_up"))

    created = _plan_slots(Task.TaskType.FOLLOW_UP, campaign.pk, daily_remaining, session.active_timezone)
    if created:
        logger.info(
            "[%s] planned %d follow_up slots over next 24h — 1 fires now, "
            "%d Poisson-spaced (daily=%d)",
            campaign, created, max(0, created - 1), daily_remaining,
        )
    return created


def plan_check_pending_window(session, campaign) -> int:
    """Plan the next 24h of check_pending slots for *campaign*. Slot count
    matches the PENDING deals whose backoff has already expired (due now),
    capped by ``CHECK_PENDING_DAILY_CAP``.

    The "due now" bound must match the handler's own due filter
    (``_next_due_pending_deal``): counting deals due later within the
    horizon would plan an immediate slot the handler then finds nothing
    to do for, leaving the queue empty and re-triggering reconcile in a
    tight no-op spin."""
    from linkreach.crm.models import Deal

    if not _campaign_active(campaign) or _has_pending(Task.TaskType.CHECK_PENDING, campaign.pk):
        return 0

    now = timezone.now()
    n_due = Deal.objects.filter(
        campaign_id=campaign.pk,
        state=DealState.PENDING,
        next_check_pending_at__lte=now,
    ).count()
    n = min(n_due, CHECK_PENDING_DAILY_CAP)

    created = _plan_slots(Task.TaskType.CHECK_PENDING, campaign.pk, n, session.active_timezone)
    if created:
        logger.info(
            "[%s] planned %d check_pending slots over next 24h — 1 fires now, "
            "%d Poisson-spaced (due=%d, cap=%d)",
            campaign, created, max(0, created - 1), n_due, CHECK_PENDING_DAILY_CAP,
        )
    return created


# ── Eager drain (no window) ───────────────────────────────────────────


def flush_email_queue(session, campaign) -> int:
    """Drain the READY_TO_EMAIL pool for *campaign* into immediate task slots.

    The eager counterpart to the ``plan_*_window`` planners: those *ration* a
    rate-limited action over a 24h window to fake human rhythm; email has no
    anti-bot rhythm to fake, so every queued deal is emitted as an immediate
    slot (scheduled ``now``, no Poisson spacing, no ranking) and drains
    back-to-back. The only throttle is the pool-wide per-box daily cap
    (``Mailbox.objects.remaining_today()``), re-checked at send time.

    No-op when a PENDING email task already exists, no box has headroom, or the
    pool is empty. Count is scoped to ``campaign.pk`` directly because
    ``reconcile`` does not set ``session.campaign`` before invoking it.
    """
    from linkreach.crm.models import Deal
    from linkreach.emails.models import Mailbox

    if not _campaign_active(campaign) or _has_pending(Task.TaskType.EMAIL, campaign.pk):
        return 0

    remaining = Mailbox.objects.remaining_today()
    if remaining <= 0:
        return 0

    queued = Deal.objects.filter(
        campaign_id=campaign.pk,
        state=DealState.READY_TO_EMAIL,
        lead__disqualified=False,
    ).count()
    n = min(queued, remaining)
    if n <= 0:
        return 0

    now = timezone.now()
    created = _create_lazy_slots(Task.TaskType.EMAIL, campaign.pk, [now] * n)
    logger.info(
        "[%s] flushed %d email slots to send now (queued=%d, cap_remaining=%d)",
        campaign, created, queued, remaining,
    )
    return created


# ── Delay helpers ─────────────────────────────────────────────────────


def seconds_until_tomorrow() -> float:
    """Seconds until 00:00 local time — used for daily rate-limit waits."""
    now = timezone.now()
    tomorrow = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return (tomorrow - now).total_seconds()


# ── State-transition hook ─────────────────────────────────────────────


def on_deal_state_entered(deal) -> None:
    """Stamp pending backoff or queue an approved personalized opener."""
    state = DealState(deal.state)
    if state == DealState.CONNECTED:
        enqueue_custom_first_message(deal)
        return
    if state != DealState.PENDING:
        return

    backoff = deal.backoff_hours or CAMPAIGN_CONFIG["check_pending_recheck_after_hours"]
    deal.next_check_pending_at = timezone.now() + timedelta(hours=backoff)
    deal.save(update_fields=["next_check_pending_at"])


def enqueue_custom_first_message(deal) -> bool:
    """Queue the exact imported opener once a CSV campaign lead is connected."""
    from linkreach.core.models import Campaign, Task
    from linkreach.crm.models import Deal

    if (
        deal.campaign.outreach_mode != Campaign.OutreachMode.CSV_PERSONALIZED
        or deal.campaign.status != Campaign.Status.ACTIVE
        or deal.state != DealState.CONNECTED
        or not deal.outreach_approved_at
        or not deal.custom_first_message.strip()
        or deal.custom_message_status == Deal.CustomMessageStatus.SENT
    ):
        return False
    exists = Task.objects.filter(
        task_type=Task.TaskType.CUSTOM_FIRST_MESSAGE,
        status__in=[Task.Status.PENDING, Task.Status.RUNNING],
        payload__deal_id=deal.pk,
    ).exists()
    if exists:
        return False
    Deal.objects.filter(pk=deal.pk).update(
        custom_message_status=Deal.CustomMessageStatus.PENDING,
        custom_message_error="",
    )
    Task.objects.create(
        task_type=Task.TaskType.CUSTOM_FIRST_MESSAGE,
        scheduled_at=timezone.now(),
        payload={"campaign_id": deal.campaign_id, "deal_id": deal.pk},
    )
    return True


def flush_custom_first_messages(campaign) -> int:
    from linkreach.crm.models import Deal

    if not _campaign_active(campaign):
        return 0

    count = 0
    deals = Deal.objects.filter(
        campaign=campaign,
        state=DealState.CONNECTED,
        outreach_approved_at__isnull=False,
        custom_message_status__in=[
            Deal.CustomMessageStatus.PENDING,
            Deal.CustomMessageStatus.SENDING,
        ],
    ).exclude(custom_first_message="")
    for deal in deals.select_related("campaign"):
        count += int(enqueue_custom_first_message(deal))
    return count


# ── Reconciliation ────────────────────────────────────────────────────


def cleanup_inactive_pending_tasks() -> int:
    """Delete lazy pending automation slots for inactive or deleted campaigns."""
    from linkreach.core.models import Campaign
    from linkreach.core.task_payloads import InvalidTaskPayload, required_int

    active_ids = set(
        Campaign.objects.filter(status=Campaign.Status.ACTIVE)
        .values_list("pk", flat=True)
    )
    stale_ids: list[int] = []
    for task in Task.objects.filter(
        status=Task.Status.PENDING,
        task_type__in=AUTOMATION_TASK_TYPES,
    ).only("id", "payload"):
        try:
            campaign_id = required_int(task.payload, "campaign_id")
        except InvalidTaskPayload:
            campaign_id = None
        if campaign_id not in active_ids:
            stale_ids.append(task.pk)

    if not stale_ids:
        return 0
    deleted, _ = Task.objects.filter(pk__in=stale_ids).delete()
    logger.info("Cleaned up %d inactive pending automation task(s)", deleted)
    return deleted


def _recover_stale_running_tasks() -> int:
    """Reset RUNNING tasks to PENDING. RUNNING rows can only linger if the
    daemon crashed mid-task, so they are always stale at reconcile time."""
    count = Task.objects.filter(status=Task.Status.RUNNING).update(
        status=Task.Status.PENDING,
    )
    if count:
        logger.info("Recovered %d stale running tasks", count)
    return count


_PLANNERS = (
    plan_connect_window,
    plan_follow_up_window,
    plan_check_pending_window,
)


def reconcile(session) -> None:
    """Recover stale RUNNING tasks, then ensure every (campaign, task_type)
    whose pending queue is empty gets a fresh 24h plan. Runs on daemon
    startup and whenever the queue has no ready task."""
    cleanup_inactive_pending_tasks()
    _recover_stale_running_tasks()
    for campaign in session.campaigns:
        if not _campaign_active(campaign):
            continue
        flush_custom_first_messages(campaign)
        for planner in _PLANNERS:
            planner(session, campaign)
        # Eager-drain counterpart to the window planners — queue every
        # ready email to send now (paced only by the per-box daily cap).
        flush_email_queue(session, campaign)

    pending_count = Task.objects.pending().count()
    logger.info("Task queue reconciled: %d pending tasks", pending_count)
