"""One person, two agent mounts, two conversation lists.

The board's single-page mount and the admin's sidebar mount share one database
and, in this gallery, one principal: the demo user is staff and holds the
board's API token. A conversation store keys a thread by owner and thread id,
so over one unscoped store each mount's history drawer listed the other's
conversations -- and opening one there continued it under the wrong agent: the
admin's tools, session principal and CSRF policy running on from a turn the
board's spec tools produced, or the reverse. Owner scoping cannot catch it,
because it is the same owner on both mounts.

Each mount wraps its store in `ScopedConversationStore`, which partitions by a
thread-id prefix. That is opt-in by design, since a transport that scoped by
itself would orphan every existing single-mount project's history, which is
why a project composing two mounts has to say so -- and why this gallery, as
the place the family shows how to compose them, should.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from tests.wire import AUTH, run, user_message


@pytest.mark.django_db(transaction=True)
async def test_each_mount_lists_only_the_conversations_held_on_it() -> None:
    user = await _demo_user()

    await run(user_message("what is on the board?"), thread="t-board")
    await _admin_run(user, "how many events are there?", thread="t-admin")

    assert await _listed(AsyncClient(), "/agent/threads/", headers=AUTH) == ["t-board"]
    assert await _listed(await _session(user), "/admin-agent/threads/") == ["t-admin"]


@pytest.mark.django_db(transaction=True)
async def test_a_conversation_cannot_be_opened_on_the_other_mount() -> None:
    """Not listed is not enough: a thread id comes from the client."""
    user = await _demo_user()
    await run(user_message("what is on the board?"), thread="t-board")
    await _admin_run(user, "how many events are there?", thread="t-admin")

    admin = await _session(user)
    board = AsyncClient()

    assert (await admin.get("/admin-agent/threads/t-board/")).status_code == 404
    assert (await board.get("/agent/threads/t-admin/", headers=AUTH)).status_code == 404
    # Each is still reachable where it was held, so the 404s are the partition
    # and not a thread that was never saved.
    assert (await admin.get("/admin-agent/threads/t-admin/")).status_code == 200
    assert (await board.get("/agent/threads/t-board/", headers=AUTH)).status_code == 200


async def _demo_user() -> Any:
    """The gallery's principal: staff for the admin, a token for the board."""
    user = await get_user_model().objects.acreate(
        username="demo", is_staff=True, is_superuser=True
    )
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    return user


async def _session(user: Any) -> AsyncClient:
    client = AsyncClient()
    await sync_to_async(client.force_login)(user)
    return client


async def _admin_run(user: Any, text: str, *, thread: str) -> None:
    client = await _session(user)
    payload = {
        "threadId": thread,
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": [{"id": f"m-{uuid.uuid4().hex[:6]}", "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    response = await client.post(
        "/admin-agent/", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, response.content[:400]
    # Drained, because the store saves the conversation when the stream ends.
    async for _ in response.streaming_content:
        pass


async def _listed(client: AsyncClient, url: str, **kwargs: Any) -> list[str]:
    response = await client.get(url, **kwargs)
    assert response.status_code == 200, response.content[:300]
    return [row["thread_id"] for row in json.loads(response.content)["threads"]]
