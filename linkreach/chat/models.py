from django.conf import settings
from django.db import models
from django.template.defaultfilters import truncatechars
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import reverse


class ChatMessage(models.Model):
    class Source(models.TextChoices):
        UNKNOWN = "unknown", _("Unknown")
        MANUAL = "manual", _("Manual")
        AI = "ai", _("AI")
        CSV_CUSTOM = "csv_custom", _("Campaign message")

    class Meta:
        verbose_name = _("message")
        verbose_name_plural = _("messages")
        constraints = [
            models.UniqueConstraint(
                fields=["deal", "linkedin_urn"],
                name="uniq_deal_linkedin_urn",
            ),
        ]

    deal = models.ForeignKey(
        "crm.Deal",
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("Deal"),
    )

    content = models.TextField(
        blank=True, default='',
        verbose_name=_("Message")
    )    
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE,
        verbose_name=_("Owner"),
        related_name="%(app_label)s_%(class)s_owner_related",
    )
    answer_to = models.ForeignKey(
        'self', blank=True, null=True, on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_answer_to_related",
        verbose_name=_("answer to")
    )
    topic = models.ForeignKey(
        'self', blank=True, null=True, on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_topic_related",
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Creation date")
    )
    linkedin_urn = models.CharField(
        max_length=300,
        verbose_name=_("LinkedIn message URN"),
        help_text=_("entityUrn from Voyager API, used for dedup (per deal)"),
    )
    is_outgoing = models.BooleanField(
        default=True,
        verbose_name=_("Outgoing"),
        help_text=_("True if sent by us, False if received"),
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.UNKNOWN,
        verbose_name=_("Outgoing source"),
        help_text=_("For outgoing messages: manual, AI, or legacy/unknown."),
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="chat_messages_initiated",
        verbose_name=_("Initiated by"),
    )
    def __str__(self):
        return f'{truncatechars(self.content, 70)}'

    def get_absolute_url(self):
        return reverse(f'admin:chat_{self._meta.model_name}_change', args=[str(self.id)])


class ConversationEvent(models.Model):
    class EventType(models.TextChoices):
        MANUAL_MODE_STARTED = "manual_mode_started", _("Manual mode started")
        AI_AUTO_RESUMED = "ai_auto_resumed", _("AI auto-reply resumed")

    deal = models.ForeignKey(
        "crm.Deal",
        on_delete=models.CASCADE,
        related_name="conversation_events",
        verbose_name=_("Deal"),
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="conversation_events_created",
    )

    class Meta:
        verbose_name = _("conversation event")
        verbose_name_plural = _("conversation events")
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.get_event_type_display()} for {self.deal_id}"
