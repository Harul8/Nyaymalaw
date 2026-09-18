"""Live dictation words, from a small model on this machine's processor. F-C-03.

WHY A SECOND, SMALLER MODEL
-----------------------------
Whisper is not a streaming model: it transcribes a window of audio, so the
soonest it can show a word is a second or more after it was said, and only by
re-transcribing what came before. The product owner asked for words as they are
spoken. So the LIVE words come from a small Kaldi model (Vosk) built for Indian
English, which emits the sentence it is hearing as it listens, on the processor,
while the advocate is still speaking -- and the text they KEEP is still
transcribed once at the end by Whisper large-v3
(`nm.adapters.speech.local_whisper`), which is the accurate one.

THE LIVE WORDS ARE SCAFFOLDING, and the page says so: they are replaced by the
final transcription. That is what makes a rougher model the right trade here,
and it is why the two halves are separate ports rather than one.

NOTHING LEAVES AND NOTHING IS KEPT
------------------------------------
The model runs in this process, on the processor; `docs/blueprint/processors.yaml`
records it as the same in-process speech processor as Whisper. Each frame of
audio is fed to the recogniser and dropped; no audio is written.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from nm.adapters.optional import library
from nm.domain.dictation import LIVE_SAMPLE_RATE
from nm.ports.transcription import DictationUnavailable

_log = logging.getLogger("nm.dictation")

NOT_INSTALLED = (
    "Live words are not set up on this installation: the live speech library is "
    "not installed. What you say is still recorded, and the words will appear "
    "when you stop.")
#: INSTALLED AND UNIMPORTABLE IS ITS OWN STATE. MEASURED 18 September 2026:
#: `vosk` installed with `--no-deps` left `find_spec` answering yes while
#: importing it raised `ModuleNotFoundError: srt`, so health said the live
#: words were ready and the first frame of speech failed (S1).
NOT_USABLE = (
    "Live words are not set up on this installation: the live speech library is "
    "installed but did not load ({reason}). What you say is still recorded, and "
    "the words will appear when you stop.")
NO_MODEL = (
    "Live words are not set up on this installation: the live speech model is not "
    "downloaded. What you say is still recorded, and the words will appear when "
    "you stop.")
UNREADABLE = (
    "The live words could not be read from the speech model. What you say is "
    "still recorded, and the words will appear when you stop.")


class _Session:
    """One dictation. Keeps the words it has committed, never the audio."""

    def __init__(self, recogniser) -> None:
        self._recogniser = recogniser
        self._said: list[str] = []

    def _words(self, raw: str, key: str) -> str:
        try:
            return str(json.loads(raw or "{}").get(key) or "").strip()
        except json.JSONDecodeError as exc:
            # A recogniser answering with something unreadable has not heard
            # silence -- it has failed -- and the caller must not be handed an
            # empty string, which reads as "the advocate said nothing" (§9).
            raise DictationUnavailable(UNREADABLE) from exc

    def hear(self, pcm: bytes) -> str:
        """The words so far: those the model has settled on, plus the one
        sentence it is still revising."""
        if self._recogniser.AcceptWaveform(pcm):
            settled = self._words(self._recogniser.Result(), "text")
            if settled:
                self._said.append(settled)
            return " ".join(self._said)
        revising = self._words(self._recogniser.PartialResult(), "partial")
        return " ".join([*self._said, revising]).strip()

    def close(self) -> str:
        last = self._words(self._recogniser.FinalResult(), "text")
        if last:
            self._said.append(last)
        return " ".join(self._said).strip()


class VoskLive:
    def __init__(self, *, model_dir: Path | None = None,
                 sample_rate: int = LIVE_SAMPLE_RATE) -> None:
        self.model_dir = Path(model_dir) if model_dir is not None else None
        self.sample_rate = sample_rate
        self._model = None
        self._lock = threading.Lock()

    def _library(self):
        """Whether the library RUNS, decided by `nm.adapters.optional` -- the one
        owner of that question, and the only module that may look at the import
        path."""
        return library("vosk")

    def _on_disk(self) -> bool:
        return bool(self.model_dir and (self.model_dir / "am").is_dir())

    def readiness(self) -> str:
        """For `/api/health`. Never loads the model to answer.

        THREE STATES, NOT TWO: not installed, installed with no model on disk,
        and ready. The middle one is what a fresh checkout meets, and rolling it
        into "not ready" would hide which half is missing.
        """
        if self._model is not None:
            return f"ready ({self.model_dir.name if self.model_dir else 'default model'})"
        live = self._library()
        if not live.usable:
            return f"{live.why_not('the live speech library')}; live words are off"
        if not self._on_disk():
            return "NO MODEL -- the live speech model is not downloaded; live words are off"
        return f"installed; {self.model_dir.name} loads on first use"

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            live = self._library()
            if not live.usable:
                raise DictationUnavailable(
                    NOT_INSTALLED if not live.present
                    else NOT_USABLE.format(reason=live.reason))
            if not self._on_disk():
                raise DictationUnavailable(NO_MODEL)
            try:
                from vosk import Model, SetLogLevel

                # Its own console logging is not this product's audit.
                SetLogLevel(-1)
                self._model = Model(model_path=str(self.model_dir))
            except Exception as exc:  # noqa: BLE001 -- logged with its traceback, then refused
                _log.exception("the live speech model did not load")
                raise DictationUnavailable(
                    f"The live speech model could not be loaded "
                    f"({type(exc).__name__}). What you say is still recorded, and "
                    f"the words will appear when you stop.") from exc
            return self._model

    def listen(self, sample_rate: int) -> _Session:
        model = self._load()
        from vosk import KaldiRecognizer

        return _Session(KaldiRecognizer(model, float(sample_rate or self.sample_rate)))
