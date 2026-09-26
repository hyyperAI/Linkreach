from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from linkreach.chat.models import ChatMessage
from linkreach.core.models import Campaign, SiteConfig, Task
from linkreach.core.scheduler import enqueue_custom_first_message, on_deal_state_entered
from linkreach.crm.models import Deal, DealState
from linkreach.dashboard.views import _import_campaign_rows
from linkreach.linkedin.models import LinkedInProfile
from linkreach.linkedin.tasks.custom_first_message import handle_custom_first_message
from linkreach.linkedin.tasks.follow_up import _connected_deals
from tests.factories import DealFactory, UserFactory


@pytest.fixture
def operator(db):
    return UserFactory(username="csv-operator")


@pytest.fixture
def personalized_campaign(db, operator):
    campaign = Campaign.objects.create(
        name="CSV Personalized Test",
        outreach_mode=Campaign.OutreachMode.CSV_PERSONALIZED,
        product_docs="We sell a workflow product.",
        campaign_objective="Continue naturally after the imported opener.",
    )
    campaign.users.add(operator)
    return campaign


def _mapping():
    return {
        "linkedin": "LinkedIn URL",
        "first_name": "First name",
        "last_name": "Last name",
        "website": "Website",
        "custom_message": "Message",
        "email": "",
        "company": "",
        "industry": "",
        "country": "",
        "job_title": "",
    }


def test_import_preserves_personalized_message_and_profile_context(personalized_campaign):
    body = "Hi Amina,\n\nI liked your work at Example."
    summary = _import_campaign_rows(
        personalized_campaign,
        [{
            "LinkedIn URL": "https://www.linkedin.com/in/amina-example/",
            "First name": "Amina",
            "Last name": "Khan",
            "Website": "https://example.com",
            "Message": body,
        }],
        _mapping(),
        [],
    )

    deal = Deal.objects.get(campaign=personalized_campaign)
    assert summary["created"] == 1
    assert deal.state == DealState.QUALIFIED
    assert deal.custom_first_message == body
    assert deal.custom_message_status == Deal.CustomMessageStatus.PENDING
    assert deal.profile_summary["import_fields"]["website"] == "https://example.com"


def test_import_skips_missing_and_oversized_messages(personalized_campaign):
    rows = [
        {"LinkedIn URL": "https://www.linkedin.com/in/no-message/", "Message": ""},
        {"LinkedIn URL": "https://www.linkedin.com/in/too-long/", "Message": "x" * 3001},
    ]

    summary = _import_campaign_rows(personalized_campaign, rows, _mapping(), [])

    assert summary["missing_messages"] == 1
    assert summary["oversized_messages"] == 1
    assert not Deal.objects.filter(campaign=personalized_campaign).exists()
    personalized_campaign.refresh_from_db()
    assert personalized_campaign.seed_public_ids == []


def test_start_outreach_requires_setup_and_approves_reviewed_leads(
    client, operator, personalized_campaign
):
    client.force_login(operator)
    profile = LinkedInProfile.objects.create(
        user=operator,
        linkedin_username="operator@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    config = SiteConfig.load()
    config.ai_model = "openai:gpt-4o-mini"
    config.llm_api_key = "test-key"
    config.save(update_fields=["ai_model", "llm_api_key"])
    deal = DealFactory(
        campaign=personalized_campaign,
        state=DealState.QUALIFIED,
        custom_first_message="A reviewed opener",
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )

    response = client.post(
        reverse("dashboard:campaign_start_csv_outreach", args=[personalized_campaign.pk])
    )

    assert response.status_code == 302
    deal.refresh_from_db()
    assert deal.state == DealState.READY_TO_CONNECT
    assert deal.outreach_approved_at is not None
    assert personalized_campaign.users.filter(pk=operator.pk).exists()
    profile.refresh_from_db()


def test_connected_transition_queues_only_one_custom_opener(personalized_campaign):
    personalized_campaign.status = Campaign.Status.ACTIVE
    personalized_campaign.save(update_fields=["status"])
    deal = DealFactory(
        campaign=personalized_campaign,
        state=DealState.CONNECTED,
        outreach_approved_at=timezone.now(),
        custom_first_message="Exact first message",
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )

    on_deal_state_entered(deal)
    on_deal_state_entered(deal)

    tasks = Task.objects.filter(
        task_type=Task.TaskType.CUSTOM_FIRST_MESSAGE,
        payload__deal_id=deal.pk,
    )
    assert tasks.count() == 1
    assert not enqueue_custom_first_message(deal)


def test_editing_failed_connected_message_queues_explicit_retry(
    client, operator, personalized_campaign
):
    client.force_login(operator)
    personalized_campaign.status = Campaign.Status.ACTIVE
    personalized_campaign.save(update_fields=["status"])
    deal = DealFactory(
        campaign=personalized_campaign,
        state=DealState.CONNECTED,
        outreach_approved_at=timezone.now(),
        custom_first_message="Old opener",
        custom_message_status=Deal.CustomMessageStatus.FAILED,
        custom_message_error="Browser closed",
    )

    response = client.post(
        reverse(
            "dashboard:campaign_custom_message",
            args=[personalized_campaign.pk, deal.pk],
        ),
        data={"custom_first_message": "Reviewed retry message"},
    )

    assert response.status_code == 302
    deal.refresh_from_db()
    assert deal.custom_first_message == "Reviewed retry message"
    assert deal.custom_message_status == Deal.CustomMessageStatus.PENDING
    assert deal.custom_message_error == ""
    assert Task.objects.filter(
        task_type=Task.TaskType.CUSTOM_FIRST_MESSAGE,
        status=Task.Status.PENDING,
        payload__deal_id=deal.pk,
    ).exists()


def test_ai_follow_up_waits_until_custom_opener_is_sent(personalized_campaign):
    deal = DealFactory(
        campaign=personalized_campaign,
        state=DealState.CONNECTED,
        custom_first_message="First",
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )
    assert deal not in list(_connected_deals(personalized_campaign))

    deal.custom_message_status = Deal.CustomMessageStatus.SENT
    deal.save(update_fields=["custom_message_status"])
    assert deal in list(_connected_deals(personalized_campaign))


def test_handler_sends_exact_message_and_marks_delivery(
    operator, personalized_campaign
):
    personalized_campaign.users.add(operator)
    profile = LinkedInProfile.objects.create(
        user=operator,
        linkedin_username="operator@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    body = "Hi Sam,\n\nThis is the exact imported opener."
    deal = DealFactory(
        campaign=personalized_campaign,
        state=DealState.CONNECTED,
        outreach_approved_at=timezone.now(),
        custom_first_message=body,
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )
    task = Task.objects.create(
        task_type=Task.TaskType.CUSTOM_FIRST_MESSAGE,
        scheduled_at=timezone.now(),
        payload={"campaign_id": personalized_campaign.pk, "deal_id": deal.pk},
    )
    session = SimpleNamespace(
        linkedin_profile=profile,
        campaign=personalized_campaign,
    )

    with (
        patch("linkreach.linkedin.db.chat.sync_conversation"),
        patch("linkedin_cli.actions.message.send_raw_message", return_value=True) as send,
    ):
        handle_custom_first_message(task, session, {})

    send.assert_called_once()
    assert send.call_args.args[2] == body
    deal.refresh_from_db()
    assert deal.custom_message_status == Deal.CustomMessageStatus.SENT
    assert deal.custom_message_sent_at is not None


def test_handler_stops_when_existing_conversation_is_found(
    operator, personalized_campaign
):
    profile = LinkedInProfile.objects.create(
        user=operator,
        linkedin_username="operator@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    deal = DealFactory(
        campaign=personalized_campaign,
        state=DealState.CONNECTED,
        outreach_approved_at=timezone.now(),
        custom_first_message="New opener",
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:li:msg:existing",
        content="An existing conversation",
        is_outgoing=False,
    )
    task = SimpleNamespace(payload={"deal_id": deal.pk})
    session = SimpleNamespace(linkedin_profile=profile, campaign=personalized_campaign)

    with (
        patch("linkreach.linkedin.db.chat.sync_conversation"),
        patch("linkedin_cli.actions.message.send_raw_message") as send,
        pytest.raises(RuntimeError, match="existing LinkedIn conversation"),
    ):
        handle_custom_first_message(task, session, {})

    send.assert_not_called()
    deal.refresh_from_db()
    assert deal.custom_message_status == Deal.CustomMessageStatus.FAILED


def test_handler_send_error_pauses_for_review(operator, personalized_campaign):
    profile = LinkedInProfile.objects.create(
        user=operator,
        linkedin_username="operator@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    deal = DealFactory(
        campaign=personalized_campaign,
        state=DealState.CONNECTED,
        outreach_approved_at=timezone.now(),
        custom_first_message="Do not retry silently",
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )
    task = SimpleNamespace(payload={"deal_id": deal.pk})
    session = SimpleNamespace(linkedin_profile=profile, campaign=personalized_campaign)

    with (
        patch("linkreach.linkedin.db.chat.sync_conversation"),
        patch(
            "linkedin_cli.actions.message.send_raw_message",
            side_effect=RuntimeError("browser closed"),
        ),
        pytest.raises(RuntimeError, match="browser closed"),
    ):
        handle_custom_first_message(task, session, {})

    deal.refresh_from_db()
    assert deal.custom_message_status == Deal.CustomMessageStatus.FAILED
    assert "browser closed" in deal.custom_message_error


def test_campaign_page_renders_personalized_review_ui(
    client, operator, personalized_campaign
):
    client.force_login(operator)
    DealFactory(
        campaign=personalized_campaign,
        custom_first_message="Review this opener",
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )

    response = client.get(
        reverse("dashboard:campaign_detail", args=[personalized_campaign.pk])
    )

    assert response.status_code == 200
    assert b"Personalized CSV workflow" in response.content
    assert b"Review this opener" in response.content
    assert b"Approve 1 lead for outreach" in response.content
    assert b"Start campaign" in response.content
    assert b"Draft" in response.content
    assert b"Paste URLs" not in response.content


def test_campaign_page_shows_profile_unavailable_reason(
    client, operator, personalized_campaign
):
    client.force_login(operator)
    DealFactory(
        campaign=personalized_campaign,
        state=DealState.FAILED,
        reason="Profile inaccessible: 404",
        custom_first_message="Reviewed opener",
        custom_message_status=Deal.CustomMessageStatus.PENDING,
    )

    response = client.get(
        reverse("dashboard:campaign_detail", args=[personalized_campaign.pk])
    )

    assert response.status_code == 200
    assert b"Profile unavailable" in response.content
    assert b"Profile inaccessible: 404" in response.content


def test_csv_preview_requires_and_previews_custom_message_column(
    client, operator, personalized_campaign
):
    client.force_login(operator)
    upload = SimpleUploadedFile(
        "personalized.csv",
        b"LinkedIn URL,First Name,Custom Message\n"
        b"https://www.linkedin.com/in/sample-person/,Sam,Hello from the CSV\n",
        content_type="text/csv",
    )

    response = client.post(
        reverse("dashboard:campaign_import_csv", args=[personalized_campaign.pk]),
        data={"step": "preview", "csv_file": upload},
    )

    assert response.status_code == 200
    assert b"Imported openers are sent verbatim" in response.content
    assert b"Hello from the CSV" in response.content
    assert b'name="map_custom_message"' in response.content
    assert b"required" in response.content
