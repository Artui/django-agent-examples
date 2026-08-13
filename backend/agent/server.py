"""The AG-UI mount every frontend in the gallery points at.

One `AGUIServer`, constructed once at import: the tool registry, the board's spec
registry, a conversation store so history survives a reload, and the `get_user`
hook that establishes who is acting.
"""

from __future__ import annotations

from django_ag_ui import AGUIServer, SkillRegistry, build_ag_ui_config
from django_pydantic_agent import ToolGuardConfig
from django_pydantic_agent.contrib.store.default_attachment_store import (
    DefaultAttachmentStore,
)
from django_pydantic_agent.contrib.store.default_conversation_store import (
    DefaultConversationStore,
)

from agent.auth import token_user
from agent.model import build_demo_model
from agent.tools import registry as tool_registry
from board.specs import registry as spec_registry

INSTRUCTIONS = """
You drive a scheduling board for the user. The board is the source of truth: read
it with `read_page` before acting on it, and address events and slots by the ids
the page reports. Prefer driving the page (scrolling, dragging) over describing
what the user should do. Say what changed, in one sentence.
""".strip()

skills = SkillRegistry()
# No prompt text: the client sends the bare token and the agent decides what it
# means, so nothing internal is published to anyone who can reach the catalog.
skills.add("tidy-week", title="Tidy up my week", chip=True)
skills.add("what-is-on", title="What is on the board?", chip=True)

agent = AGUIServer(
    tool_registry,
    model=build_demo_model(),
    instructions=INSTRUCTIONS,
    # The board's operations, declared once in board/specs.py, reaching the
    # agent as tools with no MCP hop in the path.
    service_specs=spec_registry,
    skills=skills,
    conversation_store=DefaultConversationStore(),
    # Uploads. One argument turns on three things at once: the composer grows a
    # clip, `attachments/` is mounted beside the run endpoint, and the agent gains
    # a per-request `read_attachment` tool scoped to the acting user.
    #
    # What travels on the wire is a *ref* -- an id, a name, a type and a size --
    # so the bytes go up once, out of band, and every later turn resends four
    # short fields instead of a base64 file. The model is told a file exists
    # through the manifest the server derives from those refs, and it reaches the
    # content by asking, server-side, for the id.
    #
    # The frontends still have to point at it: without `data-attachments-url` the
    # endpoint exists and the composer has no clip. That is the seam a host can
    # replace wholesale (`uploadHandler`) to upload straight to S3 instead.
    attachment_store=DefaultAttachmentStore(),
    # Token in a header, so no ambient cookie authority is involved and CSRF
    # does not apply. A cookie-authenticated deployment must instead pass
    # `csrf_exempt=False` and send the CSRF token from the client.
    get_user=token_user,
    # The server-side half of confirmation, and it is a different mechanism from
    # the one the apps already show. `confirmPredicate` gates a *page action* in
    # the browser: the element asks before it dispatches, and the server never
    # hears about the refusal. This gates a *service tool* inside the agent loop:
    # the call is deferred rather than executed, the run finishes on an interrupt,
    # the component renders the approval card, and the loop resumes with the
    # answer. Nothing runs until it does, which is the difference that matters for
    # a write.
    #
    # The board's writes are named explicitly because a spec tool carries no
    # destructiveness of its own: the guard reads `@tool(destructive=True)` off
    # the registry and `readOnlyHint` off drf-mcp's metadata, and a spec reaching
    # the agent in-process goes through neither.
    #
    # Per endpoint, not per project: this is `config=`, so the admin mount next
    # door keeps its own policy. `TOOL_GUARD` in settings would set the default
    # for both.
    config=build_ag_ui_config(
        tool_guard=ToolGuardConfig(
            enabled=True,
            require_approval=frozenset({"move_event", "reorder_event", "create_event"}),
        ),
        # What the card actually asks. Without these the question is the call
        # spelled out -- `Approve create_event({"title": "Design sync", ...})?` --
        # which is accurate and not something to put in front of a person. A
        # registry tool would carry its own `confirm=`; a spec tool has no such
        # field, so the wording lives here, beside the policy that gates it.
        approval_prompts={
            "create_event": "Add this event to the board?",
            "move_event": "Move this event, saving straight away?",
            "reorder_event": "Reorder the backlog?",
        },
    ),
)
