from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("linkedin", "0011_linkedinprofile_contribute_to_hub")]
    operations = [
        migrations.AddField(model_name="linkedinprofile", name="connection_status", field=models.CharField(choices=[("not_connected", "Not connected"), ("connected", "Connected"), ("verification_required", "Needs verification"), ("session_expired", "Session expired"), ("error", "Connection error")], default="not_connected", max_length=32)),
        migrations.AddField(model_name="linkedinprofile", name="last_verified_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="linkedinprofile", name="last_connection_attempt_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="linkedinprofile", name="last_error_code", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="linkedinprofile", name="last_error_message", field=models.TextField(blank=True)),
        migrations.AddField(model_name="linkedinprofile", name="checkpoint_url", field=models.URLField(blank=True, max_length=1000)),
    ]
