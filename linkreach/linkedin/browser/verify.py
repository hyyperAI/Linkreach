# linkreach/linkedin/browser/verify.py
"""One-shot background LinkedIn login, triggered by the dashboard's
"Start verification" button.

The dashboard must never run Playwright inline in a request — login can hang
for minutes and a checkpoint can pause it for up to 30 minutes
(``CHECKPOINT_RESOLVE_TIMEOUT_S`` in ``linkedin_cli.conf``). So the request
only flips ``connection_status`` to ``verifying`` and hands off to a daemon
thread here, which drives the same ``start_browser_session`` the ``rundaemon``
worker uses and persists the outcome. The dashboard then polls
``connection_status`` over HTMX.

This is intentionally separate from the ``rundaemon`` task queue: that queue
only runs once a Task is claimed, so nothing there launches a first login on
demand. Running the real worker process at the same time as a manual
verification would race two browsers over the same account — the template
warns against that.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# Profile ids with a verification thread in flight — guards against a
# double-click launching two browsers for the same account.
_running: set[int] = set()
_lock = threading.Lock()


def verification_in_progress(profile_id: int) -> bool:
    with _lock:
        return profile_id in _running


def start_verification(profile_id: int) -> bool:
    """Launch a background verification attempt. False if one is already running."""
    with _lock:
        if profile_id in _running:
            return False
        _running.add(profile_id)
    threading.Thread(target=_run, args=(profile_id,), daemon=True).start()
    return True


def _run(profile_id: int) -> None:
    from linkreach.linkedin.browser.launch import start_browser_session
    from linkreach.linkedin.browser.session import AccountSession
    from linkreach.linkedin.models import LinkedInProfile

    session = None
    try:
        profile = LinkedInProfile.objects.get(pk=profile_id)
        session = AccountSession(profile)
        try:
            start_browser_session(session)
        except Exception:
            # start_browser_session already persisted a UI-safe status for
            # CheckpointChallengeError/AuthenticationError before re-raising.
            # Anything else (browser launch failure, network error) would
            # otherwise leave the profile stuck on "verifying" forever, since
            # an uncaught exception in a daemon thread has no caller to
            # report to — so it's caught here as a last resort.
            logger.exception("LinkedIn verification failed for profile %s", profile_id)
    finally:
        if session is not None:
            session.close()
        with _lock:
            _running.discard(profile_id)
