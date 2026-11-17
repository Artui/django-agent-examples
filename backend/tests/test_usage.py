"""The board mount reports what a run cost, which the React app's `show-usage` draws.

`include_usage=True` on the mount's config puts the run's token usage on
`RUN_FINISHED`. The scripted model is a `FunctionModel`, which estimates usage
from the messages it saw, so the offline gallery reports numbers too. Read off
the wire, because the line the component draws is read off the wire.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from tests.wire import run, user_message


@pytest.mark.django_db(transaction=True)
async def test_run_finished_carries_the_runs_token_usage() -> None:
    await _seed()

    events = await run(user_message("hello"))

    usage = _finished(events).get("usage")
    assert isinstance(usage, list) and usage, _finished(events)
    assert all(entry["inputTokens"] > 0 for entry in usage)
    assert all(entry["outputTokens"] > 0 for entry in usage)


@pytest.mark.django_db(transaction=True)
async def test_the_mcp_mount_keeps_the_default_and_reports_none() -> None:
    """Per endpoint, not per project: only the board's mount opted in."""
    await _seed()

    events = await run(user_message("hello"), path="/mcp-agent/")

    assert "usage" not in _finished(events)


def _finished(events: list[dict[str, Any]]) -> dict[str, Any]:
    finished = [event for event in events if event.get("type") == "RUN_FINISHED"]
    assert len(finished) == 1, [event.get("type") for event in events]
    return finished[0]


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
