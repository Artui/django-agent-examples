from __future__ import annotations

import datetime
import json
from io import StringIO
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.test import Client, RequestFactory
from django.utils import timezone
from django_spec_tasks.worker.run_spec import run_spec

from board.models import Event, Membership, Organisation, Routine
from board.routine_policy import OwnRoutinesPolicy
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


MEMBER = {"authorization": "Token member-token-not-a-secret"}


def _member() -> Any:
    return get_user_model().objects.get(username="member")


def _copy(routine: Routine, **changes: Any) -> Routine:
    """A second routine beside the seeded one, with `changes` applied."""
    clone = Routine.objects.get(pk=routine.pk)
    clone.pk = None
    for field, value in {"name": "Mine", **changes}.items():
        setattr(clone, field, value)
    clone.save()
    return clone


def _request(user: Any) -> Any:
    request = RequestFactory().get("/")
    request.user = user
    return request


def _names(response: Any) -> list[str]:
    return [row["name"] for row in json.loads(response.content)["routines"]]


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


@pytest.mark.django_db(transaction=True)
def test_the_editor_lists_each_member_only_their_own_routines() -> None:
    routine = _seed()
    _copy(routine, principal=_member())
    client = Client()

    theirs = client.get("/agent/routines/", headers=MEMBER)
    admin = client.get("/agent/routines/", headers=AUTH)

    assert _names(theirs) == ["Mine"]
    assert _names(admin) == ["Monday week review"]


@pytest.mark.django_db(transaction=True)
def test_a_member_s_put_to_another_member_s_routine_is_a_404() -> None:
    routine = _seed()

    response = Client().put(
        f"/agent/routines/{routine.pk}/", "{}", content_type="application/json", headers=MEMBER
    )

    assert response.status_code == 404, response.content[:300]
    assert Routine.objects.get(pk=routine.pk).name == "Monday week review"


@pytest.mark.django_db(transaction=True)
def test_visible_is_the_callers_own_routines_in_their_organisation() -> None:
    routine = _seed()
    _copy(routine, principal=_member())
    elsewhere = Organisation.objects.create(name="Elsewhere")
    _copy(routine, name="Theirs", principal=_member(), organisation=elsewhere)
    policy = OwnRoutinesPolicy()

    seen = policy.visible(_request(_member()))

    assert [r.name for r in seen] == ["Mine"], "not demo's, and not one in another organisation"


@pytest.mark.django_db(transaction=True)
def test_visible_is_empty_without_a_membership_or_a_signed_in_user() -> None:
    routine = _seed()
    stranger = get_user_model().objects.create(username="stranger")
    _copy(routine, principal=stranger)
    policy = OwnRoutinesPolicy()

    for user in (stranger, AnonymousUser(), None):
        assert list(policy.visible(_request(user))) == [], user


@pytest.mark.django_db(transaction=True)
def test_can_write_refuses_another_organisation_another_principal_and_a_stranger() -> None:
    routine = _seed()
    member = _member()
    elsewhere = Organisation.objects.create(name="Elsewhere")
    abroad = _copy(routine, principal=member, organisation=elsewhere)
    shared = Routine(organisation_id=routine.organisation_id, principal=None)
    mine = _copy(routine, name="Own", principal=member)
    stranger = get_user_model().objects.create(username="stranger")
    policy = OwnRoutinesPolicy()
    request = _request(member)

    assert not policy.can_write(request, abroad), "another organisation"
    assert not policy.can_write(request, routine), "another member's"
    assert policy.can_write(request, mine)
    assert policy.can_write(request, shared), "an unsaved one has no principal yet"
    assert not policy.can_write(_request(stranger), mine), "no membership"
    assert not policy.can_write(_request(AnonymousUser()), mine), "not signed in"


@pytest.mark.django_db(transaction=True)
def test_a_principal_moved_to_another_organisation_has_the_routine_paused_not_fired() -> None:
    routine = _seed()
    elsewhere = Organisation.objects.create(name="Elsewhere")
    Membership.objects.filter(user=routine.principal).update(organisation=elsewhere)

    _fire_due()

    routine.refresh_from_db()
    assert (routine.enabled, routine.last_run_id) == (False, None)
    assert routine.paused_reason


@pytest.mark.django_db(transaction=True)
def test_an_inactive_principal_has_the_routine_paused_not_fired() -> None:
    routine = _seed()
    get_user_model().objects.filter(pk=routine.principal_id).update(is_active=False)

    _fire_due()

    routine.refresh_from_db()
    assert (routine.enabled, routine.last_run_id) == (False, None)
    assert routine.paused_reason


@pytest.mark.django_db(transaction=True)
def test_a_second_run_now_while_the_first_firing_is_pending_is_a_409() -> None:
    routine = _seed()
    url = f"/agent/routines/{routine.pk}/run/"
    client = Client()

    first = client.post(url, "{}", content_type="application/json", headers=AUTH)
    second = client.post(url, "{}", content_type="application/json", headers=AUTH)

    assert first.status_code == 202, first.content[:300]
    assert second.status_code == 409, second.content[:300]
    assert "not finished" in json.loads(second.content)["error"]


def _messages(thread_id: str) -> list[dict[str, Any]]:
    response = Client().get(f"/agent/threads/{thread_id}/", headers=AUTH)
    return json.loads(response.content)["messages"]
