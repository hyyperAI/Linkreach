from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from linkreach.core import onboarding, onboarding_wizard
from linkreach.core.models import Campaign, SiteConfig
from linkreach.linkedin.models import LinkedInProfile


class StubQuestion(onboarding_wizard.Question):
    def __init__(self, *args, results=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.results = iter(results or [])

    def _prompt(self, default, *, answers=None):
        return next(self.results)


def test_wizard_validators_and_question_cleaning():
    assert onboarding_wizard._required(" value ") is True
    assert isinstance(onboarding_wizard._required(" "), str)
    assert onboarding_wizard._integer("12") is True
    assert isinstance(onboarding_wizard._integer("bad"), str)

    question = StubQuestion("name", "Name", results=["  Alice  "])
    assert question.ask("") == "Alice"
    optional = StubQuestion("note", "Note", required=False, results=[])
    optional._prompt = MagicMock(side_effect=EOFError)
    assert optional.ask("default") == ""


def test_wizard_back_cancel_and_completion(monkeypatch):
    monkeypatch.setattr(onboarding_wizard, "_clear", lambda: None)
    first = StubQuestion("first", "First", results=["one", "changed"])
    second = StubQuestion("second", "Second", results=[onboarding_wizard._BACK, "two"])
    assert onboarding_wizard.ask([first, second]) == {
        "first": "changed",
        "second": "two",
    }

    cancelled = StubQuestion("cancel", "Cancel", results=[None])
    assert onboarding_wizard.ask([cancelled]) is None


def test_confirm_integer_and_autocomplete_prompt_behaviors(monkeypatch):
    prompt = MagicMock()
    prompt.ask.side_effect = [False, True]
    monkeypatch.setattr(onboarding_wizard.questionary, "confirm", lambda *a, **k: prompt)
    monkeypatch.setattr(onboarding_wizard.questionary, "print", lambda *a, **k: None)
    required = onboarding_wizard.Confirm("legal", "Accept", required=True)
    assert required.ask(False) is True

    integer = onboarding_wizard.IntText("limit", "Limit", default=5)
    assert integer._clean("12") == 12
    assert integer._empty_value("bad") == 5

    text_prompt = MagicMock()
    text_prompt.ask.return_value = "custom"
    monkeypatch.setattr(onboarding_wizard.questionary, "text", lambda *a, **k: text_prompt)
    autocomplete = onboarding_wizard.Autocomplete(
        "model", "Model", resolver=lambda answers: [], default="",
    )
    assert autocomplete.ask("", answers={}) == "custom"

    auto_prompt = MagicMock()
    auto_prompt.ask.return_value = "gpt"
    monkeypatch.setattr(
        onboarding_wizard.questionary, "autocomplete", lambda *a, **k: auto_prompt,
    )
    autocomplete = onboarding_wizard.Autocomplete(
        "model", "Model", resolver=lambda answers: ["gpt"], default="",
    )
    assert autocomplete.ask("", answers={}) == "gpt"


def test_optional_multiline_can_be_skipped(monkeypatch):
    prompt = MagicMock()
    prompt.ask.return_value = False
    monkeypatch.setattr(onboarding_wizard.questionary, "confirm", lambda *a, **k: prompt)
    question = onboarding_wizard.MultilineText("seed", "Seeds", required=False)
    assert question.ask("") == ""


@pytest.mark.django_db
def test_missing_keys_tracks_campaign_account_and_provider_requirements():
    missing = onboarding.missing_keys()
    assert onboarding._CAMPAIGN_KEYS <= missing
    assert onboarding._ACCOUNT_KEYS <= missing
    assert {"llm_api_key", "ai_model"} <= missing

    campaign = Campaign.objects.create(name="Ready")
    from tests.factories import UserFactory

    user = UserFactory()
    campaign.users.add(user)
    LinkedInProfile.objects.create(
        user=user,
        linkedin_username="operator@example.com",
        linkedin_password="secret",
        active=True,
    )
    cfg = SiteConfig.load()
    cfg.llm_api_key = "key"
    cfg.ai_model = "openai_compatible:MiniMax-M3"
    cfg.llm_api_base = ""
    cfg.save()
    assert onboarding.missing_keys() == {"llm_api_base"}


def test_collect_from_wizard_handles_complete_cancel_and_answers(monkeypatch):
    monkeypatch.setattr(onboarding, "missing_keys", lambda: set())
    assert onboarding.collect_from_wizard() == onboarding.OnboardConfig()

    monkeypatch.setattr(onboarding, "missing_keys", lambda: set(onboarding._ALL_KEYS))
    monkeypatch.setattr("linkreach.core.onboarding_wizard.ask", lambda questions: None)
    with pytest.raises(SystemExit, match="cancelled"):
        onboarding.collect_from_wizard()

    answers = {
        "campaign_name": "Launch",
        "linkedin_email": "owner@example.com",
        "unknown": "ignored",
    }
    monkeypatch.setattr("linkreach.core.onboarding_wizard.ask", lambda questions: answers)
    monkeypatch.setattr(onboarding, "_verify_llm_answers", lambda values: None)
    config = onboarding.collect_from_wizard()
    assert config.campaign_name == "Launch"
    assert config.linkedin_email == "owner@example.com"


def test_verify_llm_answers_retries_and_handles_cancel(monkeypatch):
    answers = {"ai_model": "openai:gpt", "llm_api_key": "bad"}
    verify = MagicMock(side_effect=["invalid key", None])
    monkeypatch.setattr("questionary.print", lambda *a, **k: None)
    monkeypatch.setattr("linkreach.core.llm.verify_llm_credentials", verify)
    monkeypatch.setattr(
        "linkreach.core.onboarding_wizard.ask",
        lambda questions: {"ai_model": "openai:gpt", "llm_api_key": "good"},
    )
    onboarding._verify_llm_answers(answers)
    assert answers["llm_api_key"] == "good"

    monkeypatch.setattr("linkreach.core.llm.verify_llm_credentials", lambda *a: "bad")
    monkeypatch.setattr("linkreach.core.onboarding_wizard.ask", lambda questions: None)
    with pytest.raises(SystemExit, match="cancelled"):
        onboarding._verify_llm_answers(answers)

    onboarding._verify_llm_answers({"campaign_name": "No LLM fields"})


def test_read_default_file_handles_present_and_missing(tmp_path):
    path = tmp_path / "default.txt"
    assert onboarding._read_default_file(path) == ""
    path.write_text("  content  ", encoding="utf-8")
    assert onboarding._read_default_file(path) == "content"


@pytest.mark.django_db
def test_apply_creates_complete_onboarding_once(monkeypatch):
    seeds = MagicMock()
    monkeypatch.setattr(onboarding, "_create_seed_leads", seeds)
    config = onboarding.OnboardConfig(
        linkedin_email="first.last+sales@example.com",
        linkedin_password="linkedin-secret",
        campaign_name="CSV Outreach",
        product_description="Product context",
        campaign_objective="Book calls",
        booking_link="https://example.com/book",
        seed_urls="https://www.linkedin.com/in/alice/",
        llm_api_key="provider-key",
        ai_model="openai:gpt-4o-mini",
        legal_acceptance=True,
        connect_daily_limit=7,
        follow_up_daily_limit=9,
    )

    onboarding.apply(config)
    campaign = Campaign.objects.get(name="CSV Outreach")
    profile = LinkedInProfile.objects.get(linkedin_username=config.linkedin_email)
    assert campaign.users.filter(pk=profile.user_id).exists()
    assert profile.user.username == "first_last_sales"
    assert profile.legal_accepted is True
    assert profile.connect_daily_limit == 7
    assert profile.follow_up_daily_limit == 9
    assert SiteConfig.load().ai_model == "openai:gpt-4o-mini"
    seeds.assert_called_once_with(campaign, config.seed_urls)

    onboarding.apply(config)
    assert Campaign.objects.count() == 1
    assert LinkedInProfile.objects.count() == 1


@pytest.mark.django_db
def test_create_seed_leads_ignores_empty_and_records_parsed_ids(monkeypatch):
    campaign = Campaign.objects.create(name="Seeds")
    create = MagicMock(return_value=2)
    monkeypatch.setattr(
        "linkreach.linkedin.setup.seeds.parse_seed_urls",
        lambda value: ["alice", "bob"],
    )
    monkeypatch.setattr("linkreach.linkedin.setup.seeds.create_seed_leads", create)
    onboarding._create_seed_leads(campaign, "")
    create.assert_not_called()
    onboarding._create_seed_leads(campaign, "alice\nbob")
    create.assert_called_once_with(campaign, ["alice", "bob"])
