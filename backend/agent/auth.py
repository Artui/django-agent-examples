"""Who is acting, on the agent endpoint.

The AG-UI views are plain Django views, so DRF's authentication classes do not
apply to them: establishing the principal is the host's job, through a
`get_user` hook. This one reads the same DRF token the frontends already send to
the board API, which is why one header authenticates both surfaces.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from rest_framework.authtoken.models import Token


def token_user(request: HttpRequest) -> Any:
    """Resolve `Authorization: Token <key>` to a user, or `None` for a 401.

    A sync ORM lookup is fine here — the endpoint runs sync hooks off the event
    loop.
    """
    scheme, _, key = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "token" or not key.strip():
        return None
    token = Token.objects.select_related("user").filter(key=key.strip()).first()
    return None if token is None else token.user
