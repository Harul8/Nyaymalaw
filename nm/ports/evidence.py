"""The evidence port. PRD §4.6 -- retrieval returns FINDINGS, never chunks.

Returning chunks pushes citation, binding status and paragraph kind downstream
to a layer that then skips them, which is precisely how counsel's argument comes
to be quoted as a holding. An obligation not represented in the type crossing
the boundary is an obligation that will be dropped -- so every one of them is a
required field here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol, runtime_checkable


class ParaKind(str, Enum):
    """Only the first three are attributable to a court."""

    RATIO = "ratio"
    REASONING = "reasoning"
    ORDER = "order"
    ARGUMENTS = "arguments"      # counsel's submission -- 14.8% of the corpus
    FACTS = "facts"
    HEADNOTE = "headnote"
    UNKNOWN = "unknown"          # 26.7% -- cannot be vouched either way

    @property
    def attributable(self) -> bool:
        return self in (ParaKind.RATIO, ParaKind.REASONING, ParaKind.ORDER)


class Binding(str, Enum):
    BINDING = "binding"
    PERSUASIVE = "persuasive"


class Coverage(str, Enum):
    """Three states, never two."""

    ANSWERED = "answered"
    NOT_HELD = "not_held"
    HELD_NOT_FOUND = "held_not_found"   # a DEFECT that escalates


class SourceKind(str, Enum):
    PROVISION = "provision"
    AUTHORITY = "authority"


@dataclass(frozen=True)
class Finding:
    proposition: str
    source_kind: SourceKind
    ref: str
    span: str
    locator: str
    store: str
    binding: Binding
    binding_for: str
    supports: bool
    para_kind: ParaKind = ParaKind.UNKNOWN
    valid_from: date | None = None
    valid_to: date | None = None
    origin: str = "resolved"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.span.strip():
            raise ValueError("a Finding without a verbatim span is not a Finding")
        if not self.locator.strip():
            raise ValueError("a Finding without a locator cannot be read back")
        if self.source_kind is SourceKind.AUTHORITY and not self.para_kind.attributable:
            raise ValueError(
                f"a proposition attributed to a judgment must come from a "
                f"ratio/reasoning/order paragraph, not {self.para_kind.value!r} "
                f"(PRD H7)")

    @property
    def usable(self) -> bool:
        """`supports` is a GATE, not a score. A Finding whose span does not
        support its proposition cannot be used, and blocks the answer."""
        return self.supports


@dataclass(frozen=True)
class EvidenceNeed:
    """The query is the MATTER, not a sentence.

    A need carrying only a text string would silently degrade the whole design
    back to search-first, and nothing downstream would notice -- so the
    governing date is required rather than defaulted to today.
    """

    question: str
    governing_date: date
    jurisdiction: str = "Telangana"
    forum: str | None = None
    cause_of_action: str | None = None
    provision_hint: str | None = None

    def __post_init__(self) -> None:
        if self.governing_date is None:
            raise ValueError(
                "a query without a governing date is REJECTED, not defaulted to "
                "today (PRD G1/H2)")


@dataclass(frozen=True)
class EvidenceResult:
    coverage: Coverage
    findings: tuple[Finding, ...] = ()
    missing: str | None = None
    searched_stores: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.coverage is Coverage.NOT_HELD and not self.missing:
            raise ValueError(
                "a NOT_HELD result must NAME what is missing. A vague "
                "disclaimer is silence in more words (PRD M4).")


@runtime_checkable
class EvidencePort(Protocol):
    def fetch(self, need: EvidenceNeed) -> EvidenceResult: ...
