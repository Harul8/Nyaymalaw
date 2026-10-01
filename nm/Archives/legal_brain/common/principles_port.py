"""Versioned owner guidance, supplied to the pure reasoning loop by a port."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class PrinciplesUnavailable(RuntimeError):
    """The loop must disclose this stop instead of reasoning without its guide."""


@dataclass(frozen=True)
class PrinciplesSnapshot:
    text: str
    sha256: str

    def __post_init__(self):
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("The reasoning principles are empty or are not text.")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("The reasoning principles identity does not match.")

    @property
    def version(self) -> str:
        """Content identity, not a mutable author-written version label."""
        return self.sha256


@runtime_checkable
class PrinciplesPort(Protocol):
    def load(self) -> PrinciplesSnapshot:
        """Read the current owner document at the next turn boundary."""
        ...
