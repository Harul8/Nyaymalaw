"""Local reading of admitted original bytes, never admission or legal fact creation.

The trusted upload owner supplies verified bytes and its admission. No filename,
filesystem path, URL or model instruction can select an extraction destination.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Protocol

from nm.open_matter.media_contracts import MediaAdmission

DOCUMENT_PROCESSOR = "nm-local-document-text"
DOCUMENT_OPERATION = "local_document_text_extraction"
DOCUMENT_READER_VERSION = "bounded-local-reader-v1"


class TextState(str, Enum):
    EXTRACTED = "extracted"
    NO_TEXT_LAYER = "no_text_layer"
    UNAVAILABLE = "unavailable"

    @classmethod
    def not_established(cls) -> "TextState":
        return cls.UNAVAILABLE


class DocumentFormat(str, Enum):
    PDF = "pdf"
    TEXT = "text"
    DOCX = "docx"
    UNKNOWN = "unknown"

    @classmethod
    def not_established(cls) -> "DocumentFormat":
        return cls.UNKNOWN


@dataclass(frozen=True)
class ExtractionBounds:
    max_bytes: int = 16 * 1024 * 1024
    max_units: int = 256
    max_text_characters: int = 1_000_000
    max_unit_characters: int = 100_000
    max_stream_bytes: int = 4 * 1024 * 1024
    max_zip_entries: int = 1024
    max_xml_depth: int = 64
    max_xml_elements: int = 100_000
    memory_bytes: int = 256 * 1024 * 1024
    deadline_seconds: float = 10.0

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{key} must be a positive extraction bound")
            try:
                finite = math.isfinite(value)
            except OverflowError as exc:
                raise ValueError(f"{key} must be representable as a finite bound") from exc
            if not finite:
                raise ValueError(f"{key} must be finite")
            if key != "deadline_seconds" and not isinstance(value, int):
                raise ValueError(f"{key} must be an integer extraction bound")
        if self.memory_bytes < 32 * 1024 * 1024:
            raise ValueError("memory_bytes must allow the bounded parser to start")


@dataclass(frozen=True)
class AdmittedDocument:
    """An upload owner's bytes. Construct only after ownership and admission checks."""
    data: bytes
    format: DocumentFormat
    source_sha256: str
    admission: MediaAdmission


@dataclass(frozen=True)
class LocatedText:
    number: int
    location_kind: str
    part: str
    state: TextState
    text: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, TextState) or not isinstance(self.text, str):
            raise ValueError("a text unit needs a declared state and textual result")
        if isinstance(self.number, bool) or not isinstance(self.number, int) or self.number < 1:
            raise ValueError("a text unit needs its one-based original locator")
        if self.location_kind not in {"page", "part"} or not self.part:
            raise ValueError("a text unit needs its page or document-part location")
        if self.state is TextState.EXTRACTED and not self.text.strip():
            raise ValueError("an extracted unit must carry nonblank text")
        if self.state is not TextState.EXTRACTED and (self.text or not self.reason.strip()):
            raise ValueError("an unread unit carries a reason, never extracted text")


@dataclass(frozen=True)
class ExtractionResult:
    source_sha256: str
    original_id: str
    format: DocumentFormat
    byte_length: int
    observed_units: int | None
    units: tuple[LocatedText, ...] = ()
    failure: str | None = None
    reason: str = ""
    excluded: tuple[str, ...] = ()
    parser: str = ""
    parser_version: str = ""
    off_premises: bool = False
    facts_established: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.format, DocumentFormat):
            raise ValueError("an extraction needs its declared document format")
        if not re.fullmatch(r"[a-f0-9]{64}", self.source_sha256 or "") or not self.original_id:
            raise ValueError("an extraction needs the immutable original identity")
        if isinstance(self.byte_length, bool) or not isinstance(self.byte_length, int):
            raise ValueError("an extraction needs its observed byte length")
        if (self.byte_length < 1 or self.off_premises is not False
                or self.facts_established is not False):
            raise ValueError("local extraction neither exports bytes nor establishes legal facts")
        if self.observed_units is not None and (isinstance(self.observed_units, bool)
                or not isinstance(self.observed_units, int) or self.observed_units < 0):
            raise ValueError("an observed unit count is a nonnegative integer or unknown")
        if self.failure is not None and not self.reason.strip():
            raise ValueError("an extraction failure needs its explanation")
        if not all(isinstance(unit, LocatedText) for unit in self.units):
            raise ValueError("every extracted unit needs a typed original locator")
        numbers = [unit.number for unit in self.units]
        locators = [(unit.location_kind, unit.part, unit.number) for unit in self.units]
        if len(set(locators)) != len(locators):
            raise ValueError("extracted unit locators cannot be duplicated")
        if self.units and (self.observed_units is None
                          or max(numbers) > self.observed_units):
            raise ValueError("extracted units exceed the original's observed locations")

    @property
    def complete(self) -> bool:
        return (self.failure is None and bool(self.units)
                and self.observed_units == len(self.units)
                and all(unit.state is TextState.EXTRACTED for unit in self.units))

    def as_dict(self) -> dict:
        result = asdict(self)
        result["format"] = self.format.value
        result["complete"] = self.complete
        for unit in result["units"]:
            unit["state"] = unit["state"].value
        return result


class DocumentTextPort(Protocol):
    def extract(self, document: AdmittedDocument, *,
                bounds: ExtractionBounds | None = None) -> ExtractionResult:
        """Read local text with exact locators, or name the capability/input failure."""
        ...
