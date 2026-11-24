from __future__ import annotations

from typing import Any

from django_ag_ui import AGUIHeadlessRunner
from django_spec_agents import (
    ChildSessionLimits,
    DrainInbound,
    ScopedConversationStore,
    WakingInboundQueue,
)
from django_spec_agents.child_sessions.child_sessions_toolset import ChildSessionsToolset
from django_spec_agents.contrib.store.default_child_session_index import (
    DefaultChildSessionIndex,
)
from django_spec_agents.contrib.store.default_conversation_store import (
    DefaultConversationStore,
)
from django_spec_agents.contrib.store.default_inbound_queue import DefaultInboundQueue
from django_spec_agents.contrib.store.default_run_store import DefaultRunStore

# Each child run's deadline, and each run a report or an answer wakes.
CHILD_TIMEOUT = 300.0

# One of each for every mount: a child on one mount reports into its parent's inbox on
# another, and the index reads both mounts' runs, so two stores would not see each other.
run_store = DefaultRunStore()
inbox = DefaultInboundQueue()
index = DefaultChildSessionIndex(run_store)


class MountsRunner:
    """The headless runner over both mounts, built on first use: both mounts import this module."""

    def __init__(self) -> None:
        self._built: AGUIHeadlessRunner | None = None

    def __call__(self) -> AGUIHeadlessRunner:
        if self._built is None:
            from agent.mcp_server import agent as mcp
            from agent.server import agent as board

            self._built = AGUIHeadlessRunner(board, mcp, index=index)
        return self._built

    def __getattr__(self, name: str) -> Any:
        return getattr(self(), name)


runner = MountsRunner()

# Every message wakes its thread: a child's report starts the idle parent's next run.
inbound_queue = WakingInboundQueue(
    inbox,
    runner,
    run_store,
    CHILD_TIMEOUT,
    conversations={
        "board": ScopedConversationStore(DefaultConversationStore(), scope="board"),
        "mcp": ScopedConversationStore(DefaultConversationStore(), scope="mcp"),
    },
)


def drain(agent_id: str) -> DrainInbound:
    """What hands a mount's threads their reports, questions, answers and steering."""
    return DrainInbound(inbox, agent_id)


def child_sessions() -> ChildSessionsToolset:
    """The board agent's tools to start a child session on the MCP agent and follow it."""
    return ChildSessionsToolset(
        "board",
        agents={"mcp": "Reads the board through its MCP server and answers one question."},
        runner=runner,
        index=index,
        queue=inbound_queue,
        limits=ChildSessionLimits(timeout=CHILD_TIMEOUT),
    )
