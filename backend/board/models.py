"""The board's one model.

An event is either **scheduled** (it has a day and an hour, so it sits in a cell
of the week grid) or **unscheduled** (it sits in the backlog, ordered by
`position`). Both states are the same row, which is what makes "drag it out of
the backlog onto Thursday at 15:00" a single operation.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django_spec_agents.skills import AbstractSkill, SkillPolicy


class Event(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="events",
        on_delete=models.CASCADE,
    )
    title = models.CharField(max_length=120)
    room = models.CharField(max_length=60, blank=True)
    # Null on both means "in the backlog". They move together; a day without an
    # hour is not a state the board can draw.
    day = models.DateField(null=True, blank=True)
    start_hour = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_hours = models.PositiveSmallIntegerField(default=1)
    # Backlog ordering. Meaningless while the event is scheduled, kept so a
    # round trip out of the grid and back does not lose the place it had.
    position = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("day", "start_hour", "position", "id")
        indexes = [models.Index(fields=["owner", "day", "start_hour"])]

    def __str__(self) -> str:
        if self.day is None:
            return f"{self.title} (backlog)"
        return f"{self.title} on {self.day} at {self.start_hour}:00"

    @property
    def scheduled(self) -> bool:
        return self.day is not None and self.start_hour is not None


class Organisation(models.Model):
    """The tenant a skill is shared in: the smallest one that makes "company skill" honest."""

    name = models.CharField(max_length=120)

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    """A user's one organisation and whether they administer it, which decides company writes."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="membership", on_delete=models.CASCADE
    )
    organisation = models.ForeignKey(
        Organisation, related_name="memberships", on_delete=models.CASCADE
    )
    is_admin = models.BooleanField(default=False)

    def __str__(self) -> str:
        role = "admin" if self.is_admin else "member"
        return f"{self.user} ({role} of {self.organisation})"


class Skill(AbstractSkill):
    """A stored skill in one organisation: personal with an `owner`, the company's without one."""

    organisation = models.ForeignKey(Organisation, related_name="skills", on_delete=models.CASCADE)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="skills",
        on_delete=models.CASCADE,
    )

    class Meta:
        ordering = ("organisation", "name", "pk")

    def __str__(self) -> str:
        scope = "company" if self.owner_id is None else f"personal to {self.owner}"
        return f"/{self.name} ({scope})"

    @classmethod
    def skill_policy(cls) -> SkillPolicy[Skill] | None:
        from board.skill_policy import OrganisationSkillPolicy

        return OrganisationSkillPolicy()
