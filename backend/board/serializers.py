"""Input and output shapes for the board's operations.

Inputs are dataclasses rendered through `DataclassSerializer`, so the same
declaration validates an HTTP body and reflects into the JSON Schema the agent
sees. Output is a plain `ModelSerializer` because the response mirrors the model.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from rest_framework import serializers
from rest_framework_dataclasses.serializers import DataclassSerializer

from board.models import Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "room",
            "day",
            "start_hour",
            "duration_hours",
            "position",
            "updated_at",
        )


class SelectableEventSerializer(EventSerializer):
    """`EventSerializer`, narrowed to the fields a caller names in `?fields=`.

    `?fields=title,day` renders each event with those two keys and no others, and
    a name the event does not have is refused rather than skipped. Only the list
    renders through this: the writes answer with `EventSerializer` itself, so a
    selection never reaches the result of a move or a booking.

    It reads `request.query_params`, which is the one channel both transports
    fill. Over HTTP the query string supplies it; under the agent, the `fields`
    argument `board/specs.py` declares on `list_events` is popped from the tool
    call and seeded there, so this class has no idea which transport it is
    rendering for and does not need one. No selection library is involved on
    purpose: the parsing is a split on commas, and the refusal is worded here,
    by the serializer that knows what it can render.
    """

    def to_representation(self, instance: Event) -> dict[str, object]:
        rendered = super().to_representation(instance)
        selected = self._selected()
        if selected is None:
            return rendered
        # Refused, not ignored. A name silently dropped would answer a typo with
        # a narrower row and no word about why, and that is also exactly what the
        # agent needs to hear when it writes a selection against the *page* a
        # list tool returns (`items`, `page`, ...) rather than against the row
        # this renders: the transport turns this error into a retry the model can
        # act on, and it can only do that if there is an error to turn.
        unknown = [name for name in selected if name not in rendered]
        if unknown:
            raise serializers.ValidationError(
                [f"Unknown field `{name}`." for name in unknown], code="unknown_field"
            )
        # Declared order, whatever order the caller wrote them in, so two
        # selections naming the same fields render the same row.
        return {name: value for name, value in rendered.items() if name in selected}

    def _selected(self) -> list[str] | None:
        """The names `?fields=` asks for, or `None` when it asks for nothing.

        Read defensively, because not every render has a request behind it: a
        serializer built by hand in a shell, a test, or a management command gets
        no `request` in its context, and none of those should fail for want of a
        query string they never had. An empty or all-comma value is also "no
        selection" rather than "select nothing" -- a row with no keys is never
        what a caller meant.
        """
        request = self.context.get("request")
        query_params = getattr(request, "query_params", None)
        if query_params is None:
            return None
        raw = query_params.get("fields")
        if not raw:
            return None
        names = [name.strip() for name in str(raw).split(",") if name.strip()]
        return names or None


@dataclass
class MoveEventInput:
    """Put an event in a grid cell, or send it back to the backlog.

    `day` and `start_hour` travel together: give both to schedule, give neither
    to unschedule.
    """

    event_id: int
    day: datetime.date | None = None
    start_hour: int | None = None


class MoveEventInputSerializer(DataclassSerializer):
    class Meta:
        dataclass = MoveEventInput

    def validate(self, attrs: MoveEventInput) -> MoveEventInput:
        # Shape, not state: answerable from the payload alone, so it belongs
        # here rather than in a precondition. Note the type — a
        # DataclassSerializer hands `validate` the **dataclass instance**, not
        # the dict a ModelSerializer would.
        if (attrs.day is None) != (attrs.start_hour is None):
            raise serializers.ValidationError(
                "Pass both day and start_hour to schedule an event, or neither "
                "to move it back to the backlog."
            )
        if attrs.start_hour is not None and not 0 <= attrs.start_hour <= 23:
            raise serializers.ValidationError({"start_hour": "Must be between 0 and 23."})
        return attrs


@dataclass
class ReorderEventInput:
    """Move a backlog event in front of another one, or to the end of the list."""

    event_id: int
    before_event_id: int | None = None


class ReorderEventInputSerializer(DataclassSerializer):
    class Meta:
        dataclass = ReorderEventInput


@dataclass
class CreateEventInput:
    """Add an event. With no day and hour it lands in the backlog."""

    title: str
    room: str = ""
    day: datetime.date | None = None
    start_hour: int | None = None
    duration_hours: int = 1


class CreateEventInputSerializer(DataclassSerializer):
    class Meta:
        dataclass = CreateEventInput
