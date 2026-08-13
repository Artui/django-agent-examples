"""Write side: plain callables plus the state rules that guard them.

Nothing here imports from `rest_framework`. The exceptions are
`rest_framework_services` ones, which every transport already maps: to a
response over HTTP, to a tool error the model can read under the agent.
"""

from __future__ import annotations

from typing import Any

from rest_framework_services import ServiceConflict, ServiceError, ServiceNotFound

from board.models import Event
from board.serializers import CreateEventInput, MoveEventInput, ReorderEventInput


class SlotTaken(ServiceConflict):
    """Two events cannot hold the same cell of the grid."""


class UnknownEvent(ServiceNotFound):
    """No such event, or not this user's."""


# The member says *what kind* of failure it is, and every transport gets the
# distinction: `409` and `404` over HTTP, a readable tool error under the agent.
# That is the whole point of raising the framework-agnostic error rather than a
# DRF one — a DRF `APIException` would be correct over HTTP and an unhandled 500
# everywhere else.
#
# These were both plain `ServiceError` subclasses when this gallery was built,
# because there was nothing else to raise: every non-validation error mapped to a
# fixed `422` and a `status_code` attribute on the subclass was read by nobody.
# Writing that attribute here, watching a 422 come back, and going to look is what
# produced the two members — they arrived in drf-services 0.40.0.
#
# `UnknownEvent` answers the same way for "no such event" and "not yours", which is
# `owned_event` below: a `403` on a row you cannot see confirms that it exists.


def owned_event(user: Any, event_id: int) -> Event:
    """Resolve an event id against its owner, never against the id alone.

    The caller supplies the id on both transports, so this is the one lookup
    that decides whose row an operation touches.
    """
    try:
        return Event.objects.get(pk=event_id, owner=user)
    except Event.DoesNotExist:
        raise UnknownEvent(f"No event {event_id} belongs to you.") from None


def slot_is_free(*, user: Any, data: MoveEventInput | CreateEventInput) -> None:
    """A precondition: raise to abort, and note that returning False would not.

    This is a state rule — it needs the database, not the payload — so it lives
    on the spec and travels to both transports rather than sitting in a view.

    One rule over *both* writes, because the rule belongs to the board rather than
    to an operation. It guarded only `move_event` until a CSV import created three
    events at once against a week nobody could see all of, and put two cards in one
    cell: the grid draws one, and the other is simply gone. A rule enforced on one
    write and not the other is not the board's rule.
    """
    if data.day is None or data.start_hour is None:
        return
    clash = Event.objects.filter(owner=user, day=data.day, start_hour=data.start_hour)
    if isinstance(data, MoveEventInput):
        # A move has to ignore the slot the event is already in. A create has no
        # self to exclude, which is the whole difference between the two cases.
        clash = clash.exclude(pk=data.event_id)
    held = clash.first()
    if held is not None:
        raise SlotTaken(
            f"{data.day} at {data.start_hour}:00 is already held by {held.title!r}."
        )


def move_event(*, user: Any, data: MoveEventInput) -> Event:
    """Put an event in a day and hour of the grid, or send it back to the backlog.

    The docstring is not decoration: it becomes the tool description the model
    reads, and the spec toolset warns at startup about any operation that lacks
    one, because an undescribed tool is one a model calls at the wrong time.
    """
    event = owned_event(user, data.event_id)
    event.day = data.day
    event.start_hour = data.start_hour
    written = ["day", "start_hour", "updated_at"]
    if data.day is None:
        # Coming back out of the grid means joining the backlog list, and the
        # end of it is the only place that needs no further decision.
        event.position = _next_backlog_position(user)
        written.append("position")
    event.save(update_fields=written)
    return event


def reorder_event(*, user: Any, data: ReorderEventInput) -> Event:
    """Renumber the backlog so `event_id` sits directly before `before_event_id`."""
    event = owned_event(user, data.event_id)
    if event.day is not None:
        # Deliberately the generic member, and the contrast is the point: a
        # scheduled event is not *colliding* with anything, and re-reading the
        # board will not make this call work. "Understood, and still not allowed"
        # is a 422. Not every rule is a conflict.
        raise ServiceError("Only backlog events can be reordered.")
    backlog = [
        candidate
        for candidate in Event.objects.filter(owner=user, day__isnull=True).order_by(
            "position", "id"
        )
        if candidate.pk != event.pk
    ]
    if data.before_event_id is None:
        backlog.append(event)
    else:
        anchor = owned_event(user, data.before_event_id)
        index = next(
            (i for i, candidate in enumerate(backlog) if candidate.pk == anchor.pk),
            len(backlog),
        )
        backlog.insert(index, event)
    for position, candidate in enumerate(backlog):
        if candidate.position != position:
            candidate.position = position
            candidate.save(update_fields=["position", "updated_at"])
    event.refresh_from_db()
    return event


def create_event(*, user: Any, data: CreateEventInput) -> Event:
    """Add an event to the board, scheduled if given a day and hour, else in the backlog."""
    event = Event(
        owner=user,
        title=data.title,
        room=data.room,
        day=data.day,
        start_hour=data.start_hour,
        duration_hours=data.duration_hours,
    )
    if data.day is None:
        event.position = _next_backlog_position(user)
    event.save()
    return event


def _next_backlog_position(user: Any) -> int:
    positions = Event.objects.filter(owner=user, day__isnull=True).values_list(
        "position", flat=True
    )
    return max(positions, default=-1) + 1
