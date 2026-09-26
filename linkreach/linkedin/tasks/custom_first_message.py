from __future__ import annotations

import logging

from django.utils import timezone

from linkreach.core.task_payloads import required_int
from linkreach.crm.models import Deal, DealState
from linkreach.linkedin.models import ActionLog, LinkedInProfile

logger = logging.getLogger(__name__)


def _fail(deal, message: str) -> None:
    deal.custom_message_status = Deal.CustomMessageStatus.FAILED
    deal.custom_message_error = message
    deal.save(update_fields=["custom_message_status", "custom_message_error"])
    raise RuntimeError(message)


def handle_custom_first_message(task, session, qualifiers):
    """Send one verbatim CSV opener after its LinkedIn connection is accepted."""
    from linkedin_cli.actions.message import send_raw_message
    from linkreach.chat.models import ChatMessage
    from linkreach.linkedin.db.chat import mark_synced_outgoing_message, sync_conversation
    from linkreach.linkedin.tasks.follow_up import _build_send_profile

    deal_id = required_int(task.payload, "deal_id")
    deal = (
        Deal.objects.select_related("lead", "campaign")
        .filter(pk=deal_id)
        .first()
    )
    if deal is None:
        raise RuntimeError("Deal no longer exists.")
    body = deal.custom_first_message
    if not body.strip():
        _fail(deal, "Customized first message is empty.")
    if deal.state != DealState.CONNECTED:
        _fail(deal, "Lead is not connected yet.")
    if deal.custom_message_status == Deal.CustomMessageStatus.SENT:
        return

    profile = session.linkedin_profile
    profile.refresh_from_db()
    if not profile.active or profile.connection_status != LinkedInProfile.ConnectionStatus.CONNECTED:
        _fail(deal, "LinkedIn account is not connected and active.")
    if not profile.can_execute(ActionLog.ActionType.FOLLOW_UP):
        _fail(deal, "Daily follow-up limit reached. Retry after the limit resets.")

    session.campaign = deal.campaign
    # Sync before sending. This makes a crash-after-send retry idempotent and
    # protects established conversations from receiving a new opener.
    try:
        sync_conversation(session, deal.lead.public_identifier)
    except Exception as exc:
        logger.exception("custom opener: pre-send sync failed for %s", deal.lead.public_identifier)
        _fail(deal, f"Could not check the existing LinkedIn conversation: {exc}")
    existing = deal.messages.filter(is_outgoing=True, content=body).order_by("-creation_date").first()
    if existing:
        if existing.source == ChatMessage.Source.UNKNOWN:
            existing.source = ChatMessage.Source.CSV_CUSTOM
            existing.save(update_fields=["source"])
        deal.custom_message_status = Deal.CustomMessageStatus.SENT
        deal.custom_message_sent_at = existing.creation_date or timezone.now()
        deal.custom_message_error = ""
        deal.save(update_fields=["custom_message_status", "custom_message_sent_at", "custom_message_error"])
        return
    if deal.messages.exists():
        _fail(deal, "An existing LinkedIn conversation was found. Review it before sending an opener.")

    deal.custom_message_status = Deal.CustomMessageStatus.SENDING
    deal.custom_message_attempts += 1
    deal.custom_message_error = ""
    deal.save(update_fields=["custom_message_status", "custom_message_attempts", "custom_message_error"])
    try:
        sent = send_raw_message(session, _build_send_profile(deal), body)
    except Exception as exc:
        logger.exception("custom opener: send failed for %s", deal.lead.public_identifier)
        _fail(deal, f"LinkedIn message send failed: {exc}")
    if not sent:
        _fail(deal, "LinkedIn did not accept the campaign message.")

    profile.record_action(ActionLog.ActionType.FOLLOW_UP, deal.campaign)
    deal.custom_message_status = Deal.CustomMessageStatus.SENT
    deal.custom_message_sent_at = timezone.now()
    deal.custom_message_error = ""
    deal.save(update_fields=["custom_message_status", "custom_message_sent_at", "custom_message_error"])
    try:
        sync_conversation(session, deal.lead.public_identifier)
        mark_synced_outgoing_message(deal, body, ChatMessage.Source.CSV_CUSTOM)
    except Exception:
        logger.exception("custom opener: post-send sync failed for %s", deal.lead.public_identifier)
