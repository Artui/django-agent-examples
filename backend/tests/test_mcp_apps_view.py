from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import AsyncClient

from agent.mcp_server import VIEW_URI
from tests.test_mcp_bridge import _seed
from tests.wire import AUTH, run, tool_calls, user_message

ROUTE = "/mcp-agent/mcp-apps/"


async def _post(method: str, params: dict[str, Any]) -> dict[str, Any]:
    body = {"serverId": "mcp", "method": method, "params": params}
    response = await AsyncClient().post(
        ROUTE, json.dumps(body), content_type="application/json", headers=AUTH
    )
    assert response.status_code == 200, response.content[:400]
    return json.loads(response.content)


@pytest.mark.django_db(transaction=True)
async def test_the_view_is_read_through_the_route_with_the_bridge_inlined() -> None:
    await _seed()

    contents = (await _post("resources/read", {"uri": VIEW_URI}))["result"]["contents"][0]

    assert contents["mimeType"] == "text/html;profile=mcp-app"
    assert "window.mcpApp" in contents["text"]
    assert "room_load" in contents["text"]


@pytest.mark.django_db(transaction=True)
async def test_the_app_only_tool_answers_the_view_through_the_route() -> None:
    await _seed()

    result = await _post("tools/call", {"name": "room_load", "arguments": {}})
    assert sum(result["result"]["structuredContent"]["hours"].values()) >= 1


@pytest.mark.django_db(transaction=True)
async def test_a_linked_tool_result_streams_an_mcp_apps_activity_naming_its_server() -> None:
    await _seed()

    events = await run(user_message("draw the board"), path="/mcp-agent/")

    assert tool_calls(events) == ["show_board"]
    (activity,) = [e for e in events if e.get("type") == "ACTIVITY_SNAPSHOT"]
    assert activity["activityType"] == "mcp-apps"
    assert activity["content"]["resourceUri"] == VIEW_URI
    assert activity["content"]["serverId"] == "mcp"
    assert activity["content"]["result"]["structuredContent"]["scheduled"] == 1


@pytest.mark.django_db(transaction=True)
async def test_the_catalog_lists_the_linked_tool() -> None:
    await _seed()

    catalog = await AsyncClient().get("/mcp-agent/tools/", headers=AUTH)

    assert "show_board" in {entry["name"] for entry in json.loads(catalog.content)}
