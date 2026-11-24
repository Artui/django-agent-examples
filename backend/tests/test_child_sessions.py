from __future__ import annotations

import asyncio
import datetime
import json
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from board.models import Event
from tests.wire import AUTH, run, user_message

ASK = "ask the MCP agent what is on the board"


async def _seed() -> Any:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await user.user_permissions.aadd(await Permission.objects.aget(codename="add_event"))
    await Event.objects.acreate(
        owner=user, title="Retro", day=datetime.date(2026, 8, 14), start_hour=16
    )
    return user


def _receipt(events: list[dict[str, Any]]) -> dict[str, Any]:
    [result] = [e for e in events if e["type"] == "TOOL_CALL_RESULT"]
    return json.loads(result["content"])


async def _thread(client: AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url, headers=AUTH)
    assert response.status_code == 200, response.content[:300]
    return response.json()


async def _texts(client: AsyncClient, url: str) -> list[str]:
    body = await _thread(client, url)
    return [
        m["content"]
        for m in body["messages"]
        if m.get("role") == "assistant" and isinstance(m.get("content"), str)
    ]


async def _settled(client: AsyncClient, thread_id: str) -> list[str]:
    for _ in range(200):
        texts = await _texts(client, f"/agent/threads/{thread_id}/")
        if any(text.startswith("The MCP agent reports") for text in texts):
            return texts
        await asyncio.sleep(0.05)
    return texts


@pytest.mark.django_db(transaction=True)
async def test_the_board_agent_starts_a_child_session_on_the_mcp_agent() -> None:
    await _seed()

    events = await run(user_message(ASK), thread="t-parent")
    await _settled(AsyncClient(), "t-parent")

    receipt = _receipt(events)
    assert receipt["agent_id"] == "mcp"
    assert receipt["thread_id"]


@pytest.mark.django_db(transaction=True)
async def test_the_child_thread_names_its_parent_on_the_mcp_mount() -> None:
    await _seed()
    receipt = _receipt(await run(user_message(ASK), thread="t-parent"))
    client = AsyncClient()
    await _settled(client, "t-parent")

    rows = (await _thread(client, "/mcp-agent/threads/"))["threads"]

    [child] = [row for row in rows if row["thread_id"] == receipt["thread_id"]]
    assert child["parent"] == {"thread_id": "t-parent", "scope": "board"}


@pytest.mark.django_db(transaction=True)
async def test_the_parent_answers_from_the_childs_report() -> None:
    await _seed()
    receipt = _receipt(await run(user_message(ASK), thread="t-parent"))
    client = AsyncClient()

    texts = await _settled(client, "t-parent")

    child = await _texts(client, f"/mcp-agent/threads/{receipt['thread_id']}/")
    assert child and "Retro" in child[-1]
    assert texts[-1].startswith("The MCP agent reports")
    assert "Retro" in texts[-1]
