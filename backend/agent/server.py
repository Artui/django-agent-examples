"""The AG-UI mount every frontend in the gallery points at.

One `AGUIServer`, constructed once at import: the tool registry, the board's spec
registry, a conversation store so history survives a reload, and the `get_user`
hook that establishes who is acting.
"""

from __future__ import annotations

from django_ag_ui import AGUIServer, SkillRegistry
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
    # Token in a header, so no ambient cookie authority is involved and CSRF
    # does not apply. A cookie-authenticated deployment must instead pass
    # `csrf_exempt=False` and send the CSRF token from the client.
    get_user=token_user,
)
