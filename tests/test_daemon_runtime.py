from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from pydantic_ai.exceptions import ModelHTTPError

from linkreach.core import daemon
from linkreach.core.models import Campaign, Task


def _session(campaign):
    return SimpleNamespace(
        campaigns=[campaign],
        campaign=campaign,
        active_timezone=None,
        active_timezone_provenance=lambda: "test timezone",
        close=MagicMock(),
        linkedin_profile=SimpleNamespace(linkedin_username="sender@example.com"),
    )


def test_duration_format_is_stable():
    assert daemon._hm(0) == "0h00m"
    assert daemon._hm(65 * 60) == "1h05m"


def test_heartbeat_logs_only_after_interval():
    with (
        patch.object(daemon.time, "monotonic", side_effect=[10.0, 11.0, 16.0]),
        patch.object(daemon.logger, "info") as log,
    ):
        heartbeat = daemon.Heartbeat(interval=5)
        heartbeat.maybe_log("quiet")
        heartbeat.maybe_log(lambda: "working")

    log.assert_called_once()
    assert log.call_args.args[-1] == "working"


@pytest.mark.django_db
def test_dashboard_stop_signal_raises():
    with patch("linkreach.core.bot_process.stop_requested", return_value=True):
        with pytest.raises(daemon.DashboardStopRequested):
            daemon._raise_if_dashboard_stop_requested()


@pytest.mark.django_db
def test_manual_task_wakes_sleep_loop():
    Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        scheduled_at=timezone.now(),
        payload={"deal_id": 1, "message": "Hello"},
    )
    with (
        patch.object(daemon.time, "monotonic", side_effect=[0.0, 0.0, 1.0]),
        patch.object(daemon.time, "sleep"),
        patch.object(daemon.ProcessHeartbeat, "maybe_write"),
        patch.object(daemon, "_raise_if_dashboard_stop_requested"),
    ):
        daemon.sleep_with_heartbeat(10, daemon.Heartbeat(interval=100), "waiting")


@pytest.mark.django_db
def test_run_daemon_completes_valid_task():
    campaign = Campaign.objects.create(name="Runtime active", status=Campaign.Status.ACTIVE)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )
    handler = MagicMock()
    session = _session(campaign)
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(daemon, "_raise_if_dashboard_stop_requested", side_effect=[None, daemon.DashboardStopRequested()]),
        patch.object(Task.objects, "claim_next", return_value=task),
        patch.dict(daemon._HANDLERS, {Task.TaskType.CONNECT: handler}),
        patch.object(daemon._HumanRhythmBreak, "maybe_break"),
    ):
        daemon.run_daemon(session)

    handler.assert_called_once()
    task.refresh_from_db()
    assert task.status == Task.Status.COMPLETED
    session.close.assert_called_once()


@pytest.mark.django_db
def test_run_daemon_rejects_malformed_payload_without_handler_call():
    campaign = Campaign.objects.create(name="Malformed task campaign", status=Campaign.Status.ACTIVE)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": "not-a-number"},
    )
    handler = MagicMock()
    session = _session(campaign)
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(daemon, "_raise_if_dashboard_stop_requested", side_effect=[None, daemon.DashboardStopRequested()]),
        patch.object(Task.objects, "claim_next", return_value=task),
        patch.dict(daemon._HANDLERS, {Task.TaskType.CONNECT: handler}),
    ):
        daemon.run_daemon(session)

    handler.assert_not_called()
    task.refresh_from_db()
    assert task.status == Task.Status.FAILED


@pytest.mark.django_db
def test_run_daemon_defers_task_when_campaign_is_paused():
    campaign = Campaign.objects.create(name="Runtime paused", status=Campaign.Status.PAUSED)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )
    session = _session(campaign)
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(daemon, "_raise_if_dashboard_stop_requested", side_effect=[None, daemon.DashboardStopRequested()]),
        patch.object(Task.objects, "claim_next", return_value=task),
    ):
        daemon.run_daemon(session)

    task.refresh_from_db()
    assert task.status == Task.Status.PENDING
    assert task.scheduled_at > timezone.now()


@pytest.mark.django_db
def test_run_daemon_marks_unexpected_handler_failure():
    campaign = Campaign.objects.create(name="Runtime failure", status=Campaign.Status.ACTIVE)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )
    session = _session(campaign)
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(daemon, "_raise_if_dashboard_stop_requested", side_effect=[None, daemon.DashboardStopRequested()]),
        patch.object(Task.objects, "claim_next", return_value=task),
        patch.dict(daemon._HANDLERS, {Task.TaskType.CONNECT: MagicMock(side_effect=RuntimeError("boom"))}),
    ):
        daemon.run_daemon(session)

    task.refresh_from_db()
    assert task.status == Task.Status.FAILED


def test_checkpoint_exit_fails_task_closes_browser_and_exits():
    task = MagicMock()
    session = SimpleNamespace(
        linkedin_profile=SimpleNamespace(linkedin_username="sender@example.com"),
        close=MagicMock(),
    )
    with pytest.raises(SystemExit):
        daemon._exit_on_checkpoint(session, task, "https://linkedin.example/checkpoint")
    task.mark_failed.assert_called_once()
    session.close.assert_called_once()


def test_process_heartbeat_respects_interval_and_force():
    with (
        patch.object(daemon.time, "monotonic", side_effect=[11.0, 12.0, 20.0]),
        patch("linkreach.core.bot_process.write_heartbeat") as write,
    ):
        heartbeat = daemon.ProcessHeartbeat(interval=10)
        heartbeat.maybe_write()
        heartbeat.maybe_write()
        heartbeat.maybe_write(force=True)
    assert write.call_count == 2


@pytest.mark.django_db
def test_manual_message_ready_only_for_due_manual_work():
    assert daemon._manual_message_ready() is False
    future = Task.objects.create(
        task_type=Task.TaskType.MANUAL_MESSAGE,
        scheduled_at=timezone.now() + daemon.timedelta(hours=1),
        payload={"deal_id": 1, "message": "Later"},
    )
    assert daemon._manual_message_ready() is False
    future.scheduled_at = timezone.now()
    future.save(update_fields=["scheduled_at"])
    assert daemon._manual_message_ready() is True


def test_cloud_promo_and_human_rhythm_are_rate_limited():
    with (
        patch.object(daemon.time, "monotonic", side_effect=[10.0, 11.0, 20.0]),
        patch.object(daemon.random, "choice", side_effect=lambda values: values[0]),
        patch.object(daemon.logger, "info") as log,
    ):
        promo = daemon._CloudPromoRotator(interval=5)
        promo.maybe_log()
        promo.maybe_log()
        promo.maybe_log()
    assert log.call_count == 2

    heartbeat = daemon.Heartbeat(interval=100)
    with (
        patch.object(daemon.time, "monotonic", side_effect=[0.0, 20.0, 21.0]),
        patch.object(daemon.random, "uniform", side_effect=[10.0, 60.0, 10.0]),
        patch.object(daemon, "sleep_with_heartbeat") as sleep,
    ):
        rhythm = daemon._HumanRhythmBreak(heartbeat)
        rhythm.maybe_break()
    sleep.assert_called_once()


def test_seconds_until_active_handles_disabled_unknown_open_and_closed_windows():
    with patch.object(daemon, "ENABLE_ACTIVE_HOURS", False):
        assert daemon.seconds_until_active("UTC") == 0
    with patch.object(daemon, "ENABLE_ACTIVE_HOURS", True):
        assert daemon.seconds_until_active(None) == 0

    open_now = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
    with (
        patch.object(daemon, "ENABLE_ACTIVE_HOURS", True),
        patch.object(daemon, "ACTIVE_START_HOUR", 9),
        patch.object(daemon, "ACTIVE_END_HOUR", 17),
        patch.object(daemon.timezone, "localtime", return_value=open_now),
    ):
        assert daemon.seconds_until_active("UTC") == 0

    closed_now = open_now.replace(hour=18)
    with (
        patch.object(daemon, "ENABLE_ACTIVE_HOURS", True),
        patch.object(daemon, "ACTIVE_START_HOUR", 9),
        patch.object(daemon, "ACTIVE_END_HOUR", 17),
        patch.object(daemon.timezone, "localtime", return_value=closed_now),
    ):
        assert daemon.seconds_until_active("UTC") > 0


@pytest.mark.django_db
def test_build_qualifiers_warm_starts_regular_and_skips_missing_freemium_kit():
    regular = Campaign.objects.create(name="Regular", status=Campaign.Status.ACTIVE)
    freemium = Campaign.objects.create(
        name="Freemium", status=Campaign.Status.ACTIVE, is_freemium=True,
    )
    qualifier = MagicMock()
    labels = SimpleNamespace(
        __len__=lambda self: 2,
    )
    import numpy as np
    X = np.ones((2, 2))
    y = np.array([1, 0])
    with (
        patch.object(daemon, "BayesianQualifier", return_value=qualifier),
        patch("linkreach.crm.models.Lead.get_labeled_arrays", return_value=(X, y)),
    ):
        result = daemon._build_qualifiers(
            [regular, freemium], daemon.CAMPAIGN_CONFIG, kit_model=None,
        )
    assert set(result) == {regular.pk}
    qualifier.warm_start.assert_called_once_with(X, y)


@pytest.mark.django_db
def test_run_daemon_returns_when_no_active_campaigns():
    session = SimpleNamespace(campaigns=[], campaign=None)
    with patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None):
        assert daemon.run_daemon(session) is None


@pytest.mark.django_db
@pytest.mark.parametrize("wait", [None, 30.0])
def test_run_daemon_sleeps_when_queue_has_no_ready_task(wait):
    campaign = Campaign.objects.create(name=f"Queue wait {wait}", status=Campaign.Status.ACTIVE)
    session = _session(campaign)
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(daemon, "_raise_if_dashboard_stop_requested"),
        patch.object(Task.objects, "claim_next", return_value=None),
        patch.object(Task.objects, "seconds_to_next", return_value=wait),
        patch.object(daemon, "sleep_with_heartbeat", side_effect=daemon.DashboardStopRequested),
    ):
        daemon.run_daemon(session)
    session.close.assert_called_once()


@pytest.mark.django_db
def test_run_daemon_fails_task_for_missing_campaign_and_unknown_type():
    missing = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": 999999},
    )
    campaign = Campaign.objects.create(name="Unknown handler", status=Campaign.Status.ACTIVE)
    unknown = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )
    session = _session(campaign)
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(
            daemon,
            "_raise_if_dashboard_stop_requested",
            side_effect=[None, None, daemon.DashboardStopRequested()],
        ),
        patch.object(Task.objects, "claim_next", side_effect=[missing, unknown]),
        patch.dict(daemon._HANDLERS, {Task.TaskType.CONNECT: None}),
    ):
        daemon.run_daemon(session)
    missing.refresh_from_db()
    unknown.refresh_from_db()
    assert missing.status == Task.Status.FAILED
    assert unknown.status == Task.Status.FAILED


@pytest.mark.django_db
def test_run_daemon_reauthenticates_after_expired_session():
    from linkedin_cli.exceptions import AuthenticationError

    campaign = Campaign.objects.create(name="Reauth", status=Campaign.Status.ACTIVE)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )
    session = _session(campaign)
    session.reauthenticate = MagicMock()
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(
            daemon, "_raise_if_dashboard_stop_requested",
            side_effect=[None, daemon.DashboardStopRequested()],
        ),
        patch.object(Task.objects, "claim_next", return_value=task),
        patch.dict(
            daemon._HANDLERS,
            {Task.TaskType.CONNECT: MagicMock(side_effect=AuthenticationError("expired"))},
        ),
    ):
        daemon.run_daemon(session)
    session.reauthenticate.assert_called_once()
    task.refresh_from_db()
    assert task.status == Task.Status.FAILED


@pytest.mark.django_db
def test_run_daemon_defers_llm_rate_limit():
    campaign = Campaign.objects.create(name="Rate limited", status=Campaign.Status.ACTIVE)
    task = Task.objects.create(
        task_type=Task.TaskType.CONNECT,
        scheduled_at=timezone.now(),
        payload={"campaign_id": campaign.pk},
    )
    session = _session(campaign)
    error = ModelHTTPError(status_code=429, model_name="test", body={"error": "rate"})
    with (
        patch("linkreach.linkedin.ml.hub.fetch_kit", return_value=None),
        patch.object(daemon, "_build_qualifiers", return_value={}),
        patch("linkreach.core.scheduler.reconcile"),
        patch.object(
            daemon, "_raise_if_dashboard_stop_requested",
            side_effect=[None, daemon.DashboardStopRequested()],
        ),
        patch.object(Task.objects, "claim_next", return_value=task),
        patch.dict(daemon._HANDLERS, {Task.TaskType.CONNECT: MagicMock(side_effect=error)}),
        patch.object(daemon, "sleep_with_heartbeat"),
    ):
        daemon.run_daemon(session)
    task.refresh_from_db()
    assert task.status == Task.Status.PENDING
    assert task.scheduled_at > timezone.now()
