from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0016_deal_reply_mode")]

    operations = [
        migrations.AddField(model_name="deal", name="custom_first_message", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="deal", name="custom_message_attempts", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="deal", name="custom_message_error", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="deal", name="custom_message_sent_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="deal", name="custom_message_status",
            field=models.CharField(
                choices=[("not_required", "Not required"), ("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed")],
                db_index=True, default="not_required", max_length=20,
            ),
        ),
        migrations.AddField(model_name="deal", name="outreach_approved_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
    ]
