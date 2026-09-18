"""WHETHER AN OPTIONAL LIBRARY CAN ACTUALLY BE IMPORTED. The only owner.

WHY THIS IS NOT `importlib.util.find_spec`
--------------------------------------------
`find_spec` answers *is there a package directory of that name on the import
path*. That is a PROXY for availability, and it parts company with the truth in
exactly the case that matters: a library installed without its dependencies.

Measured 18 September 2026. `vosk` was installed with `--no-deps`, so
`find_spec("vosk")` said yes, `/api/health` said
`installed; vosk-model-small-en-in-0.4 loads on first use`, and the first frame
of speech raised `ModuleNotFoundError: No module named 'srt'` from inside
`vosk/__init__.py` -- because `vosk` imports `srt` at package import, which the
note in the plan sheet had wrongly said was only used by its command-line tool.
The health line reported the shape of a clean result for a feature that could
not run: defect shape **S1**, at a site added the day before.

So availability is decided by IMPORTING, once, and remembering the answer.

AND IT REPORTS FOUR STATES, NOT TWO, because which half is missing is the
actionable part: nothing installed, installed but not importable (with the
reason), importable, and -- for the caller's own artefacts, not this module's
concern -- importable with no model on disk.

A crash during import is a fact about this installation, not about the library
(the `SentenceTransformer` traceback that turned out to be Norton's
`SSLKEYLOGFILE`), so the reason is recorded verbatim rather than interpreted.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger("nm.adapters.optional")

_lock = threading.Lock()
_remembered: dict[str, "Library"] = {}


@dataclass(frozen=True)
class Library:
    """What is known about one optional third-party library, having tried it."""

    name: str
    #: Something of that name is on the import path.
    present: bool
    #: Why importing it failed, verbatim. `None` when it imported.
    reason: str | None

    @property
    def usable(self) -> bool:
        return self.present and self.reason is None

    def why_not(self, subject: str) -> str:
        """One line for `/api/health`, naming which half is missing.

        `subject` is what the advocate would call it -- "the live speech
        library" -- because a health line naming a pip package tells the
        person reading it nothing about what stopped working.
        """
        if self.usable:
            return ""
        if not self.present:
            return f"NOT INSTALLED -- {subject} is not installed"
        return (f"NOT USABLE -- {subject} is installed but cannot be imported "
                f"({self.reason})")


def library(name: str) -> Library:
    """Import `name` once and remember what happened.

    Remembered because the answer cannot change inside a running process, and
    because `/api/health` is polled: the first call pays for the import, and no
    call after it does.
    """
    with _lock:
        if name in _remembered:
            return _remembered[name]
        if importlib.util.find_spec(name) is None:
            answer = Library(name=name, present=False, reason=None)
        else:
            try:
                importlib.import_module(name)
                answer = Library(name=name, present=True, reason=None)
            except Exception as exc:  # noqa: BLE001 -- the reason IS the finding
                # Logged with its traceback: a bare warning here is how a
                # NameError came to look like a model failure (S10).
                _log.exception("the optional library %r is installed and did not import", name)
                answer = Library(name=name, present=True,
                                 reason=f"{type(exc).__name__}: {exc}")
        _remembered[name] = answer
        return answer


def library_path(name: str) -> Path | None:
    """Where an installed library's files live, without importing it.

    This is a PATH LOOKUP and not an availability check -- it is how the CUDA
    libraries shipped inside `torch` are put on the search path -- so it stays
    beside `library()` rather than growing a second `find_spec` somewhere else.
    """
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):  # a half-installed parent package
        return None
    locations = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
    return Path(locations[0]) if locations else None


def forget(name: str) -> None:
    """Drop what was remembered about `name`. For tests only."""
    with _lock:
        _remembered.pop(name, None)
