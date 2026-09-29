"""FINDING THE BARE-ACT SECTIONS A DISPUTE NEEDS. LB-106 (owner, 29 September 2026).

"Reuse the existing bare-act vector index ... we should get the entire vector store,
BM 25, search, rerank mechanism". The data and the two models the earlier system
used are reused as they are; the search is rebuilt here, behind this port.

A SEARCH RANKS; IT NEVER DECIDES WHICH LAW GOVERNS (CLAUDE.md section 5). What
comes back are CANDIDATES: each section read word for word by the one reader of
provisions, carrying its rank as a search confidence and no support verdict -- so
it can be quoted with its limit said, and is never relied on as the governing
provision.

THREE STATES (CLAUDE.md section 9). `ran` with candidates; `ran` with none from
the curated Acts, said with what was set aside; and NOT RUN -- the models, the
libraries or a consistent set of artefacts were not there -- with the reason, so
a search that never happened cannot read as one that found nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from nm.legal_brain.retrieve.evidence_port import Finding


@dataclass(frozen=True)
class SectionSearch:
    """One search for one dispute."""

    ran: bool
    candidates: tuple[Finding, ...] = ()
    note: str = ""
    """What was searched and what was set aside when it ran; why not when it
    did not. Search instrumentation, never a legal statement."""

    def __post_init__(self) -> None:
        if not self.ran and self.candidates:
            raise ValueError("a search that did not run found nothing")
        if not self.ran and not self.note.strip():
            raise ValueError("a search that did not run must say why")


@runtime_checkable
class SectionSearchPort(Protocol):
    def search(self, words: str, *, similar: tuple[str, ...] = (), as_of: date,
               limit: int = 5) -> SectionSearch:
        """The sections `words` (the advocate's words for one dispute) most need,
        ranked by meaning and by words, reranked, and read exactly. `similar` are
        other wordings of the same words (`understand.similar_words`), searched
        alongside them and used to judge relevance -- never a passage a model
        imagined."""
        ...

    def readiness(self) -> str:
        """`ready`, `not loaded` or `unavailable: <why>` -- for the health line."""
        ...
