"""A scripted transcription backend, so voice input runs with no provider.

The same trade as `agent/scripted.py`, one seam along. That file plays the part of
a model so the gallery needs no API key; this one plays the part of speech-to-text
so it needs no provider either — and both are one object the real thing replaces:

    AGUIServer(transcription_backend=OpenAITranscriptionBackend())

What it does *not* do is pretend to hear anything. It maps the clip onto one of the
board's own utterances, so pressing the mic drives the board and the rest of the
demo continues from there.

The mapping is the clip's byte length, which makes it a **function of the audio**
rather than of a counter: the same recording always transcribes to the same
sentence, a different one usually to a different sentence, and nothing here holds
state between requests. A counter would have been friendlier to a person clicking
the mic repeatedly and would have made every test order-dependent.
"""

from __future__ import annotations

from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest

# Utterances the scripted model actually answers, so the mic is a way into the
# demo rather than a dead end. Order is part of the contract below: index 0 is
# what an empty clip transcribes to.
PHRASES = (
    "what is on the board?",
    "move standup to Friday at 11:00",
    "book a design sync on Friday at 14:00",
    "switch to the agenda view",
    "show only the Basalt room",
)


class ScriptedTranscriptionBackend:
    """Answers with a fixed phrase chosen by the clip's size.

    Async because the protocol is: a real backend is an HTTP call to a provider,
    and the view awaits it. There is nothing to await here, which is why this
    method does no I/O and still has to be declared `async` — the shape of the seam
    belongs to the thing being replaced, not to the replacement.
    """

    async def transcribe(self, audio: UploadedFile, *, request: HttpRequest) -> str:
        return PHRASES[(audio.size or 0) % len(PHRASES)]


__all__ = ["PHRASES", "ScriptedTranscriptionBackend"]
