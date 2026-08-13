"""Server-side tools, alongside the spec tools.

The board's own operations reach the agent as spec tools (see `board/specs.py`),
so what belongs here is anything that is not a board operation. One tool, to
show the registry path and to give the tool catalog a second kind of entry.
"""

from __future__ import annotations

from collections import Counter

from django_ag_ui import ToolCategory, ToolRegistry, tool
from django_pydantic_agent import AgentDeps
from pydantic_ai import RunContext

from board.models import Event

registry = ToolRegistry()


@tool(registry, category=ToolCategory.INTROSPECT, summary="Week overview")
def week_overview(ctx: RunContext[AgentDeps]) -> str:
    """Summarise the acting user's week: how many events per day, and the backlog size."""
    events = Event.objects.filter(owner=ctx.deps.user)
    per_day = Counter(event.day.isoformat() for event in events if event.day is not None)
    backlog = sum(1 for event in events if event.day is None)
    if not per_day and not backlog:
        return "The board is empty."
    scheduled = ", ".join(f"{day}: {count}" for day, count in sorted(per_day.items()))
    return f"Scheduled per day: {scheduled}. Backlog: {backlog}."
