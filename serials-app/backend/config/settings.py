"""Django settings for the serials registration app.

Persistence layer is PostgreSQL (see docker-compose.yml).  For local
verification without a Postgres server, set DB_ENGINE=sqlite — the domain
code only uses portable ORM features, and the concurrency guarantees rely on
unique constraints + SELECT ... FOR UPDATE which PostgreSQL enforces for real.
"""
import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# Docker/local development may omit a key; generate an ephemeral process-local
# value instead of committing one. Deployments should provide DJANGO_SECRET_KEY.
SECRET_KEY: str = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "serials",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DB_ENGINE = os.environ.get("DB_ENGINE", "postgres")
if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SQLITE_NAME", str(BASE_DIR / "db.sqlite3")),
            "OPTIONS": {"timeout": 30},
            # File-based test DB so multi-threaded concurrency tests share one store.
            "TEST": {"NAME": str(BASE_DIR / "test_db.sqlite3")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("PGDATABASE", "serials"),
            "USER": os.environ.get("PGUSER", "serials"),
            **{"PASSWORD": os.environ.get("PGPASSWORD")},
            "HOST": os.environ.get("PGHOST", "db"),
            "PORT": os.environ.get("PGPORT", "5432"),
        }
    }

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = DEBUG  # dev convenience; nginx proxies /api in prod

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": None,
    "UNAUTHENTICATED_USER": None,
}
