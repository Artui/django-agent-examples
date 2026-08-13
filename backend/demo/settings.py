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
    # The admin surface. It is a second, deliberately different integration of
    # the same board: server-rendered pages, a session principal, and the
    # vendored component bundle instead of an npm dependency.
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_admin_agent",
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
    # Sessions and auth are here for the admin. The API and the SPA agent
    # endpoint do not use them: DRF is configured for token auth only, and the
    # SPA mount resolves its own principal from the same header. Two auth models
    # in one project, which is the contrast the admin surface exists to show.
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "demo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Holds the one template override the admin sidebar needs.
        "DIRS": [BASE_DIR / "demo" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
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

# Demo only, and only honoured while DEBUG is on: `/demo-login/` signs the seeded
# demo user in so the admin surface needs no password typed anywhere. Delete this
# and the view in `demo/demo_login.py` when copying any of this into a real
# project — a URL that logs somebody in is exactly as dangerous as it sounds.
DEMO_AUTOLOGIN = os.environ.get("DEMO_AUTOLOGIN", "1") == "1"

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
