# linkreach/settings.py
"""
Minimal Django settings for using DjangoCRM's ORM + admin.
"""
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

ROOT_DIR = Path(__file__).resolve().parent.parent

# Browsers are installed to the project-local .browsers/ (see `make setup`,
# Start-Bot.bat), not the global ms-playwright cache. The daemon process always
# set this itself; the dashboard didn't need Playwright until the "Start
# verification" flow started launching a browser from within a web request's
# background thread, so it needs the same override.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT_DIR / ".browsers"))

BASE_DIR = ROOT_DIR

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


LOCAL_RELEASE = _env_bool("linkreach_LOCAL_RELEASE")
DEBUG = _env_bool("linkreach_DEBUG", default=not LOCAL_RELEASE)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if LOCAL_RELEASE:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is required when linkreach_LOCAL_RELEASE=1. "
            "Use the Windows launchers, which create and load a local key."
        )
    SECRET_KEY = "linkreach-local-dev-key-change-in-production"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost,testserver",
    ).split(",")
    if host.strip()
]

# This release is deliberately loopback-only HTTP. These HTTPS-specific checks
# do not apply unless the dashboard is later exposed beyond this computer.
if LOCAL_RELEASE:
    SILENCED_SYSTEM_CHECKS = [
        "security.W004",  # HSTS requires HTTPS.
        "security.W008",  # SSL redirect would break loopback HTTP.
        "security.W012",  # Secure cookies require HTTPS.
        "security.W016",  # Secure CSRF cookies require HTTPS.
    ]

# In managed/container deployments the daemon is owned by the process manager,
# so the Dashboard should display status but not spawn another bot process.
MANAGED_DEPLOYMENT = os.environ.get("linkreach_MANAGED", "").lower() in {
    "1",
    "true",
    "yes",
}

INSTALLED_APPS = [
    "django.contrib.sites",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "linkreach.crm.apps.CrmConfig",
    "linkreach.chat.apps.ChatConfig",
    "linkreach.core.apps.CoreConfig",
    "linkreach.linkedin.apps.LinkedInConfig",
    "linkreach.emails.apps.EmailsConfig",
    "linkreach.dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "linkreach.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [ROOT_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(ROOT_DIR / "data" / "db.sqlite3"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SITE_ID = 1

STATIC_URL = "/static/"
STATIC_ROOT = ROOT_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = ROOT_DIR / "media"

LOGIN_URL = "/admin/login/"

DEFAULT_FROM_EMAIL = "noreply@localhost"
EMAIL_SUBJECT_PREFIX = "CRM: "

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English")]
TIME_ZONE = "Asia/Karachi"  # PKT (UTC+5) — display only; DB still stores UTC (USE_TZ=True)
USE_I18N = True
USE_TZ = True

TESTING = sys.argv[1:2] == ["test"] or "pytest" in sys.modules
