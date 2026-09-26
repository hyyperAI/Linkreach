from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0015_lead_country_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="deal",
            name="reply_mode",
            field=models.CharField(
                choices=[("auto", "AI Auto"), ("manual", "Manual")],
                default="auto",
                max_length=10,
            ),
        ),
    ]
