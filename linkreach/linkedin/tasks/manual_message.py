from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from linkreach.core.task_payloads import (
    InvalidTaskPayload,
    optional_int,
    required_int,
    required_text,
)
from linkreach.crm.models import Deal
from linkreach.linkedin.models import LinkedInProfile

logger = logging.getLogger(__name__)


def _payload_error(task, message: str) -> None:
    payload = dict(task.payload or {})
    payload["manual_status"] = "failed"
    payload["manual_error"] = message
    payload["manual_finished_at"] = timezone.now().isoformat()
    task.payload = payload
    task.save(update_fields=["payload"])


def _payload_sent(task) -> None:
    payload = dict(task.payload or {})
    payload["manual_status"] = "sent"
    payload["manual_error"] = ""
    payload["manual_finished_at"] = timezone.now().isoformat()
    task.payload = payload
    task.save(update_fields=["payload"])


def _fail(task, message: str) -> None:
    _payload_error(task, message)
    raise RuntimeError(message)


def handle_manual_message(task, session, qualifiers):
    """Send one human-authored LinkedIn message through the daemon session."""
    from linkedin_cli.actions.message import send_raw_message
    from django.contrib.auth import get_user_model
    from linkreach.chat.models import ChatMessage
    from linkreach.linkedin.db.chat import mark_synced_outgoing_message, sync_conversation
    from linkreach.linkedin.tasks.follow_up import _build_send_profile

    try:
        deal_id = required_int(task.payload, "deal_id")
        body = required_text(task.payload, "message", max_length=3000)
        queued_by_user_id = optional_int(task.payload, "queued_by_user_id")
    except InvalidTaskPayload as exc:
        _fail(task, str(exc))

    deal = (
        Deal.objects.select_related("lead", "campaign")
        .filter(pk=deal_id)
        .first()
    )
    if deal is None:
        _fail(task, "Deal no longer exists.")
    if deal.reply_mode != Deal.ReplyMode.MANUAL:
        _fail(task, "Conversation is no longer in Manual mode.")
    if not deal.lead.public_identifier and not deal.lead.linkedin_url:
        _fail(task, "Lead is missing a usable LinkedIn profile.")

    profile = session.linkedin_profile
    profile.refresh_from_db()
    if not profile.active:
        _fail(task, "LinkedIn account automation is paused.")
    if profile.connection_status != LinkedInProfile.ConnectionStatus.CONNECTED:
        _fail(task, "LinkedIn account is not connected.")

    session.campaign = deal.campaign
    logger.info("[%s] manual_message: sending to %s", deal.campaign, deal.lead.public_identifier)

    # Synchronize first so a daemon restart can recognize a message that
    # LinkedIn accepted before the local task was marked complete.
    try:
        sync_conversation(session, deal.lead.public_identifier)
    except Exception as exc:
        logger.exception("manual_message: pre-send sync failed for %s", deal.lead.public_identifier)
        _fail(task, f"Could not check the LinkedIn conversation before sending: {exc}")
    existing = (
        deal.messages.filter(
            is_outgoing=True,
            content=body,
            creation_date__gte=task.created_at - timedelta(minutes=5),
        )
        .order_by("-creation_date")
        .first()
    )
    if existing is not None:
        user = None
        if queued_by_user_id:
            user = get_user_model().objects.filter(pk=queued_by_user_id).first()
        changed = []
        if existing.source == ChatMessage.Source.UNKNOWN:
            existing.source = ChatMessage.Source.MANUAL
            changed.append("source")
        if user is not None and existing.initiated_by_id is None:
            existing.initiated_by = user
            changed.append("initiated_by")
        if changed:
            existing.save(update_fields=changed)
        _payload_sent(task)
        return

    try:
        sent = send_raw_message(session, _build_send_profile(deal), body)
    except Exception as exc:
        _fail(task, f"LinkedIn send failed: {exc}")
    if not sent:
        _fail(task, "LinkedIn did not accept the manual message.")

    try:
        sync_conversation(session, deal.lead.public_identifier)
        user = None
        if queued_by_user_id:
            user = get_user_model().objects.filter(pk=queued_by_user_id).first()
        mark_synced_outgoing_message(
            deal,
            body,
            ChatMessage.Source.MANUAL,
            initiated_by=user,
        )
    except Exception:
        logger.exception("manual_message: post-send sync failed for %s", deal.lead.public_identifier)
    deal.save()
    _payload_sent(task)
