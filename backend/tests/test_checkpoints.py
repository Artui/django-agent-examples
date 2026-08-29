"""Resume and fork: continuing a run from a snapshot the server kept.

A conversation store records what was said. A **step** store records how a run got
there — an append-only event log, a snapshot at every provider-valid boundary, and
a ledger of which tool calls started and which finished. Configuring one mounts
three owner-scoped endpoints, and those three are the whole client contract:

- `GET runs/` — which runs have a snapshot worth continuing
- `POST resume/<id>/` — a new run seeded from that snapshot
- `POST fork/<id>/` — the same mechanism, under the verb that says why

The part that catches people is what a resumed request carries: **only the new
turn**. The prior history comes from the snapshot, so re-sending it duplicates it,
and the `run_id` must be fresh because the tool-effect ledger is keyed on
`(run_id, tool_call_id)`. Both are asserted below rather than described.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from board.models import Event
from tests.wire import AUTH, NO_CLIENT_TOOLS, run, text, tool_calls, user_message


@pytest.mark.django_db(transaction=True)
async def test_a_finished_run_is_listed_as_continuable() -> None:
    """The index reports a snapshot, not an event count."""
    await _seed()

    await run(user_message("what is on the board?"), thread="t-index")

    rows = await _runs()
    assert len(rows) == 1
    row = rows[0]
    assert row["thread_id"] == "t-index"
    assert row["parent_run_id"] is None
    assert row["continuable"] is True, "the run reached a boundary, so it has a snapshot"


@pytest.mark.django_db(transaction=True)
async def test_resuming_carries_the_history_the_request_did_not_send() -> None:
    """One message in, a whole conversation out — which is what the snapshot is for.

    The resumed request carries the new turn alone. What proves the prior turns
    arrived is the thread the run *stores*: it holds the earlier exchange as well,
    and nothing in this request supplied it.
    """
    await _seed()
    first = await run(user_message("what is on the board?"), thread="t-resume")
    assert "scheduled" in text(first)
    source = (await _runs())[0]["run_id"]

    resumed = await _continue("resume", source, "how busy is the week?", thread="t-resume")

    assert tool_calls(resumed) == ["list_events"], "an ordinary run, streamed as usual"
    stored = await _thread("t-resume")
    said = [message.get("content") for message in stored if message.get("role") == "user"]
    assert said == ["what is on the board?", "how busy is the week?"], (
        "the first turn came from the snapshot; this request never sent it"
    )


@pytest.mark.django_db(transaction=True)
async def test_a_resumed_run_records_its_parent_and_leaves_it_alone() -> None:
    """A new run id, a lineage link, and the source's own ledger untouched."""
    await _seed()
    await run(user_message("what is on the board?"), thread="t-lineage")
    source = (await _runs())[0]["run_id"]

    await _continue("resume", source, "how busy is the week?", thread="t-lineage")

    rows = {row["run_id"]: row for row in await _runs()}
    assert len(rows) == 2
    child = next(row for row in rows.values() if row["parent_run_id"] is not None)
    assert child["parent_run_id"] == source
    assert rows[source]["parent_run_id"] is None, "a continuation does not rewrite its source"


@pytest.mark.django_db(transaction=True)
async def test_forking_the_same_run_twice_gives_two_independent_branches() -> None:
    """The verb is the only difference, and branching is what it is for.

    Two forks of one snapshot, each in its own thread, each holding the shared
    first turn plus its own second one. The source is still continuable after
    both, because nothing consumed it.
    """
    await _seed()
    await run(user_message("what is on the board?"), thread="t-trunk")
    source = (await _runs())[0]["run_id"]

    await _continue("fork", source, "how busy is the week?", thread="t-branch-a")
    await _continue("fork", source, "summarise the week", thread="t-branch-b")

    for thread, second in (
        ("t-branch-a", "how busy is the week?"),
        ("t-branch-b", "summarise the week"),
    ):
        said = [
            message.get("content")
            for message in await _thread(thread)
            if message.get("role") == "user"
        ]
        assert said == ["what is on the board?", second]
    rows = {row["run_id"]: row for row in await _runs()}
    assert len(rows) == 3
    assert rows[source]["continuable"] is True, "forking reads the snapshot, it does not spend it"
    assert sum(1 for row in rows.values() if row["parent_run_id"] == source) == 2


@pytest.mark.django_db(transaction=True)
async def test_another_users_run_is_absent_rather_than_forbidden() -> None:
    """The run id is not a secret; the owner is the boundary.

    A `403` would confirm the id exists. The index simply does not list it, and
    resuming it answers `404` — the same answer an id that never existed gets.
    """
    await _seed()
    await run(user_message("what is on the board?"), thread="t-mine")
    mine = (await _runs())[0]["run_id"]
    await _seed_stranger()

    assert await _runs(token="stranger-token") == [], "another user's runs are not listed"
    assert await _status("resume", mine, token="stranger-token") == 404
    assert await _status("resume", "no-such-run") == 404, "and an invented id reads the same"


@pytest.mark.django_db(transaction=True)
async def test_reusing_the_source_run_id_is_refused_in_the_stream(caplog) -> None:
    """The documented hazard, checked instead of trusted — and it is guarded.

    The ledger is keyed on `(run_id, tool_call_id)`, so continuing a run under its
    own id would write a second history into the first run's rows. It does not: the
    harness refuses, by name, and the source's records are untouched. Worth knowing
    the guard exists, because the warning to send a fresh id reads like the only
    thing standing between you and a corrupted ledger.

    The refusal is a `RUN_ERROR` **event**, not an HTTP status, and it could not
    be otherwise: `RUN_STARTED` has already gone out, so the response is committed
    at 200 before anything is validated. Anything that goes wrong in a streaming
    endpoint after its first byte is an event — a client that only checks
    `response.ok` treats this as a success.
    """
    await _seed()
    await run(user_message("what is on the board?"), thread="t-reuse")
    source = (await _runs())[0]["run_id"]

    with caplog.at_level(logging.WARNING, logger="django_pydantic_agent.audit"):
        events = await _stream(
            await _post("resume", source, "how busy is the week?", thread="t-reuse", run_id=source)
        )

    assert [event["type"] for event in events] == ["RUN_STARTED", "RUN_ERROR"]
    # **The browser is not told why**, and that is the transport doing its job:
    # from django-ag-ui 0.50.0 a ``RUN_ERROR`` raised outside a tool carries a
    # fixed sentence unless ``TOOL_FAILURE["INCLUDE_DETAIL"]`` opts in, because
    # pydantic-ai builds the message as ``str(error)`` and an exception's own
    # words are written for an operator -- an ORM error carrying SQL, an
    # ``OSError`` carrying a server path.
    #
    # This gallery leaves the safe default in place, so the assertion here is
    # that the redaction is in force, not that it is absent.
    assert events[-1]["message"] == "The run failed. The failure has been recorded."
    rows = await _runs()
    assert [row["run_id"] for row in rows] == [source], "nothing new was recorded"
    assert rows[0]["continuable"] is True, "and the source can still be continued"
    # The operator's copy keeps what the browser was not given, so the redaction
    # is a disclosure boundary rather than a swallowed error. Asserted because
    # the two halves are only correct together: redacting *and* dropping the
    # detail passes the assertion above and leaves the refusal reaching nobody,
    # which is exactly what the default null audit logger does.
    assert any(
        "already in the store" in record.getMessage() for record in caplog.records
    ), "the refusal names the guard in the audit record"


# --- the three endpoints a step store mounts ----------------------------------


async def _runs(token: str = "demo-token-not-a-secret") -> list[dict[str, Any]]:
    response = await AsyncClient().get(
        "/agent/runs/", headers={"authorization": f"Token {token}"}
    )
    assert response.status_code == 200, response.content[:300]
    return list(json.loads(response.content)["runs"])


async def _post(
    verb: str,
    source: str,
    content: str,
    *,
    thread: str,
    run_id: str = "run-continued",
    token: str = "demo-token-not-a-secret",
) -> Any:
    """A continuation request: the new turn alone, under a fresh run id."""
    payload = {
        "threadId": thread,
        "runId": run_id,
        "messages": [user_message(content)],
        "tools": NO_CLIENT_TOOLS,
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    return await AsyncClient().post(
        f"/agent/{verb}/{source}/",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"authorization": f"Token {token}"},
    )


async def _continue(verb: str, source: str, content: str, *, thread: str) -> list[dict[str, Any]]:
    response = await _post(verb, source, content, thread=thread, run_id=f"run-{verb}-{thread}")
    assert response.status_code == 200, response.content[:300]
    return await _stream(response)


async def _stream(response: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async for chunk in response.streaming_content:
        for line in chunk.decode().splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def _status(verb: str, source: str, *, token: str = "demo-token-not-a-secret") -> int:
    response = await _post(verb, source, "anything", thread="t-denied", token=token)
    return int(response.status_code)


async def _thread(thread_id: str) -> list[dict[str, Any]]:
    response = await AsyncClient().get(f"/agent/threads/{thread_id}/", headers=AUTH)
    assert response.status_code == 200, response.content[:300]
    return list(json.loads(response.content)["messages"])


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=user, title="Standup", day="2026-08-10", start_hour=9)
    await Event.objects.acreate(owner=user, title="Write the release notes", position=0)


async def _seed_stranger() -> None:
    stranger = await get_user_model().objects.acreate(username="stranger")
    await Token.objects.acreate(user=stranger, key="stranger-token")
