"""Read side. Plain callables; the framework passes only what they declare."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from board.models import Event


def list_events(*, user: Any) -> QuerySet[Event]:
    """Every event belonging to the acting user, in board order.

    The scoping is the `owner=user` filter and nothing else. Over HTTP the user
    comes from DRF authentication, under the agent from the AG-UI endpoint's
    `get_user` hook; the selector cannot tell the difference and does not need to.
    """
    return Event.objects.filter(owner=user)
