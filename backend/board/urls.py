"""Board routes: a plain DRF router over the spec-driven viewset."""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from board.views import EventViewSet

router = DefaultRouter()
router.register("events", EventViewSet, basename="event")

urlpatterns = router.urls
