from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from linkreach.chat.models import ChatMessage
from linkreach.core.models import Campaign, Task
from linkreach.crm.models import Deal, DealState
from linkreach.linkedin.models import LinkedInProfile
from linkreach.linkedin.tasks.custom_first_message import handle_custom_first_message
from linkreach.linkedin.tasks.manual_message import handle_manual_message
from tests.factories import DealFactory, LeadFactory, UserFactory


def _task(task_type, payload):
    return Task.objects.create(
        task_type=task_type,
        status=Task.Status.RUNNING,
        scheduled_at=timezone.now(),
        started_at=timezone.now(),
        payload=payload,
    )


def _connected_session(fake_session):
    profile = fake_session.linkedin_profile
    profile.active = True
    profile.connection_status = LinkedInProfile.ConnectionStatus.CONNECTED
    profile.save(update_fields=["active", "connection_status"])
    return fake_session


def _custom_deal(fake_session, **kwargs):
    defaults = {
        "campaign": fake_session.campaign,
        "state": DealState.CONNECTED,
        "custom_first_message": "A personalized opener",
        "custom_message_status": Deal.CustomMessageStatus.PENDING,
    }
    defaults.update(kwargs)
    return DealFactory(**defaults)


@pytest.mark.django_db
def test_custom_opener_rejects_missing_deal():
    session = SimpleNamespace()
    with pytest.raises(RuntimeError, match="no longer exists"):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": 999999}),
            session,
            {},
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"custom_first_message": ""}, "empty"),
        ({"state": DealState.PENDING}, "not connected"),
    ],
)
def test_custom_opener_records_invalid_deal_state(fake_session, overrides, message):
    deal = _custom_deal(fake_session, **overrides)
    with pytest.raises(RuntimeError, match=message):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )
    deal.refresh_from_db()
    assert deal.custom_message_status == Deal.CustomMessageStatus.FAILED


@pytest.mark.django_db
def test_custom_opener_is_idempotent_when_already_sent(fake_session):
    deal = _custom_deal(
        fake_session,
        custom_message_status=Deal.CustomMessageStatus.SENT,
    )
    with patch("linkedin_cli.actions.message.send_raw_message") as send:
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )
    send.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("active", "status", "limit", "message"),
    [
        (False, LinkedInProfile.ConnectionStatus.CONNECTED, 10, "not connected and active"),
        (True, LinkedInProfile.ConnectionStatus.ERROR, 10, "not connected and active"),
        (True, LinkedInProfile.ConnectionStatus.CONNECTED, 0, "Daily follow-up limit"),
    ],
)
def test_custom_opener_checks_account_and_daily_limit(
    fake_session, active, status, limit, message,
):
    deal = _custom_deal(fake_session)
    profile = fake_session.linkedin_profile
    profile.active = active
    profile.connection_status = status
    profile.follow_up_daily_limit = limit
    profile.save(update_fields=["active", "connection_status", "follow_up_daily_limit"])
    with pytest.raises(RuntimeError, match=message):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )


@pytest.mark.django_db
def test_custom_opener_pre_send_sync_failure_is_persisted(fake_session):
    _connected_session(fake_session)
    deal = _custom_deal(fake_session)
    with (
        patch("linkreach.linkedin.db.chat.sync_conversation", side_effect=OSError("offline")),
        pytest.raises(RuntimeError, match="Could not check"),
    ):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )
    deal.refresh_from_db()
    assert "offline" in deal.custom_message_error


@pytest.mark.django_db
def test_custom_opener_recovers_existing_synced_message(fake_session):
    _connected_session(fake_session)
    deal = _custom_deal(fake_session)
    existing = ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:custom-existing",
        content=deal.custom_first_message,
        is_outgoing=True,
        source=ChatMessage.Source.UNKNOWN,
    )
    with (
        patch("linkreach.linkedin.db.chat.sync_conversation"),
        patch("linkedin_cli.actions.message.send_raw_message") as send,
    ):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )
    send.assert_not_called()
    deal.refresh_from_db()
    existing.refresh_from_db()
    assert deal.custom_message_status == Deal.CustomMessageStatus.SENT
    assert existing.source == ChatMessage.Source.CSV_CUSTOM


@pytest.mark.django_db
def test_custom_opener_refuses_to_overwrite_existing_conversation(fake_session):
    _connected_session(fake_session)
    deal = _custom_deal(fake_session)
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:prior",
        content="Prior conversation",
        is_outgoing=False,
    )
    with (
        patch("linkreach.linkedin.db.chat.sync_conversation"),
        pytest.raises(RuntimeError, match="existing LinkedIn conversation"),
    ):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )


@pytest.mark.django_db
@pytest.mark.parametrize("send_result", [False, OSError("send offline")])
def test_custom_opener_records_send_failure(fake_session, send_result):
    _connected_session(fake_session)
    deal = _custom_deal(fake_session)
    send = MagicMock(
        side_effect=send_result if isinstance(send_result, Exception) else None,
        return_value=send_result if not isinstance(send_result, Exception) else None,
    )
    with (
        patch("linkreach.linkedin.db.chat.sync_conversation"),
        patch("linkedin_cli.actions.message.send_raw_message", send),
        pytest.raises(RuntimeError),
    ):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )
    deal.refresh_from_db()
    assert deal.custom_message_status == Deal.CustomMessageStatus.FAILED


@pytest.mark.django_db
def test_custom_opener_send_succeeds_even_if_post_sync_fails(fake_session):
    _connected_session(fake_session)
    deal = _custom_deal(fake_session)
    with (
        patch(
            "linkreach.linkedin.db.chat.sync_conversation",
            side_effect=[None, OSError("post-sync offline")],
        ),
        patch("linkedin_cli.actions.message.send_raw_message", return_value=True),
    ):
        handle_custom_first_message(
            _task(Task.TaskType.CUSTOM_FIRST_MESSAGE, {"deal_id": deal.pk}),
            fake_session,
            {},
        )
    deal.refresh_from_db()
    assert deal.custom_message_status == Deal.CustomMessageStatus.SENT
    assert deal.custom_message_attempts == 1


def _manual_deal(fake_session, **kwargs):
    defaults = {
        "campaign": fake_session.campaign,
        "state": DealState.CONNECTED,
        "reply_mode": Deal.ReplyMode.MANUAL,
    }
    defaults.update(kwargs)
    return DealFactory(**defaults)


@pytest.mark.django_db
def test_manual_message_rejects_missing_deal(fake_session):
    task = _task(Task.TaskType.MANUAL_MESSAGE, {"deal_id": 999999, "message": "Hi"})
    with pytest.raises(RuntimeError, match="no longer exists"):
        handle_manual_message(task, fake_session, {})
    task.refresh_from_db()
    assert task.payload["manual_status"] == "failed"


@pytest.mark.django_db
def test_manual_message_rejects_missing_profile_identifier(fake_session):
    deal = _manual_deal(
        fake_session,
        lead=LeadFactory(public_identifier="", linkedin_url=""),
    )
    with pytest.raises(RuntimeError, match="usable LinkedIn profile"):
        handle_manual_message(
            _task(Task.TaskType.MANUAL_MESSAGE, {"deal_id": deal.pk, "message": "Hi"}),
            fake_session,
            {},
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("active", "status", "message"),
    [
        (False, LinkedInProfile.ConnectionStatus.CONNECTED, "automation is paused"),
        (True, LinkedInProfile.ConnectionStatus.ERROR, "not connected"),
    ],
)
def test_manual_message_checks_linkedin_account(fake_session, active, status, message):
    deal = _manual_deal(fake_session)
    profile = fake_session.linkedin_profile
    profile.active = active
    profile.connection_status = status
    profile.save(update_fields=["active", "connection_status"])
    with pytest.raises(RuntimeError, match=message):
        handle_manual_message(
            _task(Task.TaskType.MANUAL_MESSAGE, {"deal_id": deal.pk, "message": "Hi"}),
            fake_session,
            {},
        )


@pytest.mark.django_db
def test_manual_message_records_pre_sync_and_send_exceptions(fake_session):
    _connected_session(fake_session)
    deal = _manual_deal(fake_session)
    with (
        patch("linkreach.linkedin.db.chat.sync_conversation", side_effect=OSError("sync offline")),
        pytest.raises(RuntimeError, match="Could not check"),
    ):
        handle_manual_message(
            _task(Task.TaskType.MANUAL_MESSAGE, {"deal_id": deal.pk, "message": "Hi"}),
            fake_session,
            {},
        )

    with (
        patch("linkreach.linkedin.db.chat.sync_conversation"),
        patch("linkedin_cli.actions.message.send_raw_message", side_effect=OSError("send offline")),
        pytest.raises(RuntimeError, match="LinkedIn send failed"),
    ):
        handle_manual_message(
            _task(Task.TaskType.MANUAL_MESSAGE, {"deal_id": deal.pk, "message": "Again"}),
            fake_session,
            {},
        )


@pytest.mark.django_db
def test_manual_retry_attributes_existing_message_to_queued_user(fake_session):
    _connected_session(fake_session)
    deal = _manual_deal(fake_session)
    user = UserFactory()
    existing = ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:manual-existing",
        content="Human message",
        is_outgoing=True,
        source=ChatMessage.Source.UNKNOWN,
    )
    task = _task(
        Task.TaskType.MANUAL_MESSAGE,
        {"deal_id": deal.pk, "message": "Human message", "queued_by_user_id": user.pk},
    )
    with patch("linkreach.linkedin.db.chat.sync_conversation"):
        handle_manual_message(task, fake_session, {})
    existing.refresh_from_db()
    assert existing.source == ChatMessage.Source.MANUAL
    assert existing.initiated_by == user


@pytest.mark.django_db
def test_manual_send_completes_when_post_sync_fails(fake_session):
    _connected_session(fake_session)
    deal = _manual_deal(fake_session)
    task = _task(Task.TaskType.MANUAL_MESSAGE, {"deal_id": deal.pk, "message": "Human message"})
    with (
        patch(
            "linkreach.linkedin.db.chat.sync_conversation",
            side_effect=[None, OSError("post-sync offline")],
        ),
        patch("linkedin_cli.actions.message.send_raw_message", return_value=True),
    ):
        handle_manual_message(task, fake_session, {})
    task.refresh_from_db()
    assert task.payload["manual_status"] == "sent"
