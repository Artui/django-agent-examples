"""The server-side approval loop, driven the way the web component drives it.

The apps already show a client-side confirmation: `confirmPredicate` asks before
the element dispatches a page action, and a refusal never leaves the browser.
This is the other mechanism, and it is the one that matters for a write. A gated
service tool is *deferred* instead of executed: the run finishes carrying an
interrupt, the client answers it in the next `RunAgentInput`, and only then does
the tool run.

Everything here is asserted off the wire, because the two halves of the loop are
a wire contract: `RUN_FINISHED` with an `interrupt` outcome going out, a `resume`
array coming back. A round-trip through the component would prove agreement
rather than correctness.
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

# Deliberately none of the board's page actions: this turn never touches the page,
# so the only tools on offer are the server's own.
NO_CLIENT_TOOLS: list[dict[str, Any]] = []


@pytest.mark.django_db(transaction=True)
async def test_a_gated_write_defers_instead_of_running() -> None:
    """The run finishes on an interrupt, and the row is not there yet."""
    await _seed()

    events = await _run(_user_message("add a design sync to the backlog"))

    assert _tool_calls(events) == ["create_event"], "the model still calls the tool"
    interrupts = _interrupts(events)
    assert len(interrupts) == 1
    assert interrupts[0]["toolCallId"] == _tool_call_ids(events)[0]
    assert not await Event.objects.filter(title="Design sync").aexists(), (
        "a deferred call must not have written anything"
    )


@pytest.mark.django_db(transaction=True)
async def test_approving_the_interrupt_runs_the_tool_and_the_agent_reports_it() -> None:
    """The resumed run executes the write and hands the result back to the model."""
    await _seed()
    messages = [_user_message("add a design sync to the backlog")]
    deferred = await _run(*messages)

    resumed = await _run(*messages, *_deferred_call(deferred), resume=_approve(deferred))

    event = await Event.objects.aget(title="Design sync")
    assert event.day is None, "no day and hour means the backlog, which is the service's rule"
    assert "backlog" in _text(resumed).lower()
    assert _interrupts(resumed) == [], "the resumed run finishes normally"


@pytest.mark.django_db(transaction=True)
async def test_denying_the_interrupt_writes_nothing_and_the_agent_says_so() -> None:
    """A denial arrives as a tool return, so the model reads it like any result."""
    await _seed()
    messages = [_user_message("add a design sync to the backlog")]
    deferred = await _run(*messages)

    settled = await _run(*messages, *_deferred_call(deferred), resume=_deny(deferred))

    assert not await Event.objects.filter(title="Design sync").aexists()
    assert "nothing was booked" in _text(settled).lower()


@pytest.mark.django_db(transaction=True)
async def test_a_scheduled_booking_carries_the_day_and_hour_through_the_gate() -> None:
    """The arguments the user approved are the arguments that run."""
    await _seed()
    messages = [_user_message("book a design sync on 2026-08-14 at 14:00")]
    deferred = await _run(*messages)

    assert _arguments(deferred) == {
        "title": "Design sync",
        "day": "2026-08-14",
        "start_hour": 14,
    }

    await _run(*messages, *_deferred_call(deferred), resume=_approve(deferred))

    event = await Event.objects.aget(title="Design sync")
    assert (str(event.day), event.start_hour) == ("2026-08-14", 14)


@pytest.mark.django_db(transaction=True)
async def test_a_read_is_not_gated() -> None:
    """The policy names the writes, so a read still answers in one round."""
    await _seed()

    events = await _run(_user_message("what is on the board?"))

    assert _tool_calls(events) == ["list_events"]
    assert _interrupts(events) == []
    assert "scheduled" in _text(events)


@pytest.mark.django_db(transaction=True)
async def test_a_weekday_booking_lands_on_that_weekday() -> None:
    """No page in the path, so this is the one turn where the script picks a date."""
    await _seed()
    messages = [_user_message("book a design sync on Friday at 14:00")]
    deferred = await _run(*messages)

    await _run(*messages, *_deferred_call(deferred), resume=_approve(deferred))

    event = await Event.objects.aget(title="Design sync")
    assert event.day is not None
    assert event.day.weekday() == 4, "Friday"


# --- driving the endpoint the way the web component does -----------------------


def _deferred_call(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The assistant message the resumed request has to carry.

    The `resume` array answers an interrupt; it does not describe the call being
    resumed. The pending call itself lives in `messages`, exactly as any other
    assistant turn does, and there is no tool message beside it because nothing
    has run yet. Send the answer without the call and the run has no deferred
    request to attach it to.
    """
    start = next(event for event in events if event.get("type") == "TOOL_CALL_START")
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
                    "function": {
                        "name": start["toolCallName"],
                        "arguments": _raw_arguments(events) or "{}",
                    },
                }
            ],
        }
    ]


def _approve(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"interruptId": interrupt["id"], "status": "resolved", "payload": {"approved": True}}
        for interrupt in _interrupts(events)
    ]


def _deny(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"interruptId": interrupt["id"], "status": "cancelled"}
        for interrupt in _interrupts(events)
    ]


def _interrupts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The interrupts a run finished on, read out of `RUN_FINISHED.outcome`.

    They travel inside the outcome rather than beside it, so a producer that
    knows nothing about interrupts simply omits the field.
    """
    for event in events:
        if event.get("type") == "RUN_FINISHED":
            outcome = event.get("outcome") or {}
            if outcome.get("type") == "interrupt":
                return list(outcome["interrupts"])
    return []


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=user, title="Standup", day="2026-08-10", start_hour=9)


async def _run(
    *messages: dict[str, Any], resume: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "threadId": "thread-approval",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": list(messages),
        "tools": NO_CLIENT_TOOLS,
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    if resume is not None:
        payload["resume"] = resume
    response = await AsyncClient().post(
        "/agent/",
        data=json.dumps(payload),
        content_type="application/json",
        headers=AUTH,
    )
    assert response.status_code == 200, response.content[:400]
    events: list[dict[str, Any]] = []
    async for chunk in response.streaming_content:
        for line in chunk.decode().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _user_message(content: str) -> dict[str, Any]:
    return {"id": f"msg-{uuid.uuid4().hex[:8]}", "role": "user", "content": content}


def _tool_calls(events: list[dict[str, Any]]) -> list[str]:
    return [event["toolCallName"] for event in events if event.get("type") == "TOOL_CALL_START"]


def _tool_call_ids(events: list[dict[str, Any]]) -> list[str]:
    return [event["toolCallId"] for event in events if event.get("type") == "TOOL_CALL_START"]


def _raw_arguments(events: list[dict[str, Any]]) -> str:
    return "".join(
        event["delta"] for event in events if event.get("type") == "TOOL_CALL_ARGS"
    )


def _arguments(events: list[dict[str, Any]]) -> dict[str, Any]:
    raw = _raw_arguments(events)
    return json.loads(raw) if raw else {}


def _text(events: list[dict[str, Any]]) -> str:
    return "".join(
        event["delta"] for event in events if event.get("type") == "TEXT_MESSAGE_CONTENT"
    )
