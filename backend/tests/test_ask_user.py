"""Asking the user a question, which is a tool call and nothing more.

`ask_user` is a **frontend** tool the web component offers when the host sets
`askUser`. The agent calls it, the browser renders a card, and the answer comes
back as that call's result. No server configuration, no new event, no interrupt —
which is the point worth showing next to the approval loop, because from the
outside both look like "the run paused and came back":

| | who runs it | how the run ends | how the answer travels |
| --- | --- | --- | --- |
| approval | nobody; the call is deferred | `RUN_FINISHED` with an interrupt | `resume[]` beside the pending call |
| `ask_user` | the browser | `RUN_FINISHED`, ordinarily | a tool message, like any client tool |

So the tool the agent has here exists only because a client declared it, which is
what the first test pins: the same utterance behaves differently depending on
what the page offers, and the script has to cope with both.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from board.models import Event
from tests.wire import answered, calls, run, text, tool_calls, user_message

ASK_USER: dict[str, Any] = {
    "name": "ask_user",
    "description": "Ask the user a question and wait for their answer.",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "allow_custom": {"type": "boolean"},
        },
        "required": ["question"],
    },
}

READ_PAGE: dict[str, Any] = {
    "name": "read_page",
    "description": "Read the board's addressable surface.",
    "parameters": {"type": "object", "properties": {}},
}

DRAG: dict[str, Any] = {
    "name": "drag_and_drop",
    "description": "Drag one element onto another.",
    "parameters": {
        "type": "object",
        "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
        "required": ["from", "to"],
    },
}

BOARD_TOOLS = [READ_PAGE, DRAG]
BOARD_TOOLS_WITH_ASK = [*BOARD_TOOLS, ASK_USER]

# Thursday 15:00 is occupied, so the free slots are the other three. The page is
# the authority on all of it — these ids and labels are the page's own.
PAGE: dict[str, Any] = {
    "view": "week",
    "slots": [
        {"id": "slot-2026-08-13-15", "label": "Thu 15:00", "day": "2026-08-13", "hour": 15},
        {"id": "slot-2026-08-14-11", "label": "Fri 11:00", "day": "2026-08-14", "hour": 11},
        {"id": "slot-2026-08-14-15", "label": "Fri 15:00", "day": "2026-08-14", "hour": 15},
        {"id": "slot-2026-08-14-17", "label": "Fri 17:00", "day": "2026-08-14", "hour": 17},
    ],
    "events": [
        {"id": "event-1", "label": "Standup", "day": "2026-08-10", "hour": 9},
        {"id": "event-2", "label": "Release checklist", "day": "2026-08-13", "hour": 15},
    ],
    "backlog": [],
}


@pytest.mark.django_db(transaction=True)
async def test_without_the_tool_the_agent_asks_in_prose() -> None:
    """A page that does not offer the question has to be told how to phrase one."""
    await _seed()
    history = [user_message("move standup to Friday")]
    first = await run(*history, tools=BOARD_TOOLS)

    settled = await run(*answered(history, first, PAGE), tools=BOARD_TOOLS)

    assert tool_calls(settled) == [], "nothing to call: the tool does not exist here"
    assert "tell me which day and hour" in text(settled).lower()


@pytest.mark.django_db(transaction=True)
async def test_with_the_tool_it_asks_the_page_which_slots_to_offer() -> None:
    """The options are the free slots the page reported, not a list held server-side."""
    await _seed()
    history = [user_message("move standup to Friday")]
    first = await run(*history, tools=BOARD_TOOLS_WITH_ASK)

    asked = await run(*answered(history, first, PAGE), tools=BOARD_TOOLS_WITH_ASK)

    assert tool_calls(asked) == ["ask_user"]
    question = calls(asked)[0].arguments
    assert question["question"] == "Which slot should Standup move to?"
    assert question["options"] == ["Fri 11:00", "Fri 15:00", "Fri 17:00"], (
        "narrowed to the day the user named, and the taken slot is not offered"
    )
    assert question["allow_custom"] is True


@pytest.mark.django_db(transaction=True)
async def test_the_answer_arrives_as_a_tool_result_and_the_move_proceeds() -> None:
    """One chosen option, and the run continues into the step it was missing."""
    await _seed()
    history, asked = await _asked()

    dragged = await run(*answered(history, asked, "Fri 17:00"), tools=BOARD_TOOLS_WITH_ASK)

    assert tool_calls(dragged) == ["drag_and_drop"]
    assert calls(dragged)[0].arguments == {"from": "event-1", "to": "slot-2026-08-14-17"}


@pytest.mark.django_db(transaction=True)
async def test_a_typed_answer_works_as_well_as_a_chosen_one() -> None:
    """`allow_custom` is load-bearing: free text goes through the same matcher.

    The card offers three slots and the page has four. Typing the fourth reaches
    it, because the answer is resolved against the page exactly as the original
    utterance is — not compared to the options that were displayed.
    """
    await _seed()
    history, asked = await _asked()

    dragged = await run(*answered(history, asked, "Thursday at 15:00"), tools=BOARD_TOOLS_WITH_ASK)

    assert calls(dragged)[0].arguments == {"from": "event-1", "to": "slot-2026-08-13-15"}


@pytest.mark.django_db(transaction=True)
async def test_a_chosen_option_is_matched_to_the_page_not_parsed() -> None:
    """A label the parser cannot read at all, which only identity can resolve.

    The page owns its labels. This one carries no time to find, so an answer that
    had to be parsed would fall back to "some Friday slot" — three of them — and ask
    the user to rephrase the option it had just offered them.
    """
    await _seed()
    worded = {
        **PAGE,
        "slots": [
            {"id": "slot-2026-08-14-9", "label": "Friday morning", "day": "2026-08-14", "hour": 9},
            {"id": "slot-2026-08-14-14", "label": "Friday afternoon", "day": "2026-08-14", "hour": 14},
        ],
    }
    history = [user_message("move standup to Friday")]
    first = await run(*history, tools=BOARD_TOOLS_WITH_ASK)
    history = answered(history, first, worded)
    asked = await run(*history, tools=BOARD_TOOLS_WITH_ASK)
    assert calls(asked)[0].arguments["options"] == ["Friday morning", "Friday afternoon"]

    dragged = await run(*answered(history, asked, "Friday afternoon"), tools=BOARD_TOOLS_WITH_ASK)

    assert calls(dragged)[0].arguments == {"from": "event-1", "to": "slot-2026-08-14-14"}


@pytest.mark.django_db(transaction=True)
async def test_a_written_time_beats_a_bare_number_beside_it() -> None:
    """Found in a browser: the real page labels its slots `Fri 14 10:00`.

    A card of labels shaped like that teaches the user to type one, and a typed
    answer is parsed rather than matched — so the first small number in the phrase
    is the day of the month. Reading it as the hour moved the card to 14:00, the
    same trap `_booking` documents for ISO dates arriving from a new direction. An
    hour written as a time therefore wins over a number that merely could be one.
    """
    await _seed()
    history, asked = await _asked()

    dragged = await run(*answered(history, asked, "Friday 14 11:00"), tools=BOARD_TOOLS_WITH_ASK)

    assert calls(dragged)[0].arguments == {"from": "event-1", "to": "slot-2026-08-14-11"}


@pytest.mark.django_db(transaction=True)
async def test_an_answer_naming_no_slot_is_not_asked_again() -> None:
    """One question per turn: a loop of cards is worse than a sentence."""
    await _seed()
    history, asked = await _asked()

    settled = await run(*answered(history, asked, "wherever you like"), tools=BOARD_TOOLS_WITH_ASK)

    assert tool_calls(settled) == []
    assert "tell me which day and hour" in text(settled).lower()


@pytest.mark.django_db(transaction=True)
async def test_the_inserted_question_does_not_renumber_the_steps_after_it() -> None:
    """The verification read still happens, and still judges the answered slot.

    The whole reason the question is lifted out of the turn. With it counted, the
    drag's result would look like the second page read and the move would be
    reported without ever being checked.
    """
    await _seed()
    history, asked = await _asked()
    history = answered(history, asked, "Fri 17:00")
    dragged = await run(*history, tools=BOARD_TOOLS_WITH_ASK)
    # What the component's own `drag_and_drop` returns. A bare sentence here would
    # be a decline: the script tells a page action that ran from one that did not
    # by the shape of the result, since the decline's wording is the host's.
    history = answered(history, dragged, {"dragged": True, "from": "event-1", "to": "slot-2"})

    verifying = await run(*history, tools=BOARD_TOOLS_WITH_ASK)
    assert tool_calls(verifying) == ["read_page"], "the drag is checked, not assumed"

    moved = {
        **PAGE,
        "events": [
            {"id": "event-1", "label": "Standup", "day": "2026-08-14", "hour": 17},
            PAGE["events"][1],
        ],
    }
    settled = await run(*answered(history, verifying, moved), tools=BOARD_TOOLS_WITH_ASK)

    assert "Standup is now at Fri 17:00" in text(settled)


async def _asked() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The conversation up to the question, and the run that asked it."""
    history = [user_message("move standup to Friday")]
    first = await run(*history, tools=BOARD_TOOLS_WITH_ASK)
    history = answered(history, first, PAGE)
    return history, await run(*history, tools=BOARD_TOOLS_WITH_ASK)


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
    await Event.objects.acreate(owner=user, title="Standup", day="2026-08-10", start_hour=9)
