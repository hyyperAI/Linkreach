import pytest
from django.db import connection

from linkreach.core.models import SiteConfig
from linkreach.emails.models import Mailbox
from linkreach.linkedin.models import LinkedInProfile
from tests.factories import UserFactory


def _raw(table: str, column: str, pk: int):
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT "{column}" FROM "{table}" WHERE "id" = %s', [pk])
        return cursor.fetchone()[0]


@pytest.mark.django_db
def test_site_api_keys_are_encrypted_at_rest():
    config = SiteConfig.load()
    config.llm_api_key = "sk-sensitive-value"
    config.bettercontact_api_key = "better-sensitive-value"
    config.contacts_api_token = "contact-sensitive-value"
    config.save()

    assert _raw("core_siteconfig", "llm_api_key", config.pk).startswith("enc:v1:")
    assert "sk-sensitive-value" not in _raw("core_siteconfig", "llm_api_key", config.pk)
    config.refresh_from_db()
    assert config.llm_api_key == "sk-sensitive-value"
    assert config.bettercontact_api_key == "better-sensitive-value"
    assert config.contacts_api_token == "contact-sensitive-value"


@pytest.mark.django_db
def test_linkedin_password_and_cookies_are_encrypted_at_rest():
    user = UserFactory()
    profile = LinkedInProfile.objects.create(
        user=user,
        linkedin_username="sender@example.com",
        linkedin_password="linkedin-secret",
        cookie_data={"cookies": [{"name": "li_at", "value": "cookie-secret"}]},
    )

    raw_password = _raw("linkedin_linkedinprofile", "linkedin_password", profile.pk)
    raw_cookie = _raw("linkedin_linkedinprofile", "cookie_data", profile.pk)
    assert raw_password.startswith("enc:v1:")
    assert "linkedin-secret" not in raw_password
    assert raw_cookie.startswith("enc:v1:")
    assert "cookie-secret" not in raw_cookie
    profile.refresh_from_db()
    assert profile.linkedin_password == "linkedin-secret"
    assert profile.cookie_data["cookies"][0]["value"] == "cookie-secret"


@pytest.mark.django_db
def test_mailbox_password_is_encrypted_at_rest():
    mailbox = Mailbox.objects.create(
        username="sender@example.com",
        password="smtp-secret",
        from_address="sender@example.com",
    )

    raw_password = _raw("emails_mailbox", "password", mailbox.pk)
    assert raw_password.startswith("enc:v1:")
    assert "smtp-secret" not in raw_password
    mailbox.refresh_from_db()
    assert mailbox.password == "smtp-secret"
