"""Owned, admitted matter-document text, separate from public legal authority.

Quarantine decisions come from a configured trusted checker, never a model or
an upload request. Derivatives are immutable encrypted objects; the matter CAS
alone publishes their receipts. Local parsing neither admits facts nor grants
external-provider permission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from nm.open_matter.document_text_port import DocumentFormat
from nm.open_matter.media_contracts import Quarantine

MAX_DERIVATIVE_BYTES = 8 * 1024 * 1024
MAX_QUOTE_CHARACTERS = 8000


class DocumentRefused(ValueError):
    """An attributed reading/search is unavailable, forbidden or stale."""


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank")


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("an original needs its exact lowercase SHA-256 digest")


@dataclass(frozen=True)
class DocumentReadInstruction:
    """Explicit user instruction to analyse this exact original, not merely hold it."""

    request_key: str
    actor_id: str
    original_id: str
    asset_version: int
    source_sha256: str
    purpose: str
    authority: str
    analysis_allowed: bool

    def __post_init__(self):
        for name in ("request_key", "actor_id", "original_id", "purpose", "authority"):
            _text(getattr(self, name), name)
        _hash(self.source_sha256)
        if type(self.asset_version) is not int or self.asset_version < 1:
            raise ValueError("an instruction names an exact positive original version")
        if self.analysis_allowed is not True:
            raise ValueError("holding permission is not permission to analyse an original")
        if len(self.request_key) > 100 or len(self.purpose) > 2000 or len(self.authority) > 2000:
            raise ValueError("the explicit reading instruction exceeds its bound")


@dataclass(frozen=True)
class QuarantineRead:
    """A trusted checker's result bound to the actual bytes it examined."""

    original_id: str
    source_sha256: str
    byte_length: int
    state: Quarantine
    format: DocumentFormat
    checker: str
    checker_version: str
    reason: str

    def __post_init__(self):
        for name in ("original_id", "checker", "checker_version", "reason"):
            _text(getattr(self, name), name)
        _hash(self.source_sha256)
        if type(self.byte_length) is not int or self.byte_length < 1:
            raise ValueError("a quarantine result names the actual positive byte count")
        if not isinstance(self.state, Quarantine) or not isinstance(self.format, DocumentFormat):
            raise ValueError("quarantine and document format require explicit typed states")
        if self.state is Quarantine.RELEASED and self.format is DocumentFormat.UNKNOWN:
            raise ValueError("unverified document format cannot be released for parsing")


class QuarantinePort(Protocol):
    def inspect(self, original_id: str, source_sha256: str, data: bytes) -> QuarantineRead:
        """Check bounded local original bytes; unavailable is NOT_ASSESSED, never release."""
        ...


class DocumentDerivativePort(Protocol):
    def put(self, matter_id: str, object_id: str, data: bytes) -> None:
        """Durably seal an immutable bounded object, before its receipt is published."""
        ...

    def read(self, matter_id: str, object_id: str, sha256: str) -> bytes:
        """Open bounded bytes in their matter key scope and verify their exact identity."""
        ...

    def forget(self, matter_id: str, object_id: str, sha256: str) -> bool:
        """Remove this exact object or report failure; approval is the service owner's job."""
        ...


@dataclass(frozen=True)
class MatterDocumentSearch:
    matches: tuple[dict, ...] = ()
    matched_count: int = 0
    searched: tuple[str, ...] = ()
    not_searched: tuple[dict, ...] = ()
    partial: bool = False


@dataclass(frozen=True)
class MatterDocumentQuote:
    text: str
    locator: str
    source: dict = field(default_factory=dict)

    def __post_init__(self):
        _text(self.text, "quoted text")
        _text(self.locator, "quotation locator")
        if len(self.text) > MAX_QUOTE_CHARACTERS:
            raise ValueError("a quotation exceeds its bounded source window")


class MatterDocumentsPort(Protocol):
    def search(
        self, matter_id: str, actor_id: str, expected_version: int, query: str, *, limit: int = 200
    ) -> MatterDocumentSearch:
        """Search permitted exact derivatives and disclose every unread original."""
        ...

    def quote(
        self,
        matter_id: str,
        actor_id: str,
        expected_version: int,
        *,
        original_id: str,
        asset_version: int,
        source_sha256: str,
        derivative_sha256: str,
        number: int,
        location_kind: str,
        part: str,
        start: int,
        end: int,
    ) -> MatterDocumentQuote:
        """Read an exact original/version/unit/span, never a guessed page or stale text."""
        ...
