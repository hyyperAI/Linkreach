import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError

from linkreach.core.management.commands.rundaemon import Command
from linkreach.core.models import BotProcess, Campaign, SiteConfig
from linkreach.linkedin.models import LinkedInProfile
from tests.factories import UserFactory


@pytest.mark.django_db
def test_handle_runs_composition_flow_and_always_closes_session():
    command = Command()
    session = SimpleNamespace(close=MagicMock())
    with (
        patch.object(command, "_configure_logging") as configure,
        patch.object(command, "_ensure_db") as ensure_db,
        patch.object(command, "_apply_runtime_patches") as patches,
        patch.object(command, "_register_process") as register,
        patch.object(command, "_ensure_onboarded") as onboard,
        patch.object(command, "_nudge_email_setup") as nudge,
        patch.object(command, "_create_session", return_value=session),
        patch.object(command, "_ensure_newsletter") as newsletter,
        patch("linkreach.core.daemon.run_daemon") as run,
        patch.object(command, "_clear_process") as clear,
    ):
        command.handle(verbosity=2)
    configure.assert_called_once_with(verbose=True)
    ensure_db.assert_called_once()
    patches.assert_called_once()
    register.assert_called_once()
    onboard.assert_called_once()
    nudge.assert_called_once()
    newsletter.assert_called_once_with(session)
    run.assert_called_once_with(session)
    session.close.assert_called_once()
    clear.assert_called_once()


def test_configure_db_runtime_patch_and_email_nudge_steps():
    command = Command()
    with (
        patch("linkreach.core.logging.configure_logging") as configure,
        patch("linkreach.core.logging.print_banner") as banner,
    ):
        command._configure_logging(verbose=True)
    configure.assert_called_once_with(level=logging.DEBUG)
    banner.assert_called_once()

    with (
        patch("linkreach.core.management.commands.rundaemon.call_command") as call,
        patch("linkreach.core.management.setup_crm.setup_crm") as setup,
    ):
        command._ensure_db()
    call.assert_called_once_with("migrate", "--no-input")
    setup.assert_called_once()

    with patch(
        "linkreach.linkedin.browser.runtime_patches.apply_linkedin_cli_runtime_patches"
    ) as apply_patches:
        command._apply_runtime_patches()
    apply_patches.assert_called_once()

    with patch("linkreach.emails.nudge.prompt_email_setup") as prompt:
        command._nudge_email_setup()
    prompt.assert_called_once()


@pytest.mark.django_db
def test_register_and_clear_process_preserve_other_process_pid(monkeypatch):
    command = Command()
    user = UserFactory()
    monkeypatch.setenv("linkreach_STARTED_BY_USER_ID", str(user.pk))
    monkeypatch.setattr("linkreach.core.management.commands.rundaemon.os.getpid", lambda: 4321)
    command._register_process()
    proc = BotProcess.load()
    assert proc.pid == 4321
    assert proc.started_by == user
    assert proc.stop_requested is False

    command._clear_process()
    proc.refresh_from_db()
    assert proc.pid is None
    assert proc.stopped_at is not None

    proc.pid = 9999
    proc.save(update_fields=["pid"])
    command._clear_process()
    proc.refresh_from_db()
    assert proc.pid == 9999


@pytest.mark.django_db
def test_ensure_onboarded_complete_tty_and_headless(monkeypatch):
    command = Command()
    monkeypatch.setattr("linkreach.core.onboarding.missing_keys", lambda: set())
    command._ensure_onboarded()

    monkeypatch.setattr("linkreach.core.onboarding.missing_keys", lambda: {"ai_model"})
    monkeypatch.setattr(
        "linkreach.core.onboarding.collect_from_wizard", lambda: SimpleNamespace(),
    )
    apply = MagicMock()
    monkeypatch.setattr("linkreach.core.onboarding.apply", apply)
    monkeypatch.setattr(
        "linkreach.core.management.commands.rundaemon.sys.stdin.isatty", lambda: True,
    )
    command._ensure_onboarded()
    apply.assert_called_once()

    monkeypatch.setattr(
        "linkreach.core.management.commands.rundaemon.sys.stdin.isatty", lambda: False,
    )
    with pytest.raises(SystemExit) as exc:
        command._ensure_onboarded()
    assert exc.value.code == 1


@pytest.mark.django_db
def test_create_session_validates_key_profile_and_campaign(monkeypatch):
    command = Command()
    cfg = SiteConfig.load()
    cfg.llm_api_key = ""
    cfg.save(update_fields=["llm_api_key"])
    with pytest.raises(SystemExit):
        command._create_session()

    cfg.llm_api_key = "key"
    cfg.save(update_fields=["llm_api_key"])
    monkeypatch.setattr(
        "linkreach.linkedin.browser.registry.get_first_active_profile", lambda: None,
    )
    with pytest.raises(SystemExit):
        command._create_session()

    profile = SimpleNamespace()
    session = SimpleNamespace(campaigns=[], campaign=None)
    monkeypatch.setattr(
        "linkreach.linkedin.browser.registry.get_first_active_profile", lambda: profile,
    )
    monkeypatch.setattr(
        "linkreach.linkedin.browser.registry.get_or_create_session", lambda value: session,
    )
    with pytest.raises(SystemExit):
        command._create_session()

    freemium = SimpleNamespace(is_freemium=True)
    regular = SimpleNamespace(is_freemium=False)
    session.campaigns = [freemium, regular]
    assert command._create_session() is session
    assert session.campaign is regular


@pytest.mark.django_db
def test_newsletter_skips_processed_and_saves_completed(monkeypatch):
    command = Command()
    user = UserFactory()
    profile = LinkedInProfile.objects.create(
        user=user,
        linkedin_username="owner@example.com",
        linkedin_password="secret",
        newsletter_processed=True,
    )
    session = SimpleNamespace(linkedin_profile=profile)
    command._ensure_newsletter(session)

    profile.newsletter_processed = False
    profile.save(update_fields=["newsletter_processed"])
    session.self_profile = {"country_code": "us", "public_identifier": "owner"}
    with (
        patch("linkreach.linkedin.setup.geo.apply_gdpr_newsletter_override") as newsletter,
        patch("linkreach.linkedin.setup.geo.apply_gdpr_contribution_override") as contribution,
        patch("linkreach.linkedin.api.newsletter.ensure_newsletter_subscription") as ensure,
    ):
        command._ensure_newsletter(session)
    newsletter.assert_called_once_with(session, "us")
    contribution.assert_called_once_with(session, "us")
    assert ensure.call_args.kwargs["linkedin_url"].endswith("/in/owner/")
    profile.refresh_from_db()
    assert profile.newsletter_processed is True
