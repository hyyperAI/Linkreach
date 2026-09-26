from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("crm", "0016_deal_reply_mode"),
        ("chat", "0004_remove_chatmessage_recipients_remove_chatmessage_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatmessage",
            name="initiated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="chat_messages_initiated",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Initiated by",
            ),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="source",
            field=models.CharField(
                choices=[("unknown", "Unknown"), ("manual", "Manual"), ("ai", "AI")],
                default="unknown",
                help_text="For outgoing messages: manual, AI, or legacy/unknown.",
                max_length=20,
                verbose_name="Outgoing source",
            ),
        ),
        migrations.CreateModel(
            name="ConversationEvent",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("manual_mode_started", "Manual mode started"), ("ai_auto_resumed", "AI auto-reply resumed")], max_length=40)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="conversation_events_created", to=settings.AUTH_USER_MODEL)),
                ("deal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversation_events", to="crm.deal", verbose_name="Deal")),
            ],
            options={
                "verbose_name": "conversation event",
                "verbose_name_plural": "conversation events",
                "ordering": ["created_at", "pk"],
            },
        ),
    ]
