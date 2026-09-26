from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_campaign_outreach_mode_custom_message_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("active", "Active"),
                    ("paused", "Paused"),
                ],
                db_index=True,
                default="draft",
                max_length=12,
            ),
        ),
    ]
