# tests/dashboard/test_linkedin_account.py
from unittest.mock import patch

import pytest
from django.urls import reverse

from linkreach.linkedin.models import LinkedInProfile
from tests.factories import UserFactory

ACCOUNT_URL = reverse("dashboard:linkedin_account")
SAVE_URL = reverse("dashboard:linkedin_account_save")
STATUS_URL = reverse("dashboard:linkedin_account_status")


def _action_url(action):
    return reverse("dashboard:linkedin_account_action", args=[action])


@pytest.fixture
def user(db):
    return UserFactory(username="operator")


@pytest.fixture
def logged_in_client(client, user):
    client.force_login(user)
    return client


def test_page_requires_login(client):
    response = client.get(ACCOUNT_URL)
    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")


def test_page_loads_with_no_profile(logged_in_client):
    response = logged_in_client.get(ACCOUNT_URL)
    assert response.status_code == 200
    assert b"Connect your LinkedIn account" in response.content


def test_empty_form_does_not_create_profile(logged_in_client, user):
    response = logged_in_client.post(SAVE_URL, data={})
    assert response.status_code == 302
    assert not LinkedInProfile.objects.filter(user=user).exists()


def test_save_creates_profile(logged_in_client, user):
    response = logged_in_client.post(SAVE_URL, data={
        "linkedin_username": "me@example.com",
        "linkedin_password": "s3cret",
        "connect_daily_limit": 20,
        "follow_up_daily_limit": 25,
        "legal_accepted": "on",
    })
    assert response.status_code == 302
    profile = LinkedInProfile.objects.get(user=user)
    assert profile.linkedin_username == "me@example.com"
    assert profile.linkedin_password == "s3cret"
    assert profile.connection_status == LinkedInProfile.ConnectionStatus.CREDENTIALS_SAVED


def test_save_without_legal_acceptance_marks_not_connected(logged_in_client, user):
    logged_in_client.post(SAVE_URL, data={
        "linkedin_username": "me@example.com",
        "linkedin_password": "s3cret",
        "connect_daily_limit": 20,
        "follow_up_daily_limit": 25,
    })
    profile = LinkedInProfile.objects.get(user=user)
    assert profile.connection_status == LinkedInProfile.ConnectionStatus.NOT_CONNECTED


def test_update_preserves_password_when_blank(logged_in_client, user):
    profile = LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="original",
        legal_accepted=True, connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
    )
    logged_in_client.post(SAVE_URL, data={
        "linkedin_username": "me@example.com",
        "linkedin_password": "",
        "connect_daily_limit": 15,
        "follow_up_daily_limit": 10,
        "legal_accepted": "on",
    })
    profile.refresh_from_db()
    assert profile.linkedin_password == "original"
    assert profile.connect_daily_limit == 15
    # Credentials unchanged → status untouched, still connected.
    assert profile.connection_status == LinkedInProfile.ConnectionStatus.CONNECTED


def test_update_with_new_password_resets_status_and_clears_cookies(logged_in_client, user):
    profile = LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="original",
        legal_accepted=True, connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
        cookie_data={"cookies": []},
    )
    logged_in_client.post(SAVE_URL, data={
        "linkedin_username": "me@example.com",
        "linkedin_password": "new-password",
        "connect_daily_limit": 15,
        "follow_up_daily_limit": 10,
        "legal_accepted": "on",
    })
    profile.refresh_from_db()
    assert profile.linkedin_password == "new-password"
    assert profile.cookie_data is None
    assert profile.connection_status == LinkedInProfile.ConnectionStatus.CREDENTIALS_SAVED


def test_verify_action_requires_credentials(logged_in_client, user):
    LinkedInProfile.objects.create(user=user, linkedin_username="", linkedin_password="", legal_accepted=True)
    with patch("linkreach.linkedin.browser.verify.start_verification") as mock_start:
        logged_in_client.post(_action_url("verify"))
    mock_start.assert_not_called()


def test_verify_action_requires_legal_acceptance(logged_in_client, user):
    LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="pw", legal_accepted=False,
    )
    with patch("linkreach.linkedin.browser.verify.start_verification") as mock_start:
        logged_in_client.post(_action_url("verify"))
    mock_start.assert_not_called()


def test_verify_action_starts_background_verification(logged_in_client, user):
    profile = LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="pw", legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.CREDENTIALS_SAVED,
    )
    with patch("linkreach.linkedin.browser.verify.start_verification") as mock_start:
        response = logged_in_client.post(_action_url("verify"))
    assert response.status_code == 302
    mock_start.assert_called_once_with(profile.pk)
    profile.refresh_from_db()
    assert profile.connection_status == LinkedInProfile.ConnectionStatus.VERIFYING
    assert profile.verification_requested_at is not None


def test_reconnect_clears_cookies_and_starts_verification(logged_in_client, user):
    profile = LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="pw", legal_accepted=True,
        connection_status=LinkedInProfile.ConnectionStatus.SESSION_EXPIRED,
        cookie_data={"cookies": []},
    )
    with patch("linkreach.linkedin.browser.verify.start_verification") as mock_start:
        logged_in_client.post(_action_url("reconnect"))
    mock_start.assert_called_once_with(profile.pk)
    profile.refresh_from_db()
    assert profile.cookie_data is None
    assert profile.connection_status == LinkedInProfile.ConnectionStatus.VERIFYING


def test_pause_and_resume(logged_in_client, user):
    LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="pw",
        legal_accepted=True, active=True,
    )
    logged_in_client.post(_action_url("pause"))
    profile = LinkedInProfile.objects.get(user=user)
    assert profile.active is False

    logged_in_client.post(_action_url("resume"))
    profile.refresh_from_db()
    assert profile.active is True


def test_disconnect_clears_session_and_pauses(logged_in_client, user):
    LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="pw",
        legal_accepted=True, active=True,
        connection_status=LinkedInProfile.ConnectionStatus.CONNECTED,
        cookie_data={"cookies": []},
    )
    logged_in_client.post(_action_url("disconnect"))
    profile = LinkedInProfile.objects.get(user=user)
    assert profile.active is False
    assert profile.cookie_data is None
    assert profile.connection_status == LinkedInProfile.ConnectionStatus.NOT_CONNECTED


@pytest.mark.parametrize("status,expected_text", [
    (LinkedInProfile.ConnectionStatus.CREDENTIALS_SAVED, b"Ready to verify"),
    (LinkedInProfile.ConnectionStatus.VERIFYING, b"a browser window is opening"),
    (LinkedInProfile.ConnectionStatus.CHECKPOINT_REQUIRED, b"Verification required"),
    (LinkedInProfile.ConnectionStatus.SESSION_EXPIRED, b"Session expired"),
    (LinkedInProfile.ConnectionStatus.ERROR, b"Connection failed"),
    (LinkedInProfile.ConnectionStatus.CONNECTED, b"Last verified"),
])
def test_status_panel_renders_each_state(logged_in_client, user, status, expected_text):
    from django.utils import timezone

    LinkedInProfile.objects.create(
        user=user, linkedin_username="me@example.com", linkedin_password="pw",
        legal_accepted=True, connection_status=status,
        last_verified_at=timezone.now() if status == LinkedInProfile.ConnectionStatus.CONNECTED else None,
    )
    response = logged_in_client.get(STATUS_URL)
    assert response.status_code == 200
    assert expected_text in response.content


def test_migration_0013_applied(db):
    from django.db import connection

    with connection.cursor() as cursor:
        columns = {c.name for c in connection.introspection.get_table_description(cursor, "linkedin_linkedinprofile")}
    assert "connection_status" in columns
    assert "verification_requested_at" in columns
