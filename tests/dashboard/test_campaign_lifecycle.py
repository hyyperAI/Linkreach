from types import SimpleNamespace
from unittest.mock import patch
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from linkedin_cli.exceptions import ProfileInaccessibleError
from linkreach.core import scheduler
from linkreach.core.daemon import defer_inactive_campaign_task
from linkreach.core.models import Campaign, Task
from linkreach.crm.models import Deal, DealState
from linkreach.dashboard import services
from linkreach.linkedin.models import LinkedInProfile
from linkreach.linkedin.tasks.connect import MAX_CONNECT_ATTEMPTS, handle_connect
from tests.factories import CampaignFactory, DealFactory, UserFactory


def test_new_campaigns_default_to_draft(db):
    campaign = Campaign.objects.create(name="Draft by default")

    assert campaign.status == Campaign.Status.DRAFT


def test_campaign_status_start_and_pause(client, db):
    user = UserFactory(username="campaign-owner")
    client.force_login(user)
    campaign = CampaignFactory()
    campaign.users.add(user)
    DealFactory(campaign=campaign, state=DealState.QUALIFIED)
    LinkedInProfile.objects.create(
        user=user,
        linkedin_username="owner@example.com",
        linkedin_password="pw",
        active=True,
        legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )

    response = client.post(
        reverse("dashboard:campaign_status", args=[campaign.pk]),
        data={"status": Campaign.Status.ACTIVE},
    )

    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.ACTIVE
    assert campaign.users.filter(pk=user.pk).exists()

    response = client.post(
        reverse("dashboard:campaign_status", args=[campaign.pk]),
        data={"status": Campaign.Status.PAUSED},
    )

    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.PAUSED


def test_campaign_status_start_requires_connected_account(client, db):
    user = UserFactory(username="missing-account")
    client.force_login(user)
    campaign = CampaignFactory()
    DealFactory(campaign=campaign, state=DealState.QUALIFIED)

    client.post(
        reverse("dashboard:campaign_status", args=[campaign.pk]),
        data={"status": Campaign.Status.ACTIVE},
    )

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.DRAFT


@patch("linkreach.core.scheduler.ENABLE_ACTIVE_HOURS", False)
def test_draft_campaign_does_not_plan_connect_slots(fake_session):
    fake_session.campaign.status = Campaign.Status.DRAFT
    fake_session.campaign.save(update_fields=["status"])

    created = scheduler.plan_connect_window(fake_session, fake_session.campaign)

    assert created == 0
    assert not Task.objects.filter(task_type=Task.TaskType.CONNECT).exists()


@patch("linkreach.core.scheduler.ENABLE_ACTIVE_HOURS", False)
def test_active_campaign_plans_connect_slots(fake_session):
    fake_session.campaign.status = Campaign.Status.ACTIVE
    fake_session.campaign.save(update_fields=["status"])

    created = scheduler.plan_connect_window(fake_session, fake_session.campaign)

    assert created > 0
    assert Task.objects.filter(
        task_type=Task.TaskType.CONNECT,
        payload__campaign_id=fake_session.campaign.pk,
    ).exists()


def test_inactive_campaign_task_is_deferred(db):
    campaign = CampaignFactory(status=Campaign.Status.PAUSED)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )
    before = timezone.now()

    defer_inactive_campaign_task(task, campaign, minutes=5)

    task.refresh_from_db()
    assert task.status == Task.Status.PENDING
    assert task.started_at is None
    assert task.scheduled_at > before


def test_draft_campaign_tasks_are_not_runnable_or_next_up(db):
    campaign = CampaignFactory(status=Campaign.Status.DRAFT)
    task = Task.objects.create(
        task_type=Task.TaskType.FOLLOW_UP,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )

    assert task not in list(Task.objects.pending())
    assert Task.objects.claim_next() is None
    assert services.next_up() == []


def test_active_campaign_tasks_are_runnable_and_next_up(db):
    campaign = CampaignFactory(status=Campaign.Status.ACTIVE)
    due_task = Task.objects.create(
        task_type=Task.TaskType.FOLLOW_UP,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )

    assert due_task in list(Task.objects.pending())
    assert Task.objects.claim_next() == due_task

    due_task.delete()
    Task.objects.create(
        task_type=Task.TaskType.FOLLOW_UP,
        scheduled_at=timezone.now() + timedelta(minutes=1),
        payload={"campaign_id": campaign.pk},
    )
    assert services.next_up()[0]["campaign"] == campaign.name


def test_cleanup_removes_inactive_and_orphaned_pending_automation_tasks(db):
    active = CampaignFactory(status=Campaign.Status.ACTIVE)
    paused = CampaignFactory(status=Campaign.Status.PAUSED)
    active_task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": active.pk},
    )
    paused_task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": paused.pk},
    )
    orphan_task = Task.objects.create(
        task_type=Task.TaskType.FOLLOW_UP,
        scheduled_at=timezone.now(),
        payload={"campaign_id": 999999},
    )

    deleted = scheduler.cleanup_inactive_pending_tasks()

    assert deleted == 2
    assert Task.objects.filter(pk=active_task.pk).exists()
    assert not Task.objects.filter(pk=paused_task.pk).exists()
    assert not Task.objects.filter(pk=orphan_task.pk).exists()


def test_manual_message_task_remains_runnable_for_paused_campaign(db):
    campaign = CampaignFactory(status=Campaign.Status.PAUSED)
    deal = DealFactory(campaign=campaign)
    task = Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        scheduled_at=timezone.now(),
        payload={"deal_id": deal.pk, "message": "Manual reply"},
    )

    assert task in list(Task.objects.pending())
    assert Task.objects.claim_next() == task
    assert scheduler.cleanup_inactive_pending_tasks() == 0
    assert Task.objects.filter(pk=task.pk).exists()


def test_pausing_campaign_removes_pending_automation_slots(client, db):
    user = UserFactory(username="pause-cleanup")
    client.force_login(user)
    campaign = CampaignFactory(status=Campaign.Status.ACTIVE)
    campaign.users.add(user)
    DealFactory(campaign=campaign, state=DealState.QUALIFIED)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )

    response = client.post(
        reverse("dashboard:campaign_status", args=[campaign.pk]),
        data={"status": Campaign.Status.PAUSED},
    )

    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.PAUSED
    assert not Task.objects.filter(pk=task.pk).exists()


def test_csv_no_connect_button_marks_profile_unavailable_without_global_disqualify(db):
    campaign = CampaignFactory(
        status=Campaign.Status.ACTIVE,
        outreach_mode=Campaign.OutreachMode.CSV_PERSONALIZED,
    )
    deal = DealFactory(
        campaign=campaign,
        state=DealState.READY_TO_CONNECT,
        connect_attempts=MAX_CONNECT_ATTEMPTS - 1,
    )
    session = SimpleNamespace(
        campaign=campaign,
        linkedin_profile=SimpleNamespace(
            can_execute=lambda _action: True,
            record_action=lambda *_args, **_kwargs: None,
        ),
    )
    observed = SimpleNamespace(value=DealState.QUALIFIED)

    with (
        patch("linkedin_cli.actions.status.get_connection_status", return_value=observed),
        patch("linkedin_cli.actions.connect.send_connection_request", return_value=observed),
    ):
        handle_connect(SimpleNamespace(payload={"campaign_id": campaign.pk}), session, {})

    deal.refresh_from_db()
    deal.lead.refresh_from_db()
    assert deal.state == DealState.FAILED
    assert "Unreachable: no Connect button" in deal.reason
    assert deal.lead.disqualified is False


def test_csv_profile_inaccessible_sets_clear_reason(db):
    campaign = CampaignFactory(
        status=Campaign.Status.ACTIVE,
        outreach_mode=Campaign.OutreachMode.CSV_PERSONALIZED,
    )
    deal = DealFactory(campaign=campaign, state=DealState.READY_TO_CONNECT)
    session = SimpleNamespace(
        campaign=campaign,
        linkedin_profile=SimpleNamespace(
            can_execute=lambda _action: True,
            record_action=lambda *_args, **_kwargs: None,
        ),
    )

    with patch(
        "linkedin_cli.actions.status.get_connection_status",
        side_effect=ProfileInaccessibleError("404"),
    ):
        handle_connect(SimpleNamespace(payload={"campaign_id": campaign.pk}), session, {})

    deal.refresh_from_db()
    assert deal.state == DealState.FAILED
    assert "Profile inaccessible" in deal.reason
