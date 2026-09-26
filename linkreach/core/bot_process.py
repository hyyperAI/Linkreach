from __future__ import annotations

import os
import signal
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from linkreach.core.models import BotProcess

HEARTBEAT_FRESH_FOR = timedelta(seconds=45)
STARTING_GRACE = timedelta(seconds=90)
STOPPING_GRACE = timedelta(seconds=60)


def is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False

    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        output = result.stdout.lower()
        return str(pid) in output and "no tasks are running" not in output

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def get_status() -> dict:
    proc = BotProcess.load()
    now = timezone.now()
    pid_alive = is_pid_alive(proc.pid)
    heartbeat_age = None
    if proc.last_heartbeat_at:
        heartbeat_age = max((now - proc.last_heartbeat_at).total_seconds(), 0)

    if getattr(settings, "MANAGED_DEPLOYMENT", False):
        controls_allowed = False
        controls_message = "This bot runs as part of the managed container and starts automatically."
    else:
        controls_allowed = True
        controls_message = ""

    state = "not_running"
    label = "Not running"
    tone = "neutral"
    detail = "The bot has not been started yet."

    if proc.pid and not pid_alive:
        if proc.stopped_at:
            state = "not_running"
            label = "Not running"
            tone = "neutral"
            detail = "The bot stopped cleanly."
        else:
            state = "crashed"
            label = "Crashed"
            tone = "danger"
            detail = "The bot process ended without a clean shutdown."
    elif pid_alive:
        if proc.stop_requested:
            state = "stopping"
            label = "Stopping"
            tone = "warning"
            detail = "A clean stop was requested. The bot will finish its current checkpoint and close."
            if proc.started_at and now - proc.started_at > STOPPING_GRACE and not proc.last_heartbeat_at:
                detail = "Stop was requested, but no heartbeat has arrived yet."
        elif proc.last_heartbeat_at and now - proc.last_heartbeat_at <= HEARTBEAT_FRESH_FOR:
            state = "running"
            label = "Running"
            tone = "good"
            detail = "Heartbeat confirmed."
        elif proc.started_at and now - proc.started_at <= STARTING_GRACE and not proc.last_heartbeat_at:
            state = "starting"
            label = "Starting"
            tone = "info"
            detail = "A separate Chrome window may open on this computer. Do not close it."
        else:
            state = "hung"
            label = "Unresponsive"
            tone = "warning"
            detail = "The process exists, but its heartbeat is stale."

    return {
        "state": state,
        "label": label,
        "tone": tone,
        "detail": detail,
        "pid": proc.pid,
        "started_at": proc.started_at,
        "started_by": proc.started_by,
        "last_heartbeat_at": proc.last_heartbeat_at,
        "stopped_at": proc.stopped_at,
        "stop_requested": proc.stop_requested,
        "heartbeat_age": heartbeat_age,
        "pid_alive": pid_alive,
        "controls_allowed": controls_allowed,
        "controls_message": controls_message,
    }


def start(user) -> tuple[bool, str]:
    if getattr(settings, "MANAGED_DEPLOYMENT", False):
        return False, "This deployment manages the bot automatically."

    with transaction.atomic():
        proc = BotProcess.objects.select_for_update().get_or_create(pk=1)[0]
        status = get_status()
        if status["state"] in {"running", "starting", "stopping"}:
            return False, "The bot is already running or starting."
        if status["state"] == "hung":
            return False, "The bot appears unresponsive. Force stop it before starting another run."

        logs_dir = Path(settings.BASE_DIR) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "daemon.log"
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(settings.BASE_DIR) / ".browsers")
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        if getattr(user, "pk", None):
            env["linkreach_STARTED_BY_USER_ID"] = str(user.pk)

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            with log_path.open("a", encoding="utf-8", errors="replace") as log:
                child = subprocess.Popen(
                    [sys.executable, "manage.py", "rundaemon"],
                    cwd=str(settings.BASE_DIR),
                    env=env,
                    stdout=log,
                    stderr=log,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                    close_fds=(os.name != "nt"),
                )
        except OSError as exc:
            proc.pid = None
            proc.stop_requested = False
            proc.save(update_fields=["pid", "stop_requested"])
            return False, f"Could not start the bot: {exc}"

        proc.pid = child.pid
        proc.started_at = timezone.now()
        proc.started_by = user if getattr(user, "is_authenticated", False) else None
        proc.last_heartbeat_at = None
        proc.stopped_at = None
        proc.stop_requested = False
        proc.save(update_fields=[
            "pid",
            "started_at",
            "started_by",
            "last_heartbeat_at",
            "stopped_at",
            "stop_requested",
        ])
    return True, "Bot start requested. A Chrome window may open on this computer."


def request_stop(user=None) -> tuple[bool, str]:
    proc = BotProcess.load()
    status = get_status()
    if status["state"] in {"not_running", "crashed"}:
        return False, "The bot is not currently running."
    if status["state"] == "hung":
        return False, "The bot is not responding. Use Force stop if you need to end it."
    proc.stop_requested = True
    proc.stopped_at = None
    proc.save(update_fields=["stop_requested", "stopped_at"])
    return True, "Stop requested. The bot will shut down cleanly at the next safe checkpoint."


def force_kill(user=None) -> tuple[bool, str]:
    proc = BotProcess.load()
    pid = proc.pid
    if not pid:
        return False, "No bot process is recorded."

    if is_pid_alive(pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], timeout=10, check=False)
            else:
                os.kill(int(pid), signal.SIGKILL)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"Could not force stop the bot: {exc}"

    proc.pid = None
    proc.last_heartbeat_at = None
    proc.stopped_at = timezone.now()
    proc.stop_requested = False
    proc.save(update_fields=["pid", "last_heartbeat_at", "stopped_at", "stop_requested"])
    return True, "Bot process was force stopped."


def write_heartbeat() -> None:
    BotProcess.objects.filter(pk=1).update(last_heartbeat_at=timezone.now())


def stop_requested() -> bool:
    return BotProcess.objects.filter(pk=1, stop_requested=True).exists()
