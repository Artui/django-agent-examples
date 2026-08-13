"""Two mounts: the board API and the agent endpoint.

`agent.urls` is the `(patterns, app_name, namespace)` triple, mounted directly at
a prefix of this project's choosing — the `admin.site.urls` idiom. Everything the
web component needs hangs off that one prefix: the run endpoint itself plus the
tool, skill and thread catalogs.
"""

from __future__ import annotations

from django.urls import include, path

from agent.server import agent

urlpatterns = [
    path("api/", include("board.urls")),
    path("agent/", agent.urls),
]
