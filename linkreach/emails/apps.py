# linkreach/emails/apps.py
from django.apps import AppConfig


class EmailsConfig(AppConfig):
    name = "linkreach.emails"
    label = "emails"
    default_auto_field = "django.db.models.BigAutoField"
