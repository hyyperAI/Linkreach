from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_botprocess"),
    ]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("connect", "Connect"),
                    ("check_pending", "Check Pending"),
                    ("follow_up", "Follow Up"),
                    ("email", "Email"),
                    ("manual_message", "Manual Message"),
                ],
                max_length=20,
            ),
        ),
    ]
