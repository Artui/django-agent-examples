from __future__ import annotations

import datetime
import json
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from django_spec_tasks.worker.run_spec import run_spec

from board.models import Event, Membership, Routine
from tests.wire import AUTH


def _seed() -> Routine:
    call_command("seed_board", stdout=StringIO())
    return Routine.objects.get(name="Monday week review")


def _fire_due() -> None:
    """One sweep, then the worker's half of each firing it enqueued, as `db_worker` would."""
    past = timezone.now() - datetime.timedelta(minutes=1)
    Routine.objects.filter(enabled=True).update(next_fire_at=past)
    call_command("run_due_routines", stdout=StringIO())
    for run_id in Routine.objects.exclude(last_run_id=None).values_list("last_run_id", flat=True):
        run_spec(run_id)


def _thread_row(thread_id: str) -> dict[str, Any]:
    rows = json.loads(Client().get("/agent/threads/", headers=AUTH).content)["threads"]
    return next(row for row in rows if row["thread_id"] == thread_id)


@pytest.mark.django_db(transaction=True)
def test_the_seeded_routine_is_due_next_monday_at_eight_in_its_zone() -> None:
    routine = _seed()

    fires = routine.next_fire_at.astimezone(routine.get_timezone())

    assert (fires.weekday(), fires.time()) == (0, datetime.time(8, 0))
    assert routine.get_preapproved_tools()[0].destructive is True


@pytest.mark.django_db(transaction=True)
def test_a_firing_lands_a_thread_that_names_its_routine() -> None:
    routine = _seed()

    _fire_due()

    routine.refresh_from_db()
    assert routine.last_thread_id is not None
    row = _thread_row(routine.last_thread_id)
    assert row["routine"] == {"id": str(routine.pk), "name": "Monday week review"}


@pytest.mark.django_db(transaction=True)
def test_a_pre_approved_destructive_call_runs_unasked_and_is_recorded_as_the_routine_s() -> None:
    routine = _seed()

    _fire_due()

    routine.refresh_from_db()
    assert Event.objects.filter(title="Week review", start_hour=17).exists()
    assert _thread_row(routine.last_thread_id)["status"] != "waiting"
    tool = next(m for m in _messages(routine.last_thread_id) if m["role"] == "tool")
    assert tool["metadata"]["answered_by"] == f"routine:{routine.pk}"


@pytest.mark.django_db(transaction=True)
def test_a_gated_call_the_routine_was_not_granted_parks_under_needs_you() -> None:
    routine = _seed()
    Routine.objects.filter(pk=routine.pk).update(preapproved_tools=[])

    _fire_due()

    routine.refresh_from_db()
    assert not Event.objects.filter(title="Week review").exists()
    rows = json.loads(Client().get("/agents-home/inbox/", headers=AUTH).content)["threads"]
    row = next(row for row in rows if row["thread_id"] == routine.last_thread_id)
    assert (row["agent_id"], row["status"]) == ("board", "waiting")
    assert row["run_id"]


@pytest.mark.django_db(transaction=True)
def test_a_parked_firing_holds_the_next_one_back() -> None:
    routine = _seed()
    Routine.objects.filter(pk=routine.pk).update(preapproved_tools=[])
    _fire_due()
    routine.refresh_from_db()
    parked = routine.last_thread_id

    _fire_due()

    routine.refresh_from_db()
    assert routine.last_thread_id == parked


@pytest.mark.django_db(transaction=True)
def test_the_editor_pins_the_seeded_grant_as_the_mount_s_guard_does() -> None:
    _seed()
    body = {
        "name": "Friday booking",
        "prompt": "Book a wrap-up on Friday at 16:00",
        "schedule": {"kind": "weekly", "weekdays": [4], "at": "09:00"},
        "timezone": "Europe/London",
        "preapprovedTools": ["create_event"],
        "enabled": True,
    }
    client = Client()

    refused = client.post(
        "/agent/routines/",
        json.dumps(body),
        content_type="application/json",
        headers=AUTH,
    )
    body["confirmDestructive"] = ["create_event"]
    made = client.post(
        "/agent/routines/",
        json.dumps(body),
        content_type="application/json",
        headers=AUTH,
    )

    assert refused.status_code == 409, refused.content[:300]
    assert made.status_code == 201, made.content[:300]
    granted = json.loads(made.content)["preapprovedTools"]
    assert granted == [{"name": "create_event", "destructive": True}]


@pytest.mark.django_db(transaction=True)
def test_a_principal_who_left_the_organisation_has_the_routine_paused_not_fired() -> None:
    routine = _seed()
    Membership.objects.filter(user=routine.principal).delete()

    _fire_due()

    routine.refresh_from_db()
    assert (routine.enabled, routine.last_run_id) == (False, None)
    assert routine.paused_reason


def _messages(thread_id: str) -> list[dict[str, Any]]:
    response = Client().get(f"/agent/threads/{thread_id}/", headers=AUTH)
    return json.loads(response.content)["messages"]
