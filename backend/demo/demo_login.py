"""A one-click sign-in, so the gallery needs no password typed anywhere.

Demo only. It is mounted only when `DEBUG` and `DEMO_AUTOLOGIN` are both on, and
it exists because the admin surface needs a session principal while the point of
the demo is somewhere else entirely. **Do not copy this into anything real.**
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect


def demo_login(request: HttpRequest) -> HttpResponse:
    if not (settings.DEBUG and settings.DEMO_AUTOLOGIN):
        return HttpResponseNotFound("Demo login is off.")
    user = get_user_model().objects.filter(username="demo").first()
    if user is None:
        return HttpResponseNotFound("Run `manage.py seed_board` first.")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(request.GET.get("next") or "/admin/board/event/")
