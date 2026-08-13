"""Uploads: the bytes go out of band, and the model reaches them by asking.

The composer never puts a file on the wire. It uploads to `attachments/`, keeps
the ref the server issues, and rides that ref on the message — so the run request
carries an id, a name, a type and a size. The server turns the refs it finds on
the posted messages into a manifest it hands the model as run instructions, and
the model reads the content through a `read_attachment` tool that exists only for
this request and only for this user.

That is three seams, and none of them is visible from the browser: an endpoint, a
manifest, and a per-request tool. All three are asserted here off the wire.
"""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from board.models import Event
from tests.wire import (
    approve,
    calls,
    decide,
    deny,
    interrupts,
    run,
    text,
    tool_calls,
    transcript,
    upload,
    user_message,
)

# The file the gallery ships as `samples/week.csv`, byte for byte. Two rows land
# in the grid and the third has no slot, which the service puts in the backlog.
WEEK_CSV = (
    b"title,day,start_hour,duration_hours,room\n"
    b"Roadmap review,Wednesday,14,2,Aurora\n"
    b"Vendor demo,Thursday,11,1,Basalt\n"
    b"Refresh the status page,,,,\n"
)


@pytest.mark.django_db(transaction=True)
async def test_the_upload_answers_with_a_ref_and_not_with_the_file() -> None:
    """What the composer keeps is four short fields, which is what rides on a message."""
    await _seed()

    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")

    assert set(ref) >= {"id", "name", "mime", "size"}
    assert (ref["name"], ref["mime"], ref["size"]) == ("week.csv", "text/csv", len(WEEK_CSV))
    assert "Roadmap review" not in str(ref), "the ref is a handle, not the content"


@pytest.mark.django_db(transaction=True)
async def test_the_model_is_told_a_file_exists_and_reads_it_by_id() -> None:
    """The manifest is the whole delivery mechanism, and the id in it is the ref's."""
    await _seed()
    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")

    events = await run(user_message("what is in this file?", [ref]))

    read = calls(events)
    assert [call.name for call in read] == ["read_attachment"]
    assert read[0].arguments == {"attachment_id": ref["id"]}, (
        "the id the model passed came from its own instructions"
    )
    assert "Roadmap review" in text(events), "and the content came back through the tool"


@pytest.mark.django_db(transaction=True)
async def test_an_id_the_client_made_up_reads_nothing() -> None:
    """Refs arrive from the browser, so the store resolves them; it does not trust them.

    Nothing about a manifest entry is authoritative — it is assembled from the
    posted messages, which the client wrote. The id is only useful through the
    tool, and the tool looks it up owner-scoped.
    """
    await _seed()
    forged = {"id": "0" * 32, "name": "week.csv", "mime": "text/csv", "size": 139}

    events = await run(user_message("what is in this file?", [forged]))

    assert tool_calls(events) == ["read_attachment"]
    assert "no attachment" in text(events).lower()


@pytest.mark.django_db(transaction=True)
async def test_importing_defers_one_call_per_row_and_writes_nothing_yet() -> None:
    """Three rows, three gated calls, one run — and three cards to answer."""
    await _seed()
    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")

    events = await run(user_message("import these events", [ref]))

    assert tool_calls(events) == [
        "read_attachment",
        "create_event",
        "create_event",
        "create_event",
    ], "reading is not gated, so it ran; the writes did not"
    pending = interrupts(events)
    assert len(pending) == 3
    assert [interrupt["metadata"]["x-confirm"] for interrupt in pending] == [
        "Add this event to the board?"
    ] * 3, "each card asks in words rather than spelling out the call"
    assert not await Event.objects.filter(title__in=_CSV_TITLES).aexists()


@pytest.mark.django_db(transaction=True)
async def test_approving_every_row_puts_the_file_on_the_board() -> None:
    """The rows become events, and the row with no slot joins the backlog."""
    await _seed()
    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")
    messages = [user_message("import these events", [ref])]
    deferred = await run(*messages)

    settled = await run(*messages, *transcript(deferred), resume=approve(deferred))

    review = await Event.objects.aget(title="Roadmap review")
    assert (review.day.weekday(), review.start_hour, review.duration_hours) == (2, 14, 2)
    assert review.room == "Aurora"
    demo = await Event.objects.aget(title="Vendor demo")
    assert (demo.day.weekday(), demo.start_hour) == (3, 11)
    assert review.day == _this_weekday(2), (
        "a weekday in the file means that day of the week on screen, so the row "
        "lands where the user can see it and the sample never goes stale"
    )
    backlog = await Event.objects.aget(title="Refresh the status page")
    assert (backlog.day, backlog.start_hour) == (None, None)
    assert "Roadmap review" in text(settled) and "week.csv" in text(settled)


@pytest.mark.django_db(transaction=True)
async def test_answering_the_cards_differently_imports_only_what_was_approved() -> None:
    """Three interrupts are three decisions, and the report describes the mix."""
    await _seed()
    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")
    messages = [user_message("import these events", [ref])]
    deferred = await run(*messages)

    settled = await run(
        *messages,
        *transcript(deferred),
        resume=decide(deferred, lambda call: call.arguments["title"] != "Vendor demo"),
    )

    assert await Event.objects.filter(title="Roadmap review").aexists()
    assert await Event.objects.filter(title="Refresh the status page").aexists()
    assert not await Event.objects.filter(title="Vendor demo").aexists()
    answer = text(settled)
    assert "Vendor demo" not in answer
    assert "turned down 1" in answer


@pytest.mark.django_db(transaction=True)
async def test_refusing_every_card_leaves_the_board_alone() -> None:
    await _seed()
    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")
    messages = [user_message("import these events", [ref])]
    deferred = await run(*messages)

    settled = await run(*messages, *transcript(deferred), resume=deny(deferred))

    assert not await Event.objects.filter(title__in=_CSV_TITLES).aexists()
    assert "nothing from week.csv" in text(settled).lower()


@pytest.mark.django_db(transaction=True)
async def test_a_row_the_board_refuses_is_told_apart_from_a_row_you_declined() -> None:
    """Approved, and still refused — by the board, in the board's own words.

    The third way a row can end. `create_event` carries the same slot precondition
    as `move_event`, so importing onto an occupied cell raises `SlotTaken`, and a
    `ServiceConflict` reaches the model as an `error` on the tool return rather
    than as a 500 or a silent success. A report that read only the created events
    would call this an import.
    """
    await _seed()
    await Event.objects.acreate(
        owner=await get_user_model().objects.aget(username="demo"),
        title="Squatter",
        day=_this_weekday(2),
        start_hour=14,
    )
    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")
    messages = [user_message("import these events", [ref])]
    deferred = await run(*messages)

    settled = await run(*messages, *transcript(deferred), resume=approve(deferred))

    assert not await Event.objects.filter(title="Roadmap review").aexists()
    assert await Event.objects.filter(title="Vendor demo").aexists()
    answer = text(settled)
    assert "The board refused a row" in answer
    assert "already held by 'Squatter'" in answer
    assert "turned down" not in answer, "nobody declined anything; the board refused"


@pytest.mark.django_db(transaction=True)
async def test_a_later_turn_about_the_board_is_not_about_the_file() -> None:
    """The manifest rides every turn of the thread, so the words decide.

    Deliberate upstream behaviour: the refs are read from the message history
    rather than from one run's upload list, so they survive a reload and stay
    readable for as long as the conversation does. The cost is that "a file is
    attached" is true forever after, which is why the script also asks whether the
    user is talking about it.
    """
    await _seed()
    ref = await upload(WEEK_CSV, name="week.csv", mime="text/csv")

    events = await run(
        user_message("import these events", [ref]),
        user_message("what is on the board?"),
    )

    assert tool_calls(events) == ["list_events"]


_CSV_TITLES = ("Roadmap review", "Vendor demo", "Refresh the status page")


def _this_weekday(offset: int) -> datetime.date:
    """That day of the week the board is showing, counting Monday as zero."""
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(days=offset)


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
