# tests/browser/test_launch_status.py
"""start_browser_session must persist a UI-safe connection_status for every
outcome, without ever touching a real browser or linkedin.com. Each login
path (launch_browser / authenticate / goto_page) is mocked at the boundary
``linkreach.linkedin.browser.launch`` imports it through."""
from unittest.mock import MagicMock, patch

import pytest
from linkedin_cli.exceptions import AuthenticationError, CheckpointChallengeError

from linkreach.linkedin.browser.launch import start_browser_session
from linkreach.linkedin.browser.session import AccountSession
from linkreach.linkedin.models import LinkedInProfile
from tests.factories import UserFactory


@pytest.fixture
def session(db):
    user = UserFactory(username="verifyuser")
    profile = LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="pw", legal_accepted=True,
    )
    return AccountSession(profile)


def _mock_page():
    page = MagicMock()
    page.wait_for_load_state.return_value = None
    return page


def test_fresh_login_success_marks_connected(session):
    context = MagicMock()
    context.storage_state.return_value = {"cookies": []}
    with patch("linkreach.linkedin.browser.launch.launch_browser", return_value=(_mock_page(), context, MagicMock(), MagicMock())), \
         patch("linkreach.linkedin.browser.launch.authenticate") as mock_auth:
        mock_auth.return_value = None
        start_browser_session(session)

    session.linkedin_profile.refresh_from_db()
    assert session.linkedin_profile.connection_status == LinkedInProfile.ConnectionStatus.CONNECTED
    assert session.linkedin_profile.last_verified_at is not None
    assert session.linkedin_profile.last_error_message == ""


def test_checkpoint_challenge_marks_checkpoint_required(session):
    with patch("linkreach.linkedin.browser.launch.launch_browser", return_value=(_mock_page(), MagicMock(), MagicMock(), MagicMock())), \
         patch("linkreach.linkedin.browser.launch.authenticate", side_effect=CheckpointChallengeError("https://www.linkedin.com/checkpoint/challenge/abc")):
        with pytest.raises(CheckpointChallengeError):
            start_browser_session(session)

    session.linkedin_profile.refresh_from_db()
    assert session.linkedin_profile.connection_status == LinkedInProfile.ConnectionStatus.CHECKPOINT_REQUIRED
    assert session.linkedin_profile.checkpoint_url == "https://www.linkedin.com/checkpoint/challenge/abc"


def test_rejected_credentials_marks_error(session):
    with patch("linkreach.linkedin.browser.launch.launch_browser", return_value=(_mock_page(), MagicMock(), MagicMock(), MagicMock())), \
         patch("linkreach.linkedin.browser.launch.authenticate", side_effect=AuthenticationError("Rejected credentials")):
        with pytest.raises(AuthenticationError):
            start_browser_session(session)

    session.linkedin_profile.refresh_from_db()
    assert session.linkedin_profile.connection_status == LinkedInProfile.ConnectionStatus.ERROR
    assert session.linkedin_profile.last_error_code == "authentication_failed"
    assert "pw" not in session.linkedin_profile.last_error_message


def test_expired_saved_session_marks_session_expired(session):
    session.linkedin_profile.cookie_data = {"cookies": [{"name": "li_at", "value": "x", "expires": -1}]}
    session.linkedin_profile.save(update_fields=["cookie_data"])

    with patch("linkreach.linkedin.browser.launch.launch_browser", return_value=(_mock_page(), MagicMock(), MagicMock(), MagicMock())), \
         patch("linkreach.linkedin.browser.launch.dismiss_comply_gate"), \
         patch("linkreach.linkedin.browser.launch.goto_page", side_effect=RuntimeError("Saved session invalid")):
        with pytest.raises(RuntimeError):
            start_browser_session(session)

    session.linkedin_profile.refresh_from_db()
    assert session.linkedin_profile.connection_status == LinkedInProfile.ConnectionStatus.SESSION_EXPIRED


def test_browser_launch_failure_marks_error(session):
    with patch("linkreach.linkedin.browser.launch.launch_browser", side_effect=RuntimeError("could not reach linkedin.com")):
        with pytest.raises(RuntimeError):
            start_browser_session(session)

    session.linkedin_profile.refresh_from_db()
    assert session.linkedin_profile.connection_status == LinkedInProfile.ConnectionStatus.ERROR
    assert session.linkedin_profile.last_error_code == "browser_error"
