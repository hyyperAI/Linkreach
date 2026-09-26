# linkreach/linkedin/browser/launch.py
"""Persist + orchestrate the daemon's LinkedIn browser session.

Cookie persistence (to the Django DB) and the launch/login orchestration are
linkreach concerns, so they live here. The reusable *mechanics* — launching a
stealthed browser, driving the login form, clearing checkpoints — stay in the
Django-free ``linkedin_cli.browser`` library and are called from here.
"""
from __future__ import annotations

import logging

from django.utils import timezone
from termcolor import colored

from linkedin_cli.auth import authenticate
from linkedin_cli.browser.login import dismiss_comply_gate, launch_browser
from linkedin_cli.browser.nav import goto_page
from linkedin_cli.exceptions import AuthenticationError, CheckpointChallengeError

logger = logging.getLogger(__name__)

LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"


def _save_cookies(session):
    """Persist Playwright storage state (cookies) to the DB."""
    state = session.context.storage_state()
    session.linkedin_profile.cookie_data = state
    session.linkedin_profile.save(update_fields=["cookie_data"])


def start_browser_session(session):
    """Launch/recover the browser and drive it to the feed.

    On the way out, always leaves ``linkedin_profile.connection_status``
    reflecting what actually happened — connected, checkpoint/2FA pending, or
    failed — since this is the one chokepoint every login path (the dashboard's
    manual verification, ``AccountSession.reauthenticate``, and the daemon's
    lazy ``ensure_browser``) goes through.
    """
    from linkreach.linkedin.models import LinkedInProfile

    logger.debug("Configuring browser for %s", session)
    lp = session.linkedin_profile

    lp.refresh_from_db(fields=["cookie_data"])
    storage_state = lp.cookie_data or None
    if storage_state:
        logger.info("Loading saved session for %s", session)

    try:
        session.page, session.context, session.browser, session.playwright = launch_browser(storage_state=storage_state)

        if not storage_state:
            authenticate(session, username=lp.linkedin_username, password=lp.linkedin_password)
            _save_cookies(session)
            logger.info(colored("Login successful – session saved", "green", attrs=["bold"]))
        else:
            session.page.goto(LINKEDIN_FEED_URL)
            dismiss_comply_gate(session.page)
            goto_page(
                session,
                action=lambda: None,
                expected_url_pattern="/feed",
                error_message="Saved session invalid",
            )

        # "domcontentloaded" — "load" waits for every subresource (analytics
        # beacons, lazy media) and on LinkedIn that event may never fire,
        # hanging the daemon for the duration of the browser timeout.
        session.page.wait_for_load_state("domcontentloaded")
    except CheckpointChallengeError as exc:
        lp.connection_status = LinkedInProfile.ConnectionStatus.CHECKPOINT_REQUIRED
        lp.checkpoint_url = exc.url[:1000]
        lp.last_error_code = "checkpoint"
        lp.last_error_message = "LinkedIn asked for extra verification in the browser window."
        lp.save(update_fields=["connection_status", "checkpoint_url", "last_error_code", "last_error_message"])
        raise
    except AuthenticationError as exc:
        lp.connection_status = LinkedInProfile.ConnectionStatus.ERROR
        lp.last_error_code = "authentication_failed"
        lp.last_error_message = str(exc) or "LinkedIn rejected the saved credentials."
        lp.save(update_fields=["connection_status", "last_error_code", "last_error_message"])
        raise
    except RuntimeError as exc:
        # goto_page's "Saved session invalid" — the stored cookie no longer
        # gets the browser to the feed, distinct from a fresh-login failure.
        if storage_state:
            lp.connection_status = LinkedInProfile.ConnectionStatus.SESSION_EXPIRED
            lp.last_error_code = "session_expired"
            lp.last_error_message = str(exc) or "The saved LinkedIn session is no longer valid."
            lp.save(update_fields=["connection_status", "last_error_code", "last_error_message"])
            raise
        lp.connection_status = LinkedInProfile.ConnectionStatus.ERROR
        lp.last_error_code = "browser_error"
        lp.last_error_message = str(exc)[:2000] or "The browser could not complete login."
        lp.save(update_fields=["connection_status", "last_error_code", "last_error_message"])
        raise
    except Exception as exc:
        lp.connection_status = LinkedInProfile.ConnectionStatus.ERROR
        lp.last_error_code = "browser_error"
        lp.last_error_message = str(exc)[:2000] or "The browser could not complete login."
        lp.save(update_fields=["connection_status", "last_error_code", "last_error_message"])
        raise
    else:
        lp.connection_status = LinkedInProfile.ConnectionStatus.CONNECTED
        lp.last_verified_at = timezone.now()
        lp.checkpoint_url = ""
        lp.last_error_code = ""
        lp.last_error_message = ""
        lp.save(update_fields=[
            "connection_status", "last_verified_at", "checkpoint_url",
            "last_error_code", "last_error_message",
        ])
        logger.info(colored("Browser ready", "green", attrs=["bold"]))
