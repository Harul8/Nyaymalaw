"""Dictation transcribed on this machine by an open-source Whisper model. F-C-02.

WHY ON THIS MACHINE
---------------------
A dictated brief is the client's instructions in the advocate's voice.
`docs/blueprint/processors.yaml` admits no outside recipient of client material,
so the speech model runs in this process and the recording never leaves it --
the product owner's decision of 15 September 2026.

WHICH MODEL
-------------
Whisper `large-v3`, run through faster-whisper (CTranslate2). It is the most
accurate open Whisper model and handles Indian English and code-mixed Hindi and
Telugu better than the smaller ones. In float16 it needs about 4.5 GB of GPU
memory, which fits the 8 GB RTX 4060 this installation runs on. For faster and
slightly less accurate transcription set `NM_DICTATION_MODEL=large-v3-turbo`.
If the GPU cannot be used the model loads on the processor instead, which is
correct and slow, and the transcript says where it ran.

IN ENGLISH, UNLESS THE INSTALLATION SAYS OTHERWISE
----------------------------------------------------
The model is ASKED for English (`NM_DICTATION_LANGUAGE`) rather than left to
detect the language. Detection on a few seconds of Indian-accented English is a
guess: "Hi, I am Rahul" came back in Urdu script on 15 September 2026, and an
advocate cannot correct a brief they cannot read. Set the language to `auto` to
detect it, and `NM_DICTATION_TRANSLATE=1` with it to have other languages come
back in English rather than their own script.

NOTHING IS WRITTEN
--------------------
The recording is decoded from memory and dropped when the call returns. The
model's weights are the only files involved, downloaded once into the
installation's `.nm/models`.

LOADED ON FIRST USE, NOT AT START
-----------------------------------
Constructing this adapter imports nothing heavy, so an installation without the
speech library starts normally and says dictation is not set up.
"""
from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path

from nm.adapters.optional import library, library_path
from nm.domain.dictation import Transcript
from nm.ports.transcription import DictationUnavailable

_log = logging.getLogger("nm.dictation")

NOT_INSTALLED = (
    "Dictation is not set up on this installation: the local speech model is not "
    "installed. Type the brief, or ask the administrator to install it.")
#: INSTALLED AND UNIMPORTABLE IS ITS OWN STATE, not a variant of missing: the
#: administrator's next step is different, and rolling the two together is how
#: `/api/health` came to report a library as ready that raised on import (S1).
NOT_USABLE = (
    "Dictation is not set up on this installation: the local speech library is "
    "installed but did not load ({reason}). Type the brief, or ask the "
    "administrator to check the installation.")
UNREADABLE = (
    "The recording could not be read as audio. Nothing was transcribed; try "
    "recording again.")


def _gpu_libraries_on_path() -> None:
    """On Windows, CTranslate2 needs the cuBLAS and cuDNN libraries.

    The installed PyTorch CUDA build already ships them, so the loader is pointed
    there rather than a second copy being installed beside it.
    """
    if os.name != "nt":
        return
    installed = library_path("torch")
    if installed is None:
        return
    libraries = installed / "lib"
    if not libraries.is_dir():
        return
    os.add_dll_directory(str(libraries))
    # ON PATH TOO. CTranslate2 loads cuBLAS lazily, at the first transcription,
    # with a plain library search that ignores `add_dll_directory`. Measured on
    # 15 September 2026: the model loaded on the GPU and the first transcription
    # then failed with "cublas64_12.dll is not found".
    path = os.environ.get("PATH", "")
    if str(libraries).lower() not in path.lower().split(os.pathsep):
        os.environ["PATH"] = str(libraries) + os.pathsep + path


class LocalWhisper:
    def __init__(self, *, model: str = "large-v3", device: str = "auto",
                 compute_type: str = "", download_root: Path | None = None,
                 language: str = "en", translate: bool = False) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        #: THE LANGUAGE ASKED FOR, and English is the default rather than
        #: "whatever the model detects". MEASURED 15 September 2026: "Hi, I am
        #: Rahul" came back in Urdu script, because detection on a few seconds
        #: of Indian-accented English is a guess and the advocate is then
        #: holding a brief they cannot read. `auto` detects, as before.
        self.language = language
        #: With `auto`, whether other languages come back translated into
        #: English rather than written in their own script.
        self.translate = translate
        self._model = None
        self._device_used = ""
        self._lock = threading.Lock()

    def _on_disk(self) -> bool:
        """Whether this model's weights are already in the download folder."""
        if self.download_root is None:
            return False
        pattern = f"models--*faster-whisper-{self.model_name}/snapshots/*/model.bin"
        return any(Path(self.download_root).glob(pattern))

    def readiness(self) -> str:
        """For `/api/health`. Never loads the model to answer."""
        if self._model is not None:
            return f"ready ({self.model_name} on {self._device_used})"
        # THE LIBRARY IS IMPORTED TO ANSWER THIS, not looked for on the import
        # path: the answer that matters is whether it runs. `nm.adapters.optional`
        # owns that and remembers it, so only the first poll pays for the import.
        speech = library("faster_whisper")
        if not speech.usable:
            return f"{speech.why_not('the local speech library')}; dictation is refused"
        return f"installed; {self.model_name} loads on first use"

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            speech = library("faster_whisper")
            if not speech.usable:
                raise DictationUnavailable(
                    NOT_INSTALLED if not speech.present
                    else NOT_USABLE.format(reason=speech.reason))
            _gpu_libraries_on_path()
            from faster_whisper import WhisperModel
            if self.device in ("auto", "cuda"):
                attempts = [("cuda", self.compute_type or "float16"), ("cpu", "int8")]
            else:
                attempts = [(self.device, self.compute_type or "int8")]
            failures = []
            root = str(self.download_root) if self.download_root else None
            # A MODEL ALREADY ON DISK IS LOADED FROM DISK, with no call to the
            # model hub: no network at every start, and no TLS handshake for
            # Norton's `SSLKEYLOGFILE` to crash (CLAUDE.md, Tooling).
            local_only = self._on_disk()
            for device, compute in attempts:
                try:
                    self._model = WhisperModel(self.model_name, device=device,
                                               compute_type=compute, download_root=root,
                                               local_files_only=local_only)
                except Exception as exc:  # noqa: BLE001 -- logged with its traceback, then the next device is tried
                    _log.exception("the speech model did not load on %s", device)
                    failures.append(f"{device}: {type(exc).__name__}")
                    continue
                self._device_used = device
                return self._model
            raise DictationUnavailable(
                "The local speech model could not be loaded ("
                + "; ".join(failures) + "). Nothing was transcribed.")

    def transcribe(self, audio: bytes, media_type: str) -> Transcript:
        model = self._load()
        try:
            wanted = (self.language or "").strip().lower()
            segments, info = model.transcribe(
                io.BytesIO(audio),
                language=None if wanted in ("", "auto") else wanted,
                task="translate" if self.translate else "transcribe",
                vad_filter=True, beam_size=5, condition_on_previous_text=False)
            text = " ".join(part.text.strip() for part in segments if part.text.strip())
        except Exception as exc:
            # A RECORDING THAT WILL NOT DECODE is the advocate's to retry. Any
            # other failure is a defect, and it is raised, not reworded.
            if type(exc).__module__.split(".")[0] == "av":
                raise DictationUnavailable(UNREADABLE) from exc
            raise
        return Transcript(text=text, language=info.language or "",
                          seconds=round(float(info.duration or 0.0), 1),
                          device=self._device_used)
