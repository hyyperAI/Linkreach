from django.db import migrations

import linkreach.core.secret_fields


def encrypt_existing(apps, schema_editor):
    LinkedInProfile = apps.get_model("linkedin", "LinkedInProfile")
    for profile in LinkedInProfile.objects.all():
        profile.save(update_fields=["linkedin_password", "cookie_data"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_encrypt_sensitive_fields"),
        ("linkedin", "0013_linkedinprofile_connection_states"),
    ]
    operations = [
        migrations.AlterField(
            model_name="linkedinprofile",
            name="linkedin_password",
            field=linkreach.core.secret_fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name="linkedinprofile",
            name="cookie_data",
            field=linkreach.core.secret_fields.EncryptedJSONField(blank=True, null=True),
        ),
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
