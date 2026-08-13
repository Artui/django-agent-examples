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
