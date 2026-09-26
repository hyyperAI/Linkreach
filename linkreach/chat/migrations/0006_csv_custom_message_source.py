from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat", "0005_message_source_conversation_event")]

    operations = [
        migrations.AlterField(
            model_name="chatmessage", name="source",
            field=models.CharField(
                choices=[("unknown", "Unknown"), ("manual", "Manual"), ("ai", "AI"), ("csv_custom", "Campaign message")],
                default="unknown", help_text="For outgoing messages: manual, AI, or legacy/unknown.",
                max_length=20, verbose_name="Outgoing source",
            ),
        ),
    ]
