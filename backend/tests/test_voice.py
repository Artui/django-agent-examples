"""Voice input: audio in, text out, and nothing kept.

The last of the gallery's offline stand-ins. A `TranscriptionBackend` is one async
method — no store, no artefact, nothing to open or delete — so replacing it with a
real provider is one argument on the mount and nothing else. Which is why the
scripted one is worth having: the seam is provable without a key.

The endpoint is a plain multipart POST answering `{"text": ...}`, and the mic in
the composer exists only because a host pointed at it. Both are asserted here; what
a browser adds is the recorder, and the component owns that.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import AsyncClient
from rest_framework.authtoken.models import Token

from agent.transcribe import PHRASES, ScriptedTranscriptionBackend

AUTH = {"authorization": "Token demo-token-not-a-secret"}


@pytest.mark.django_db(transaction=True)
async def test_a_clip_comes_back_as_something_the_board_understands() -> None:
    """The transcript is a phrase the scripted model answers, not filler.

    A stand-in that returned "lorem ipsum" would prove the endpoint and dead-end
    the demo. Every phrase it can return drives the board.
    """
    await _seed()

    text = await _transcribe(b"x" * 12)

    assert text in PHRASES


@pytest.mark.django_db(transaction=True)
async def test_the_same_clip_always_transcribes_the_same_way() -> None:
    """A function of the audio, not of a counter — which is what keeps it testable.

    A rotating index would read more naturally to someone clicking the mic twice,
    and would make every test here depend on the order the suite happened to run
    in. The clip's own size chooses the phrase instead, so this is reproducible
    and holds no state between requests.
    """
    await _seed()
    clip = b"a" * 3

    assert await _transcribe(clip) == await _transcribe(clip)
    assert await _transcribe(clip) == PHRASES[3 % len(PHRASES)]


@pytest.mark.django_db(transaction=True)
async def test_an_empty_clip_still_answers() -> None:
    """A recorder that captured nothing is a real case, and it is not an error.

    The browser can hand over a zero-byte blob when a click is quicker than the
    microphone; answering with the first phrase keeps the composer moving rather
    than surfacing a failure the user cannot act on.
    """
    await _seed()

    assert await _transcribe(b"") == PHRASES[0]


@pytest.mark.django_db(transaction=True)
async def test_voice_is_refused_without_a_token() -> None:
    """The same closed default as every other route on this mount."""
    await _seed()

    response = await AsyncClient().post(
        "/agent/transcribe/",
        data={"audio": SimpleUploadedFile("clip.webm", b"x", content_type="audio/webm")},
    )

    assert response.status_code in (401, 403)


async def test_the_backend_is_a_transcription_backend() -> None:
    """Structural, because the protocol is what the mount type-checks against.

    `TranscriptionBackend` is a runtime-checkable Protocol, so this catches a
    signature drifting out of shape — a renamed keyword, a sync `def` — which the
    HTTP tests above would report as a 500 rather than as what it is.
    """
    from django_ag_ui import TranscriptionBackend

    assert isinstance(ScriptedTranscriptionBackend(), TranscriptionBackend)


async def _transcribe(clip: bytes) -> str:
    response = await AsyncClient().post(
        "/agent/transcribe/",
        data={"audio": SimpleUploadedFile("clip.webm", clip, content_type="audio/webm")},
        headers=AUTH,
    )
    assert response.status_code == 200, response.content[:300]
    body: dict[str, Any] = json.loads(response.content)
    return str(body["text"])


async def _seed() -> None:
    user = await get_user_model().objects.acreate(username="demo")
    await Token.objects.acreate(user=user, key="demo-token-not-a-secret")
