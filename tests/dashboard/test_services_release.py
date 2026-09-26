from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from linkreach.chat.models import ChatMessage, ConversationEvent
from linkreach.core.models import Campaign, Task
from linkreach.crm.models import Deal, DealState
from linkreach.dashboard import services
from linkreach.linkedin.models import ActionLog
from linkreach.linkedin.models import LinkedInProfile
from tests.factories import CampaignFactory, DealFactory, LeadFactory, UserFactory


@pytest.mark.django_db
def test_campaign_action_summary_covers_lifecycle_and_pipeline_states():
    draft = CampaignFactory(status=Campaign.Status.DRAFT)
    assert services.campaign_action_summary(draft)["metric"] == "Draft"
    draft.status = Campaign.Status.PAUSED
    draft.save(update_fields=["status"])
    assert services.campaign_action_summary(draft)["metric"] == "Paused"

    campaign = CampaignFactory(status=Campaign.Status.ACTIVE)
    assert services.campaign_action_summary(campaign)["label"] == "Account missing"
    campaign.users.add(UserFactory())
    cases = [
        (DealState.QUALIFIED, "Ready to queue"),
        (DealState.READY_TO_CONNECT, "Queued"),
        (DealState.PENDING, "Invites pending"),
        (DealState.CONNECTED, "Conversations next"),
        (DealState.FAILED, "No active leads"),
    ]
    for state, label in cases:
        campaign.deals.all().delete()
        DealFactory(campaign=campaign, state=state)
        assert services.campaign_action_summary(campaign)["label"] == label


@pytest.mark.django_db
def test_csv_campaign_action_summary_prioritizes_failure_review_and_delivery():
    campaign = CampaignFactory(
        status=Campaign.Status.ACTIVE,
        outreach_mode=Campaign.OutreachMode.CSV_PERSONALIZED,
    )
    campaign.users.add(UserFactory())
    DealFactory(
        campaign=campaign,
        state=DealState.CONNECTED,
        custom_message_status=Deal.CustomMessageStatus.FAILED,
    )
    assert services.campaign_action_summary(campaign)["label"] == "Messages need review"

    campaign.deals.all().delete()
    DealFactory(campaign=campaign, state=DealState.QUALIFIED)
    assert services.campaign_action_summary(campaign)["label"] == "Review and start"

    campaign.deals.all().delete()
    DealFactory(
        campaign=campaign,
        state=DealState.CONNECTED,
        custom_message_status=Deal.CustomMessageStatus.SENT,
    )
    assert services.campaign_action_summary(campaign)["label"] == "Personalized outreach active"


@pytest.mark.django_db
def test_overview_chart_pipeline_and_conversation_queries_are_user_scoped():
    user = UserFactory()
    other = UserFactory()
    campaign = CampaignFactory(status=Campaign.Status.ACTIVE)
    campaign.users.add(user)
    foreign = CampaignFactory(status=Campaign.Status.ACTIVE)
    foreign.users.add(other)
    deal = DealFactory(campaign=campaign, state=DealState.CONNECTED)
    DealFactory(campaign=foreign, state=DealState.CONNECTED)
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:visible",
        content="Hello",
        is_outgoing=False,
    )
    profile = LinkedInProfile.objects.create(
        user=user,
        linkedin_username="owner@example.com",
        linkedin_password="secret",
    )
    ActionLog.objects.create(
        campaign=campaign,
        linkedin_profile=profile,
        action_type=ActionLog.ActionType.CONNECT,
    )
    stats = services.overview_stats(user)
    assert stats["connects_sent"] == 1
    assert stats["active_campaigns"] == 1
    assert stats["connected"] == 1
    assert stats["in_conversation"] == 1
    conversations = services.conversations(user)
    assert conversations == [deal]
    assert conversations[0].last_incoming is True
    labels, values = services.connects_last_30_days(user)
    assert len(labels) == len(values) == 30
    assert sum(values) == 1
    assert dict(services.pipeline_counts(campaign))["Connected"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "state", "label"),
    [
        (Task.Status.PENDING, "queued", "Queued"),
        (Task.Status.RUNNING, "sending", "Sending"),
        (Task.Status.COMPLETED, "sent", "Sent"),
        (Task.Status.FAILED, "failed", "Failed"),
    ],
)
def test_latest_manual_task_maps_task_state(status, state, label):
    deal = DealFactory()
    task = Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status=status,
        scheduled_at=timezone.now(),
        payload={"deal_id": deal.pk, "message": "Hello", "manual_error": "error"},
    )
    result = services.latest_manual_task(deal)
    assert result["task"] == task
    assert result["state"] == state
    assert result["label"] == label
    assert result["error"] == "error"


@pytest.mark.django_db
def test_conversation_timeline_combines_modes_messages_and_queued_manual_work():
    user = UserFactory()
    deal = DealFactory()
    event = ConversationEvent.objects.create(
        deal=deal,
        event_type=ConversationEvent.EventType.MANUAL_MODE_STARTED,
        created_by=user,
    )
    ChatMessage.objects.create(
        deal=deal,
        linkedin_urn="urn:message",
        content="Existing",
        is_outgoing=False,
    )
    Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status=Task.Status.PENDING,
        scheduled_at=timezone.now(),
        payload={"deal_id": deal.pk, "message": "Queued reply"},
    )
    Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        status=Task.Status.PENDING,
        scheduled_at=timezone.now(),
        payload={"deal_id": deal.pk, "message": ""},
    )
    timeline = services.conversation_timeline(deal)
    assert {item["kind"] for item in timeline} == {"event", "message", "pending_manual"}
    assert next(item for item in timeline if item.get("event") == event)["label"] == "Manual mode started by you"
    assert services.has_duplicate_manual_task(deal, "Queued reply") is True


@pytest.mark.django_db
def test_badges_and_profile_helpers_use_real_available_fields():
    campaign = CampaignFactory(
        status=Campaign.Status.ACTIVE,
        outreach_mode=Campaign.OutreachMode.CSV_PERSONALIZED,
    )
    lead = LeadFactory(
        public_identifier="jane-doe",
        country_code="us",
        api_email="jane@example.com",
    )
    deal = DealFactory(
        campaign=campaign,
        lead=lead,
        state=DealState.FAILED,
        reason="Profile inaccessible after redirect",
        profile_summary={
            "facts": ["AI SaaS founder", "B2B growth platform"],
            "import_fields": {"first_name": "Jane", "last_name": "Doe"},
            "custom_import_fields": {"company": "Acme"},
        },
    )
    assert services.campaign_status_badge(campaign)["label"] == "Active"
    badge = services.deal_state_badge(deal)
    assert badge["label"] == "Profile unavailable"
    assert "inaccessible" in badge["title"].lower()
    assert services.deal_display_name(deal) == "Jane Doe"
    assert services.email_status(lead)["label"] == "Available"
    assert services.lead_email(lead) == "jane@example.com"
    keywords = services.deal_keywords(deal, limit=2)
    assert keywords["visible"] == ["AI", "SaaS"]
    assert services.summary_preview(deal.profile_summary)
    context = services.conversation_detail_context(deal)
    assert context["name"] == "Jane Doe"
    assert context["custom_import_fields"] == {"company": "Acme"}


def test_pure_summary_email_state_and_profile_helpers_cover_missing_shapes():
    assert services.summary_facts(None) == []
    assert services.summary_facts({"facts": "bad"}) == []
    assert services.summary_facts([" one ", "", 2]) == ["one", "2"]
    assert services.summary_preview(["a" * 100], max_chars=10).endswith("…")
    assert services.pretty_name("john_smith.jr") == "John Smith Jr"
    assert services.pretty_name("") == ""
    assert services.state_tone(DealState.QUALIFIED) == "action"
    assert services.state_tone(DealState.PENDING) == "waiting"
    assert services.state_tone(DealState.CONNECTED) == "good"
    assert services.state_tone(DealState.FAILED) == "danger"
    assert services.state_tone("unknown") == "muted"
    assert services.lead_email(SimpleNamespace(api_email="", contact_info={"email": "one@example.com"})) == "one@example.com"
    assert services.lead_email(SimpleNamespace(api_email="", contact_info={"emails": ["two@example.com"]})) == "two@example.com"
    assert services.lead_email(SimpleNamespace(api_email="", contact_info=None)) == ""
    assert services._csv_profile_unavailable_reason("") is True
    assert services._csv_profile_unavailable_reason("Temporary rate limit") is False


def test_log_helpers_and_issue_classification(tmp_path):
    log = tmp_path / "daemon.log"
    with patch.object(services, "LOG_PATH", log):
        assert services.log_exists() is False
        assert services.read_log_tail() == []
        log.write_text("one\nSearching leads\nTaking a 5m break\n", encoding="utf-8")
        assert services.log_exists() is True
        assert services.read_log_tail(2) == ["Searching leads", "Taking a 5m break"]
        assert services._stage_from_log()[0] == "On a break"
    assert "rate limit" in services._issue_from_log_text("status_code: 429").lower()
    assert "groq" in services._issue_from_log_text("groq rate_limit_exceeded").lower()
    assert "API error" in services._issue_from_log_text("llm api error")
    assert "error" in services._issue_from_log_text("Traceback").lower()
    assert services._issue_from_log_text("all good") == ""
