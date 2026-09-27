"""Exact admitted document extracts, never public law or established case facts."""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field

from nm.legal_brain.loop_contracts import StepKind, digest
from nm.open_matter.matter_documents_port import MatterDocumentQuote
from nm.work_the_file.matter_contracts import Matter

REFERENCE_KEYS = frozenset({"original_id", "asset_version", "source_sha256", "derivative_sha256",
                            "number", "location_kind", "part", "start", "end"})
_SOURCE_KEYS = REFERENCE_KEYS | {"filename", "facts_established", "representation"}


def require_quote(quote: MatterDocumentQuote) -> None:
    """A closed extracted-text receipt with exact immutable source identity."""
    if not isinstance(quote, MatterDocumentQuote) or set(quote.source) != _SOURCE_KEYS:
        raise ValueError("Matter support needs the complete admitted document quote contract")
    source = quote.source
    for name in ("original_id", "location_kind", "part", "filename"):
        if not isinstance(source[name], str) or not source[name].strip():
            raise ValueError("Document support needs its exact nonblank source metadata")
    for name in ("source_sha256", "derivative_sha256"):
        value = source[name]
        if (not isinstance(value, str) or len(value) != 64
                or any(character not in "abcdef0123456789" for character in value)):
            raise ValueError("Document support needs the exact original and derivative digests")
    if (any(type(source[name]) is not int for name in ("asset_version", "number", "start", "end"))
            or source["asset_version"] < 1 or source["number"] < 1
            or not 0 <= source["start"] < source["end"]
            or source["end"] - source["start"] != len(quote.text)
            or source["facts_established"] is not False
            or source["representation"] != "local_extracted_text"):
        raise ValueError("Document support cannot establish facts or invent its extraction window")


@dataclass(frozen=True)
class MatterDocumentSpan:
    """A minimum quote within one actual captured derivative window."""
    id: str
    captured_quote: MatterDocumentQuote
    start: int
    end: int
    _identity: str = field(init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "captured_quote", deepcopy(self.captured_quote))
        self._validate()
        object.__setattr__(self, "_identity", digest(asdict(self.captured_quote)))

    def _validate(self):
        require_quote(self.captured_quote)
        if (not isinstance(self.id, str) or not self.id.strip()
                or type(self.start) is not int or type(self.end) is not int
                or not 0 <= self.start < self.end <= len(self.captured_quote.text)
                or not self.text.strip()):
            raise ValueError("A document support span needs one exact nonblank captured window")

    def validate(self):
        self._validate()
        if digest(asdict(self.captured_quote)) != self._identity:
            raise ValueError("The captured document receipt changed after admission")

    @property
    def text(self):
        return self.captured_quote.text[self.start:self.end]

    @property
    def locator(self):
        return self.captured_quote.locator

    @property
    def source(self):
        return dict(self.captured_quote.source)

    @property
    def captured_identity(self):
        self.validate()
        return self._identity

    def payload(self):
        return {"id": self.id, "text": self.text, "locator": self.locator,
                "source": self.source, "captured_identity": self.captured_identity,
                "limits": "These are locally extracted document words, not authenticated "
                    "events or a finding that the allegations are true. They supply no law."}


DocumentCurrent = Callable[[Matter, MatterDocumentSpan], bool]


def captured_documents(record) -> tuple[MatterDocumentQuote, ...]:
    """Only an actual quote_matter result, not search snippets or arbitrary data."""
    quotes, calls = [], {}
    for event in record.events:
        if event.kind is StepKind.TOOL_STARTED:
            call = event.payload.get("call", {})
            if call.get("name") == "quote_matter":
                if call.get("call_id") in calls:
                    raise ValueError("A matter quote dispatch cannot be repeated")
                calls[call["call_id"]] = call["arguments"]
        if event.kind is not StepKind.TOOL_RETURNED:
            continue
        envelope = event.payload.get("receipt", {})
        if envelope.get("kind") != "matter" or envelope.get("tool") != "quote_matter":
            continue
        value = envelope.get("data")
        if (envelope.get("outcome") != "results" or not isinstance(value, dict)
                or set(value) != {"text", "locator", "source"}):
            raise ValueError("The matter document read lacks its exact captured quotation")
        quote = MatterDocumentQuote(**value)
        require_quote(quote)
        requested = calls.pop(event.payload.get("call_id"), None)
        if (not isinstance(requested, dict) or set(requested) != REFERENCE_KEYS
                or requested != {key: quote.source[key] for key in REFERENCE_KEYS}
                or envelope.get("receipt", {}).get("matter_id") != record.identity.matter_id
                or envelope.get("receipt", {}).get("matter_version")
                != record.identity.matter_version + event.sequence - 1
                or envelope.get("receipt", {}).get("snapshot") != digest(value)):
            raise ValueError("The captured document differs from its actual admitted read request")
        if quote not in quotes:
            quotes.append(quote)
    return tuple(quotes)


def require_current_documents(matter, packages, current) -> None:
    """A sealed old extract is not proof that its original is still admitted."""
    for package in packages:
        for span in (*package.documents, *package.document_contrary):
            _require_current_span(matter, span, current)


def require_current_captured_documents(matter, quotes, current) -> None:
    """Author errors cannot hide lost admission of an already captured extract."""
    for index, quote in enumerate(quotes):
        span = MatterDocumentSpan(f"captured_document_{index}", quote, 0, len(quote.text))
        _require_current_span(matter, span, current)


def _require_current_span(matter, span, current):
    span.validate()
    if current is None or current(matter, span) is not True:
        raise ValueError("The admitted matter document is missing, stale or no longer permitted")
