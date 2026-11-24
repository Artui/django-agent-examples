from __future__ import annotations

import json
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from tests.wire import AUTH, run, user_message


@pytest.mark.django_db(transaction=True)
async def test_the_token_home_lists_the_board_and_mcp_agents_by_name() -> None:
    await _demo_user()

    response = await AsyncClient().get("/agents-home/agents/", headers=AUTH)

    assert response.status_code == 200, response.content[:300]
    agents = json.loads(response.content)["agents"]
    assert [(a["id"], a["name"]) for a in agents] == [
        ("board", "Board assistant"),
        ("mcp", "Board over MCP"),
    ]
    assert agents[0]["endpoint"] == "/agent/"
    assert agents[0]["threads_url"] == "/agent/threads/"
    assert agents[1]["endpoint"] == "/mcp-agent/"


@pytest.mark.django_db(transaction=True)
async def test_a_staff_session_also_sees_the_admin_agent() -> None:
    user = await _demo_user()
    client = AsyncClient()
    await sync_to_async(client.force_login)(user)

    response = await client.get("/agents-home/agents/")

    assert response.status_code == 200, response.content[:300]
    ids = [a["id"] for a in json.loads(response.content)["agents"]]
    assert "admin" in ids


@pytest.mark.django_db(transaction=True)
async def test_the_inbox_carries_each_row_s_agent() -> None:
    await _demo_user()
    await run(user_message("what is on the board?"), thread="t-home")

    response = await AsyncClient().get("/agents-home/inbox/", headers=AUTH)

    assert response.status_code == 200, response.content[:300]
    rows = json.loads(response.content)["threads"]
    assert [(r["thread_id"], r["agent_id"]) for r in rows] == [("t-home", "board")]


async def test_an_anonymous_caller_is_refused() -> None:
    response = await AsyncClient().get("/agents-home/agents/")

    assert response.status_code in (401, 403)


async def _demo_user() -> Any:
    user = await get_user_model().objects.acreate(
        username="demo", is_staff=True, is_superuser=True
    )
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    return user
