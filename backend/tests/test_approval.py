"""The server-side approval loop, driven the way the web component drives it.

The apps already show a client-side confirmation: `confirmPredicate` asks before
the element dispatches a page action, and a refusal never leaves the browser.
This is the other mechanism, and it is the one that matters for a write. A gated
service tool is *deferred* instead of executed: the run finishes carrying an
interrupt, the client answers it in the next `RunAgentInput`, and only then does
the tool run.

Everything here is asserted off the wire — see `tests/wire.py`, which is the
client written out.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from board.models import Event
from tests.wire import (
    approve,
    calls,
    deny,
    interrupts,
    run,
    text,
    tool_calls,
    transcript,
    user_message,
)


@pytest.mark.django_db(transaction=True)
async def test_a_gated_write_defers_instead_of_running() -> None:
    """The run finishes on an interrupt, and the row is not there yet."""
    await _seed()

    events = await run(user_message("add a design sync to the backlog"))

    assert tool_calls(events) == ["create_event"], "the model still calls the tool"
    pending = interrupts(events)
    assert len(pending) == 1
    assert pending[0]["toolCallId"] == calls(events)[0].id
    assert not await Event.objects.filter(title="Design sync").aexists(), (
        "a deferred call must not have written anything"
    )


@pytest.mark.django_db(transaction=True)
async def test_approving_the_interrupt_runs_the_tool_and_the_agent_reports_it() -> None:
    """The resumed run executes the write and hands the result back to the model."""
    await _seed()
    messages = [user_message("add a design sync to the backlog")]
    deferred = await run(*messages)

    resumed = await run(*messages, *transcript(deferred), resume=approve(deferred))

    event = await Event.objects.aget(title="Design sync")
    assert event.day is None, "no day and hour means the backlog, which is the service's rule"
    assert "backlog" in text(resumed).lower()
    assert interrupts(resumed) == [], "the resumed run finishes normally"


@pytest.mark.django_db(transaction=True)
async def test_denying_the_interrupt_writes_nothing_and_the_agent_says_so() -> None:
    """A denial arrives as a tool return, so the model reads it like any result."""
    await _seed()
    messages = [user_message("add a design sync to the backlog")]
    deferred = await run(*messages)

    settled = await run(*messages, *transcript(deferred), resume=deny(deferred))

    assert not await Event.objects.filter(title="Design sync").aexists()
    assert "nothing was booked" in text(settled).lower()


@pytest.mark.django_db(transaction=True)
async def test_a_scheduled_booking_carries_the_day_and_hour_through_the_gate() -> None:
    """The arguments the user approved are the arguments that run."""
    await _seed()
    messages = [user_message("book a design sync on 2026-08-14 at 14:00")]
    deferred = await run(*messages)

    assert calls(deferred)[0].arguments == {
        "title": "Design sync",
        "day": "2026-08-14",
        "start_hour": 14,
    }

    await run(*messages, *transcript(deferred), resume=approve(deferred))

    event = await Event.objects.aget(title="Design sync")
    assert (str(event.day), event.start_hour) == ("2026-08-14", 14)


@pytest.mark.django_db(transaction=True)
async def test_a_read_is_not_gated() -> None:
    """The policy names the writes, so a read still answers in one round."""
    await _seed()

    events = await run(user_message("what is on the board?"))

    assert tool_calls(events) == ["list_events"]
    assert interrupts(events) == []
    assert "scheduled" in text(events)


@pytest.mark.django_db(transaction=True)
async def test_a_weekday_booking_lands_on_that_weekday() -> None:
    """No page in the path, so this is the one turn where the script picks a date."""
    await _seed()
    messages = [user_message("book a design sync on Friday at 14:00")]
    deferred = await run(*messages)

    await run(*messages, *transcript(deferred), resume=approve(deferred))

    event = await Event.objects.aget(title="Design sync")
    assert event.day is not None
    assert event.day.weekday() == 4, "Friday"


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=user, title="Standup", day="2026-08-10", start_hour=9)


@pytest.mark.django_db(transaction=True)
async def test_a_booking_the_board_refuses_is_not_reported_as_added() -> None:
    """A refused write must not be answered as a successful one.

    The board refuses a taken slot with a ``ServiceConflict``, which reaches the
    model as an ordinary successful tool return carrying ``{"error": ...}`` --
    ``outcome`` is ``"success"`` and nothing structural says otherwise. So the
    only signal is the shape of the content, and an answer that reads the fields
    it expected finds none of them: the title falls back to "it", the day is
    absent, and the reply used to be "Added it to the backlog." for a write that
    created nothing.

    ``_import_verdict`` has always read this correctly for a batch, and says in
    its own docstring that reporting only the created rows "would call a refused
    import a success, which is the failure mode worth writing out". This is that
    failure mode, on the single-booking path.
    """
    await _seed()
    taken = user_message("book a design sync on 2026-08-10 at 9:00")

    first = await run(taken)
    await run(*[taken], *transcript(first), resume=approve(first))

    second = await run(taken)
    settled = await run(*[taken], *transcript(second), resume=approve(second))

    answer = text(settled).lower()
    assert "refused" in answer, f"a refused booking must say so, got: {text(settled)!r}"
    assert "added" not in answer, f"a refused booking must not claim it landed: {text(settled)!r}"
    assert "booked" not in answer, f"a refused booking must not claim it landed: {text(settled)!r}"


@pytest.mark.django_db(transaction=True)
async def test_a_board_refusal_reaches_the_browser_marked_failed() -> None:
    """The whole chain, asserted where it composes.

    Five packages have to agree for a refused tool call to render as one: the
    spec raises a ``ServiceConflict``; ``djangorestframework-pydantic-ai`` turns
    that into a ``ToolFailed`` rather than a successful return carrying
    ``{"error": ...}``; pydantic-ai marks the tool return ``outcome="failed"``;
    ``django-ag-ui`` forwards that onto ``TOOL_CALL_RESULT``; and the web
    component reads it to settle the card as an error instead of a success.

    Only the last of those is invisible from here, so this asserts the four that
    are not -- on the bytes a browser receives rather than on any object in
    process. Before this batch of releases the same refusal reached the browser
    as a ``TOOL_CALL_RESULT`` indistinguishable from a success, which is what
    made a refused booking render as a green card.
    """
    await _seed()
    taken = user_message("book a design sync on 2026-08-10 at 9:00")

    first = await run(taken)
    await run(*[taken], *transcript(first), resume=approve(first))

    second = await run(taken)
    settled = await run(*[taken], *transcript(second), resume=approve(second))

    results = [event for event in settled if event.get("type") == "TOOL_CALL_RESULT"]
    assert results, "the refused booking produced no tool result at all"
    assert results[-1].get("outcome") == "failed", (
        f"a board refusal must reach the browser marked failed, got: {results[-1]!r}"
    )
    # And the reason travels with it, so the card has something to show.
    assert "already held by" in str(results[-1].get("content"))
