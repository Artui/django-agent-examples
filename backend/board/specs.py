"""The board's operations, declared once.

Each spec is the kernel's, and transport-neutral: the same object drives an HTTP
route in `board/views.py` and an agent tool in `agent/server.py`. DRF fills three
of its seats -- a serializer validates the input, a serializer renders the
result, and DRF permission classes decide who may call it. `permissions` is set
on every one of them, not inherited -- off HTTP there is no viewset and no
`DEFAULT_PERMISSION_CLASSES` to fall back to, and the kernel refuses to dispatch
a spec that declares none.
"""

from __future__ import annotations

from django_service_specs import (
    Parameter,
    Parameters,
    SelectorKind,
    SelectorSpec,
    ServiceSpec,
    SpecRegistry,
)
from django_spec_rest.service_specs.drf_permission_check import DRFPermissionCheck
from django_spec_rest.service_specs.serializer_presenter import SerializerPresenter
from django_spec_rest.service_specs.serializer_validator import SerializerValidator
from rest_framework.permissions import IsAuthenticated

from board.selectors import list_events
from board.serializers import (
    CreateEventInputSerializer,
    EventSerializer,
    MoveEventInputSerializer,
    ReorderEventInputSerializer,
    SelectableEventSerializer,
)
from board.services import create_event, move_event, reorder_event, slot_is_free

_signed_in = (DRFPermissionCheck([IsAuthenticated]),)
_rendered_event = SerializerPresenter(EventSerializer)

list_events_spec = SelectorSpec(
    kind=SelectorKind.LIST,
    selector=list_events,
    # The selectable subclass, and only here: the writes below render through
    # `EventSerializer` itself, so a selection can narrow the board and never the
    # answer to a move. `shaped=True` because a `fields` selection decides which
    # keys a row has, so the declared output promises none of them.
    presenter=SerializerPresenter(SelectableEventSerializer, shaped=True),
    permissions=_signed_in,
    # What a caller with no query string has to be told. Over HTTP `?fields=` is
    # just there for the serializer to read; the agent has no URL, so the
    # argument is declared on the spec as a shape -- one no callable names --
    # and the transport advertises it on the tool, and the presenter hands it to
    # the serializer as the query string of the request it renders under.
    # Declared on the spec rather than on the registry entry or the transport's
    # constructor so any transport handed this registry advertises the same
    # argument.
    #
    # The description says what a *row* has, and deliberately not what the
    # result looks like: the transport appends that on a list tool itself,
    # because the envelope a page arrives in is the transport's shape, not the
    # board's.
    shapes=Parameters.of(
        Parameter(
            "fields",
            "string",
            help=(
                "Comma-separated names of the event fields to return, for "
                "example `title,day`. Omit it for every field."
            ),
        ),
    ),
)

move_event_spec = ServiceSpec(
    service=move_event,
    validator=SerializerValidator(MoveEventInputSerializer),
    # A state rule, on the spec, so it holds on both transports.
    preconditions=[slot_is_free],
    presenter=_rendered_event,
    permissions=_signed_in,
)

reorder_event_spec = ServiceSpec(
    service=reorder_event,
    validator=SerializerValidator(ReorderEventInputSerializer),
    presenter=_rendered_event,
    permissions=_signed_in,
)

create_event_spec = ServiceSpec(
    service=create_event,
    validator=SerializerValidator(CreateEventInputSerializer),
    # The same precondition as the move, and one object is why: the rule is the
    # board's, so declaring it here is all it takes for a create to obey it on
    # both transports.
    preconditions=[slot_is_free],
    presenter=_rendered_event,
    permissions=_signed_in,
)

# The one declaration site. `board/views.py` reads it for the HTTP routes and
# `agent/server.py` hands it to AGUIServer, so a new operation cannot arrive on
# one transport and be forgotten on the other.
registry = SpecRegistry()
registry.register("list_events", list_events_spec, tags=("read",))
registry.register("move_event", move_event_spec, tags=("write",))
registry.register("reorder_event", reorder_event_spec, tags=("write",))
registry.register("create_event", create_event_spec, tags=("write",))
