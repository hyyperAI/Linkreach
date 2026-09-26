from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from linkreach.core import bot_process
from linkreach.core.models import BotProcess
from tests.factories import UserFactory


@pytest.mark.django_db
def test_status_reports_running_from_live_pid_and_fresh_heartbeat():
    proc = BotProcess.load()
    proc.pid = 1234
    proc.started_at = timezone.now() - timedelta(minutes=1)
    proc.last_heartbeat_at = timezone.now()
    proc.save()

    with patch.object(bot_process, "is_pid_alive", return_value=True):
        status = bot_process.get_status()

    assert status["state"] == "running"
    assert status["pid_alive"] is True
    assert status["tone"] == "good"


@pytest.mark.django_db
def test_status_reports_hung_for_stale_heartbeat():
    proc = BotProcess.load()
    proc.pid = 1234
    proc.started_at = timezone.now() - timedelta(minutes=10)
    proc.last_heartbeat_at = timezone.now() - timedelta(minutes=5)
    proc.save()

    with patch.object(bot_process, "is_pid_alive", return_value=True):
        status = bot_process.get_status()

    assert status["state"] == "hung"
    assert status["tone"] == "warning"


@pytest.mark.django_db
def test_status_reports_crash_when_pid_disappears_without_clean_stop():
    proc = BotProcess.load()
    proc.pid = 1234
    proc.started_at = timezone.now() - timedelta(minutes=2)
    proc.stopped_at = None
    proc.save()

    with patch.object(bot_process, "is_pid_alive", return_value=False):
        status = bot_process.get_status()

    assert status["state"] == "crashed"


@pytest.mark.django_db
def test_start_spawns_detached_daemon_and_records_pid(tmp_path):
    user = UserFactory()
    child = SimpleNamespace(pid=4567)
    status = {"state": "not_running"}
    with (
        override_settings(BASE_DIR=tmp_path, MANAGED_DEPLOYMENT=False),
        patch.object(bot_process, "get_status", return_value=status),
        patch.object(bot_process.subprocess, "Popen", return_value=child) as popen,
    ):
        ok, message = bot_process.start(user)

    assert ok is True
    assert "start requested" in message.lower()
    proc = BotProcess.load()
    assert proc.pid == 4567
    assert proc.started_by == user
    command = popen.call_args.args[0]
    assert command[1:] == ["manage.py", "rundaemon"]
    assert popen.call_args.kwargs["cwd"] == str(tmp_path)
    assert popen.call_args.kwargs["stdin"] == bot_process.subprocess.DEVNULL
    assert (tmp_path / "logs" / "daemon.log").exists()


@pytest.mark.django_db
def test_start_refuses_duplicate_process():
    user = UserFactory()
    with (
        patch.object(bot_process, "get_status", return_value={"state": "running"}),
        patch.object(bot_process.subprocess, "Popen") as popen,
    ):
        ok, message = bot_process.start(user)

    assert ok is False
    assert "already running" in message.lower()
    popen.assert_not_called()


@pytest.mark.django_db
def test_start_surfaces_process_creation_error(tmp_path):
    user = UserFactory()
    with (
        override_settings(BASE_DIR=tmp_path, MANAGED_DEPLOYMENT=False),
        patch.object(bot_process, "get_status", return_value={"state": "not_running"}),
        patch.object(bot_process.subprocess, "Popen", side_effect=OSError("blocked")),
    ):
        ok, message = bot_process.start(user)

    assert ok is False
    assert "blocked" in message
    assert BotProcess.load().pid is None


@pytest.mark.django_db
def test_clean_stop_sets_request_flag():
    proc = BotProcess.load()
    proc.pid = 1234
    proc.save(update_fields=["pid"])
    with patch.object(bot_process, "get_status", return_value={"state": "running"}):
        ok, _message = bot_process.request_stop()

    proc.refresh_from_db()
    assert ok is True
    assert proc.stop_requested is True


@pytest.mark.django_db
def test_force_stop_clears_process_state():
    proc = BotProcess.load()
    proc.pid = 1234
    proc.last_heartbeat_at = timezone.now()
    proc.save(update_fields=["pid", "last_heartbeat_at"])
    with (
        patch.object(bot_process, "is_pid_alive", return_value=True),
        patch.object(bot_process.subprocess, "run") as run,
        patch.object(bot_process.os, "name", "nt"),
    ):
        ok, _message = bot_process.force_kill()

    proc.refresh_from_db()
    assert ok is True
    assert proc.pid is None
    assert proc.last_heartbeat_at is None
    assert proc.stop_requested is False
    run.assert_called_once()


@pytest.mark.django_db
def test_heartbeat_and_stop_requested_helpers():
    proc = BotProcess.load()
    proc.stop_requested = True
    proc.save(update_fields=["stop_requested"])

    bot_process.write_heartbeat()

    proc.refresh_from_db()
    assert proc.last_heartbeat_at is not None
    assert bot_process.stop_requested() is True


@pytest.mark.parametrize("pid", [None, 0, -1, "bad"])
def test_invalid_pid_is_not_alive(pid):
    assert bot_process.is_pid_alive(pid) is False


def test_windows_pid_detection_handles_live_missing_and_command_error():
    with (
        patch.object(bot_process.os, "name", "nt"),
        patch.object(
            bot_process.subprocess,
            "run",
            return_value=SimpleNamespace(stdout='"python.exe","1234"'),
        ),
    ):
        assert bot_process.is_pid_alive(1234) is True

    with (
        patch.object(bot_process.os, "name", "nt"),
        patch.object(
            bot_process.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="INFO: No tasks are running"),
        ),
    ):
        assert bot_process.is_pid_alive(1234) is False

    with (
        patch.object(bot_process.os, "name", "nt"),
        patch.object(bot_process.subprocess, "run", side_effect=OSError("tasklist unavailable")),
    ):
        assert bot_process.is_pid_alive(1234) is False


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, True),
        (ProcessLookupError(), False),
        (PermissionError(), True),
        (OSError(), False),
    ],
)
def test_posix_pid_detection(error, expected):
    side_effect = error if error is not None else None
    with (
        patch.object(bot_process.os, "name", "posix"),
        patch.object(bot_process.os, "kill", side_effect=side_effect),
    ):
        assert bot_process.is_pid_alive(1234) is expected


@pytest.mark.django_db
def test_status_reports_clean_stop_starting_and_stopping():
    proc = BotProcess.load()
    proc.pid = 222
    proc.started_at = timezone.now()
    proc.stopped_at = None
    proc.save()

    with patch.object(bot_process, "is_pid_alive", return_value=True):
        assert bot_process.get_status()["state"] == "starting"

    proc.stop_requested = True
    proc.save(update_fields=["stop_requested"])
    with patch.object(bot_process, "is_pid_alive", return_value=True):
        assert bot_process.get_status()["state"] == "stopping"

    proc.pid = 222
    proc.stop_requested = False
    proc.stopped_at = timezone.now()
    proc.save(update_fields=["pid", "stop_requested", "stopped_at"])
    with patch.object(bot_process, "is_pid_alive", return_value=False):
        assert bot_process.get_status()["detail"] == "The bot stopped cleanly."


@pytest.mark.django_db
def test_managed_deployment_disables_controls_and_start():
    user = UserFactory()
    with override_settings(MANAGED_DEPLOYMENT=True):
        status = bot_process.get_status()
        ok, message = bot_process.start(user)

    assert status["controls_allowed"] is False
    assert ok is False
    assert "automatically" in message


@pytest.mark.django_db
def test_start_refuses_hung_process():
    with patch.object(bot_process, "get_status", return_value={"state": "hung"}):
        ok, message = bot_process.start(UserFactory())
    assert ok is False
    assert "force stop" in message.lower()


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["not_running", "crashed"])
def test_request_stop_rejects_inactive_process(state):
    with patch.object(bot_process, "get_status", return_value={"state": state}):
        ok, message = bot_process.request_stop()
    assert ok is False
    assert "not currently running" in message


@pytest.mark.django_db
def test_request_stop_rejects_hung_process():
    with patch.object(bot_process, "get_status", return_value={"state": "hung"}):
        ok, message = bot_process.request_stop()
    assert ok is False
    assert "Force stop" in message


@pytest.mark.django_db
def test_force_stop_handles_missing_pid_and_kill_error():
    ok, message = bot_process.force_kill()
    assert ok is False
    assert "No bot process" in message

    proc = BotProcess.load()
    proc.pid = 444
    proc.save(update_fields=["pid"])
    with (
        patch.object(bot_process, "is_pid_alive", return_value=True),
        patch.object(bot_process.os, "name", "nt"),
        patch.object(bot_process.subprocess, "run", side_effect=OSError("denied")),
    ):
        ok, message = bot_process.force_kill()
    assert ok is False
    assert "denied" in message


@pytest.mark.django_db
def test_force_stop_clears_already_dead_recorded_process():
    proc = BotProcess.load()
    proc.pid = 555
    proc.save(update_fields=["pid"])
    with patch.object(bot_process, "is_pid_alive", return_value=False):
        ok, _message = bot_process.force_kill()
    proc.refresh_from_db()
    assert ok is True
    assert proc.pid is None
