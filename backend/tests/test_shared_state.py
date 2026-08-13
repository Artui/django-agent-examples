"""AG-UI shared state: the channel that is not a tool call.

The board's view and filter reach the agent as `read_board` / `set_board`, which
are ordinary tool calls — they land in the transcript and a confirmation card can
gate them. The week note is the other channel: it rides `RunAgentInput.state`, a
tool rewrites it, and the change comes back as a `STATE_SNAPSHOT` event rather
than as a tool result.

Asserted off the wire, because the snapshot *is* wire: what the model sees
(`return_value`) and what the client sees (`metadata`) are different things, and
only the stream shows the second.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from board.models import Event

AUTH = {"authorization": "Token demo-token-not-a-secret"}


@pytest.mark.django_db(transaction=True)
async def test_the_agent_reads_the_note_the_page_sent() -> None:
    await _seed()

    events = await _run("what does the note say?", state={"note": "ship the gallery"})

    assert _tool_calls(events) == ["read_week_note"]
    assert "ship the gallery" in _text(events)


@pytest.mark.django_db(transaction=True)
async def test_writing_the_note_streams_a_state_snapshot() -> None:
    """The page re-renders off this event, not off the tool result."""
    await _seed()

    events = await _run("note: ship the gallery this week", state={"note": ""})

    assert _tool_calls(events) == ["write_week_note"]
    assert _snapshots(events) == [{"note": "ship the gallery this week"}]


@pytest.mark.django_db(transaction=True)
async def test_the_snapshot_keeps_the_rest_of_the_state() -> None:
    """A tool that owns one key must not drop the keys it does not."""
    await _seed()

    events = await _run("note: written", state={"note": "old", "theme": "dark"})

    assert _snapshots(events) == [{"note": "written", "theme": "dark"}]


@pytest.mark.django_db(transaction=True)
async def test_summarising_the_week_into_the_note_takes_two_tools() -> None:
    """Two tools in **one request**, the second's argument being the first's result.

    Both are server-side, so the loop never returns to the browser between them —
    unlike a page action, whose result the client has to post back. So the client
    sees one stream carrying two tool calls and one snapshot, and the note it
    renders was composed by a tool it never executed.
    """
    await _seed()

    events = await _run("summarise the week into the note", state={"note": ""})

    assert _tool_calls(events) == ["week_overview", "write_week_note"]
    written = _snapshots(events)[0]["note"]
    assert "Scheduled per day" in written and "2026-08-10" in written


@pytest.mark.django_db(transaction=True)
async def test_reading_the_board_is_still_a_tool_and_not_state() -> None:
    """The contrast, asserted: a board read produces no snapshot at all."""
    await _seed()

    events = await _run("what is on the board?", state={"note": "untouched"})

    assert _tool_calls(events) == ["list_events"]
    assert _snapshots(events) == []


# --- driving the endpoint the way the web component does -----------------------


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=user, title="Standup", day="2026-08-10", start_hour=9)


async def _run(prompt: str, *, state: dict[str, Any]) -> list[dict[str, Any]]:
    return await _run_messages([_user_message(prompt)], state=state)


async def _run_messages(
    messages: list[dict[str, Any]], *, state: dict[str, Any]
) -> list[dict[str, Any]]:
    payload = {
        "threadId": "thread-state",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": messages,
        "tools": [],
        "context": [],
        # The element sends this on every run; that is the whole outbound half.
        "state": state,
        "forwardedProps": {},
    }
    response = await AsyncClient().post(
        "/agent/", data=json.dumps(payload), content_type="application/json", headers=AUTH
    )
    assert response.status_code == 200, response.content[:400]
    events: list[dict[str, Any]] = []
    async for chunk in response.streaming_content:
        for line in chunk.decode().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _user_message(content: str) -> dict[str, Any]:
    return {"id": f"m-{uuid.uuid4().hex[:6]}", "role": "user", "content": content}


def _answered(events: list[dict[str, Any]], result: str) -> list[dict[str, Any]]:
    start = next(e for e in events if e.get("type") == "TOOL_CALL_START")
    call_id = start["toolCallId"]
    return [
        {
            "id": f"a-{call_id}",
            "role": "assistant",
            "content": "",
            "toolCalls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": start["toolCallName"], "arguments": "{}"},
                }
            ],
        },
        {"id": f"t-{call_id}", "role": "tool", "toolCallId": call_id, "content": result},
    ]


def _tool_calls(events: list[dict[str, Any]]) -> list[str]:
    return [e["toolCallName"] for e in events if e.get("type") == "TOOL_CALL_START"]


def _snapshots(events: list[dict[str, Any]]) -> list[Any]:
    return [e["snapshot"] for e in events if e.get("type") == "STATE_SNAPSHOT"]


def _text(events: list[dict[str, Any]]) -> str:
    return "".join(e["delta"] for e in events if e.get("type") == "TEXT_MESSAGE_CONTENT")
