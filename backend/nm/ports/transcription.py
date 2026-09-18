"""Speech to text, for dictating a brief. Implementation Plan F-C-02.

ONE METHOD, AND IT RAISES
---------------------------
`transcribe` returns what was heard or raises `DictationUnavailable`. It never
returns empty text to mean "could not run": empty text means the recording had
no words in it, and an advocate told they said nothing when the model was never
loaded would simply speak again into a control that cannot work.

Which speech model is live is the composition root's business. This build
admits only a model running in this process; an outside speech service is an
external recipient of client material and the egress policy refuses it.
"""
from __future__ import annotations

from typing import Protocol

from nm.domain.dictation import Transcript


class DictationUnavailable(RuntimeError):
    """The recording could not be transcribed, and the message says why.

    DECLARED BY THE PORT, like `AlreadyEnrolled`, so the edge can report it
    without knowing which adapter is live.
    """


class TranscriptionPort(Protocol):
    def transcribe(self, audio: bytes, media_type: str) -> Transcript:
        """The words in one recording, or `DictationUnavailable`. Nothing is kept."""
        ...


class LiveDictation(Protocol):
    """One live dictation in progress. Holds no audio once a frame is read."""

    def hear(self, pcm: bytes) -> str:
        """The words heard SO FAR, including the ones still being revised."""
        ...

    def close(self) -> str:
        """The words at the end of the dictation. The session is then finished."""
        ...


class LiveTranscriptionPort(Protocol):
    def listen(self, sample_rate: int) -> LiveDictation:
        """Start one live dictation, or raise `DictationUnavailable`.

        SEPARATE FROM `TranscriptionPort` BECAUSE THE TWO ANSWER DIFFERENT
        QUESTIONS. Live words are provisional and must arrive while the advocate
        is still speaking; the text they keep is transcribed once, at the end, by
        the most accurate model the installation has. An adapter may implement
        one and not the other, and the page says which it has.
        """
        ...
