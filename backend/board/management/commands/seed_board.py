"""Create the demo user, its API token, and a week's worth of events.

Idempotent: run it as often as you like. `--reset` throws the events away first.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from board.models import Event

DEMO_USERNAME = "demo"
# A fixed, obviously-fake token so the frontends can ship a working default and
# the gallery needs no setup step. Nothing here is a secret; the database is a
# local SQLite file seeded from this command.
DEMO_TOKEN = "demo-token-not-a-secret"

SCHEDULED = [
    ("Standup", 0, 9, 1, "Aurora"),
    ("Design review", 0, 14, 2, "Aurora"),
    ("Sprint planning", 1, 10, 2, "Basalt"),
    ("1:1 with Sam", 1, 16, 1, ""),
    ("Architecture sync", 2, 11, 1, "Basalt"),
    ("Customer call", 3, 9, 1, "Aurora"),
    ("Release checklist", 3, 15, 1, ""),
    ("Retro", 4, 16, 1, "Basalt"),
]

BACKLOG = [
    "Write the release notes",
    "Review the migration plan",
    "Draft the onboarding doc",
    "Book the offsite room",
]


class Command(BaseCommand):
    help = "Seed the demo user, token and scheduling board."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the demo user's events before seeding.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={
                "email": "demo@example.com",
                "is_active": True,
                # Staff, because the same demo person also uses the admin
                # surface, and the admin agent's gate fails closed on non-staff.
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            # No usable password anywhere in the gallery: the admin is reached
            # through `/demo-login/`, which only works while DEBUG is on.
            user.set_unusable_password()
            user.save(update_fields=["password"])
        elif not (user.is_staff and user.is_superuser):
            # Idempotent means idempotent: `get_or_create` defaults only apply on
            # creation, so a user seeded before the admin surface existed would
            # never become staff and the admin agent would refuse it.
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])
        Token.objects.get_or_create(user=user, defaults={"key": DEMO_TOKEN})

        if options["reset"]:
            Event.objects.filter(owner=user).delete()

        monday = _monday_of_this_week()
        for title, day_offset, hour, duration, room in SCHEDULED:
            Event.objects.get_or_create(
                owner=user,
                title=title,
                defaults={
                    "day": monday + datetime.timedelta(days=day_offset),
                    "start_hour": hour,
                    "duration_hours": duration,
                    "room": room,
                },
            )
        for position, title in enumerate(BACKLOG):
            Event.objects.get_or_create(
                owner=user,
                title=title,
                defaults={"position": position},
            )

        total = Event.objects.filter(owner=user).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {total} events for {DEMO_USERNAME}. "
                f"API token: {Token.objects.get(user=user).key}"
            )
        )


def _monday_of_this_week() -> datetime.date:
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())
