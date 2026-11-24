"""The board's operations served by an MCP server, and an agent that reaches them.

The other route a spec can reach an agent by. `agent/server.py` hands the board's
registry to `service_specs=`, and the spec toolset calls each spec in process.
This mount hands `mcp_server=` a django-spec-mcp `MCPServer`, and the bridge
calls the server's own `tools/list` and `tools/call` in process: the schemas,
argument checks and permission answers are the ones an MCP client would get over
HTTP, acting as the request's user, with no network hop. No `service_specs=` is
passed, so every tool this agent has arrives through the bridge.

The specs are declared here rather than taken from `board/specs.py`. Those are
kernel specs too, with DRF in their seats -- serializers to validate and render,
DRF permission classes to decide who may call. These two show the other way to
fill the same seats: the kernel's own validator, presenters and permission
checks, over the same `board/selectors.py` and `board/services.py` functions, so
the server is handed nothing DRF-shaped. The functions are shared with the
board's HTTP route, and so is what they import. Two operations are enough to
show the route: one read, and one write that can be refused two ways.

The server is never mounted over HTTP. `MCPServer.urls` refuses without an auth
backend, and authorizing an MCP client is the deployment's job, not a gallery's;
the bridge needs none, because it acts as the user the endpoint resolved.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from collections import Counter
from typing import Any

from django_ag_ui import AGUIServer, ToolRegistry, build_ag_ui_config
from django_service_specs import (
    DataclassPresenter,
    DataclassValidator,
    PermissionCheck,
    SelectorKind,
    SelectorSpec,
    ServiceSpec,
    ServiceValidationError,
)
from django_spec_agents import ScopedConversationStore, ToolGuardConfig
from django_spec_agents.contrib.store.default_conversation_store import (
    DefaultConversationStore,
)
from django_spec_agents.contrib.store.default_step_store import DefaultStepStore
from django_spec_agents.policy.audit.logging_audit_logger import LoggingAuditLogger
from django_spec_mcp import MCPServer
from django_spec_mcp.registry.types.ui_tool_meta import UIToolMeta
from django_spec_mcp.types.ui_visibility import UIVisibility
from django_spec_mcp.ui.build_app_document import build_app_document
from django_spec_mcp.config import build_mcp_config

from agent.auth import token_user
from agent.child_sessions import drain, inbound_queue, run_store, runner
from agent.model import build_demo_model
from board.selectors import list_events
from board.serializers import CreateEventInput
from board.services import create_event, slot_is_free

INSTRUCTIONS = """
You read and book on a scheduling board for the user, through the board's MCP
server. Read it with `list_events` before answering about it, and draw it with `show_board`. Say what changed,
in one sentence.
""".strip()


class SignedIn(PermissionCheck):
    """Any signed-in user. The endpoint already answers 401 without a token, so
    this refuses nobody who gets this far; it is here because the server
    refuses to register a tool that declares no permission at all, and a read
    open to every caller should say so rather than leave it unset."""

    def has_permission(self, principal: Any, spec: Any) -> bool:
        return bool(getattr(principal, "is_authenticated", False))


class HoldsPermission(PermissionCheck):
    """The principal holds one Django model permission, by its dotted name."""

    def __init__(self, codename: str) -> None:
        self.codename = codename

    def has_permission(self, principal: Any, spec: Any) -> bool:
        return principal.has_perm(self.codename)


@dataclass
class EventRow:
    """What a model is told about an event. Rendered off the model row by
    attribute, so it is a declaration of the output and never instantiated."""

    id: int
    title: str
    room: str
    day: datetime.date | None
    start_hour: int | None
    duration_hours: int
    position: int


def title_is_set(*, user: Any, data: CreateEventInput) -> None:
    """The one rule the board's input serializer adds that the dataclass does
    not state: a title may not be blank. `DataclassValidator` takes an empty
    string as a string, so without this the route would book an untitled event
    the other two refuse."""
    if not data.title.strip():
        raise ServiceValidationError({"title": ["This field may not be blank."]})


@dataclass
class Overview:
    """What the board view draws on arrival: counts and the rooms in use."""

    scheduled: int
    backlog: int
    rooms: list[str]


@dataclass
class RoomLoad:
    """Hours booked per room, what the view asks for after it is drawn."""

    hours: dict[str, int]


def board_overview(*, user: Any) -> Overview:
    """The acting user's board in three numbers, for the view to open on."""
    events = list(list_events(user=user))
    scheduled = [e for e in events if e.day is not None]
    return Overview(
        scheduled=len(scheduled),
        backlog=len(events) - len(scheduled),
        rooms=sorted({e.room for e in scheduled}),
    )


def room_load(*, user: Any) -> RoomLoad:
    """Booked hours per room, summed over the acting user's scheduled events."""
    hours: Counter[str] = Counter()
    for event in list_events(user=user):
        if event.day is not None:
            hours[event.room] += event.duration_hours
    return RoomLoad(hours=dict(hours))


list_events_spec = SelectorSpec(
    kind=SelectorKind.LIST,
    selector=list_events,
    presenter=DataclassPresenter(EventRow),
    permissions=[SignedIn()],
)

board_overview_spec = SelectorSpec(
    kind=SelectorKind.RETRIEVE,
    selector=board_overview,
    presenter=DataclassPresenter(Overview),
    permissions=[SignedIn()],
)

room_load_spec = SelectorSpec(
    kind=SelectorKind.RETRIEVE,
    selector=room_load,
    presenter=DataclassPresenter(RoomLoad),
    permissions=[SignedIn()],
)

create_event_spec = ServiceSpec(
    service=create_event,
    # The board's own input dataclass, which states every type the serializer
    # checks; the blank title it also refuses is `title_is_set`'s.
    validator=DataclassValidator(CreateEventInput),
    # Then the board's rule, and the reason a write here can be refused while
    # the caller is entitled to make it: a taken slot is a failed call the
    # model reads, and the run goes on.
    preconditions=[title_is_set, slot_is_free],
    presenter=DataclassPresenter(EventRow),
    # The other refusal, and the one that ends the run. Booking needs the model
    # permission, so a user without it is answered `-32006`, which the bridge
    # raises as Django's `PermissionDenied` rather than handing the model a
    # failed call it could answer by trying again.
    permissions=[HoldsPermission("board.add_event")],
)

# Off by default, `tools/list` shows every tool to every caller and leaves the
# refusal to the call. On, a user is listed only what their permissions allow,
# which is what a deployment would want a model to be offered.
server = MCPServer(
    name="gallery-board",
    config=build_mcp_config(filter_listings_by_permissions=True),
)
server.register_tool(
    list_events_spec,
    name="list_events",
    # The label the component draws on the call's card. It reaches the browser
    # through the mount's tool catalog, which reads it off this registration;
    # a `service_specs=` tool has no such field and is labelled by its name.
    title="Read the board",
    description="Every event on the acting user's board, scheduled and in the backlog.",
    # A page with `nextCursor` rather than an unbounded list, which the server
    # warns about at registration: a model reading a clipped list as complete
    # is the failure a page envelope exists to prevent.
    paginate=True,
)
server.register_tool(
    create_event_spec,
    name="create_event",
    title="Book an event",
    description=(
        "Add an event to the board: scheduled when given a day and an hour, "
        "otherwise in the backlog."
    ),
    # Listed for everyone, including a user the call will refuse, as the one
    # exception to the filter above. Without it the model never sees the write
    # and the refusal is unreachable; with it the model is offered a write it
    # may be refused, and a refusal ends the run. A deployment that would rather
    # the tool not exist for such a user leaves this off.
    always_listed=True,
)

VIEW_URI = "ui://gallery-board/overview"

VIEW_BODY = """
<style>
#mcp-app-root { background: Canvas; color: CanvasText; padding: 8px; border-radius: 6px; }
</style>
<h3>Board overview</h3>
<p id="counts">Waiting for the result...</p>
<p><button id="load" type="button">Hours per room</button>
<button id="full" type="button">Fullscreen</button></p>
<pre id="out" style="min-height: 2.5em"></pre>
<script>
var out = document.getElementById("out");
mcpApp.onToolResult = function (data) {
  document.getElementById("counts").textContent =
    data.scheduled + " scheduled, " + data.backlog + " in the backlog";
};
document.getElementById("load").onclick = function () {
  mcpApp.callTool("room_load", {}).then(function (r) {
    out.textContent = JSON.stringify(r.structuredContent.hours);
  });
};
var mode = "inline";
mcpApp.onHostContext = function (context) {
  mode = context.displayMode || mode;
};
document.getElementById("full").onclick = function () {
  mcpApp.requestDisplayMode(mode === "fullscreen" ? "inline" : "fullscreen");
};
</script>
"""

server.register_ui_resource(
    name="board_overview_view",
    uri=VIEW_URI,
    html=build_app_document(VIEW_BODY, title="Board overview"),
    title="Board overview",
    description="Counts of scheduled and backlog events, and hours booked per room.",
)
server.register_tool(
    board_overview_spec,
    name="show_board",
    title="Show the board",
    description="Draw the board overview: how many events are scheduled and in the backlog.",
    ui=UIToolMeta(resource_uri=VIEW_URI),
    include_structured_content=True,
)
server.register_tool(
    room_load_spec,
    name="room_load",
    title="Hours per room",
    description="Hours booked in each room. Called by the board view, never by the model.",
    ui=UIToolMeta(resource_uri=VIEW_URI, visibility=[UIVisibility.APP]),
    include_structured_content=True,
)

agent = AGUIServer(
    ToolRegistry(),
    id="mcp",
    name="Board over MCP",
    description="Reads and books on the board through its MCP server.",
    model=build_demo_model(),
    instructions=INSTRUCTIONS,
    mcp_server=server,
    # Its own scope, for the reason the other two mounts give theirs: one table,
    # one person, and an unscoped drawer would list another agent's threads.
    conversation_store=ScopedConversationStore(DefaultConversationStore(), scope="mcp"),
    audit_logger=LoggingAuditLogger(),
    get_user=token_user,
    # The board mount keeps the default, and two mounts sharing one namespace
    # cannot both be reversed.
    namespace="mcp_agent",
    # A child session's mount: the board agent starts threads here, which run headless
    # (hence the run and step stores) and report through the shared inbox.
    run_store=run_store,
    step_store=DefaultStepStore,
    inbound_queue=inbound_queue,
    child_threads=runner,
    capabilities=[drain("mcp")],
    # Gated without naming the write. The bridge marks a tool destructive from
    # the annotations the server lists, and a service tool is not read-only, so
    # the guard defers `create_event` on that alone. The board mount next door
    # names its writes in `require_approval` instead.
    config=build_ag_ui_config(
        tool_guard=ToolGuardConfig(enabled=True),
        approval_prompts={"create_event": "Add this event to the board?"},
    ),
)
