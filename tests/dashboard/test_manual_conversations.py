import pytest
from django.urls import reverse
from django.utils import timezone

from linkreach.chat.models import ChatMessage, ConversationEvent
from linkreach.core.models import Campaign, Task
from linkreach.crm.models import Deal, DealState
from linkreach.dashboard import services
from linkreach.linkedin.db.chat import mark_synced_outgoing_message
from linkreach.linkedin.models import LinkedInProfile
from tests.factories import DealFactory, UserFactory


@pytest.fixture
def user(db):
    return UserFactory(username="operator")


@pytest.fixture
def logged_in_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def deal(db, user):
    campaign = Campaign.objects.create(name="Manual Test")
    campaign.users.add(user)
    deal = DealFactory(campaign=campaign, state=DealState.CONNECTED)
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:1",
        content="Hello",
        is_outgoing=False,
        creation_date=timezone.now(),
    )
    return deal


def test_deal_reply_mode_defaults_to_auto(db):
    deal = DealFactory()
    assert deal.reply_mode == Deal.ReplyMode.AUTO


def test_conversations_list_links_to_full_page(logged_in_client, deal):
    response = logged_in_client.get(reverse("dashboard:conversations"))
    assert response.status_code == 200
    assert reverse("dashboard:conversation_detail", args=[deal.pk]).encode() in response.content
    assert b"View chat" in response.content
    assert b"Auto" in response.content


def test_reply_mode_switching(logged_in_client, deal):
    response = logged_in_client.post(
        reverse("dashboard:conversation_reply_mode", args=[deal.pk]),
        data={"reply_mode": "manual"},
    )
    assert response.status_code == 302
    deal.refresh_from_db()
    assert deal.reply_mode == Deal.ReplyMode.MANUAL

    logged_in_client.post(
        reverse("dashboard:conversation_reply_mode", args=[deal.pk]),
        data={"reply_mode": "auto"},
    )
    deal.refresh_from_db()
    assert deal.reply_mode == Deal.ReplyMode.AUTO


def test_reply_mode_events_are_created_once_and_in_order(logged_in_client, deal):
    first_message = deal.messages.first()

    logged_in_client.post(
        reverse("dashboard:conversation_reply_mode", args=[deal.pk]),
        data={"reply_mode": "manual"},
    )
    logged_in_client.post(
        reverse("dashboard:conversation_reply_mode", args=[deal.pk]),
        data={"reply_mode": "manual"},
    )
    logged_in_client.post(
        reverse("dashboard:conversation_reply_mode", args=[deal.pk]),
        data={"reply_mode": "auto"},
    )

    events = list(ConversationEvent.objects.filter(deal=deal).order_by("created_at", "pk"))
    assert [event.event_type for event in events] == [
        ConversationEvent.EventType.MANUAL_MODE_STARTED,
        ConversationEvent.EventType.AI_AUTO_RESUMED,
    ]
    timeline = services.conversation_timeline(deal)
    assert [item["kind"] for item in timeline].count("event") == 2
    assert first_message in [item.get("message") for item in timeline if item["kind"] == "message"]


def test_valid_manual_reply_creates_queued_task(logged_in_client, user, deal):
    LinkedInProfile.objects.create(
        user=user,
        linkedin_username="me@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    deal.reply_mode = Deal.ReplyMode.MANUAL
    deal.save(update_fields=["reply_mode"])

    response = logged_in_client.post(
        reverse("dashboard:conversation_send_manual", args=[deal.pk]),
        data={"message": "Manual hello"},
    )

    assert response.status_code == 302
    task = Task.objects.get(task_type=Task.TaskType.MANUAL_MESSAGE)
    assert task.status == Task.Status.PENDING
    assert task.payload["deal_id"] == deal.pk
    assert task.payload["campaign_id"] == deal.campaign_id
    assert task.payload["message"] == "Manual hello"

    response = logged_in_client.get(reverse("dashboard:conversation_detail", args=[deal.pk]))
    assert b"Manual hello" in response.content
    assert b"Sent manually" in response.content
    assert b"Queued" in response.content


def test_outgoing_labels_render_without_labelling_incoming(logged_in_client, deal):
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:manual",
        content="Manual sent",
        is_outgoing=True,
        source=ChatMessage.Source.MANUAL,
        creation_date=timezone.now(),
    )
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:ai",
        content="AI sent",
        is_outgoing=True,
        source=ChatMessage.Source.AI,
        creation_date=timezone.now(),
    )
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:legacy",
        content="Legacy sent",
        is_outgoing=True,
        creation_date=timezone.now(),
    )

    response = logged_in_client.get(reverse("dashboard:conversation_detail", args=[deal.pk]))

    assert response.status_code == 200
    assert b"Sent manually" in response.content
    assert b"Sent by AI" in response.content
    assert b"Previous outgoing message" in response.content
    assert response.content.count(b"Hello") == 1


def test_mode_dividers_render(logged_in_client, deal, user):
    ConversationEvent.objects.create(
        deal=deal,
        event_type=ConversationEvent.EventType.MANUAL_MODE_STARTED,
        created_by=user,
    )
    ConversationEvent.objects.create(
        deal=deal,
        event_type=ConversationEvent.EventType.AI_AUTO_RESUMED,
        created_by=user,
    )

    response = logged_in_client.get(reverse("dashboard:conversation_detail", args=[deal.pk]))

    assert b"Manual mode started by you" in response.content
    assert b"AI auto-reply resumed" in response.content


def test_sync_attribution_marks_manual_and_does_not_duplicate(logged_in_client, deal, user):
    Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status=Task.Status.PENDING,
        scheduled_at=timezone.now(),
        payload={"deal_id": deal.pk, "message": "Synced manual"},
    )
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:synced-manual",
        content="Synced manual",
        is_outgoing=True,
        creation_date=timezone.now(),
    )

    msg = mark_synced_outgoing_message(
        deal,
        "Synced manual",
        ChatMessage.Source.MANUAL,
        initiated_by=user,
    )
    assert msg.source == ChatMessage.Source.MANUAL
    assert msg.initiated_by == user

    response = logged_in_client.get(reverse("dashboard:conversation_detail", args=[deal.pk]))
    assert response.content.count(b"Synced manual") == 1


def test_sync_attribution_preserves_existing_source(deal):
    msg = ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:preserve",
        content="Preserve me",
        is_outgoing=True,
        source=ChatMessage.Source.MANUAL,
        creation_date=timezone.now(),
    )

    mark_synced_outgoing_message(deal, "Preserve me", ChatMessage.Source.AI)

    msg.refresh_from_db()
    assert msg.source == ChatMessage.Source.MANUAL


def test_automatic_follow_up_label_can_be_stored_and_rendered(logged_in_client, deal):
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:auto-follow-up",
        content="Automatic follow-up",
        is_outgoing=True,
        source=ChatMessage.Source.AI,
        creation_date=timezone.now(),
    )

    response = logged_in_client.get(reverse("dashboard:conversation_detail", args=[deal.pk]))

    assert b"Automatic follow-up" in response.content
    assert b"AI assistant" in response.content
    assert b"Sent by AI" in response.content


def test_empty_manual_reply_is_rejected_and_draft_preserved(logged_in_client, user, deal):
    LinkedInProfile.objects.create(
        user=user,
        linkedin_username="me@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    deal.reply_mode = Deal.ReplyMode.MANUAL
    deal.save(update_fields=["reply_mode"])

    logged_in_client.post(
        reverse("dashboard:conversation_send_manual", args=[deal.pk]),
        data={"message": "   "},
    )

    assert not Task.objects.filter(task_type=Task.TaskType.MANUAL_MESSAGE).exists()
    response = logged_in_client.get(reverse("dashboard:conversation_detail", args=[deal.pk]))
    assert response.status_code == 200
    assert b"Write a message before sending" in response.content


def test_duplicate_manual_reply_is_rejected(logged_in_client, user, deal):
    LinkedInProfile.objects.create(
        user=user,
        linkedin_username="me@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    deal.reply_mode = Deal.ReplyMode.MANUAL
    deal.save(update_fields=["reply_mode"])
    Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status=Task.Status.PENDING,
        scheduled_at=timezone.now(),
        payload={"deal_id": deal.pk, "message": "Same message"},
    )

    logged_in_client.post(
        reverse("dashboard:conversation_send_manual", args=[deal.pk]),
        data={"message": "Same message"},
    )

    assert Task.objects.filter(task_type=Task.TaskType.MANUAL_MESSAGE).count() == 1


def test_disconnected_account_cannot_queue_manual_reply(logged_in_client, user, deal):
    LinkedInProfile.objects.create(
        user=user,
        linkedin_username="me@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.SESSION_EXPIRED,
    )
    deal.reply_mode = Deal.ReplyMode.MANUAL
    deal.save(update_fields=["reply_mode"])

    logged_in_client.post(
        reverse("dashboard:conversation_send_manual", args=[deal.pk]),
        data={"message": "Hello"},
    )

    assert not Task.objects.filter(task_type=Task.TaskType.MANUAL_MESSAGE).exists()
