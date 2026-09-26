from django.db import migrations

import linkreach.core.secret_fields


def encrypt_existing(apps, schema_editor):
    Mailbox = apps.get_model("emails", "Mailbox")
    for mailbox in Mailbox.objects.all():
        mailbox.save(update_fields=["password"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_encrypt_sensitive_fields"),
        ("emails", "0001_initial"),
    ]
    operations = [
        migrations.AlterField(
            model_name="mailbox",
            name="password",
            field=linkreach.core.secret_fields.EncryptedTextField(),
        ),
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
