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
