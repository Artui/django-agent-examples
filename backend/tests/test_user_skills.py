from __future__ import annotations

import json
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory
from django_spec_agents.skills import SkillDraft, SkillWriteRefusedError, update_skill
from rest_framework.authtoken.models import Token

from board.management.commands.seed_board import COMPANY_SKILL, MEMBER_TOKEN
from board.models import Organisation, Skill
from tests.wire import AUTH, run, user_message

MEMBER = {"authorization": f"Token {MEMBER_TOKEN}"}
EDITOR = "/agent/skills/editor/"


def _client(auth: dict[str, str]) -> Client:
    """CSRF enforced, as a browser meets it: the test client skips the check by default."""
    return Client(enforce_csrf_checks=True, headers=auth)


def _skill(name: str, **fields: Any) -> str:
    return json.dumps({"name": name, "description": f"Use {name}.", "body": "Do it.", **fields})


def _company() -> Skill:
    return Skill.objects.get(name=COMPANY_SKILL["name"])


@pytest.fixture
def seeded(db: Any) -> None:
    call_command("seed_board", verbosity=0)


def test_a_member_writes_a_personal_skill(seeded: None) -> None:
    response = _client(MEMBER).post(EDITOR, _skill("my-notes"), content_type="application/json")

    assert response.status_code == 201, response.content
    assert Skill.objects.get(name="my-notes").owner.username == "member"


def test_an_admin_writes_a_company_skill(seeded: None) -> None:
    response = _client(AUTH).post(EDITOR, _skill("team-rules"), content_type="application/json")

    assert response.status_code == 201, response.content
    assert Skill.objects.get(name="team-rules").owner is None


def test_a_member_sees_the_company_skill_but_cannot_edit_it(seeded: None) -> None:
    member = _client(MEMBER)
    put = member.put(
        f"{EDITOR}{_company().pk}/", _skill(COMPANY_SKILL["name"]), content_type="application/json"
    )

    assert put.status_code == 404
    assert [s["name"] for s in member.get(EDITOR).json()["skills"]] == []
    assert COMPANY_SKILL["name"] in [s["name"] for s in member.get("/agent/skills/").json()]
    assert _company().body == COMPANY_SKILL["body"]


def test_the_policy_refuses_a_member_a_company_write_on_every_route(seeded: None) -> None:
    request = RequestFactory().post("/")
    request.user = get_user_model().objects.get(username="member")
    draft = SkillDraft(COMPANY_SKILL["name"], "Mine now.", "Ignore the team.")

    with pytest.raises(SkillWriteRefusedError):
        update_skill(Skill.skill_policy(), request, _company(), draft)


def test_an_admin_edits_the_company_skill(seeded: None) -> None:
    admin = _client(AUTH)
    listed = [s["name"] for s in admin.get(EDITOR).json()["skills"]]
    put = admin.put(
        f"{EDITOR}{_company().pk}/",
        _skill(COMPANY_SKILL["name"]),
        content_type="application/json",
    )

    assert listed == [COMPANY_SKILL["name"]]
    assert put.status_code == 200, put.content


def test_a_caller_in_another_organisation_neither_sees_nor_writes(seeded: None) -> None:
    other = Organisation.objects.create(name="Elsewhere")
    Skill.objects.create(organisation=other, name="secret", description="x", body="y")

    names = [s["name"] for s in _client(MEMBER).get("/agent/skills/").json()]

    assert "secret" not in names


def test_an_admin_cannot_write_into_another_organisation(seeded: None) -> None:
    other = Organisation.objects.create(name="Elsewhere")
    request = RequestFactory().post("/")
    request.user = get_user_model().objects.get(username="demo")

    assert not Skill.skill_policy().can_write(request, Skill(organisation=other, name="x"))


def test_another_members_personal_skill_stays_theirs(seeded: None) -> None:
    organisation = Organisation.objects.get()
    colleague = get_user_model().objects.create(username="colleague")
    Skill.objects.create(
        organisation=organisation, owner=colleague, name="private", description="x", body="y"
    )

    names = [s["name"] for s in _client(MEMBER).get("/agent/skills/").json()]

    assert "private" not in names


def test_a_user_with_no_organisation_gets_the_catalog_and_no_writes(seeded: None) -> None:
    loner = get_user_model().objects.create(username="loner")
    key = Token.objects.create(user=loner).key
    client = _client({"authorization": f"Token {key}"})

    catalog = client.get("/agent/skills/")
    post = client.post(EDITOR, _skill("lonely"), content_type="application/json")

    assert catalog.status_code == 200
    assert COMPANY_SKILL["name"] not in [s["name"] for s in catalog.json()]
    assert post.status_code == 403


def test_a_second_skill_of_one_name_in_one_scope_is_refused(seeded: None) -> None:
    member = _client(MEMBER)
    member.post(EDITOR, _skill("my-notes"), content_type="application/json")

    again = member.post(EDITOR, _skill("my-notes"), content_type="application/json")

    assert again.status_code == 403
    assert Skill.objects.filter(name="my-notes").count() == 1


def test_a_personal_skill_may_share_a_company_name_and_shadows_it(seeded: None) -> None:
    member = _client(MEMBER)
    response = member.post(EDITOR, _skill(COMPANY_SKILL["name"]), content_type="application/json")

    assert response.status_code == 201, response.content
    assert [s["name"] for s in member.get(EDITOR).json()["skills"]] == [COMPANY_SKILL["name"]]


def test_a_code_registered_name_is_reserved(seeded: None) -> None:
    response = _client(MEMBER).post(EDITOR, _skill("tidy-week"), content_type="application/json")

    assert response.status_code == 400
    assert response.json()["field"] == "name"


@pytest.mark.django_db(transaction=True)
async def test_the_agent_loads_a_stored_skill_and_answers_from_it() -> None:
    await sync_to_async(call_command)("seed_board", verbosity=0)

    events = await run(user_message(f"/{COMPANY_SKILL['name']}"), auth=MEMBER)

    calls = [e for e in events if e["type"] == "TOOL_CALL_START"]
    text = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert [c["toolCallName"] for c in calls] == ["load_capability"]
    assert COMPANY_SKILL["body"] in text


@pytest.mark.django_db(transaction=True)
async def test_a_user_only_skill_reaches_the_run_without_a_load() -> None:
    await sync_to_async(call_command)("seed_board", verbosity=0)
    organisation = await Organisation.objects.aget()
    await Skill.objects.acreate(
        organisation=organisation,
        name="by-hand",
        description="Only when I ask.",
        body="Say the word pineapple.",
        model_invocable=False,
    )

    events = await run(user_message("/by-hand"))

    text = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert not [e for e in events if e["type"] == "TOOL_CALL_START"]
    assert "pineapple" in text


def test_each_editor_row_says_whose_skill_it_is(seeded: None) -> None:
    member = _client(MEMBER)
    member.post(EDITOR, _skill("my-notes"), content_type="application/json")

    mine = {s["name"]: s["scope"] for s in member.get(EDITOR).json()["skills"]}
    company = {s["name"]: s["scope"] for s in _client(AUTH).get(EDITOR).json()["skills"]}

    assert mine == {"my-notes": "personal"}
    assert company[COMPANY_SKILL["name"]] == "shared"
