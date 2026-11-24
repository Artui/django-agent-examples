from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.http import HttpRequest

from board.models import Membership, Routine


class OwnRoutinesPolicy:
    """Each member sees and writes their own routines, in the organisation they belong to."""

    def visible(self, request: HttpRequest) -> QuerySet[Routine]:
        membership = _membership(request.user)
        if membership is None:
            return Routine.objects.none()
        return Routine.objects.filter(
            organisation_id=membership.organisation_id, principal_id=request.user.pk
        )

    def can_write(self, request: HttpRequest, routine: Routine) -> bool:
        membership = _membership(request.user)
        if membership is None or routine.organisation_id != membership.organisation_id:
            return False
        return routine.principal_id in (None, request.user.pk)

    def can_run(self, principal: Any, routine: Routine) -> bool:
        """A firing has no request: the principal must still be active and in the organisation."""
        membership = _membership(principal)
        return (
            principal.is_active
            and membership is not None
            and membership.organisation_id == routine.organisation_id
        )

    def new_routine(self, request: HttpRequest) -> Routine:
        membership = _membership(request.user)
        if membership is None:
            return Routine()
        return Routine(organisation_id=membership.organisation_id)


def _membership(user: Any) -> Membership | None:
    if user is None or not user.is_authenticated:
        return None
    return Membership.objects.filter(user=user).first()
