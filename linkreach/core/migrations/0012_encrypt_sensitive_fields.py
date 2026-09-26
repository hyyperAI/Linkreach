from django.db import migrations

import linkreach.core.secret_fields


def encrypt_existing(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    for config in SiteConfig.objects.all():
        config.save(update_fields=[
            "llm_api_key",
            "bettercontact_api_key",
            "contacts_api_token",
        ])


class Migration(migrations.Migration):
    dependencies = [("core", "0011_campaign_status")]
    operations = [
        migrations.AlterField(
            model_name="siteconfig",
            name="llm_api_key",
            field=linkreach.core.secret_fields.EncryptedTextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="siteconfig",
            name="bettercontact_api_key",
            field=linkreach.core.secret_fields.EncryptedTextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="siteconfig",
            name="contacts_api_token",
            field=linkreach.core.secret_fields.EncryptedTextField(blank=True, default=""),
        ),
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
