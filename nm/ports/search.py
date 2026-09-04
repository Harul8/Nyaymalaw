"""A4 — what a corpus search returns, and what it may never claim.

WHY THIS IS A PORT AND NOT AN ADAPTER CONCERN
----------------------------------------------
The rules a search result must obey are not properties of SQLite. They are
properties of what the product is allowed to tell an advocate, so they live
where the core can see them and the adapter must satisfy them.

THE THREE THINGS THIS TYPE REFUSES, EACH ONE MEASURED
------------------------------------------------------
1. A ZERO THAT DOES NOT NAME ITS INDEX. `case_name` holds party names, so a
   subject search against it returns nothing, and nothing reads exactly like an
   empty corpus. Bail returned 0 by name across 33,791 cases and 1,452 against
   the summaries (B-163). So `index` is required on every result, and a result
   with no hits must carry the index identity as well -- what was searched,
   when it was built, and how much of its source it holds.

2. AN UNREADABLE INDEX REPORTED AS AN EMPTY ONE. This is the single most
   repeated defect in this project: a screen that could not run returning the
   shape of a clean result. `Coverage.NOT_ASSESSED` is a VALUE, and a search
   that could not be performed carries it rather than an empty hit list.

3. A RANKED HIT WEARING RESOLVED PROVENANCE. `Origin` already exists and is
   already required on a Finding for exactly this reason. A search box has no
   exact key, so every hit it produces is SEARCHED and carries a confidence.
   `RESOLVED` here would make a ranked guess indistinguishable from an exact
   lookup, which is E-051's counterexample wearing a different hat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from nm.domain.text import refuses_blank_text
from nm.ports.evidence import Coverage, Origin


@refuses_blank_text()
@dataclass(frozen=True)
class SearchHit:
    """One paragraph the index ranked against the query.

    `rank` is the index's own score and is meaningless across queries; it is
    carried so two hits in ONE result can be compared and for no other reason.
    `confidence` is what the advocate is shown.
    """

    case_id: str
    case_name: str
    court: str
    year: int | None
    para_type: str
    snippet: str
    rank: float
    confidence: float
    origin: Origin = Origin.SEARCHED

    def __post_init__(self) -> None:
        if self.origin is Origin.RESOLVED:
            raise ValueError(
                "a search hit may not claim RESOLVED provenance. RESOLVED "
                "means an exact lookup with no ranking anywhere in its "
                "derivation, and this arrived by ranking. Presenting it as "
                "resolved makes a guess indistinguishable from a key.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence {self.confidence} is not a probability")
        if not self.case_id.strip():
            raise ValueError(
                "a hit with no case id cannot be read back, and a citation "
                "the advocate cannot open is worse than no citation")


@refuses_blank_text()
@dataclass(frozen=True)
class IndexIdentity:
    """WHAT WAS SEARCHED, said by the index itself.

    The dense index in the previous build was 437MB of confidently wrong
    neighbours, and the ONLY reason that was knowable is that it shipped an
    `identity.json` (CLAUDE.md, defect shape S11). Every artefact this project
    produces carries its identity, and the thing a search reads is one.

    `held` and `of_source` are both carried because their RATIO is the
    disclosure that matters: an index over 451,548 of 1,015,780 source
    paragraphs holds 44% of them, and an advocate told only "451,548
    paragraphs" would reasonably read that as the corpus.
    """

    name: str
    built_at: str
    source: str
    corpus_version: str
    held: int
    of_source: int

    #: WHAT LAW THIS INDEX IS ABOUT. Required, and there is no default.
    #:
    #: The corpus is scoped to Telangana and the Union of India. A search that
    #: does not say so lets an advocate read a Kerala question's empty result
    #: as an answer about Kerala law -- confidently wrong, and nothing
    #: downstream catches it. `nm/knowledge/jurisdiction.py` states the same
    #: scope for the retrieval path; this is that fact reaching the surface an
    #: advocate types into.
    scope: str

    @property
    def fraction_of_source(self) -> float | None:
        """`None`, not 0.0, when the source size is unknown.

        A ratio of zero and an unknown ratio are different claims, and the
        first one says the index is empty."""
        if not self.of_source:
            return None
        return self.held / self.of_source


@dataclass(frozen=True)
class CorpusSearch:
    """A4's PRODUCES contract.

    An empty `hits` is a legitimate answer and is never the WHOLE answer: it
    arrives with the index that was searched, the filters that were applied,
    and a coverage that distinguishes "searched and found nothing" from "could
    not search".
    """

    query: str
    index: str
    coverage: Coverage
    identity: IndexIdentity | None = None
    filters: dict = field(default_factory=dict)
    hits: tuple[SearchHit, ...] = ()
    why: str | None = None

    def __post_init__(self) -> None:
        if not self.index.strip():
            raise ValueError(
                "every result names the index it came from, including a "
                "result of zero -- a zero from an unnamed index reads as an "
                "empty corpus (B-163)")
        if self.coverage is Coverage.NOT_ASSESSED:
            if self.hits:
                raise ValueError(
                    "a search that could not be performed returned hits")
            if not (self.why or "").strip():
                raise ValueError(
                    "NOT_ASSESSED without a reason is the absent-input shape: "
                    "the advocate is told nothing was found and not that "
                    "nothing was looked at")
        elif self.identity is None:
            raise ValueError(
                "a search that RAN must carry the identity of what it "
                "searched, so that a zero can be read against what the index "
                "actually holds")

    @property
    def hit_count(self) -> int:
        return len(self.hits)


class CorpusSearchPort(Protocol):
    """What the edge may ask for. Deliberately narrow.

    There is no `search_acts` here. An Act is identified by EXACT TITLE and
    read through the evidence adapter that already owns that lookup; giving a
    search port an Act-shaped method is how a ranked Act match gets written
    one day. CLAUDE.md §5: fuzzy may RANK, never IDENTIFY, and never an Act.
    """

    def search(self, query: str, *, court: str | None = None,
               from_year: int | None = None, to_year: int | None = None,
               limit: int = 20) -> CorpusSearch: ...
