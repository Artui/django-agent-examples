"""A delegated question, read off the wire on both mounts that delegate.

The planner sub-agent answers inside one `delegate_task` call. Everything the
browser draws about that hand-off arrives on events the transport emits around
it, so these assert on those events' own fields rather than on the reply text:
a reply saying "the planner says" would read the same if the delegation had
been drawn as nothing at all.

The join is the thing to check. `SUBAGENT_STARTED.parentToolCallId` must be the
`toolCallId` of the `delegate_task` call already on screen, or the component
opens a second row instead of filling in the card it drew.
"""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import AsyncClient
from django.urls import path
from django_ag_ui import AGUIServer
from rest_framework.authtoken.models import Token

from agent.auth import token_user
from agent.delegation import planner_subagents
from agent.model import build_demo_model
from agent.scripted import WEEKDAYS, Turn, _planner_respond, _this_week
from agent.server import INSTRUCTIONS
from agent.tools import registry as tool_registry
from board.models import Event
from board.specs import registry as spec_registry
from tests.wire import calls, run, text, user_message

SUBAGENT = "ag_ui.subagent"

# A board mount whose delegation is the one `delegation()` wraps, left bare,
# with only the options the hand-off reads. Mounted only by the test that names
# this module as the URLconf.
unwrapped = AGUIServer(
    tool_registry,
    model=build_demo_model(),
    instructions=INSTRUCTIONS,
    service_specs=spec_registry,
    capabilities=[planner_subagents()],
    get_user=token_user,
)
urlpatterns = [path("unwrapped/", unwrapped.urls)]


def _friday() -> str:
    return _this_week("friday", datetime.date.today())


async def _owner(**flags: Any) -> Any:
    user = await get_user_model().objects.acreate(username="demo", **flags)
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    # Two of Friday's hours held, so the planner's answer has to read the board.
    await Event.objects.acreate(owner=user, title="Retro", day=_friday(), start_hour=16)
    await Event.objects.acreate(owner=user, title="Demo", day=_friday(), start_hour=9)
    return user


def _delegation(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The one delegation in a run, with every event that names it."""
    delegated = [call for call in calls(events) if call.name == "delegate_task"]
    assert len(delegated) == 1, [event["type"] for event in events]
    call = delegated[0]
    started = [event for event in events if event["type"] == "SUBAGENT_STARTED"]
    finished = [event for event in events if event["type"] == "SUBAGENT_FINISHED"]
    failed = [event for event in events if event["type"] == "SUBAGENT_ERROR"]
    steps = [
        event for event in events if event["type"] == "CUSTOM" and event.get("name") == SUBAGENT
    ]
    order = [event["type"] for event in events]
    return {
        "call": call,
        "started": started,
        "finished": finished,
        "failed": failed,
        "steps": steps,
        "order": order,
    }


def _assert_delegated_to_the_planner(events: list[dict[str, Any]]) -> None:
    seen = _delegation(events)
    call = seen["call"]
    assert call.arguments["agent_name"] == "planner"

    # Opened once, on the card already drawn for the call.
    assert len(seen["started"]) == 1
    started = seen["started"][0]
    assert started["parentToolCallId"] == call.id
    assert started["name"] == "planner"

    # Closed once, as a success, naming the same child run.
    assert seen["failed"] == []
    assert len(seen["finished"]) == 1
    assert seen["finished"][0]["subagentRunId"] == started["subagentRunId"]

    # The child's one tool call, reported as it was made and as it landed.
    phases = [(step["value"]["phase"], step["value"]["tool"]["name"]) for step in seen["steps"]]
    assert phases == [("tool_call", "free_hours"), ("tool_result", "free_hours")]
    assert {step["value"]["delegationId"] for step in seen["steps"]} == {call.id}
    assert seen["steps"][-1]["value"]["tool"]["ok"] is True

    # Ordered as a client verifies them: the steps inside the lifetime, and the
    # lifetime closed before the run is.
    order = seen["order"]
    opened = order.index("SUBAGENT_STARTED")
    closed = order.index("SUBAGENT_FINISHED")
    step_positions = [i for i, kind in enumerate(order) if kind == "CUSTOM"]
    assert all(opened < i < closed for i in step_positions)
    assert closed < order.index("RUN_FINISHED")


@pytest.mark.django_db(transaction=True)
async def test_the_board_agent_delegates_to_the_planner() -> None:
    await _owner()

    events = await run(user_message("ask the planner when Friday is free"))

    _assert_delegated_to_the_planner(events)
    # The child's answer reached the parent and was read off the board: the two
    # held hours are absent, the hour between them is not.
    said = text(events)
    assert "The planner says:" in said
    assert "10:00" in said
    assert "9:00" not in said and "16:00" not in said


@pytest.mark.django_db(transaction=True)
async def test_the_admin_agent_delegates_to_the_planner() -> None:
    user = await _owner(is_staff=True, is_superuser=True)
    client = AsyncClient()
    await sync_to_async(client.force_login)(user)
    payload = {
        "threadId": "thread-admin",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": [user_message("ask the planner when Friday is free")],
        # One admin frontend tool is enough to route the script to the admin's
        # branch, which is how the sidebar's runs are told apart.
        "tools": [
            {
                "name": "open_changelist",
                "description": "Navigate to a model's admin changelist.",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    response = await client.post(
        "/admin-agent/", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, response.content[:400]
    events: list[dict[str, Any]] = []
    async for chunk in response.streaming_content:
        for line in chunk.decode().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    _assert_delegated_to_the_planner(events)


@pytest.mark.django_db(transaction=True)
async def test_an_unwrapped_delegation_still_answers_only_unseen(settings: Any) -> None:
    """Without the observer the hand-off works and the browser hears nothing of it.

    The child then runs unstreamed, so this is also what holds the scripted
    planner to keeping its non-streamed half: without it the planner crashes
    and the answer never comes back.
    """
    settings.ROOT_URLCONF = __name__
    await _owner()

    events = await run(user_message("ask the planner when Friday is free"), path="/unwrapped/")

    order = [event["type"] for event in events]
    assert "RUN_ERROR" not in order, order
    assert order[-1] == "RUN_FINISHED", order
    # One hand-off, made the same way as on the wrapped mount.
    seen = _delegation(events)
    assert seen["call"].arguments["agent_name"] == "planner"
    # And nothing around it: no lifetime and no steps for the browser to draw.
    assert seen["started"] == [] and seen["finished"] == [] and seen["failed"] == []
    assert seen["steps"] == []
    # The planner still read the board and its answer still reached the parent.
    said = text(events)
    assert "The planner says:" in said
    assert "10:00" in said
    assert "9:00" not in said and "16:00" not in said


def test_the_planner_resolves_a_named_day_inside_the_week_on_screen() -> None:
    """Friday asked about on a Saturday is the Friday the grid shows, not next week's."""
    saturday = datetime.date(2026, 11, 7)
    assert WEEKDAYS[saturday.weekday()] == "saturday"

    [call] = _planner_respond(Turn(prompt="when is Friday free?", returns=()), saturday)

    assert json.loads(call[0].json_args) == {"day": "2026-11-06"}
