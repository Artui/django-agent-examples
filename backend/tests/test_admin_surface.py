"""The admin surface: a session principal, CSRF on, and pages that reload.

What these cover that `test_smoke.py` cannot: the gate is staff-only, the sidebar
actually renders into the admin chrome with the vendored bundle behind it, and the
scripted model routes to the admin's own tools rather than the board's — decided
by which tools the client declared, not by configuration.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import AsyncClient, Client

from board.models import Event

# The admin's frontend tools, as `admin_tools.js` declares them. Only the names
# and shapes the script depends on.
ADMIN_TOOLS = [
    {
        "name": "open_changelist",
        "description": "Navigate to a model's admin changelist.",
        "parameters": {
            "type": "object",
            "properties": {"app_label": {"type": "string"}, "model": {"type": "string"}},
            "required": ["app_label", "model"],
        },
    },
    {
        "name": "open_changeform",
        "description": "Open a model's add or edit form.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_label": {"type": "string"},
                "model": {"type": "string"},
                "pk": {"type": ["string", "number", "null"]},
            },
            "required": ["app_label", "model"],
        },
    },
    {
        "name": "fill_field",
        "description": "Type a value into a change-form field.",
        "parameters": {
            "type": "object",
            "properties": {"field_name": {"type": "string"}, "value": {"type": "string"}},
            "required": ["field_name", "value"],
        },
    },
    {
        "name": "submit_form",
        "description": "Submit the change form.",
        "parameters": {"type": "object", "properties": {"action": {"type": "string"}}},
    },
]


@pytest.fixture
def staff(db: Any) -> Any:
    user = get_user_model().objects.create(
        username="demo", is_staff=True, is_superuser=True
    )
    Event.objects.create(owner=user, title="Retro", day="2026-08-14", start_hour=16)
    return user


def test_the_sidebar_renders_into_the_admin_chrome(client: Client, staff: Any) -> None:
    client.force_login(staff)

    body = client.get("/admin/board/event/").content.decode()

    assert "<ag-ui-chat" in body
    assert 'endpoint="/admin-agent/"' in body
    # The vendored bundle, not an npm dependency. This is the whole reason the
    # admin needs no build step.
    assert "django_admin_agent/admin_agent.js" in body
    # The conversation is scoped to whoever is signed in. `sessionStorage` is
    # scoped to the tab and not to the session, so it outlives the navigation a
    # logout is -- and this gallery's admin is the shape where that bites: one
    # browser, several principals, a shared demo machine.
    assert f'user-key="{staff.pk}"' in body


def test_the_sidebars_bundle_is_findable_as_a_static_file() -> None:
    """The sidebar is a static file, which is why serving them is not optional.

    A bare ASGI server serves no static files, and `runserver` — which would —
    cannot stream the agent endpoint, so a project that follows only the "deploy
    under ASGI" half gets an admin with no agent in it at all. This asserts the
    file ships and the finders can see it; `demo/urls.py` is what serves it.
    """
    assert finders.find("django_admin_agent/admin_agent.js") is not None


def test_the_admin_agent_refuses_an_anonymous_request(client: Client, db: Any) -> None:
    response = client.post(
        "/admin-agent/", data="{}", content_type="application/json"
    )

    assert response.status_code in {401, 403}


def test_the_admin_agent_refuses_a_signed_in_non_staff_user(client: Client, db: Any) -> None:
    outsider = get_user_model().objects.create(username="outsider")
    client.force_login(outsider)

    response = client.post("/admin-agent/", data="{}", content_type="application/json")

    assert response.status_code in {401, 403}


@pytest.mark.django_db(transaction=True)
async def test_the_script_answers_from_the_admins_own_orm_tools() -> None:
    """Same model, different surface: the tools on offer decide the route taken."""
    user, _ = await _staff()

    events = await _run(user, _user_message("how many events are there?"))

    assert _tool_calls(events) == ["count_model"]


@pytest.mark.django_db(transaction=True)
async def test_a_navigating_tool_is_answered_by_the_page_it_lands_on() -> None:
    user, _ = await _staff()
    messages = [_user_message("open the events list")]

    first = await _run(user, *messages)
    assert _tool_calls(first) == ["open_changelist"]

    # The component completes a navigating call from the landed page.
    landed = {"url": "/admin/board/event/", "title": "Select event to change"}
    settled = await _run(user, *messages, *_answered(first, landed))
    assert "Opened /admin/board/event/" in _text(settled)


@pytest.mark.django_db(transaction=True)
async def test_a_rename_walks_find_open_type_save_across_two_reloads() -> None:
    user, event = await _staff()
    history = [_user_message("rename Retro to Sprint retro")]

    # Two calls in one run, and the split is the point: `query_model` runs
    # server-side, so pydantic-ai answers it in-process and the model carries on
    # to the navigating client tool without the browser round trip.
    found = await _run(user, *history)
    assert _tool_calls(found) == ["query_model", "open_changeform"]
    assert _arguments(found, index=1)["pk"] == event.pk

    history += _answered_all(
        found,
        [
            [{"id": event.pk, "title": "Retro"}],
            {"url": f"/admin/board/event/{event.pk}/change/"},
        ],
    )
    typed = await _run(user, *history)
    assert _tool_calls(typed) == ["fill_field"]
    assert _arguments(typed) == {"field_name": "title", "value": "Sprint retro"}

    history += _answered(typed, {"ok": True})
    saved = await _run(user, *history)
    assert _tool_calls(saved) == ["submit_form"]

    history += _answered(saved, {"url": "/admin/board/event/"})
    settled = await _run(user, *history)
    assert "Renamed it to Sprint retro" in _text(settled)


@pytest.mark.django_db(transaction=True)
async def test_a_declined_save_says_nothing_changed() -> None:
    user, event = await _staff()
    history = [_user_message("rename Retro to Sprint retro")]
    found = await _run(user, *history)
    history += _answered_all(
        found,
        [
            [{"id": event.pk, "title": "Retro"}],
            {"url": f"/admin/board/event/{event.pk}/change/"},
        ],
    )
    typed = await _run(user, *history)

    history += _answered(typed, "User declined the action.")
    settled = await _run(user, *history)

    assert _tool_calls(settled) == []
    assert "left the title alone" in _text(settled)


# --- helpers -------------------------------------------------------------------


async def _staff() -> tuple[Any, Event]:
    user = await get_user_model().objects.acreate(
        username="demo", is_staff=True, is_superuser=True
    )
    event = await Event.objects.acreate(
        owner=user, title="Retro", day="2026-08-14", start_hour=16
    )
    return user, event


async def _run(user: Any, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    client = AsyncClient()
    await sync_to_async(client.force_login)(user)
    payload = {
        "threadId": "thread-admin",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": list(messages),
        "tools": ADMIN_TOOLS,
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    response = await client.post(
        "/admin-agent/", data=json.dumps(payload), content_type="application/json"
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


def _answered_all(events: list[dict[str, Any]], results: list[Any]) -> list[dict[str, Any]]:
    """Answer every tool call a run made, in order — one result per call."""
    starts = [event for event in events if event["type"] == "TOOL_CALL_START"]
    assert len(starts) == len(results), (len(starts), len(results))
    messages: list[dict[str, Any]] = []
    for index, (start, result) in enumerate(zip(starts, results)):
        call_id = start["toolCallId"]
        messages.append(
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
                            "arguments": _raw_arguments(events, index=index) or "{}",
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "id": f"t-{call_id}",
                "role": "tool",
                "toolCallId": call_id,
                "content": result if isinstance(result, str) else json.dumps(result),
            }
        )
    return messages


def _tool_calls(events: list[dict[str, Any]]) -> list[str]:
    return [event["toolCallName"] for event in events if event["type"] == "TOOL_CALL_START"]


def _raw_arguments(events: list[dict[str, Any]], index: int = 0) -> str:
    """The argument deltas of the index-th tool call in a run."""
    call_ids = [e["toolCallId"] for e in events if e["type"] == "TOOL_CALL_START"]
    if index >= len(call_ids):
        return ""
    wanted = call_ids[index]
    return "".join(
        event["delta"]
        for event in events
        if event["type"] == "TOOL_CALL_ARGS" and event.get("toolCallId") == wanted
    )


def _arguments(events: list[dict[str, Any]], index: int = 0) -> dict[str, Any]:
    return json.loads(_raw_arguments(events, index=index))


def _text(events: list[dict[str, Any]]) -> str:
    return "".join(
        event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"
    )
