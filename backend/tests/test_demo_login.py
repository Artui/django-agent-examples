"""The demo sign-in only ever lands you back on this host.

`?next=` is caller-controlled, and this view redirects after signing someone in,
which is the sequence that makes an open redirect worth exploiting: the person
following the link has just watched this site accept them. The sign-in itself is
a demo shortcut and is guarded by `DEBUG`; where it lands is not, because the
shape of this file is what a reader copies.

Driven against the view rather than the URL: `/demo-login/` is registered at
import time only while `DEBUG` is on, so calling the function keeps the test
saying what it means whatever the environment did to that setting.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings

from demo.demo_login import DEFAULT_DESTINATION, demo_login

# Every spelling of "somewhere else" this view has to refuse. The bare absolute
# URL is the obvious one; the rest are the ones a hand-rolled check waves through
# -- a protocol-relative URL carries no scheme to match on, a backslash is
# normalised to a slash by browsers but not by `urlsplit`, a leading control
# character is stripped before the URL is parsed, and the last one starts with
# this view's own path as a prefix of somebody else's domain.
OFF_SITE = [
    "https://evil.example/",
    "http://evil.example/admin/",
    "//evil.example/",
    "/\\evil.example/",
    "\\\\evil.example/",
    "\x00//evil.example/",
    "https://demo-login.evil.example/",
]

# What a legitimate `?next=` looks like: this host, or no host at all.
ON_SITE = ["/admin/", "/admin/board/event/?room=blue", "/api/events/"]


@pytest.mark.django_db
@pytest.mark.parametrize("target", OFF_SITE)
def test_an_off_site_next_is_refused(target: str) -> None:
    _, response = _sign_in(next=target)

    assert response.status_code == 302
    assert response["Location"] == DEFAULT_DESTINATION


@pytest.mark.django_db
@pytest.mark.parametrize("target", ON_SITE)
def test_a_same_site_next_is_honoured(target: str) -> None:
    """The refusal has to be narrow, or the parameter may as well not exist."""
    _, response = _sign_in(next=target)

    assert response.status_code == 302
    assert response["Location"] == target


@pytest.mark.django_db
def test_no_next_lands_on_the_board() -> None:
    _, response = _sign_in()

    assert response.status_code == 302
    assert response["Location"] == DEFAULT_DESTINATION


@pytest.mark.django_db
def test_the_person_really_is_signed_in() -> None:
    """The redirect only matters because the session is real by the time it runs."""
    request, response = _sign_in(next="https://evil.example/")

    assert SESSION_KEY in request.session
    assert response["Location"] == DEFAULT_DESTINATION


@pytest.mark.django_db
def test_the_view_is_off_without_debug() -> None:
    """The gate the file-level warning is about, asserted rather than assumed."""
    get_user_model().objects.get_or_create(username="demo")
    with override_settings(DEBUG=False, DEMO_AUTOLOGIN=True):
        response = demo_login(_request())

    assert response.status_code == 404


def _sign_in(**query: str) -> tuple[HttpRequest, HttpResponse]:
    """Call the view the way the demo runs it: DEBUG on, autologin on."""
    get_user_model().objects.get_or_create(username="demo")
    request = _request(**query)
    with override_settings(DEBUG=True, DEMO_AUTOLOGIN=True):
        return request, demo_login(request)


def _request(**query: str) -> HttpRequest:
    """A GET with a session attached, the way a real request arrives."""
    request = RequestFactory().get("/demo-login/", query)
    SessionMiddleware(lambda _: HttpResponse()).process_request(request)
    request.session.save()
    return request
