"""The board's operations, declared once.

Each spec is transport-neutral: the same object drives an HTTP route in
`board/views.py` and an agent tool in `agent/server.py`. `permission_classes` is
set on every one of them, not inherited — off HTTP there is no viewset and no
`DEFAULT_PERMISSION_CLASSES` to fall back to, so a spec that leaves it unset is
refused when the AG-UI server is constructed.
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework_services import (
    OfflineContract,
    QueryParam,
    SelectorKind,
    SelectorSpec,
    ServiceSpec,
    SpecRegistry,
)

from board.selectors import list_events
from board.serializers import (
    CreateEventInputSerializer,
    EventSerializer,
    MoveEventInputSerializer,
    ReorderEventInputSerializer,
    SelectableEventSerializer,
)
from board.services import create_event, move_event, reorder_event, slot_is_free

_rendered_event = SelectorSpec(
    kind=SelectorKind.RETRIEVE,
    output_serializer=EventSerializer,
)

list_events_spec = SelectorSpec(
    kind=SelectorKind.LIST,
    selector=list_events,
    # The selectable subclass, and only here: the writes below render through
    # `EventSerializer` itself, so a selection can narrow the board and never the
    # answer to a move.
    output_serializer=SelectableEventSerializer,
    permission_classes=[IsAuthenticated],
)

move_event_spec = ServiceSpec(
    service=move_event,
    input_serializer=MoveEventInputSerializer,
    # A state rule, on the spec, so it holds on both transports.
    preconditions=[slot_is_free],
    output_selector_spec=_rendered_event,
    permission_classes=[IsAuthenticated],
)

reorder_event_spec = ServiceSpec(
    service=reorder_event,
    input_serializer=ReorderEventInputSerializer,
    output_selector_spec=_rendered_event,
    permission_classes=[IsAuthenticated],
)

create_event_spec = ServiceSpec(
    service=create_event,
    input_serializer=CreateEventInputSerializer,
    # The same precondition as the move, and one object is why: the rule is the
    # board's, so declaring it here is all it takes for a create to obey it on
    # both transports.
    preconditions=[slot_is_free],
    output_selector_spec=_rendered_event,
    permission_classes=[IsAuthenticated],
)

# The one declaration site. `board/views.py` reads it for the HTTP routes and
# `agent/server.py` hands it to AGUIServer, so a new operation cannot arrive on
# one transport and be forgotten on the other.
registry = SpecRegistry()
registry.register(
    "list_events",
    list_events_spec,
    tags=("read",),
    # What a caller with no query string has to be told. Over HTTP `?fields=` is
    # just there for the serializer to read; the agent has no URL, so the
    # argument is declared here and the transport advertises it on the tool,
    # pops it from the call, and seeds it into `request.query_params` where the
    # same serializer reads it. Declared on the entry rather than on the
    # transport's constructor so any other transport handed this registry --
    # an MCP server, say -- advertises the same argument.
    #
    # The description says what a *row* has, and deliberately not what the
    # result looks like: the transport appends that on a list tool itself,
    # because the envelope a page arrives in is the transport's shape, not the
    # board's.
    agent_contract=OfflineContract(
        query_params=(
            QueryParam(
                "fields",
                description=(
                    "Comma-separated names of the event fields to return, for "
                    "example `title,day`. Omit it for every field."
                ),
            ),
        ),
    ),
)
registry.register("move_event", move_event_spec, tags=("write",))
registry.register("reorder_event", reorder_event_spec, tags=("write",))
registry.register("create_event", create_event_spec, tags=("write",))
