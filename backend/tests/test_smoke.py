"""The gallery's gate: the backend boots, the board answers, the agent drives.

These are apps, not a library, so the bar is "it works from the outside" rather
than a coverage number. Every request here is made the way a frontend makes it —
a token in a header, a `RunAgentInput` body, SSE parsed off the wire — so a
change that breaks the published contract fails here rather than in a demo.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import AsyncClient, Client
from rest_framework.authtoken.models import Token

from board.models import Event

AUTH = {"authorization": "Token demo-token-not-a-secret"}

# What the page reports to `read_page`. The ids are the page's, which is the
# point: the agent addresses what the page says exists.
PAGE: dict[str, Any] = {
    "view": "week",
    "slots": [
        {"id": "slot-2026-08-13-15", "label": "Thu 15:00", "day": "2026-08-13", "hour": 15},
        {"id": "slot-2026-08-14-17", "label": "Fri 17:00", "day": "2026-08-14", "hour": 17},
    ],
    "events": [{"id": "event-1", "label": "Standup", "day": "2026-08-10", "hour": 9}],
    "backlog": [
        {"id": "event-9", "label": "Write the release notes", "position": 0},
        {"id": "event-10", "label": "Review the migration plan", "position": 1},
    ],
}

CLIENT_TOOLS = [
    {
        "name": "set_board",
        "description": "Set the board's filter or selection.",
        "parameters": {
            "type": "object",
            "properties": {"room": {"type": "string"}},
        },
    },
    {
        "name": "read_page",
        "description": "Read the board's addressable surface.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "drag_and_drop",
        "description": "Drag one element onto another.",
        "parameters": {
            "type": "object",
            "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
            "required": ["from", "to"],
        },
    },
    {
        "name": "scroll_to",
        "description": "Scroll a target into view.",
        "parameters": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    {
        "name": "navigate_to_route",
        "description": "Navigate to a named route.",
        "parameters": {
            "type": "object",
            "properties": {"route_id": {"type": "string"}},
            "required": ["route_id"],
        },
    },
]


@pytest.fixture
def demo_user(db: Any) -> Any:
    user = get_user_model().objects.create(username="demo")
    Token.objects.create(user=user, key="demo-token-not-a-secret")
    Event.objects.create(owner=user, title="Standup", day="2026-08-10", start_hour=9)
    Event.objects.create(owner=user, title="Write the release notes", position=0)
    return user


@pytest.fixture
def api(demo_user: Any) -> Client:
    return Client(headers=AUTH)


def test_board_reads_are_scoped_to_the_token_holder(api: Client, demo_user: Any) -> None:
    stranger = get_user_model().objects.create(username="stranger")
    Event.objects.create(owner=stranger, title="Not yours", day="2026-08-10", start_hour=11)

    titles = [row["title"] for row in api.get("/api/events/").json()]

    assert "Standup" in titles
    assert "Not yours" not in titles


def test_board_refuses_an_unknown_token(db: Any) -> None:
    assert Client(headers={"authorization": "Token nope"}).get("/api/events/").status_code == 401


def test_move_persists_and_the_precondition_holds_the_slot(api: Client, demo_user: Any) -> None:
    event = Event.objects.get(owner=demo_user, title="Write the release notes")
    body = {"event_id": event.pk, "day": "2026-08-12", "start_hour": 15}

    assert api.post("/api/events/move/", body, content_type="application/json").status_code == 200
    event.refresh_from_db()
    assert (str(event.day), event.start_hour) == ("2026-08-12", 15)

    # A second event onto the same cell is a state rule, declared on the spec, so
    # it answers the same way on both transports. Over HTTP that is now a 409,
    # because `SlotTaken` is a `ServiceConflict` -- and this test used to assert
    # 422 with a comment explaining that every non-validation error mapped there
    # "whatever the subclass says". Writing that comment is what produced the
    # typed members in drf-services 0.40.0.
    other = Event.objects.create(owner=demo_user, title="Elsewhere")
    clash = api.post(
        "/api/events/move/",
        {"event_id": other.pk, "day": "2026-08-12", "start_hour": 15},
        content_type="application/json",
    )
    assert clash.status_code == 409
    assert "already held by" in clash.json()["detail"]


def test_create_obeys_the_same_slot_rule_as_move(api: Client, demo_user: Any) -> None:
    """One precondition on two specs, so the board cannot be double-booked either way.

    It guarded the move alone until a CSV import created three events at once and
    put two of them in one cell. The grid draws one card per slot, so the second was
    written and invisible — a rule enforced on one write and not the other is not a
    rule.
    """
    Event.objects.filter(owner=demo_user, day="2026-08-12", start_hour=15).delete()
    taken = {"title": "First", "day": "2026-08-12", "start_hour": 15}
    assert api.post("/api/events/", taken, content_type="application/json").status_code == 201

    clash = api.post(
        "/api/events/",
        {"title": "Second", "day": "2026-08-12", "start_hour": 15},
        content_type="application/json",
    )

    assert clash.status_code == 409
    assert "already held by" in clash.json()["detail"]
    assert not Event.objects.filter(owner=demo_user, title="Second").exists()


def test_move_rejects_a_day_without_an_hour(api: Client, demo_user: Any) -> None:
    event = Event.objects.get(owner=demo_user, title="Standup")
    response = api.post(
        "/api/events/move/",
        {"event_id": event.pk, "day": "2026-08-12"},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_move_refuses_an_event_owned_by_someone_else(api: Client, demo_user: Any) -> None:
    """A row you cannot see answers 404, not 403, and that is deliberate.

    `UnknownEvent` is a `ServiceNotFound`, and the lookup that raises it is scoped
    to the owner, so "no such event" and "not yours" are indistinguishable from
    outside. Answering 403 here would confirm that somebody else's row exists.
    """
    stranger = get_user_model().objects.create(username="stranger")
    theirs = Event.objects.create(owner=stranger, title="Not yours")

    response = api.post(
        "/api/events/move/",
        {"event_id": theirs.pk, "day": "2026-08-12", "start_hour": 9},
        content_type="application/json",
    )

    assert response.status_code == 404


def test_the_tool_catalog_carries_both_kinds_of_tool(api: Client) -> None:
    names = {entry["name"] for entry in api.get("/agent/tools/").json()}

    assert "week_overview" in names  # the @tool registry
    assert {"list_events", "move_event"} <= names  # the spec registry


@pytest.mark.django_db(transaction=True)
async def test_the_agent_answers_from_the_server_side_spec_tool() -> None:
    await _seed()
    events = await _run(_user_message("what is on the board?"))

    assert _tool_calls(events) == ["list_events"]
    assert "scheduled" in _text(events)


@pytest.mark.django_db(transaction=True)
async def test_the_agent_reads_the_page_then_drags_the_card_the_page_named() -> None:
    await _seed()
    messages = [_user_message("move standup to Thursday at 15:00")]

    first = await _run(*messages)
    assert _tool_calls(first) == ["read_page"]

    second = await _run(*messages, *_answered(first, PAGE))
    assert _tool_calls(second) == ["drag_and_drop"]
    assert _arguments(second) == {"from": "event-1", "to": "slot-2026-08-13-15"}


@pytest.mark.django_db(transaction=True)
async def test_a_declined_confirmation_is_reported_as_a_decline() -> None:
    """The card the user cancels comes back as a declined result, not a failure."""
    await _seed()
    messages = [_user_message("move standup to Thursday at 15:00")]
    first = await _run(*messages)
    with_page = [*messages, *_answered(first, PAGE)]
    dragged = await _run(*with_page)

    settled = await _run(*with_page, *_answered(dragged, "User declined the action."))

    assert _tool_calls(settled) == []
    assert "left it where it was" in _text(settled).lower()


@pytest.mark.django_db(transaction=True)
async def test_a_verification_read_waits_for_a_page_that_is_still_saving() -> None:
    """A page action returns before the page's own save lands, so `saving` is honoured."""
    await _seed()
    history = await _after_the_drag({**_moved(PAGE), "saving": True})

    again = await _run(*history)

    assert _tool_calls(again) == ["read_page"], "a saving page must be re-read, not judged"
    settled = await _run(*history, *_answered(again, _moved(PAGE)))
    assert "is now at Thu 15:00" in _text(settled)


@pytest.mark.django_db(transaction=True)
async def test_a_move_is_confirmed_from_the_page_rather_than_assumed() -> None:
    """The drag reports only that it fired, so the claim is checked before it is made."""
    await _seed()
    settled = await _run(*(await _after_the_drag(_moved(PAGE))))

    assert _tool_calls(settled) == []
    assert "is now at Thu 15:00" in _text(settled)


@pytest.mark.django_db(transaction=True)
async def test_a_refused_move_is_reported_as_refused() -> None:
    """A slot the board would not give up: the tool call still succeeded."""
    await _seed()
    held = {**PAGE, "events": [*PAGE["events"], _holder()]}

    settled = await _run(*(await _after_the_drag(held)))

    assert "refused" in _text(settled)
    assert "Release checklist" in _text(settled)


@pytest.mark.django_db(transaction=True)
async def test_a_filter_request_writes_the_hosts_own_state() -> None:
    """Through the tools `registerPageState` generated, not through the board API."""
    await _seed()
    events = await _run(_user_message("show only the Basalt room"))

    assert _tool_calls(events) == ["set_board"]
    assert _arguments(events) == {"room": "Basalt"}


@pytest.mark.django_db(transaction=True)
async def test_an_unrecognised_request_offers_what_it_can_do() -> None:
    await _seed()
    events = await _run(_user_message("write me a poem"))

    assert _tool_calls(events) == []
    assert "drive this board" in _text(events)


# --- driving the endpoint the way the web component does -----------------------


def _moved(page: dict[str, Any]) -> dict[str, Any]:
    """The page as it looks once the drag has actually landed."""
    return {
        **page,
        "events": [{"id": "event-1", "label": "Standup", "day": "2026-08-13", "hour": 15}],
    }


def _holder() -> dict[str, Any]:
    """Something else already sitting in the target slot."""
    return {"id": "event-7", "label": "Release checklist", "day": "2026-08-13", "hour": 15}


async def _after_the_drag(page_after: dict[str, Any]) -> list[dict[str, Any]]:
    """Replay a whole move turn and return the history up to the verdict round."""
    messages = [_user_message("move standup to Thursday at 15:00")]
    read = await _run(*messages)
    with_page = [*messages, *_answered(read, PAGE)]
    dragged = await _run(*with_page)
    with_drag = [*with_page, *_answered(dragged, {"dragged": True})]
    reread = await _run(*with_drag)
    assert _tool_calls(reread) == ["read_page"], "the script must verify before reporting"
    return [*with_drag, *_answered(reread, page_after)]


async def _seed() -> None:
    """The async tests own their rows: a sync fixture cannot reach across the loop."""
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=user, title="Standup", day="2026-08-10", start_hour=9)
    await Event.objects.acreate(owner=user, title="Write the release notes", position=0)


async def _run(*messages: dict[str, Any]) -> list[dict[str, Any]]:
    payload = {
        "threadId": "thread-smoke",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": list(messages),
        "tools": CLIENT_TOOLS,
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    # Headers go on the request, not on the constructor: Django's AsyncClient
    # puts constructor kwargs straight into the ASGI scope, so a default
    # `headers=` there never reaches the view (the sync Client does honour it).
    response = await AsyncClient().post(
        "/agent/",
        data=json.dumps(payload),
        content_type="application/json",
        headers=AUTH,
    )
    assert response.status_code == 200, response.content[:400]
    events = []
    async for chunk in response.streaming_content:
        for line in chunk.decode().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _user_message(text: str) -> dict[str, Any]:
    return {"id": f"m-{uuid.uuid4().hex[:6]}", "role": "user", "content": text}


def _answered(events: list[dict[str, Any]], result: Any) -> list[dict[str, Any]]:
    """The two messages a client appends after running a frontend tool."""
    start = next(event for event in events if event["type"] == "TOOL_CALL_START")
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
        },
        {
            "id": f"t-{call_id}",
            "role": "tool",
            "toolCallId": call_id,
            "content": result if isinstance(result, str) else json.dumps(result),
        },
    ]


def _tool_calls(events: list[dict[str, Any]]) -> list[str]:
    return [event["toolCallName"] for event in events if event["type"] == "TOOL_CALL_START"]


def _raw_arguments(events: list[dict[str, Any]]) -> str:
    return "".join(event["delta"] for event in events if event["type"] == "TOOL_CALL_ARGS")


def _arguments(events: list[dict[str, Any]]) -> dict[str, Any]:
    return json.loads(_raw_arguments(events))


def _text(events: list[dict[str, Any]]) -> str:
    return "".join(
        event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"
    )


def test_the_skill_catalog_publishes_one_prompt_and_withholds_two(api: Client) -> None:
    """Two kinds of skill, and the catalog is where the difference is visible.

    A skill with no `prompt` sends the bare `/name` token and the wording stays on
    the server — which is the right default, because this endpoint is a plain GET
    and anything in it is published. The templated one pays that price on purpose:
    its `{day}` is filled by the page, and the server does not know which day the
    user is looking at.
    """
    catalog = {skill["name"]: skill for skill in api.get("/agent/skills/").json()}

    assert "prompt" not in catalog["tidy-week"]
    assert "prompt" not in catalog["what-is-on"]
    assert catalog["plan-day"]["prompt"] == "What is on {day}?"
    assert catalog["plan-day"]["sendImmediately"] is True


@pytest.mark.django_db(transaction=True)
async def test_a_question_naming_a_day_is_answered_for_that_day() -> None:
    """The page fills `{day}`, so the answer has to honour it.

    Sent as the component sends it: the placeholder already replaced with the
    page's own label for the day. Answering with the whole week would make the
    templated skill a demo that reads well and says something false.
    """
    await _seed()
    await Event.objects.acreate(
        owner=await get_user_model().objects.aget(username="demo"),
        title="Vendor demo",
        day="2026-08-13",
        start_hour=11,
    )

    events = await _run(_user_message("What is on Thu 13?"))

    answer = _text(events)
    assert "On Thursday you have 1" in answer
    assert "Vendor demo at 11:00" in answer
    assert "Standup" not in answer, "Monday's event is not on Thursday"


@pytest.mark.django_db(transaction=True)
async def test_a_question_naming_no_day_still_summarises_the_week() -> None:
    await _seed()

    answer = _text(await _run(_user_message("what is on the board?")))

    assert "scheduled" in answer and "backlog" in answer
