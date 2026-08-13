"""Driving the agent endpoint the way the web component drives it.

Shared by the tests that assert on the protocol rather than on the database. Both
halves of a deferred call are a wire contract — `RUN_FINISHED` carrying an
interrupt going out, a `resume` array coming back — so these read events off the
SSE stream and build requests as literal JSON. A round-trip through the component
would prove the two agree, not that either is right.

Nothing here is application code; it is the client, written out.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import AsyncClient

AUTH = {"authorization": "Token demo-token-not-a-secret"}

# The default: no page is involved, so the only tools on offer are the server's
# own. A test that drives a page declares its tools with `tools=`, exactly as a
# browser does — the client's list is what makes a frontend tool exist.
NO_CLIENT_TOOLS: list[dict[str, Any]] = []


@dataclass(frozen=True)
class Call:
    """One tool call, with its argument deltas reassembled."""

    id: str
    name: str
    raw_arguments: str

    @property
    def arguments(self) -> dict[str, Any]:
        return json.loads(self.raw_arguments) if self.raw_arguments else {}


async def run(
    *messages: dict[str, Any],
    resume: list[dict[str, Any]] | None = None,
    thread: str = "thread-test",
    tools: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """POST one `RunAgentInput` and collect the events it streams back."""
    payload: dict[str, Any] = {
        "threadId": thread,
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": list(messages),
        "tools": NO_CLIENT_TOOLS if tools is None else tools,
        "context": [],
        "state": {} if state is None else state,
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


async def upload(content: bytes, *, name: str, mime: str) -> dict[str, Any]:
    """Upload one file and return the ref the server issued.

    Out of band, before any run: the bytes go to `attachments/` over multipart and
    what comes back is four short fields. That ref is what a message carries.
    """
    response = await AsyncClient().post(
        "/agent/attachments/",
        data={"file": SimpleUploadedFile(name, content, content_type=mime)},
        headers=AUTH,
    )
    assert response.status_code == 201, response.content[:400]
    ref: dict[str, Any] = json.loads(response.content)
    return ref


def user_message(
    content: str, attachments: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """A user turn, with the attachment refs the composer rides on it.

    `attachments` is not an AG-UI field. `RunAgentInput` validates with
    `extra="allow"`, so it arrives intact and the adapter ignores it; the server
    reads it only to build the manifest.
    """
    message: dict[str, Any] = {
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": "user",
        "content": content,
    }
    if attachments:
        message["attachments"] = attachments
    return message


def calls(events: list[dict[str, Any]]) -> list[Call]:
    """Every tool call in the stream, in the order it started."""
    names: dict[str, str] = {}
    deltas: dict[str, list[str]] = {}
    for event in events:
        if event.get("type") == "TOOL_CALL_START":
            names[event["toolCallId"]] = event["toolCallName"]
            deltas.setdefault(event["toolCallId"], [])
        elif event.get("type") == "TOOL_CALL_ARGS":
            deltas.setdefault(event["toolCallId"], []).append(event["delta"])
    return [
        Call(id=call_id, name=name, raw_arguments="".join(deltas[call_id]))
        for call_id, name in names.items()
    ]


def tool_calls(events: list[dict[str, Any]]) -> list[str]:
    return [call.name for call in calls(events)]


def interrupts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def transcript(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The run rebuilt as messages, which is what the next request has to resend.

    The client is the one holding the conversation, so a resumed or continued run
    carries everything that happened: the assistant turns, their tool calls, and
    the results of the calls that ran. `parentMessageId` on each `TOOL_CALL_START`
    says which assistant turn a call belonged to, so three calls the model made
    together stay one message rather than becoming three.

    This is also what makes an interrupt answerable. The `resume` array answers
    one; it does not describe it. The deferred call itself is here, in an
    assistant message with no tool result beside it, because nothing ran — send
    the answer without the call and the run has no pending request to attach it
    to.
    """
    messages: list[dict[str, Any]] = []
    by_parent: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event.get("type")
        if kind == "TEXT_MESSAGE_START":
            messages.append({"id": event["messageId"], "role": "assistant", "content": ""})
        elif kind == "TEXT_MESSAGE_CONTENT":
            messages[-1]["content"] += event["delta"]
        elif kind == "TOOL_CALL_START":
            parent = event.get("parentMessageId") or event["toolCallId"]
            if parent not in by_parent:
                by_parent[parent] = {
                    "id": parent,
                    "role": "assistant",
                    "content": "",
                    "toolCalls": [],
                }
                messages.append(by_parent[parent])
            by_parent[parent]["toolCalls"].append(
                {
                    "id": event["toolCallId"],
                    "type": "function",
                    "function": {"name": event["toolCallName"], "arguments": ""},
                }
            )
        elif kind == "TOOL_CALL_ARGS":
            _append_arguments(messages, event["toolCallId"], event["delta"])
        elif kind == "TOOL_CALL_RESULT":
            messages.append(
                {
                    "id": event["messageId"],
                    "role": "tool",
                    "toolCallId": event["toolCallId"],
                    "content": event["content"],
                }
            )
    return messages


def _append_arguments(messages: list[dict[str, Any]], call_id: str, delta: str) -> None:
    for message in messages:
        for call in message.get("toolCalls") or []:
            if call["id"] == call_id:
                call["function"]["arguments"] += delta
                return


def answered(
    history: list[dict[str, Any]], events: list[dict[str, Any]], result: Any
) -> list[dict[str, Any]]:
    """`history` plus the run that just happened plus the frontend tool's result.

    A **frontend** tool ends the run rather than suspending it: the server has no
    way to execute something that lives in a browser, so it streams the call and
    stops. The client runs it, appends the result as a tool message, and posts the
    whole conversation again. Nothing is deferred and no interrupt is involved —
    the contrast with `resume` is worth keeping straight, because both look like
    "the run paused and came back" from the outside.

    Takes the previous messages and returns the whole conversation, so a multi-round
    turn accumulates rather than being reassembled: the client is the only thing
    holding the conversation, and forgetting the user's own turn is the easiest way
    to prove it (the run starts over against an empty prompt).

    `result` is whatever the browser would report: a page map, a string, a
    declined-action sentence.
    """
    pending = calls(events)
    assert pending, "no frontend tool was called, so there is nothing to answer"
    last = pending[-1]
    return [
        *history,
        *transcript(events),
        {
            "id": f"t-{last.id}",
            "role": "tool",
            "toolCallId": last.id,
            "content": result if isinstance(result, str) else json.dumps(result),
        },
    ]


def approve(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_resolved(interrupt) for interrupt in interrupts(events)]


def deny(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_cancelled(interrupt) for interrupt in interrupts(events)]


def decide(
    events: list[dict[str, Any]], approved: Callable[[Call], bool]
) -> list[dict[str, Any]]:
    """Answer each interrupt separately, by what the call it gates would do.

    The array is per interrupt, so a round that deferred three calls can have two
    approved and one refused — the shape a person clicking through three cards
    produces.
    """
    by_id = {call.id: call for call in calls(events)}
    return [
        _resolved(interrupt)
        if approved(by_id[interrupt["toolCallId"]])
        else _cancelled(interrupt)
        for interrupt in interrupts(events)
    ]


def text(events: list[dict[str, Any]]) -> str:
    return "".join(
        event["delta"] for event in events if event.get("type") == "TEXT_MESSAGE_CONTENT"
    )


def _resolved(interrupt: dict[str, Any]) -> dict[str, Any]:
    return {
        "interruptId": interrupt["id"],
        "status": "resolved",
        "payload": {"approved": True},
    }


def _cancelled(interrupt: dict[str, Any]) -> dict[str, Any]:
    return {"interruptId": interrupt["id"], "status": "cancelled"}
