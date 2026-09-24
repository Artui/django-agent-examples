"""A read the caller shapes, and what happens when it shapes the wrong thing.

`list_events` takes a `fields` argument its serializer reads to narrow each row.
The tool answers with a page -- `{"items": [...], "page", "totalPages",
"hasNext"}` -- while the serializer renders one event at a time, so a selection
written against the page it was told to expect (`fields=items`) names a field no
row has. The serializer refuses it, in its own words, and the transport turns
that refusal into a retry carrying those words plus a sentence saying what the
selection applies to. The run goes on, and the next call is the corrected one.

Nothing here is specific to a selection library: the serializer splits on commas
and words its own refusal, and the retry is built from whatever it said. So the
thing asserted is the general mechanism, on the bytes a browser receives.

The same argument works over HTTP as `?fields=`, because both transports reach
the serializer through `request.query_params`. The last tests hold that half,
and hold the more important thing beside it: with no `fields`, the board's HTTP
list the frontends read renders exactly as it did before any of this existed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import ToolDefinition
from rest_framework.authtoken.models import Token

from board.models import Event
from board.serializers import EventSerializer, SelectableEventSerializer
from tests.wire import AUTH, calls, run, text, user_message

PHRASE = "just the titles on the board"


@pytest.mark.django_db(transaction=True)
async def test_a_selection_aimed_at_the_page_is_retried_rather_than_ending_the_run() -> None:
    """Two calls, one refusal between them, and no error anywhere in the run."""
    await _seed()

    events = await run(user_message(PHRASE))

    made = calls(events)
    assert [call.name for call in made] == ["list_events", "list_events"], (
        f"the refused selection should be followed by a corrected one, got {made!r}"
    )
    assert made[0].arguments == {"fields": "items"}, "the first call aims at the envelope"
    assert made[1].arguments == {"fields": "title"}, "the second aims at each row"

    errors = [event for event in events if event.get("type") == "RUN_ERROR"]
    assert errors == [], f"a refused selection must not end the run: {errors!r}"

    results = {
        event["toolCallId"]: event for event in events if event.get("type") == "TOOL_CALL_RESULT"
    }
    refused = results[made[0].id]
    # Both halves: the argument to change, named by the transport, and the
    # reason, in the serializer's own words. Either alone leaves a model to
    # guess -- the detail says nothing about which argument carried it, and the
    # name says nothing about what was wrong with it.
    assert "`fields`" in refused["content"], refused
    assert "Unknown field `items`." in refused["content"], refused
    # And what the selection applies to, which is what makes the second call the
    # one a model reading this would make.
    assert "each item in `items`" in refused["content"], refused
    # A retry is not a failure: the call is handed back, not settled. The
    # transport stamps `outcome` only on a failed or denied call, and the
    # component settles a card as an error when it finds one, so it has to be
    # absent here -- not null, which is a value the component would read. Checked
    # in both places, since the transport writes it in `metadata` for the
    # component and at the top level for older clients.
    assert "outcome" not in refused, refused
    assert "outcome" not in (refused.get("metadata") or {}), refused

    answer = text(events)
    assert "Standup" in answer and "Write the release notes" in answer, answer


@pytest.mark.django_db(transaction=True)
async def test_the_list_tool_tells_the_model_what_a_selection_applies_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scope sentence is in the schema, before any selection is ever wrong.

    Read off the request the model actually receives. The tool catalog endpoint
    lists names and descriptions but no parameters, so the schema is only
    observable where pydantic-ai hands it to the model -- which, offline, is
    `FunctionModel.request_stream`. Wrapped rather than replaced, so the run
    underneath is the ordinary one.

    The declaration lives on the registry entry in `board/specs.py`, not on the
    AG-UI mount, so this is also what shows the transport read it from there.
    """
    await _seed()
    served: dict[str, ToolDefinition] = {}
    original = FunctionModel.request_stream

    @asynccontextmanager
    async def recording(
        self: FunctionModel, messages: Any, settings: Any, parameters: Any, *args: Any, **kw: Any
    ) -> AsyncIterator[Any]:
        served.update({tool.name: tool for tool in parameters.function_tools})
        async with original(self, messages, settings, parameters, *args, **kw) as stream:
            yield stream

    monkeypatch.setattr(FunctionModel, "request_stream", recording)

    await run(user_message(PHRASE))

    assert "list_events" in served, f"the model was never offered the list: {sorted(served)}"
    fields = served["list_events"].parameters_json_schema["properties"].get("fields")
    assert fields is not None, "the `fields` argument the registry declares is not on the tool"
    description = fields["description"]
    # The board's own words first, then the transport's: the row is the board's
    # to describe, and the page it arrives in is the transport's.
    assert description.startswith("Comma-separated names of the event fields"), description
    assert "each item in `items`, never to the page envelope" in description, description


def test_the_http_list_renders_every_field_when_no_selection_is_sent(db: Any) -> None:
    """The route every frontend reads the board through, unchanged."""
    user = _seed_sync()

    response = Client(headers=AUTH).get("/api/events/")

    assert response.status_code == 200
    assert response.json() == EventSerializer(
        Event.objects.filter(owner=user), many=True
    ).data


def test_the_http_list_honours_the_same_selection(db: Any) -> None:
    """One serializer, one channel, so the query string narrows it too."""
    _seed_sync()
    api = Client(headers=AUTH)

    narrowed = api.get("/api/events/", {"fields": "title"})
    refused = api.get("/api/events/", {"fields": "items"})

    assert narrowed.status_code == 200
    assert narrowed.json() == [{"title": "Write the release notes"}, {"title": "Standup"}]
    # Over HTTP the refusal is an ordinary 400 with the serializer's words, since
    # there is no model to hand a retry to.
    assert refused.status_code == 400
    assert refused.json() == ["Unknown field `items`."]


def test_a_render_with_no_request_is_not_narrowed(db: Any) -> None:
    """A shell, a test, a management command: no request, and nothing to read."""
    _seed_sync()
    event = Event.objects.get(title="Standup")

    assert SelectableEventSerializer(event).data == EventSerializer(event).data


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=user, title="Standup", day="2026-08-10", start_hour=9)
    await Event.objects.acreate(owner=user, title="Write the release notes", position=0)


def _seed_sync() -> Any:
    user = get_user_model().objects.create(username="demo")
    Token.objects.create(user=user, key="demo-token-not-a-secret")
    Event.objects.create(owner=user, title="Standup", day="2026-08-10", start_hour=9)
    Event.objects.create(owner=user, title="Write the release notes", position=0)
    return user
