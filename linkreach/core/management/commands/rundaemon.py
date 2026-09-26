import logging
import os
import sys

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from linkreach.core.models import BotProcess

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the linkreach daemon (onboard, validate, start task queue)."

    def handle(self, *args, **options):
        self._configure_logging(verbose=options["verbosity"] >= 2)
        self._ensure_db()
        self._apply_runtime_patches()
        self._register_process()
        session = None
        try:
            self._ensure_onboarded()
            self._nudge_email_setup()
            session = self._create_session()
            self._ensure_newsletter(session)

            from linkreach.core.daemon import run_daemon
            run_daemon(session)
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    logger.exception("Failed to close LinkedIn session during daemon shutdown")
            self._clear_process()

    # -- Steps ---------------------------------------------------------------

    def _configure_logging(self, verbose: bool = False):
        from linkreach.core.logging import configure_logging, print_banner

        level = logging.DEBUG if verbose else logging.INFO
        configure_logging(level=level)
        print_banner()

    def _ensure_db(self):
        call_command("migrate", "--no-input")

        from linkreach.core.management.setup_crm import setup_crm
        setup_crm()

    def _apply_runtime_patches(self):
        from linkreach.linkedin.browser.runtime_patches import apply_linkedin_cli_runtime_patches

        apply_linkedin_cli_runtime_patches()

    def _register_process(self):
        started_by = None
        user_id = os.environ.get("linkreach_STARTED_BY_USER_ID")
        if user_id:
            started_by = User.objects.filter(pk=user_id).first()
        proc = BotProcess.load()
        proc.pid = os.getpid()
        proc.started_at = timezone.now()
        proc.started_by = started_by
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

    def _clear_process(self):
        proc = BotProcess.load()
        if proc.pid == os.getpid():
            proc.pid = None
        proc.last_heartbeat_at = None
        proc.stopped_at = timezone.now()
        proc.stop_requested = False
        proc.save(update_fields=["pid", "last_heartbeat_at", "stopped_at", "stop_requested"])

    def _ensure_onboarded(self):
        from linkreach.core.onboarding import apply, collect_from_wizard, missing_keys

        if not missing_keys():
            return

        if sys.stdin.isatty():
            apply(collect_from_wizard())
        else:
            missing = missing_keys()
            self.stderr.write(
                f"Onboarding incomplete and no TTY available.\n"
                f"Missing: {', '.join(sorted(missing))}\n"
                f"Run with an interactive terminal to complete onboarding."
            )
            sys.exit(1)

    def _nudge_email_setup(self):
        """Prompt (TTY) or log (headless) the next email-setup step. Deferrable —
        never blocks the LinkedIn discovery leg."""
        from linkreach.emails.nudge import prompt_email_setup
        prompt_email_setup()

    def _create_session(self):
        from linkreach.linkedin.browser.registry import get_first_active_profile, get_or_create_session
        from linkreach.core.models import SiteConfig

        if not SiteConfig.load().llm_api_key:
            logger.error("LLM_API_KEY is required. Set it in Site Configuration (Django Admin).")
            sys.exit(1)

        profile = get_first_active_profile()
        if profile is None:
            logger.error("No active LinkedIn profiles found.")
            sys.exit(1)

        session = get_or_create_session(profile)

        if not session.campaigns:
            logger.error("No campaigns found for this user.")
            sys.exit(1)
        campaign = next(
            (c for c in session.campaigns if not c.is_freemium), None,
        ) or session.campaigns[0]
        session.campaign = campaign

        return session

    def _ensure_newsletter(self, session):
        if session.linkedin_profile.newsletter_processed:
            return

        from linkreach.linkedin.api.newsletter import ensure_newsletter_subscription
        from linkreach.linkedin.setup.geo import (
            apply_gdpr_contribution_override,
            apply_gdpr_newsletter_override,
        )
        from linkedin_cli.url_utils import public_id_to_url

        profile = session.self_profile
        country_code = profile.get("country_code")
        apply_gdpr_newsletter_override(session, country_code)
        apply_gdpr_contribution_override(session, country_code)
        linkedin_url = public_id_to_url(profile["public_identifier"])
        ensure_newsletter_subscription(session, linkedin_url=linkedin_url)
        session.linkedin_profile.newsletter_processed = True
        session.linkedin_profile.save(update_fields=["newsletter_processed"])
