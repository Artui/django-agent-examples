"""Four mounts, two of them agents.

`/api/` and `/agent/` serve the single-page apps: token auth, no cookie, JSON and
SSE. `/admin/` and `/admin-agent/` serve the admin: a session principal, CSRF on,
server-rendered pages. Both agent mounts are the same class underneath and neither
knows about the other — which is what makes running them side by side worth doing.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from agent.admin_server import agent as admin_agent
from agent.server import agent as spa_agent
from demo.demo_login import demo_login

urlpatterns = [
    path("api/", include("board.urls")),
    path("agent/", spa_agent.urls),
    path("admin/", admin.site.urls),
    path("admin-agent/", admin_agent.urls),
]

# The agent endpoint streams, so this project runs under an ASGI server — and a
# bare ASGI server serves no static files. `runserver` would serve them and
# cannot stream, so the two halves of "run it in development" pull apart. These
# patterns are the seam that satisfies both: an ordinary Django view under
# whatever server, DEBUG only. Without it the admin loses its stylesheets *and*
# the vendored component bundle, so the sidebar silently does not exist.
urlpatterns += staticfiles_urlpatterns()

if settings.DEBUG and settings.DEMO_AUTOLOGIN:
    # Demo only. See demo/demo_login.py.
    urlpatterns.append(path("demo-login/", demo_login, name="demo-login"))
