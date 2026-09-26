from unittest.mock import patch

import pytest

from linkreach.core.models import Campaign, SiteConfig
from linkreach.dashboard.forms import AISettingsForm, CampaignForm, LinkedInAccountForm
from linkreach.linkedin.models import LinkedInProfile
from tests.factories import DealFactory, UserFactory


@pytest.mark.django_db
def test_linkedin_form_requires_new_password_and_preserves_existing_password():
    fresh = LinkedInAccountForm()
    assert fresh.fields["linkedin_password"].required is True

    profile = LinkedInProfile.objects.create(
        user=UserFactory(),
        linkedin_username="owner@example.com",
        linkedin_password="saved-password",
    )
    form = LinkedInAccountForm(
        data={
            "linkedin_username": "owner@example.com",
            "linkedin_password": "",
            "connect_daily_limit": 10,
            "follow_up_daily_limit": 10,
            "legal_accepted": True,
        },
        instance=profile,
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["linkedin_password"] == "saved-password"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("saved_model", "saved_base", "provider", "model", "base"),
    [
        ("", "", "openai", "gpt-4o-mini", ""),
        ("openai:gpt-4.1", "", "openai", "gpt-4.1", ""),
        ("anthropic:claude-test", "", "anthropic", "claude-test", ""),
        ("openai_compatible:grok-test", "https://api.x.ai/v1", "grok", "grok-test", "https://api.x.ai/v1"),
        ("openai_compatible:MiniMax-M3", "https://api.minimax.io/v1", "custom", "MiniMax-M3", "https://api.minimax.io/v1"),
        ("claude-legacy", "", "anthropic", "claude-legacy", ""),
        ("unsupported:model", "", "openai", "model", ""),
    ],
)
def test_ai_settings_initial_provider_mapping(saved_model, saved_base, provider, model, base):
    cfg = SiteConfig.load()
    cfg.ai_model = saved_model
    cfg.llm_api_base = saved_base
    cfg.save(update_fields=["ai_model", "llm_api_base"])
    form = AISettingsForm(site_config=cfg)
    assert form.initial["llm_provider"] == provider
    assert form.initial["model_name"] == model
    assert form.initial["llm_api_base"] == base


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("provider", "model", "base", "expected_model", "expected_base"),
    [
        ("openai", "gpt-4.1-mini", "https://ignored.example/v1", "openai:gpt-4.1-mini", ""),
        ("anthropic", "claude-sonnet", "https://ignored.example/v1", "anthropic:claude-sonnet", ""),
        ("grok", "grok-4.6", "", "openai_compatible:grok-4.6", "https://api.x.ai/v1"),
        ("custom", "MiniMax-M3", "https://api.minimax.io/v1", "openai_compatible:MiniMax-M3", "https://api.minimax.io/v1"),
    ],
)
def test_ai_settings_validate_and_save_provider_formats(provider, model, base, expected_model, expected_base):
    cfg = SiteConfig.load()
    cfg.llm_api_key = "saved-key"
    cfg.save(update_fields=["llm_api_key"])
    form = AISettingsForm(
        data={
            "llm_provider": provider,
            "model_name": model,
            "llm_api_key": "",
            "llm_api_base": base,
        },
        site_config=cfg,
    )
    with patch("linkreach.dashboard.forms.build_llm_model") as build:
        assert form.is_valid(), form.errors
        saved = form.save()
    build.assert_called_once_with(expected_model, "saved-key", expected_base)
    assert saved.ai_model == expected_model
    assert saved.llm_api_base == expected_base
    assert saved.llm_api_key == "saved-key"


@pytest.mark.django_db
def test_ai_settings_reports_missing_key_model_and_provider_validation_error():
    cfg = SiteConfig.load()
    cfg.llm_api_key = ""
    cfg.save(update_fields=["llm_api_key"])
    missing = AISettingsForm(
        data={"llm_provider": "openai", "model_name": "", "llm_api_key": ""},
        site_config=cfg,
    )
    assert missing.is_valid() is False
    assert "model_name" in missing.errors

    invalid = AISettingsForm(
        data={"llm_provider": "openai", "model_name": "bad", "llm_api_key": "key"},
        site_config=cfg,
    )
    with patch("linkreach.dashboard.forms.build_llm_model", side_effect=ValueError("Unsupported model")):
        assert invalid.is_valid() is False
    assert "Unsupported model" in invalid.errors["model_name"][0]


@pytest.mark.django_db
def test_campaign_type_locks_after_leads_exist():
    campaign = Campaign.objects.create(name="Locked")
    DealFactory(campaign=campaign)
    form = CampaignForm(instance=campaign)
    assert form.fields["outreach_mode"].disabled is True
    assert "locked" in form.fields["outreach_mode"].help_text.lower()

    empty = CampaignForm(instance=Campaign.objects.create(name="Editable"))
    assert empty.fields["outreach_mode"].disabled is False
