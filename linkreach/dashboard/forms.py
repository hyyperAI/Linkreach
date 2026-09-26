from django import forms

from linkreach.core.llm import build_llm_model
from linkreach.core.models import Campaign, SiteConfig
from linkreach.linkedin.models import LinkedInProfile

class LinkedInAccountForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["linkedin_password"].required = self.instance is None or not self.instance.pk

    def clean_linkedin_password(self):
        value = self.cleaned_data.get("linkedin_password")
        if not value and self.instance and self.instance.pk:
            return self.instance.linkedin_password
        return value

    class Meta:
        model = LinkedInProfile
        fields = ["linkedin_username", "linkedin_password", "connect_daily_limit", "follow_up_daily_limit", "legal_accepted"]
        labels = {"linkedin_username": "LinkedIn email or username", "linkedin_password": "LinkedIn password", "connect_daily_limit": "Daily connection requests", "follow_up_daily_limit": "Daily follow-up messages", "legal_accepted": "I understand and accept LinkedFlow’s safety and legal guidelines"}
        widgets = {"linkedin_username": forms.TextInput(attrs={"autocomplete": "username", "placeholder": "you@example.com"}), "linkedin_password": forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "Enter a new password to update it"}), "connect_daily_limit": forms.NumberInput(attrs={"min": 0, "max": 100}), "follow_up_daily_limit": forms.NumberInput(attrs={"min": 0, "max": 100}), "legal_accepted": forms.CheckboxInput()}


class AISettingsForm(forms.Form):
    PROVIDER_OPENAI = "openai"
    PROVIDER_ANTHROPIC = "anthropic"
    PROVIDER_GROK = "grok"
    PROVIDER_CUSTOM = "custom"

    PROVIDER_CHOICES = (
        (PROVIDER_OPENAI, "OpenAI"),
        (PROVIDER_ANTHROPIC, "Claude"),
        (PROVIDER_GROK, "Grok / xAI"),
        (PROVIDER_CUSTOM, "OpenAI Compatible / MiniMax"),
    )
    DEFAULT_MODELS = {
        PROVIDER_OPENAI: "gpt-4o-mini",
        PROVIDER_ANTHROPIC: "claude-sonnet-4-5-20250929",
        PROVIDER_GROK: "grok-4.6",
        PROVIDER_CUSTOM: "MiniMax-M3",
    }
    DEFAULT_BASE_URLS = {
        PROVIDER_OPENAI: "",
        PROVIDER_ANTHROPIC: "",
        PROVIDER_GROK: "https://api.x.ai/v1",
        PROVIDER_CUSTOM: "https://api.minimax.io/v1",
    }
    PROVIDER_PREFIXES = {
        PROVIDER_OPENAI: "openai",
        PROVIDER_ANTHROPIC: "anthropic",
        PROVIDER_GROK: "openai_compatible",
        PROVIDER_CUSTOM: "openai_compatible",
    }

    llm_provider = forms.ChoiceField(
        label="Framework / provider",
        choices=PROVIDER_CHOICES,
        help_text="Choose the AI provider framework this key belongs to.",
        widget=forms.Select(attrs={
            "autocomplete": "off",
        }),
    )
    model_name = forms.CharField(
        label="Model name",
        help_text="This is saved with the correct provider prefix automatically.",
        widget=forms.TextInput(attrs={
            "placeholder": DEFAULT_MODELS[PROVIDER_OPENAI],
            "autocomplete": "off",
        }),
    )
    llm_api_key = forms.CharField(
        label="API key",
        required=False,
        help_text="Leave blank to keep the current saved key.",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Paste a new API key to replace the saved key",
            "autocomplete": "new-password",
        }),
    )
    llm_api_base = forms.URLField(
        label="API base URL",
        required=False,
        help_text="Required for Grok, MiniMax, and other OpenAI-compatible APIs.",
        widget=forms.URLInput(attrs={
            "placeholder": DEFAULT_BASE_URLS[PROVIDER_CUSTOM],
            "autocomplete": "off",
        }),
    )

    def __init__(self, *args, site_config: SiteConfig | None = None, **kwargs):
        self.site_config = site_config or SiteConfig.load()
        if "initial" not in kwargs:
            provider, model_name, api_base = self._initial_provider_values()
            kwargs["initial"] = {
                "llm_provider": provider,
                "model_name": model_name,
                "llm_api_base": api_base,
            }
        super().__init__(*args, **kwargs)

    def _initial_provider_values(self) -> tuple[str, str, str]:
        ai_model = (self.site_config.ai_model or "").strip()
        api_base = (self.site_config.llm_api_base or "").strip()
        if not ai_model:
            return (
                self.PROVIDER_OPENAI,
                self.DEFAULT_MODELS[self.PROVIDER_OPENAI],
                self.DEFAULT_BASE_URLS[self.PROVIDER_OPENAI],
            )

        provider, _, model_name = ai_model.partition(":")
        if not model_name:
            model_name = ai_model
            if ai_model.startswith(("gpt", "o1", "o3")):
                provider = "openai"
            elif ai_model.startswith("claude"):
                provider = "anthropic"

        if provider == "openai":
            return self.PROVIDER_OPENAI, model_name, ""
        if provider == "anthropic":
            return self.PROVIDER_ANTHROPIC, model_name, ""
        if provider == "openai_compatible" and (
            "api.x.ai" in api_base.lower() or model_name.startswith("grok")
        ):
            return self.PROVIDER_GROK, model_name, api_base or self.DEFAULT_BASE_URLS[self.PROVIDER_GROK]
        if provider == "openai_compatible":
            return self.PROVIDER_CUSTOM, model_name, api_base or self.DEFAULT_BASE_URLS[self.PROVIDER_CUSTOM]

        # Keep unsupported existing values readable while nudging the user into
        # the simplified three-provider UI on the next save.
        return self.PROVIDER_OPENAI, model_name or ai_model, ""

    def _compose_ai_model(self, provider: str, model_name: str) -> str:
        prefix = self.PROVIDER_PREFIXES[provider]
        return f"{prefix}:{model_name.strip()}"

    def _compose_api_base(self, provider: str, api_base: str) -> str:
        if provider in (self.PROVIDER_GROK, self.PROVIDER_CUSTOM):
            return api_base.strip() or self.DEFAULT_BASE_URLS[provider]
        return ""

    def clean(self):
        cleaned = super().clean()
        provider = cleaned.get("llm_provider") or self.PROVIDER_OPENAI
        model_name = (cleaned.get("model_name") or "").strip()
        api_key = (cleaned.get("llm_api_key") or "").strip() or self.site_config.llm_api_key
        api_base = self._compose_api_base(provider, cleaned.get("llm_api_base") or "")

        if not model_name:
            self.add_error("model_name", "Add a model name before saving AI settings.")
            return cleaned

        if not api_key:
            self.add_error("llm_api_key", "Add an API key before saving AI settings.")
            return cleaned

        ai_model = self._compose_ai_model(provider, model_name)
        try:
            build_llm_model(ai_model, api_key, api_base)
        except Exception as exc:
            self.add_error("model_name", str(exc))
        cleaned["ai_model"] = ai_model
        cleaned["llm_api_base"] = api_base
        return cleaned

    def save(self) -> SiteConfig:
        cfg = self.site_config
        cfg.ai_model = self.cleaned_data["ai_model"].strip()
        cfg.llm_api_base = self.cleaned_data.get("llm_api_base") or ""
        new_key = (self.cleaned_data.get("llm_api_key") or "").strip()
        update_fields = ["ai_model", "llm_api_base"]
        if new_key:
            cfg.llm_api_key = new_key
            update_fields.append("llm_api_key")
        cfg.save(update_fields=update_fields)
        return cfg


class CampaignForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.deals.exists():
            self.fields["outreach_mode"].disabled = True
            self.fields["outreach_mode"].help_text = (
                "Campaign type is locked after leads are added so existing outreach data stays consistent."
            )

    class Meta:
        model = Campaign
        fields = ["name", "outreach_mode", "product_docs", "campaign_objective", "booking_link"]
        labels = {
            "name": "Campaign name",
            "outreach_mode": "Campaign type",
            "product_docs": "Product docs",
            "campaign_objective": "Campaign objective",
            "booking_link": "Booking link",
        }
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Rehan Framer",
                "autocomplete": "off",
            }),
            "outreach_mode": forms.Select(),
            "product_docs": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Describe the offer, product, proof, ideal use cases, and important context the AI agent should know.",
            }),
            "campaign_objective": forms.Textarea(attrs={
                "rows": 6,
                "placeholder": "Describe who this campaign should target, what the outreach should say, voice, qualification rules, and what the AI should avoid.",
            }),
            "booking_link": forms.URLInput(attrs={
                "placeholder": "https://cal.com/your-link",
            }),
        }
        help_texts = {
            "name": "Used across breadcrumbs, campaign lists, and exports.",
            "outreach_mode": "CSV personalized campaigns skip lead qualification and send each imported first message after connection acceptance.",
            "product_docs": "Background context for the AI agent when qualifying and writing outreach.",
            "campaign_objective": "The main instruction set for targeting, tone, offer, and outreach behavior.",
            "booking_link": "Optional. Used when the campaign needs to share a meeting link.",
        }
