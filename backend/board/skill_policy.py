from __future__ import annotations

from django.db.models import F, Q, QuerySet
from django.http import HttpRequest

from board.models import Membership, Skill


class OrganisationSkillPolicy:
    """Members write personal skills, admins write the company's; everyone reads both."""

    def visible(self, request: HttpRequest) -> QuerySet[Skill]:
        """The caller's organisation's skills, personal ones first so they shadow the company's."""
        membership = _membership(request)
        if membership is None:
            return Skill.objects.none()
        return Skill.objects.filter(
            Q(owner__isnull=True) | Q(owner_id=request.user.pk),
            organisation_id=membership.organisation_id,
        ).order_by(F("owner").asc(nulls_last=True), "pk")

    def can_write(self, request: HttpRequest, skill: Skill) -> bool:
        membership = _membership(request)
        if membership is None or skill.organisation_id != membership.organisation_id:
            return False
        if skill.owner_id is None and not membership.is_admin:
            return False
        if skill.owner_id is not None and skill.owner_id != request.user.pk:
            return False
        return not _name_taken_in_scope(skill)

    def new_skill(self, request: HttpRequest) -> Skill:
        """An admin's new skill is the company's, a member's their own: the wire names no scope."""
        membership = _membership(request)
        if membership is None:
            return Skill()
        owner = None if membership.is_admin else request.user
        return Skill(organisation_id=membership.organisation_id, owner=owner)


def _membership(request: HttpRequest) -> Membership | None:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return Membership.objects.filter(user=user).first()


def _name_taken_in_scope(skill: Skill) -> bool:
    """A second row of one name in one scope would never be reached, so it is refused instead."""
    return (
        Skill.objects.filter(
            organisation_id=skill.organisation_id, owner_id=skill.owner_id, name=skill.name
        )
        .exclude(pk=skill.pk)
        .exists()
    )
