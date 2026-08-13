"""The board in the Django admin.

An ordinary `ModelAdmin` — the agent's admin tools work off admin's structural
DOM contracts (`#id_<field>`, the `_save` submit names, the filter sidebar), so
nothing here is written for the agent's benefit.
"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from board.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "day", "start_hour", "duration_hours", "room", "owner")
    list_filter = ("room", "day")
    search_fields = ("title", "room")
    ordering = ("day", "start_hour", "position")
    fields = ("owner", "title", "room", "day", "start_hour", "duration_hours", "position")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Event]:
        """Scoped like every other surface: staff see their own board here too.

        A real admin usually shows everything to staff. Keeping the same scoping
        as the API is what lets the two surfaces be compared honestly.
        """
        queryset: QuerySet[Event] = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(owner=request.user)
