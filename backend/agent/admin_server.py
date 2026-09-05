"""The admin surface's agent mount.

`AdminAgentServer` is the same `AGUIServer` underneath, pre-configured for the
admin: the admin tool registry, and a staff gate that fails closed. What is worth
comparing against `agent/server.py` is everything that differs:

- **The principal is a session**, not a header token, so `csrf_exempt=False` and
  the sidebar sends the CSRF token. On the SPA mount there is no cookie, so the
  default exemption is correct there and would be a hole here.
- **The tools drive server-rendered pages.** A save, a filter, a navigation is a
  full reload, and the tools that cause one carry `x-navigates` so the component
  checkpoints the run and resumes it on the page it lands on. None of the
  single-page apps in this gallery exercise that path.
- **No `service_specs`.** The board's operations reach this agent through the
  admin's own ORM tools instead, which is the more honest comparison: this is what
  an admin integration looks like with nothing bespoke added.
"""

from __future__ import annotations

from django_admin_agent import AdminAgentServer
from django_pydantic_agent.contrib.store.default_conversation_store import (
    DefaultConversationStore,
)
from django_pydantic_agent.policy.audit.logging_audit_logger import LoggingAuditLogger

from agent.model import build_demo_model

INSTRUCTIONS = """
You operate a Django admin on the user's behalf. Read the page before acting on
it, prefer the typed admin tools over generic DOM ones, and remember that a save
or a filter reloads the page. Say what changed, in one sentence.
""".strip()

agent = AdminAgentServer(
    model=build_demo_model(),
    instructions=INSTRUCTIONS,
    conversation_store=DefaultConversationStore(),
    # The admin authenticates with a session cookie, so CSRF applies. The sidebar
    # sends the token; without this the endpoint would let any third-party page
    # drive the admin as the logged-in staff user.
    csrf_exempt=False,
    # The same reason the board mount sets one, and the same consequence for
    # leaving it unset: ``RUN_ERROR`` is redacted to a fixed sentence because an
    # exception's words are written for an operator, and the default
    # ``audit_logger`` is a null one -- so a mount that configures neither
    # redacts the failure to the browser and then drops it, and the reason
    # reaches nobody. This mount had that gap while the board mount documented
    # it two files away.
    audit_logger=LoggingAuditLogger(),
)
