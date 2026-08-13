"""HTTP routes over the same specs the agent calls.

The frontends read the board through `list`, and their drop handlers persist a
move through `move` / `reorder` — the very operations the agent invokes as tools.
That is the point of the shared registry: the drag the user performs and the
drag the agent performs end in the same service.
"""

from __future__ import annotations

from rest_framework.viewsets import GenericViewSet
from rest_framework_services import (
    ActionSerializerResolver,
    SelectorListMixin,
    ServiceCreateMixin,
    service_action,
)

from board.models import Event
from board.serializers import EventSerializer
from board.specs import registry


class EventViewSet(
    SelectorListMixin,
    ServiceCreateMixin,
    ActionSerializerResolver,
    GenericViewSet,
):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    action_specs = {
        "list": registry.get("list_events").spec,
        "create": registry.get("create_event").spec,
    }

    @service_action(registry.get("move_event").spec, detail=False, methods=["post"])
    def move(self, request):
        """Put an event in a grid cell, or send it back to the backlog."""

    @service_action(registry.get("reorder_event").spec, detail=False, methods=["post"])
    def reorder(self, request):
        """Move a backlog event in front of another one."""
