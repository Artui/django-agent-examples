from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from agent.server import agent, run_store
from board.management.commands.run_headless import run_headless
from board.models import Event
from tests.wire import AUTH, run, user_message


async def _seed() -> Any:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    return user


def _payload(thread: str, prompt: str, **props: Any) -> str:
    return json.dumps(
        {
            "threadId": thread,
            "runId": f"run-{uuid.uuid4().hex[:8]}",
            "messages": [user_message(prompt)],
            "tools": [],
            "context": [],
            "state": {},
            "forwardedProps": props,
        }
    )


@pytest.mark.django_db(transaction=True)
async def test_a_detached_run_leaves_a_log_a_browser_can_replay() -> None:
    await _seed()
    client = AsyncClient()

    started = await client.post(
        "/agent/",
        data=_payload("t-detach", "what is on the board?", detach=True),
        content_type="application/json",
        headers=AUTH,
    )
    assert started.status_code == 200
    body = b"".join([chunk async for chunk in started.streaming_content])
    assert b"RUN_FINISHED" in body

    page = await client.get("/agent/threads/t-detach/events/?after=0&limit=500", headers=AUTH)

    assert page.status_code == 200, page.content[:300]
    assert "RUN_FINISHED" in page.content.decode()


@pytest.mark.django_db(transaction=True)
async def test_a_second_start_on_a_held_thread_is_refused_naming_the_run() -> None:
    user = await _seed()
    request = agent.headless_request(user)
    claim = await run_store.claim(
        "t-held", "run-first", request=request, lease=timedelta(minutes=1)
    )
    assert claim.claimed

    response = await AsyncClient().post(
        "/agent/",
        data=_payload("t-held", "what is on the board?"),
        content_type="application/json",
        headers=AUTH,
    )

    assert response.status_code == 409
    assert "run-first" in response.content.decode()


@pytest.mark.django_db(transaction=True)
async def test_a_headless_booking_parks_on_the_gated_call_and_writes_nothing() -> None:
    user = await _seed()

    stop = await run_headless("book a design sync on 2026-08-14 at 14:00", "demo", 30.0)

    state = await run_store.get(stop.thread_id, request=agent.headless_request(user))
    assert state is not None and state.status.value == "waiting"
    assert stop.outcome.value == "waiting"
    assert not await Event.objects.filter(title="Design sync").aexists()


@pytest.mark.django_db(transaction=True)
async def test_the_slow_answer_streams_word_by_word(monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed()
    monkeypatch.setattr("agent.scripted.SLOW_PACE", 0)

    events = await run(user_message("answer slowly"), thread="t-slow")

    assert len([e for e in events if e["type"] == "TEXT_MESSAGE_CONTENT"]) > 20
