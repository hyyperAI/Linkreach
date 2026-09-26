# linkreach/core/models.py
from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from linkreach.core.secret_fields import EncryptedTextField


class SiteConfig(models.Model):
    """Singleton model for global site configuration (LLM keys, etc.)."""

    # The model is a pydantic-ai model identifier in `provider:model` form
    # (e.g. ``anthropic:claude-sonnet-4-5-20250929``, ``openai:gpt-4o``,
    # ``groq:llama-3.3-70b``). The provider lives inside this single string —
    # there is no separate provider field to drift out of sync. A bare model
    # name whose prefix is unambiguous (``gpt``/``o1``/``o3``→openai,
    # ``claude``→anthropic, ``gemini``→google) is also accepted; everything
    # else must carry an explicit prefix. See core/llm.py:split_model_id.
    ai_model = models.CharField(
        max_length=200, blank=True, default="",
        help_text="provider:model, e.g. anthropic:claude-sonnet-4-5-20250929",
    )
    llm_api_key = EncryptedTextField(blank=True, default="")
    # Only consulted for the openai_compatible provider (OpenRouter / Together / Ollama / vLLM).
    llm_api_base = models.CharField(max_length=500, blank=True, default="")

    # BetterContact email-finder key; blank disables enrichment (see emails/bettercontact.py).
    bettercontact_api_key = EncryptedTextField(blank=True, default="")

    # Central contacts service (see linkreach/contacts/). The token is earned
    # on the first contribution and persisted here — never in the repo; blank
    # means "not registered yet" (resolve misses until the first give-back mints
    # it). The URL is blank by default (falls back to DEFAULT_CONTACTS_API_URL).
    contacts_api_token = EncryptedTextField(blank=True, default="")
    contacts_api_url = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self):
        return "Site Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BotProcess(models.Model):
    """Singleton row tracking the current/last-known daemon process."""

    pid = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    stop_requested = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Bot Process"
        verbose_name_plural = "Bot Process"

    def __str__(self):
        return f"Bot Process pid={self.pid or 'stopped'}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "BotProcess":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Campaign(models.Model):
    class OutreachMode(models.TextChoices):
        STANDARD = "standard", "Standard campaign"
        CSV_PERSONALIZED = "csv_personalized", "CSV personalized"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"

    name = models.CharField(max_length=200, unique=True)
    users = models.ManyToManyField(User, blank=True, related_name="campaigns")
    product_docs = models.TextField(blank=True)
    campaign_objective = models.TextField(blank=True)
    booking_link = models.URLField(max_length=500, blank=True)
    is_freemium = models.BooleanField(default=False)
    action_fraction = models.FloatField(default=0.2)
    seed_public_ids = models.JSONField(default=list, blank=True)
    model_blob = models.BinaryField(null=True, blank=True)
    outreach_mode = models.CharField(
        max_length=24,
        choices=OutreachMode.choices,
        default=OutreachMode.STANDARD,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    def __str__(self):
        return self.name


class TaskQuerySet(models.QuerySet):
    def pending(self):
        """Runnable pending tasks, urgent manual replies first.

        Manual LinkedIn replies are explicitly user-triggered, so they outrank
        background email and automation. Email still outranks the scheduled
        LinkedIn channels so a ready email send preempts connect/follow-up slots.
        Automation tasks only run for active campaigns; draft/paused campaign
        slots are lazy schedule rows and are ignored until cleanup removes them.
        """
        active_campaign_ids = list(
            Campaign.objects.filter(status=Campaign.Status.ACTIVE)
            .values_list("pk", flat=True)
        )
        runnable = (
            models.Q(task_type=Task.TaskType.MANUAL_MESSAGE)
            | models.Q(payload__campaign_id__in=active_campaign_ids)
        )
        priority = models.Case(
            models.When(task_type=Task.TaskType.MANUAL_MESSAGE, then=models.Value(0)),
            models.When(task_type=Task.TaskType.CUSTOM_FIRST_MESSAGE, then=models.Value(1)),
            models.When(task_type=Task.TaskType.EMAIL, then=models.Value(2)),
            default=models.Value(3),
            output_field=models.IntegerField(),
        )
        return self.filter(status=Task.Status.PENDING).filter(runnable).order_by(priority, "scheduled_at")

    def claim_next(self) -> "Task | None":
        return self.pending().filter(scheduled_at__lte=timezone.now()).first()

    def seconds_to_next(self) -> float | None:
        """Seconds until the next pending task, or None if queue is empty."""
        next_task = self.pending().only("scheduled_at").first()
        if next_task is None:
            return None
        return max((next_task.scheduled_at - timezone.now()).total_seconds(), 0)


class Task(models.Model):
    class TaskType(models.TextChoices):
        CONNECT = "connect"
        CHECK_PENDING = "check_pending"
        FOLLOW_UP = "follow_up"
        EMAIL = "email"
        MANUAL_MESSAGE = "manual_message"
        CUSTOM_FIRST_MESSAGE = "custom_first_message"

    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"

    task_type = models.CharField(max_length=20, choices=TaskType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    scheduled_at = models.DateTimeField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(
                fields=["status", "scheduled_at"],
                name="core_task_status_sched_idx",
            ),
        ]

    def __str__(self):
        return f"{self.task_type} [{self.status}] scheduled={self.scheduled_at}"

    def mark_running(self):
        self.status = self.Status.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_completed(self):
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

    def mark_failed(self):
        self.status = self.Status.FAILED
        self.save(update_fields=["status"])
