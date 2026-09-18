"""Dictating a brief: speech in, words out, nothing kept. Implementation Plan F-C-02.

THE RECORDING IS NOT A RECORD
-------------------------------
An advocate dictating a brief is typing with their voice. The words come back
into the brief box to be read and corrected, and only what the advocate then
sends becomes part of the file. The recording itself is transcribed and dropped:
keeping it would be a second, unread copy of the client's instructions that
nobody decided to hold. A voice note the advocate WANTS kept goes through the
original-material window instead, where it is sealed and not read.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The largest recording accepted for one dictation. Five minutes of the Opus
#: audio a browser records is a few MiB; this leaves room for other codecs and
#: refuses anything that is not a spoken note before it is read.
MAX_DICTATION_BYTES = 25 * 1024 * 1024

#: The recordings a browser produces, and the common audio containers. Anything
#: else is refused before a byte of it is decoded.
DICTATION_MEDIA = frozenset({
    "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav",
    "video/webm",
})


@dataclass(frozen=True)
class Transcript:
    """What the speech model heard. Carries no audio, deliberately."""

    text: str
    #: The language the model detected, as a short code (`en`, `hi`, `te`), or
    #: empty when it could not tell. The text is in that language: nothing is
    #: translated.
    language: str
    seconds: float
    #: Where the model ran: `cuda` or `cpu`. A transcription on the processor is
    #: as correct and much slower, and the advocate is told which it was.
    device: str


#: Live dictation (F-C-03) is fed 16 kHz mono 16-bit audio, the rate the live
#: speech model is built for. The page resamples to it before sending, so no
#: resampling happens on the way in.
LIVE_SAMPLE_RATE = 16_000

#: The largest single piece of live audio accepted. The page sends about a tenth
#: of a second at a time (~3 KiB); this refuses a frame that is not that.
MAX_LIVE_FRAME_BYTES = 64 * 1024

#: The longest one live dictation may run, as bytes at the rate above: five
#: minutes, the same limit the page shows. A socket that keeps sending is closed
#: rather than listened to forever.
MAX_LIVE_BYTES = LIVE_SAMPLE_RATE * 2 * 60 * 5
