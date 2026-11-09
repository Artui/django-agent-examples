"""A sub-agent the board's agents hand one question to, and how they hand it.

The planner answers a single kind of question -- which hours of a day are still
free -- in a run of its own: its own model, its own one tool, and no sight of the
conversation that asked. That is the shape delegation is for. The parent says
*what* it wants in one self-contained task, the child works it out, and only the
answer comes back as the parent's tool result.

Two pieces of the family meet here, and neither knows about the other.

- **`SubAgents`** is pydantic-ai-harness's capability. It gives the parent one
  `delegate_task(agent_name, task)` tool and lists the planner in the parent's
  instructions, so the model can find it without this file writing a prompt.
- **`SubAgentObserver`** is django-ag-ui's wrapper around it, and the only reason
  the browser hears about any of this. A delegation runs to completion inside
  one tool call, and a tool call is silent between its arguments and its result,
  so unwrapped the chat would show a `delegate_task` card that simply waits.
  Wrapped, the transport opens the delegation with the protocol's own
  `SUBAGENT_STARTED`, closes it with `SUBAGENT_FINISHED` (or `_ERROR`), and
  reports each tool the child calls in between on a `CUSTOM` event. The web
  component draws all three onto the card it already drew for the call.

Both mounts take one, built by `delegation()`: the board mount for the four
single-page apps, and the admin mount for the sidebar. A fresh capability per
mount rather than one shared, because the observer installs its event handler
on the instance it wraps and the instance carries per-run state.

The planner reads the database and writes nothing, on purpose: a write inside a
delegation would raise the question of whose approval card gates it, and that is
a different demonstration from this one.
"""

from __future__ import annotations

import datetime
from typing import Any

from django_ag_ui import SubAgentObserver
from django_spec_agents import AgentDeps
from pydantic_ai import Agent, RunContext
from pydantic_ai_harness import SubAgent, SubAgents

from agent.model import build_planner_model
from board.models import Event

# The hours the board's grid draws. A slot outside them cannot be dropped on,
# so calling it free would offer the user something the page cannot show.
BOARD_HOURS = range(8, 19)


def free_hours(ctx: RunContext[AgentDeps], day: str) -> dict[str, Any]:
    """The hours on `day` (an ISO date) where nothing on the acting user's board starts."""
    held = set(
        Event.objects.filter(owner=ctx.deps.user, day=datetime.date.fromisoformat(day))
        .exclude(start_hour=None)
        .values_list("start_hour", flat=True)
    )
    # "Free" is the board's own rule, `slot_is_free`: a slot is held when an
    # event starts in it. Duration is not read there, so it is not read here
    # either -- a planner stricter than the write it plans for would turn away
    # slots a booking would accept.
    return {"day": day, "free": [hour for hour in BOARD_HOURS if hour not in held]}


planner: Agent[AgentDeps, str] = Agent(
    build_planner_model(),
    name="planner",
    description="Finds the free hours on one day of the user's board.",
    deps_type=AgentDeps,
    instructions=(
        "You find free hours on a scheduling board. Call `free_hours` for the day "
        "the task names and answer with the free hours, in one sentence."
    ),
    tools=[free_hours],
)


def planner_subagents() -> SubAgents:
    """The bare delegation, with no observer: what `delegation()` wraps."""
    return SubAgents(agents=[SubAgent(planner)])


def delegation() -> SubAgentObserver:
    """A delegation capability for one mount: the planner, observed."""
    return SubAgentObserver(planner_subagents())
