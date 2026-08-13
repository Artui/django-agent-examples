"""A scripted local model, so the gallery runs with no API key and in CI.

This is a Pydantic-AI `FunctionModel`: a function that plays the part of a model,
reading the message history and emitting either text or a tool call. It routes a
handful of phrasings to the tool sequence they imply, which is enough to
demonstrate every interaction the frontends expose without pretending to be an
LLM. Anything it does not recognise gets a short help reply.

Two rules of the seam it sits behind:

- A response is either all text or all tool calls, never a mix.
- Which round of a turn we are in is derived from the history — the number of
  tool returns recorded since the last user prompt — so the same function serves
  every round without holding state.

The ids it acts on are never guessed. It asks the page for them with the web
component's `read_page` tool and matches the labels the page reported, so the
page stays the authority on what exists and what it is called.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

HELP = (
    "I can drive this board for you. Try:\n\n"
    "- *move standup to Friday at 11:00*\n"
    "- *scroll to Friday 17:00*\n"
    "- *switch to the agenda view*\n"
    "- *what is on the board?*\n"
    "- *put the onboarding doc first in the backlog*\n"
    "- *book a design sync on Friday at 14:00*\n"
    "- *note: ship the gallery this week*\n"
    "- attach `samples/week.csv` and say *import these events*"
)

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class Attached:
    """One file the user uploaded, as the run instructions describe it."""

    id: str
    name: str


@dataclass(frozen=True)
class Turn:
    """One user utterance and everything the tools have answered since."""

    prompt: str
    returns: tuple[Any, ...]
    # One per return, from `ToolReturnPart.outcome`: "success", "failed",
    # "denied" or "interrupted". A denied approval is the only refusal in this
    # gallery that says so in a field rather than in prose.
    outcomes: tuple[str, ...] = ()
    # One per return: which tool answered. Only the branches that have to tell
    # their own steps apart from an inserted one read it.
    names: tuple[str, ...] = ()
    # The files this conversation carries. Not read from the messages like
    # everything else above -- see `_attached`.
    attached: tuple[Attached, ...] = field(default_factory=tuple)

    @property
    def round(self) -> int:
        return len(self.returns)

    @property
    def last(self) -> Any:
        return self.returns[-1] if self.returns else None

    @property
    def last_outcome(self) -> str:
        return self.outcomes[-1] if self.outcomes else "success"

    def answer_to(self, name: str) -> Any:
        """What `name` last returned this turn, or `None` if it was never called."""
        for index in reversed(range(len(self.returns))):
            if self.names[index] == name:
                return self.returns[index]
        return None

    def without(self, name: str) -> Turn:
        """This turn as if `name` had never been called.

        Every script here reads its position from the number of returns so far, so
        a step inserted in the middle would renumber everything after it — asking a
        question would make the drag think it was the verification read. Lifting the
        inserted step out is what keeps the rest of a branch counting what it always
        counted, and the alternative (name-based state everywhere) is a lot of
        machinery for one optional question.
        """
        keep = [index for index, called in enumerate(self.names) if called != name]
        return Turn(
            prompt=self.prompt,
            returns=tuple(self.returns[index] for index in keep),
            outcomes=tuple(self.outcomes[index] for index in keep),
            names=tuple(self.names[index] for index in keep),
            attached=self.attached,
        )


def build_scripted_model() -> FunctionModel:
    return FunctionModel(stream_function=_stream, model_name="scripted-demo")


async def _stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
    turn = _read_turn(messages, _attached(info.instructions))
    available = {definition.name for definition in info.function_tools}
    for chunk in _respond(turn, available):
        yield chunk


def _respond(turn: Turn, available: set[str]) -> list[Any]:
    """The whole script: one utterance plus a round number in, one response out."""
    text = turn.prompt.lower()

    # Which surface is this? The tools the client declared say so, and they differ
    # completely: the board apps register page actions, the admin registers
    # admin-aware ones. Routing on capability rather than on configuration is how
    # one model serves both.
    if "open_changelist" in available:
        return _admin_respond(turn, available, text)

    # Before every verb below, because with a file in hand the verb is about the
    # file: "add these to the board" is an import, not a booking.
    #
    # Both halves of the condition are load-bearing. The manifest is derived from
    # the message history rather than from this run, so it rides *every* later
    # turn of the conversation -- deliberately, so the ids survive a reload. A
    # branch that keyed on the attachment alone would therefore hijack the next
    # "move standup to Friday" for as long as the thread lived.
    if turn.attached and _ABOUT_THE_FILE.search(text):
        return _attachment_script(turn, available)

    # Before the move branch: "book" and "schedule" are both scheduling verbs, and
    # this one writes through the server rather than through the page.
    if re.search(r"\b(book|schedule|create)\b", text) or re.search(r"^add\b", text):
        return _book_script(turn, available)
    if re.search(r"\b(move|reschedule|drag|shift)\b", text) and "backlog" not in text:
        return _move_script(turn, available)
    if re.search(r"\b(scroll|jump|show me|find|where is)\b", text):
        return _scroll_script(turn, available)
    if re.search(r"\b(agenda|day view|week view|switch to|open the)\b", text):
        return _navigate_script(turn, available)
    if re.search(r"\b(backlog|first|top|reorder|before)\b", text):
        return _reorder_script(turn, available)
    if re.search(r"\b(filter|only|hide|room)\b", text):
        return _filter_script(turn, available)
    if re.search(r"\bnote\b", text):
        return _note_script(turn, available)
    if re.search(r"\b(what|which|list|how many|summar|overview|busy)\b", text):
        return _overview_script(turn, available)
    return [HELP]


# --- the admin surface --------------------------------------------------------

ADMIN_HELP = (
    "I can drive this admin for you. Try:\n\n"
    "- *open the events list*\n"
    "- *how many events are there?*\n"
    "- *rename standup to Morning standup*\n"
    "- *what is registered in the admin?*"
)

MODEL = {"app_label": "board", "model": "event"}


def _admin_respond(turn: Turn, available: set[str], text: str) -> list[Any]:
    if re.search(r"\b(rename|retitle|call it|change the title)\b", text):
        return _rename_script(turn, available)
    if re.search(r"\b(open|list|show|go to)\b", text) and "admin" not in text:
        return _changelist_script(turn, available)
    if re.search(r"\b(how many|count)\b", text):
        return _count_script(turn, available)
    if re.search(r"\b(registered|models|admin|what)\b", text):
        return _admin_models_script(turn, available)
    return [ADMIN_HELP]


def _changelist_script(turn: Turn, available: set[str]) -> list[Any]:
    """Navigate, which in an admin means a full page reload.

    `open_changelist` carries `x-navigates`, so the component writes a checkpoint,
    lets the browser leave, and completes the tool call from the page it lands on.
    The result this round sees is that landed page — the round trip is an
    observation point rather than a dropped conversation.
    """
    if "open_changelist" not in available:
        return [_missing_tools("open_changelist")]
    if turn.round == 0:
        return [_call("open_changelist", MODEL)]
    landed = _as_page(turn.last)
    where = landed.get("url") or landed.get("title") or "the changelist"
    return [f"Opened {where}."]


def _count_script(turn: Turn, available: set[str]) -> list[Any]:
    """Answered from the ORM, server-side, with no page involved."""
    if "count_model" not in available:
        return [_missing_tools("count_model")]
    if turn.round == 0:
        return [_call("count_model", MODEL)]
    return [f"There are {turn.last} events."]


def _admin_models_script(turn: Turn, available: set[str]) -> list[Any]:
    if "list_admin_models" not in available:
        return [_missing_tools("list_admin_models")]
    if turn.round == 0:
        return [_call("list_admin_models", {})]
    rows = turn.last if isinstance(turn.last, list) else []
    names = [str(row.get("model") or row.get("label")) for row in rows if isinstance(row, dict)]
    return ["Registered in this admin: " + (", ".join(names) if names else "nothing.")]


def _rename_script(turn: Turn, available: set[str]) -> list[Any]:
    """Find it, open its form, type, save — across two page reloads.

    This is the multi-page shape in full: a server tool to find the row, a
    navigating tool to reach it, a destructive tool the user confirms, and a
    second navigating tool whose result is the page Django rendered in reply,
    validation errors included.
    """
    needed = {"query_model", "open_changeform", "fill_field", "submit_form"}
    if not needed <= available:
        return [_missing_tools(", ".join(sorted(needed)))]
    old, new = _rename_parts(turn.prompt)
    if new is None:
        return ['Say it as *rename standup to "Morning standup"*.']
    if turn.round == 0:
        return [
            _call(
                "query_model",
                {**MODEL, "filter": {"title__icontains": old}, "fields": ["id", "title"], "limit": 1},
            )
        ]
    if turn.round == 1:
        rows = turn.last if isinstance(turn.last, list) else []
        if not rows or not isinstance(rows[0], dict):
            return [f"I could not find an event matching {old!r}."]
        return [_call("open_changeform", {**MODEL, "pk": rows[0].get("id")})]
    if turn.round == 2:
        return [_call("fill_field", {"field_name": "title", "value": new})]
    if turn.round == 3:
        if _refused(turn):
            return ["I left the title alone."]
        return [_call("submit_form", {"action": "save"})]
    if _refused(turn):
        return ["I typed it but did not save, so nothing changed."]
    landed = _as_page(turn.last)
    errors = landed.get("errors") or landed.get("errorlist")
    if errors:
        return [f"Django refused the save: {errors}"]
    return [f"Renamed it to {new}."]


def _rename_parts(prompt: str) -> tuple[str, str | None]:
    match = re.search(r"rename\s+(.+?)\s+to\s+(.+?)\s*$", prompt, re.I)
    if match is None:
        return prompt, None
    return match.group(1).strip(), match.group(2).strip().strip("\"'")


# --- the board surface --------------------------------------------------------


def _move_script(turn: Turn, available: set[str]) -> list[Any]:
    """Read the page, drag the card onto the slot, read the page again, report.

    The drag is what persists the move: the page's own drop handler posts it to
    the board API, which is also the operation this agent could have called
    directly as a spec tool. Driving the page is the point — the user watches the
    card move.

    The fourth step is there because of what the third one cannot tell us.
    `drag_and_drop` returns as soon as it has dispatched the drag; whether the
    page's own save succeeded is invisible to it, so a refused move (the slot was
    already taken) still comes back as a successful tool call. Reading the page a
    second time is how the claim gets checked before it is made. An agent that
    drives a page instead of calling the operation trades the server's answer for
    the visible action, and this is the price of that trade.

    One step is optional, and finding out why is what put it here. "Move standup to
    Friday" names a day and not an hour, and the board has four Friday slots — this
    used to take the first one, silently. So the ambiguity is the trigger: when more
    than one slot fits what the user said, ask which, using `ask_user`.

    That is a *frontend* tool, offered by the component when the host sets
    `askUser`. The agent calls it, the browser renders a card, and the answer comes
    back as that call's result — an ordinary client tool whose handler is a person.
    Nothing is configured server-side, and the options are the slots the page
    reported rather than a list held here, so the user is offered what exists.
    """
    if not {"read_page", "drag_and_drop"} <= available:
        return [_missing_tools("read_page and drag_and_drop")]
    if turn.round == 0:
        return [_call("read_page", {})]
    # Lifted out before the rounds below are counted -- see `Turn.without`.
    answer = turn.answer_to("ask_user")
    turn = turn.without("ask_user")
    if turn.round == 1:
        page = _as_page(turn.last)
        card = _match_card(page, turn.prompt)
        if card is None:
            return [f"I could not find an event matching that on the board. {_names(page)}"]
        choices = _slot_choices(page, turn.prompt, answer)
        if len(choices) == 1:
            return [_call("drag_and_drop", {"from": card["id"], "to": choices[0]["id"]})]
        # More than one slot fits, or none does. Both are questions, and only one of
        # them is worth asking twice: having already asked and still not got a slot,
        # say how to phrase it rather than showing another card.
        if answer is None and "ask_user" in available:
            return [_ask_which_slot(page, card, choices)]
        return ["Tell me which day and hour to move it to, for example *Friday at 11:00*."]
    if turn.round == 2:
        if _refused(turn):
            return ["I left it where it was."]
        return [_call("read_page", {})]
    # The page reports when it is mid-save, so the verification waits for it
    # instead of racing it. Bounded: the client stops the loop at ten rounds, and
    # a page stuck saving is itself the answer.
    if _as_page(turn.last).get("saving") is True and turn.round < 6:
        return [_call("read_page", {})]
    return [_verdict(turn, answer)]


def _slot_choices(
    page: dict[str, Any], prompt: str, answer: Any = None
) -> list[dict[str, Any]]:
    """The slots consistent with the day and hour that were mentioned.

    Cardinality is the whole reason this exists rather than a first-match lookup:
    one slot means go, several mean ask, none means the utterance said nothing
    about where. An occupied slot is still a choice here — naming one outright is
    allowed to fail, and it failing visibly is what the verification read is for.
    The question offers only free ones, which is `_ask_which_slot`'s job.

    An answer is matched to a label first and only then parsed, because the options
    came from the page: a chosen one is that slot, whatever its label happens to
    read like, and a host free to label a slot "Friday morning" should not need the
    parser to understand it.

    Text that matches no label is parsed, and that is what makes `allow_custom`
    real: type *Friday at 17:00* and it resolves even if the card showed four other
    slots. An answer that narrows to nothing falls back to what was already known,
    so "wherever you like" leaves the original ambiguity in place instead of
    replacing it with silence.
    """
    if answer is not None:
        named = _slot_labelled(page, str(answer))
        if named is not None:
            return [named]
        narrowed = _slot_choices(page, str(answer))
        if narrowed:
            return narrowed
    weekday = next((day for day in WEEKDAYS if day[:3] in prompt.lower()), None)
    hour = _hour(prompt)
    if weekday is None and hour is None:
        return []
    return [
        slot
        for slot in page.get("slots") or []
        if (hour is None or slot.get("hour") == hour)
        and (weekday is None or _weekday_of(slot.get("day")) == weekday)
    ]


def _ask_which_slot(
    page: dict[str, Any], card: dict[str, Any], choices: list[dict[str, Any]]
) -> dict[int, DeltaToolCall]:
    """Ask which slot, offering the free ones among the candidates.

    Occupied slots are dropped here and only here: offering a cell that is already
    held would be inviting the user to pick a move the board will refuse.
    """
    taken = {(event.get("day"), event.get("hour")) for event in _events(page)}
    free = [slot for slot in choices if (slot.get("day"), slot.get("hour")) not in taken]
    label = card.get("label", "it")
    if not free:
        # Nothing worth offering, so ask in words rather than showing an empty card.
        return _call(
            "ask_user",
            {"question": f"Where should {label} go?", "allow_custom": True},
        )
    return _call(
        "ask_user",
        {
            "question": f"Which slot should {label} move to?",
            "options": [str(slot.get("label")) for slot in free[:4]],
            "allow_custom": True,
        },
    )


def _verdict(turn: Turn, answer: Any = None) -> str:
    """Did the move actually take? Compare the page before and after.

    The target is resolved from the first page read, the same way the drag resolved
    it — including the answer to any question — so the claim is checked against the
    slot the drag actually aimed at rather than a re-reading of the utterance.
    """
    before, after = _as_page(turn.returns[0]), _as_page(turn.last)
    choices = _slot_choices(before, turn.prompt, answer)
    slot = choices[0] if len(choices) == 1 else None
    card = _match_card(before, turn.prompt)
    if slot is None or card is None:
        return "The board has moved on since I looked; ask me again."
    moved = next(
        (
            event
            for event in _events(after)
            if event.get("id") == card["id"]
            and event.get("day") == slot.get("day")
            and event.get("hour") == slot.get("hour")
        ),
        None,
    )
    if moved is not None:
        return f"{card['label']} is now at {slot['label']}."
    holder = next(
        (
            event.get("label")
            for event in _events(after)
            if event.get("day") == slot.get("day") and event.get("hour") == slot.get("hour")
        ),
        None,
    )
    if holder is not None:
        return (
            f"The board refused that: {slot['label']} is held by {holder}. "
            f"{card['label']} has not moved. Pick another slot and I will try again."
        )
    return f"The board did not accept the move, so {card['label']} has not moved."


def _scroll_script(turn: Turn, available: set[str]) -> list[Any]:
    if not {"read_page", "scroll_to"} <= available:
        return [_missing_tools("read_page and scroll_to")]
    if turn.round == 0:
        return [_call("read_page", {})]
    if turn.round == 1:
        page = _as_page(turn.last)
        target = _match_slot(page, turn.prompt) or _match_card(page, turn.prompt)
        if target is None:
            return [f"I could not tell what to scroll to. {_names(page)}"]
        return [_call("scroll_to", {"target": target["id"]})]
    return ["There it is, in the middle of the board."]


def _navigate_script(turn: Turn, available: set[str]) -> list[Any]:
    if "navigate_to_route" not in available:
        return [_missing_tools("navigate_to_route")]
    if turn.round == 0:
        route = _match_route(turn.prompt)
        if route is None:
            return ["I can switch between the *week*, *day* and *agenda* views."]
        return [_call("navigate_to_route", {"route_id": route})]
    return ["Switched the view."]


def _reorder_script(turn: Turn, available: set[str]) -> list[Any]:
    """Reordering within the backlog list, by dragging one card onto another."""
    if not {"read_page", "drag_and_drop"} <= available:
        return [_missing_tools("read_page and drag_and_drop")]
    if turn.round == 0:
        return [_call("read_page", {})]
    if turn.round == 1:
        page = _as_page(turn.last)
        backlog = page.get("backlog") or []
        card = _match_card(page, turn.prompt, pool=backlog)
        if card is None or not backlog:
            return [f"I could not find that in the backlog. {_names(page)}"]
        anchor = backlog[0] if backlog[0]["id"] != card["id"] else None
        if anchor is None:
            return [f"{card['label']} is already first in the backlog."]
        return [_call("drag_and_drop", {"from": card["id"], "to": anchor["id"]})]
    return [_settled(turn, "Reordered the backlog.", "I left the backlog alone.")]


def _filter_script(turn: Turn, available: set[str]) -> list[Any]:
    """Write a piece of the host's own state, through the tools it registered.

    `set_board` is stamped destructive by `registerPageState`, and this page's
    `confirmPredicate` returns false for it — so changing a filter does not
    prompt while a drag still does. The predicate is authoritative in both
    directions, which a static schema flag cannot be.
    """
    if "set_board" not in available:
        return [_missing_tools("set_board")]
    if turn.round == 0:
        room = _match_room(turn.prompt)
        return [_call("set_board", {"room": room})]
    return ["Filter applied."]


def _match_room(prompt: str) -> str:
    lowered = prompt.lower()
    if "all" in lowered or "everything" in lowered or "clear" in lowered:
        return "all"
    # The rooms are the page's, so match on the words it uses rather than a list
    # held here. Anything unrecognised falls back to showing everything.
    for word in re.findall(r"[A-Za-z]+", prompt):
        if word.istitle() and word.lower() not in {"filter", "room", "show", "only", "hide"}:
            return word
    return "all"


def _book_script(turn: Turn, available: set[str]) -> list[Any]:
    """Write through the server, which is where the approval gate lives.

    Nothing in this script mentions the gate, and that is the point. A gated call
    is deferred rather than executed: the run finishes on an interrupt, the
    component asks, and the resumed run delivers the tool return this script is
    already waiting for. So the round it sees is the round it would have seen
    unguarded, which is what makes gating a deployment decision rather than
    something a model has to be taught.

    The denial is the exception it does have to read, because a denied call also
    comes back as a tool return.
    """
    if "create_event" not in available:
        return [_missing_tools("create_event")]
    if turn.round == 0:
        title, day, hour = _booking(turn.prompt)
        if title is None:
            return ["Say it as *book a design sync on Friday at 14:00*."]
        arguments: dict[str, Any] = {"title": title}
        if day is not None and hour is not None:
            arguments |= {"day": day, "start_hour": hour}
        return [_call("create_event", arguments)]
    if _refused(turn):
        return ["Nothing was booked."]
    event = _as_page(turn.last)
    title = event.get("title") or "it"
    if event.get("day"):
        return [f"Booked {title} for {event['day']} at {event.get('start_hour')}:00."]
    return [f"Added {title} to the backlog."]


# --- the file the user attached -----------------------------------------------

# What makes an utterance about the attachment rather than about the board. Kept
# narrow on purpose: see the routing comment in `_respond`.
_ABOUT_THE_FILE = re.compile(r"\b(import|csv|file|attachment|attached|upload(?:ed)?|these)\b")

_ASKING_WHAT_IT_SAYS = re.compile(r"\b(what|read|says?|show|summar|contain)\b")


def _attachment_script(turn: Turn, available: set[str]) -> list[Any]:
    """Read the uploaded file, and put what it says on the board.

    The bytes never came through the conversation. The composer uploaded them to
    `attachments/` and sent an id, the server turned the ids into a manifest this
    model reads in its own instructions, and the content is fetched here, in a
    tool call, from the store. So a 2 MB file costs one upload rather than a
    base64 payload on every turn of the thread.

    A real model needs none of this spelled out; the manifest already names the
    tool to call. The parsing below is what an LLM would do with the CSV text once
    it had it, written out longhand because this stand-in cannot read.
    """
    if "read_attachment" not in available:
        # The tool is per-request and only exists when a store is configured, so
        # this is the reply a mount without `attachment_store=` would give.
        return [_missing_tools("read_attachment")]
    attached = turn.attached[-1]
    if turn.round == 0:
        return [_call("read_attachment", {"attachment_id": attached.id})]
    content = str(turn.returns[0])
    if _ASKING_WHAT_IT_SAYS.search(turn.prompt.lower()):
        return [f"{attached.name} says:\n\n{content}"]
    if "create_event" not in available:
        return [_missing_tools("create_event")]
    rows = _csv_rows(content)
    if not rows:
        return [
            f"I read {attached.name} and found no events in it. I can import a CSV "
            "with a title, day, start_hour, duration_hours and room column."
        ]
    if turn.round == 1:
        # One round, one call per row -- which is how a model that has just read
        # three rows actually behaves. Each call is gated independently, so the
        # component renders three cards and the run resumes once they are all
        # answered. Approving two and denying one is a supported outcome, and the
        # report below is written to describe it.
        return [_calls([("create_event", row) for row in rows])]
    return [_import_verdict(turn, attached.name)]


def _csv_rows(content: str) -> list[dict[str, Any]]:
    """The CSV as `create_event` arguments, one dict per usable row.

    Weekday names are resolved here rather than shipped as dates, so the sample
    file does not go stale — a fixed `2026-08-19` in the repository would import
    into the past a month later. A row with only one of day and hour lands in the
    backlog rather than half-scheduled, which is the service's own rule for an
    event with no slot.
    """
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(content)):
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        arguments: dict[str, Any] = {"title": title}
        room = (raw.get("room") or "").strip()
        if room:
            arguments["room"] = room
        duration = _positive_int(raw.get("duration_hours"))
        if duration is not None:
            arguments["duration_hours"] = duration
        day, hour = _day(raw.get("day")), _positive_int(raw.get("start_hour"))
        if day is not None and hour is not None:
            arguments |= {"day": day, "start_hour": hour}
        rows.append(arguments)
    return rows


def _day(value: str | None) -> str | None:
    """An ISO date as itself, a weekday name as that day of the week on screen.

    Deliberately not `_next_weekday`, which is what a spoken booking uses. A file
    listing "Wednesday" is describing the week the board is showing, so resolving
    it forwards would put half an import into next week — correct by the letter
    and invisible in a grid that displays one week. A booking is a request about
    the future and does resolve forwards. The two readings differ because the
    utterances do.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        pass
    lowered = text.lower()
    weekday = next((day for day in WEEKDAYS if day.startswith(lowered[:3])), None)
    return None if weekday is None else _this_week(weekday, datetime.date.today())


def _this_week(name: str, today: datetime.date) -> str:
    """That weekday of the week `today` falls in, counting from Monday."""
    monday = today - datetime.timedelta(days=today.weekday())
    return (monday + datetime.timedelta(days=WEEKDAYS.index(name))).isoformat()


def _positive_int(value: str | None) -> int | None:
    text = (value or "").strip()
    return int(text) if text.isdigit() else None


def _import_verdict(turn: Turn, filename: str) -> str:
    """Report the import from the returns, not from the calls that were made.

    Three rows can end three ways and every one of them is a tool *return*, so the
    calls say nothing: counting them would report three imports for one approval.
    Each return is read instead, and the three are told apart by what came back —

    - the created event, so the row landed;
    - `outcome == "denied"`, so the person said no to that card;
    - an `error`, so the board itself refused. That is the service's own
      `ServiceConflict` reaching the model as text, which is what a slot already
      taken looks like from here.

    A demo that reported only the first of those would call a refused import a
    success, which is the failure mode worth writing out.
    """
    added: list[str] = []
    refused: list[str] = []
    declined = 0
    for content, outcome in zip(turn.returns[1:], turn.outcomes[1:]):
        row = _as_page(content)
        if row.get("title") is not None:
            added.append(str(row["title"]))
        elif outcome == "denied":
            declined += 1
        else:
            refused.append(str(row.get("error") or content))
    parts = [
        f"Added {_join(added)} from {filename}."
        if added
        else f"Nothing from {filename} reached the board."
    ]
    if declined:
        parts.append(f"You turned down {declined} of them.")
    parts.extend(f"The board refused a row: {reason}" for reason in refused)
    return " ".join(parts)


def _join(titles: list[str]) -> str:
    if len(titles) == 1:
        return titles[0]
    return ", ".join(titles[:-1]) + f" and {titles[-1]}"


def _note_script(turn: Turn, available: set[str]) -> list[Any]:
    """The week note, which lives in AG-UI shared state rather than in the board.

    Two shapes, and the second is the interesting one. Given a body, this writes it
    straight through. Told to summarise the week into the note, it reads the board
    first and writes what it found — two tools, the second's argument coming from
    the first's result, with the page re-rendering off the state snapshot rather
    than off either tool's return value.
    """
    if "write_week_note" not in available:
        return [_missing_tools("write_week_note, read_week_note")]
    text = turn.prompt.lower()
    body = _note_body(turn.prompt)
    if body is None and re.search(r"\b(what|read|say|says|show|does)\b", text):
        if turn.round == 0:
            return [_call("read_week_note", {})]
        return [str(turn.last)]
    if body is None:
        # No body given: read the week, then write what it says.
        if turn.round == 0:
            return [_call("week_overview", {})]
        if turn.round == 1:
            return [_call("write_week_note", {"body": str(turn.last)})]
        return ["Written to the week note."]
    if turn.round == 0:
        return [_call("write_week_note", {"body": body})]
    return [f"The week note now reads: {body}"]


def _note_body(prompt: str) -> str | None:
    """The text to write, when the utterance carries one."""
    for pattern in (
        r"note\s*:\s*(.+)$",
        r"note\s+(?:that\s+says|to\s+say|to\s+read)\s+(.+)$",
        r"note\s+to\s+(.+)$",
    ):
        match = re.search(pattern, prompt, re.I)
        if match is not None:
            return match.group(1).strip().strip("\"'")
    return None


def _overview_script(turn: Turn, available: set[str]) -> list[Any]:
    """Answer from the server, through the spec tool the board declares."""
    if turn.round == 0 and "list_events" in available:
        return [_call("list_events", {})]
    if turn.round == 0 and "week_overview" in available:
        return [_call("week_overview", {})]
    if turn.round == 0:
        return [_missing_tools("list_events")]
    return _summarise(turn.last)


# --- helpers ------------------------------------------------------------------


def _call(name: str, arguments: dict[str, Any]) -> dict[int, DeltaToolCall]:
    return {0: DeltaToolCall(name=name, json_args=json.dumps(arguments))}


def _calls(requested: list[tuple[str, dict[str, Any]]]) -> dict[int, DeltaToolCall]:
    """Several calls in one response, which the index of each keeps apart."""
    return {
        index: DeltaToolCall(name=name, json_args=json.dumps(arguments))
        for index, (name, arguments) in enumerate(requested)
    }


def _missing_tools(names: str) -> str:
    return (
        f"This page has not registered {names}, so I cannot do that here. "
        "The host decides which tools exist."
    )


_MANIFEST_LABEL = "Files the user has attached to this conversation"
_MANIFEST_LINE = re.compile(r"^- (?P<name>.+?) \(id: (?P<id>[^,)]+)[,)]", re.M)


def _attached(instructions: str | None) -> tuple[Attached, ...]:
    """The uploaded files, read out of this run's own instructions.

    The one place this script reads its instructions instead of its messages, and
    that is where the manifest is: the server delivers it as additional run
    instructions, fenced and labelled as client-supplied data, so it is never
    merged into the operator's prompt, never stored on the thread, and never
    echoed back to the browser. A real model reads it the same way — as a list of
    ids it may pass to `read_attachment` — and this parses the lines it would read.

    The label is checked before the lines are matched, so a page that described
    itself in the same shape could not be mistaken for a file.
    """
    if not instructions or _MANIFEST_LABEL not in instructions:
        return ()
    return tuple(
        Attached(id=match.group("id").strip(), name=match.group("name").strip())
        for match in _MANIFEST_LINE.finditer(instructions)
    )


def _read_turn(messages: Sequence[ModelMessage], attached: tuple[Attached, ...]) -> Turn:
    """Pull the current utterance and the tool returns recorded after it."""
    prompt = ""
    returns: list[Any] = []
    outcomes: list[str] = []
    names: list[str] = []
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                content = part.content
                prompt = content if isinstance(content, str) else _flatten(content)
                # A new utterance resets the round count.
                returns = []
                outcomes = []
                names = []
            elif isinstance(part, ToolReturnPart):
                returns.append(part.content)
                outcomes.append(part.outcome)
                names.append(part.tool_name)
    return Turn(
        prompt=prompt,
        returns=tuple(returns),
        outcomes=tuple(outcomes),
        names=tuple(names),
        attached=attached,
    )


def _flatten(content: Sequence[Any]) -> str:
    return " ".join(item for item in content if isinstance(item, str))


def _as_page(content: Any) -> dict[str, Any]:
    """A tool result arrives as whatever the client serialised; be forgiving."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return {}
    return content if isinstance(content, dict) else {}


def _slot_labelled(page: dict[str, Any], answer: str) -> dict[str, Any] | None:
    """The slot whose own label the answer repeats, ignoring case and spacing."""
    wanted = " ".join(answer.split()).casefold()
    for slot in page.get("slots") or []:
        if " ".join(str(slot.get("label", "")).split()).casefold() == wanted:
            return slot
    return None


def _match_card(
    page: dict[str, Any], prompt: str, pool: list[dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    """Find the event whose label shares the most words with the utterance."""
    candidates = pool if pool is not None else [*_events(page), *(page.get("backlog") or [])]
    words = _words(prompt)
    best, score = None, 0
    for candidate in candidates:
        overlap = len(_words(candidate.get("label", "")) & words)
        if overlap > score:
            best, score = candidate, overlap
    return best


def _match_slot(page: dict[str, Any], prompt: str) -> dict[str, Any] | None:
    """Resolve "Thursday at 15:00" against the slots the page reported.

    Weekday names are compared against each slot's own date, so the calendar
    lives in the page rather than in this function.
    """
    weekday = next((day for day in WEEKDAYS if day[:3] in prompt.lower()), None)
    hour = _hour(prompt)
    if weekday is None and hour is None:
        return None
    for slot in page.get("slots") or []:
        if hour is not None and slot.get("hour") != hour:
            continue
        if weekday is not None and _weekday_of(slot.get("day")) != weekday:
            continue
        return slot
    return None


_BOOKING = re.compile(
    r"\b(?:book|schedule|create|add)\s+(?:a|an|the)?\s*(.+?)(?:\s+(?:on|for|at|to)\s+.*)?$",
    re.I,
)


def _booking(prompt: str) -> tuple[str | None, str | None, int | None]:
    """Pull a title, and a day and hour if the utterance carries both.

    With no day and hour the event lands in the backlog, which is the service's
    own rule rather than something this script decides.
    """
    match = _BOOKING.search(prompt.strip())
    if match is None:
        return None, None, None
    title = match.group(1).strip(" .!?").capitalize()
    if not title:
        return None, None, None
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", prompt)
    # `_hour` reads the first small number it finds, and an ISO date is full of
    # them, so the date is removed before the time is read rather than after.
    hour = _hour(prompt.replace(iso.group(1), " ") if iso else prompt)
    if iso is not None:
        return title, iso.group(1), hour
    weekday = next((day for day in WEEKDAYS if day[:3] in prompt.lower()), None)
    if weekday is None:
        return title, None, hour
    return title, _next_weekday(weekday, datetime.date.today()), hour


def _next_weekday(name: str, today: datetime.date) -> str:
    """The next occurrence of a weekday, today included.

    A page-driven move resolves a weekday against the slots the page reported, so
    the page stays the authority. A server-side booking has no page in the path,
    so this is the one place the script picks a date itself.
    """
    ahead = (WEEKDAYS.index(name) - today.weekday()) % 7
    return (today + datetime.timedelta(days=ahead)).isoformat()


def _match_route(prompt: str) -> str | None:
    for route in ("agenda", "day", "week"):
        if route in prompt.lower():
            return route
    return None


def _hour(prompt: str) -> int | None:
    """The hour a phrase names, preferring one written as a time.

    Two patterns, tried in order, because a bare number is the loosest possible
    reading: "Fri 14 10:00" carries a day of the month before it carries an hour,
    and 14 is a perfectly plausible hour. An explicit `10:00` or `10am` says what it
    is, so it wins; a bare number is still accepted, since *move it to 11* is a
    reasonable thing to type.
    """
    lowered = prompt.lower()
    match = re.search(r"\b(\d{1,2})(?::(\d{2})|\s*(?=am|pm))\s*(am|pm)?\b", lowered)
    if match is None:
        match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", lowered)
    if match is None:
        return None
    hour = int(match.group(1))
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return hour if 0 <= hour <= 23 else None


def _weekday_of(iso_day: Any) -> str | None:
    if not isinstance(iso_day, str):
        return None
    try:
        return WEEKDAYS[datetime.date.fromisoformat(iso_day).weekday()]
    except ValueError:
        return None


def _events(page: dict[str, Any]) -> list[dict[str, Any]]:
    return page.get("events") or []


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2}


def _names(page: dict[str, Any]) -> str:
    labels = [item.get("label", "") for item in [*_events(page), *(page.get("backlog") or [])]]
    return "On the board: " + ", ".join(label for label in labels if label) if labels else ""


def _settled(turn: Turn, done: str, declined: str) -> str:
    """Report what the last tool actually returned, decline included."""
    return declined if _refused(turn) else done


def _refused(turn: Turn) -> bool:
    """Whether the last tool return was a refusal rather than a result.

    A refused action is a tool *return*, not an error, which is why an answer
    reads the result instead of assuming the action happened: the tool call looks
    identical either way.

    The two mechanisms this gallery shows refuse differently, and only one of them
    is structured:

    - A **server-side** approval the user denies comes back with
      ``ToolReturnPart.outcome == "denied"``. That flag is the reliable signal, and
      it is checked first.
    - A **client-side** confirmation the user cancels is an ordinary successful
      tool result whose *content* happens to say so, because the browser executed
      the tool and reported a string. There is nothing structured to read.

    The prose check is therefore for the client-side case only, and it is
    deliberately loose: the wording is not ours and it is not stable. Three
    phrasings already reach here for one idea — the component's "User declined the
    action.", django-ag-ui's "Cancelled by user." for a denied approval, and
    pydantic-ai's own "The tool call was denied." default underneath it.
    """
    if turn.last_outcome == "denied":
        return True
    body = turn.last if isinstance(turn.last, str) else json.dumps(turn.last)
    return any(word in body.lower() for word in ("declin", "denied", "cancel"))


def _summarise(content: Any) -> list[str]:
    rows = content
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except json.JSONDecodeError:
            return [rows]
    if isinstance(rows, dict):
        rows = rows.get("results", rows.get("events", []))
    if not isinstance(rows, list) or not rows:
        return ["The board is empty."]
    scheduled = [row for row in rows if isinstance(row, dict) and row.get("day")]
    backlog = [row for row in rows if isinstance(row, dict) and not row.get("day")]
    lines = [f"You have {len(scheduled)} scheduled and {len(backlog)} in the backlog.\n\n"]
    for row in scheduled:
        lines.append(f"- {row.get('title')} on {row.get('day')} at {row.get('start_hour')}:00\n")
    for row in backlog:
        lines.append(f"- {row.get('title')} (backlog)\n")
    return lines
