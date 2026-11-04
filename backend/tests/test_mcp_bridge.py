"""The MCP route, driven over the wire: `mcp_server=` and the in-process bridge.

`/mcp-agent/` is given an MCP server and no `service_specs=`, so every tool its
agent calls arrives through django-spec-agents' bridge to django-spec-mcp: the
server's own `tools/list` for the definitions, its own `tools/call` for the
call, acting as the user the endpoint resolved. Everything else in this suite
reaches the board's specs through the spec toolset, so this file is the one
place outside django-spec-agents' own tests where the bridge is measured.

Asserted on the events a browser receives (`tests/wire.py`), not on the toolset:
the claims are about what reaches the client, and the toolset is the thing
under test.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from agent.mcp_server import server
from board.models import Event
from tests.wire import (
    AUTH,
    approve,
    interrupts,
    run,
    text,
    tool_calls,
    transcript,
    user_message,
)

MOUNT = "/mcp-agent/"

# Signed in, with a token, and without `board.add_event`: entitled to read the
# board and refused a booking.
VISITOR = {"authorization": "Token visitor-token-not-a-secret"}


@pytest.mark.django_db(transaction=True)
async def test_a_read_goes_through_the_bridge_as_the_acting_user() -> None:
    """The call is made, answered by the server, and scoped to the token's user.

    The visitor's own event is on the same board table, so a bridge acting as
    anyone but the resolved user -- the request's anonymous session user, say --
    would show either nothing or both.

    The two routes stream a call identically, by design: a spec toolset handed
    these same specs would pass every assertion on the events below. What tells
    them apart in the browser is the catalog the component fetches to label the
    cards, which for this mount is read off the server's registrations, so it
    carries the `title` and `description` the server registered rather than a
    prettified name and the selector's docstring.
    """
    await _seed()

    catalog = await AsyncClient().get(f"{MOUNT}tools/", headers=AUTH)
    assert catalog.status_code == 200, catalog.content[:400]
    labels = {entry["name"]: entry for entry in json.loads(catalog.content)}
    assert labels["list_events"]["summary"] == "Read the board"
    assert labels["list_events"]["description"] == (
        "Every event on the acting user's board, scheduled and in the backlog."
    )
    assert labels["create_event"]["summary"] == "Book an event"

    events = await run(user_message("what is on the board?"), path=MOUNT)

    assert tool_calls(events) == ["list_events"]
    assert _errors(events) == []
    (result,) = _results(events)
    page = json.loads(result["content"])
    assert [row["title"] for row in page["items"]] == ["Standup"], (
        "a read is scoped to the acting user"
    )
    # The page envelope the server paginates into, so the model is told whether
    # it has the whole board.
    assert page["hasNext"] is False
    assert "You have 1 scheduled and 0 in the backlog." in text(events)


@pytest.mark.django_db(transaction=True)
async def test_a_bridged_write_is_gated_by_what_the_server_lists() -> None:
    """Deferred with no name in `require_approval`, and written once approved.

    The guard reads the destructiveness the bridge derives from the server's
    `annotations`, so the mount's policy names no tool at all.
    """
    await _seed()
    messages = [user_message("add a design sync to the backlog")]

    deferred = await run(*messages, path=MOUNT)

    assert tool_calls(deferred) == ["create_event"]
    assert len(interrupts(deferred)) == 1
    assert not await Event.objects.filter(title="Design sync").aexists()

    resumed = await run(*messages, *transcript(deferred), resume=approve(deferred), path=MOUNT)

    event = await Event.objects.aget(title="Design sync")
    assert event.day is None
    assert text(resumed) == "Added Design sync to the backlog."


@pytest.mark.django_db(transaction=True)
async def test_a_board_refusal_is_a_failed_call_and_the_run_goes_on() -> None:
    """The board's own rule refuses the slot; the model reads why and answers.

    `slot_is_free` raises the board's `SlotTaken`, the server answers it as a
    `service_error` result, and the bridge raises that as a failed call: marked
    failed for the card, with the reason in the content for the model.
    """
    await _seed()
    messages = [user_message("book a design sync on 2026-08-10 at 9:00")]
    deferred = await run(*messages, path=MOUNT)

    settled = await run(*messages, *transcript(deferred), resume=approve(deferred), path=MOUNT)

    assert _errors(settled) == []
    (result,) = _results(settled)
    assert (result.get("metadata") or {}).get("outcome") == "failed"
    assert "already held by 'Standup'" in result["content"]
    assert text(settled).startswith("The board refused that:")
    assert not await Event.objects.filter(title="Design sync").aexists()


@pytest.mark.django_db(transaction=True)
async def test_a_permission_refusal_through_the_bridge_ends_the_run(caplog: Any) -> None:
    """The server refuses the user, and the run stops rather than carrying on.

    The server answers `-32006`, which the bridge raises as Django's
    `PermissionDenied` and the tool-failure policy lets through, so the run
    ends on `RUN_ERROR`. Handed back as a failed call instead, the model would
    answer it -- and a model told "not permitted" for one id and "not found"
    for the next has learned which rows exist. So no tool result is streamed,
    the model never speaks, and the browser gets the transport's fixed
    sentences -- the card settled as interrupted, the run as failed -- while
    the reason goes to the audit log.
    """
    await _seed()
    messages = [user_message("add a design sync to the backlog")]
    deferred = await run(*messages, path=MOUNT, auth=VISITOR)
    assert tool_calls(deferred) == ["create_event"], "the write is listed to the visitor"

    # django-spec-agents kept the audit logger's old name.
    with caplog.at_level(logging.WARNING, logger="django_pydantic_agent.audit"):
        ended = await run(
            *messages, *transcript(deferred), resume=approve(deferred), path=MOUNT, auth=VISITOR
        )

    assert [event["type"] for event in ended if event["type"].startswith("RUN_")] == [
        "RUN_STARTED",
        "RUN_ERROR",
    ]
    assert _errors(ended)[0]["message"] == "The run failed. The failure has been recorded."
    # The open card is settled, failed, in the adapter's words and not the
    # server's: nothing about why reaches the browser or the model.
    (result,) = _results(ended)
    assert (result.get("metadata") or {}).get("outcome") == "failed"
    assert result["content"] == "Tool execution was interrupted by an error."
    assert text(ended) == "", "the model is not asked to answer the refusal"
    assert any("Insufficient permission" in record.getMessage() for record in caplog.records)
    assert not await Event.objects.filter(title="Design sync").aexists()


@pytest.mark.django_db(transaction=True)
async def test_a_blank_title_is_refused_as_the_other_routes_refuse_it() -> None:
    """The board's input serializer refuses a blank title, and the dataclass
    validator alone would not: the server would book an untitled event that
    `/agent/` and `/api/events/` turn away. Called on the server directly,
    because the scripted model never sends one."""
    await _seed()
    demo = await get_user_model().objects.aget(username="demo")

    answer = await server.acall_tool("create_event", {"title": "  "}, user=demo)

    assert answer["isError"] is True, answer
    assert "may not be blank" in json.dumps(answer)
    assert not await Event.objects.filter(title__regex=r"^\s*$").aexists()


def _results(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == "TOOL_CALL_RESULT"]


def _errors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == "RUN_ERROR"]


async def _seed() -> None:
    users = get_user_model().objects
    demo = await users.acreate(username="demo", is_superuser=True)
    await Token.objects.acreate(user=demo, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=demo, title="Standup", day="2026-08-10", start_hour=9)
    visitor = await users.acreate(username="visitor")
    await Token.objects.acreate(user=visitor, key="visitor-token-not-a-secret")
    await Event.objects.acreate(owner=visitor, title="Visitor's call", day="2026-08-11", start_hour=9)
