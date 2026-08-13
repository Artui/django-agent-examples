"""Settings for the gallery's shared demo backend.

Deliberately small: SQLite, no admin, no template engine beyond the default,
one app for the board and one module for the agent. Everything in here that a
real deployment would do differently is called out where it happens.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Demo only. A real deployment reads this from the environment and never has a
# usable default.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "demo-only-not-a-secret")

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver"
).split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    # DRF token auth: the frontends send `Authorization: Token <key>`, so no
    # cookie is involved and the browser's origin does not have to match.
    "rest_framework.authtoken",
    # Ships in INSTALLED_APPS so its checks run.
    "rest_framework_services",
    # The reference conversation store, so chat history survives a reload and
    # the web component's history drawer has something to list.
    "django_pydantic_agent.contrib.store",
    "board",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "demo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

ASGI_APPLICATION = "demo.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    # Nothing in this project is readable without a principal, which is what
    # makes the board's owner scoping mean something.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# The model is passed to AGUIServer explicitly rather than configured here,
# because which one you get is a runtime decision: with DEMO_MODEL unset the
# gallery runs offline against a scripted local model, so it works with no API
# key and in CI. See agent/model.py. The settings key is the other way to say
# it, when there is only ever one model:
#
#     DJANGO_AG_UI = {"MODEL": "anthropic:claude-sonnet-4.6"}
