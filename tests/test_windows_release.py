import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_release_settings_pass_deployment_check():
    env = os.environ.copy()
    env.update({
        "linkreach_LOCAL_RELEASE": "1",
        "linkreach_DEBUG": "0",
        "DJANGO_SECRET_KEY": "release-test-" + "a" * 64,
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
    })
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_windows_launchers_are_location_independent_and_release_safe():
    for filename in ("Start-Dashboard.bat", "Start-Bot.bat"):
        text = (ROOT / filename).read_text(encoding="utf-8")
        assert 'cd /d "%~dp0"' in text
        assert "call .venv\\Scripts\\activate.bat" not in text
        assert "linkreach_LOCAL_RELEASE=1" in text
        assert "DJANGO_SECRET_KEY" in text
        assert '"%PYTHON_EXE%" manage.py' in text
