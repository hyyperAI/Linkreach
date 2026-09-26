from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0009_manual_message_task")]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="outreach_mode",
            field=models.CharField(
                choices=[("standard", "Standard campaign"), ("csv_personalized", "CSV personalized")],
                default="standard",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("connect", "Connect"), ("check_pending", "Check Pending"),
                    ("follow_up", "Follow Up"), ("email", "Email"),
                    ("manual_message", "Manual Message"),
                    ("custom_first_message", "Custom First Message"),
                ],
                max_length=20,
            ),
        ),
    ]
