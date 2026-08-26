"""A one-click sign-in, so the gallery needs no password typed anywhere.

Demo only. It is mounted only when `DEBUG` and `DEMO_AUTOLOGIN` are both on, and
it exists because the admin surface needs a session principal while the point of
the demo is somewhere else entirely. **Do not copy this into anything real.**

That warning is about the sign-in, which has no password and no check of any
kind. The `?next=` handling below is the opposite: it is written the way a real
view has to write it, because the shape of this file is what gets copied even
when the warning is read. See `_destination`.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

#: Where a sign-in with no `?next=` lands: the board, through the admin.
DEFAULT_DESTINATION = "/admin/board/event/"


def demo_login(request: HttpRequest) -> HttpResponse:
    if not (settings.DEBUG and settings.DEMO_AUTOLOGIN):
        return HttpResponseNotFound("Demo login is off.")
    user = get_user_model().objects.filter(username="demo").first()
    if user is None:
        return HttpResponseNotFound("Run `manage.py seed_board` first.")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(_destination(request))


def _destination(request: HttpRequest) -> str:
    """Where to land, with `?next=` checked rather than trusted.

    `?next=` is whatever the URL said, which means whoever wrote the link chose
    it. Handing it to `redirect()` unchecked is an **open redirect**: a link to
    this host sends the browser to another one, and it does so *after* the sign-in,
    so the person following it has just been told this site is trustworthy. That is
    the whole trick -- the destination is somebody else's login page, wearing this
    site's referral.

    The check is Django's own, and the same one `django.contrib.auth`'s `LoginView`
    makes for the same reason: the target has to be relative, or point at a host
    this request already came from, and it may not downgrade an HTTPS request to
    plain HTTP. Anything else falls back to the default rather than being followed.

    This is deliberately not gated on `DEBUG`. The rest of the file is a demo
    shortcut, but a reader who keeps the shortcut and swaps the gate -- a staging
    flag instead of `DEBUG`, which is the obvious next step -- would otherwise
    inherit a working open redirect in an environment this file never anticipated.
    """
    target = request.GET.get("next") or ""
    allowed = url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )
    return target if allowed else DEFAULT_DESTINATION
