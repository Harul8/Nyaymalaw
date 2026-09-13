"""The egress policy, in front of the authority index. BK-85-AC1. P06.

    search = PolicedSearch(inner=AuthorityIndexSearch(...), gate=..., ...)

WHAT LEAVES WHEN A SEARCH RUNS
--------------------------------
The QUERY does. An advocate searching for authority types the substance of the
matter into the box, so the text going to the index is client material even
though the thing coming back is public law. A policy that gated the answer
would be gating the wrong direction.

WHY THIS REFUSES BY RETURNING AND THE MODEL REFUSES BY RAISING
----------------------------------------------------------------
Because the two ports differ, and the rule is to use the third state where one
exists. `CorpusSearch` already carries `Coverage.NOT_ASSESSED` with a required
`why`, built precisely so *searched and found nothing* and *could not search*
are different answers -- the single most repeated defect in this codebase.
A refused route is the second of those, so it is reported as the second of
those, and the advocate is told the search did not happen rather than shown an
empty result list.

`ModelPort` has no such value. A refused dispatch there would have to invent
an empty `ModelResult`, which is the defect rather than the report of it, so
it raises.

THE REFUSAL IS STILL FAIL-CLOSED. Nothing reaches the index: the policy is
consulted before `inner.search` is called at all, and the query text is never
passed to a destination the inventory has not admitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nm.domain.egress import DataClass, EgressRefused, Gatekeeper, Sink
from nm.ports.evidence import Coverage, Treatment
from nm.ports.search import (
    CaseDiscovery,
    CaseExpansion,
    CitationResolution,
    CorpusSearch,
    CorpusSearchPort,
    Paragraph,
    ResolutionState,
)

#: Read FROM THE PORT for the same reason `PolicedStore` does: a hand-written
#: list is a second declaration, and the stale one would be the copy.
_PORT_METHODS = frozenset(
    name for name in dir(CorpusSearchPort) if not name.startswith("_"))


@dataclass
class PolicedSearch:
    """Any `CorpusSearchPort`, refused before the query leaves."""

    inner: Any
    gate: Gatekeeper
    #: Which recorded processor runs the index. Named by the composition root.
    processor_id: str
    #: A query carries what the advocate is working on.
    data_classes: tuple[DataClass, ...] = (DataClass.CLIENT_MATTER,)

    def search(self, query: str, *, court: str | None = None,
               from_year: int | None = None, to_year: int | None = None,
               limit: int = 20) -> CorpusSearch:
        try:
            self.gate.permit(
                Sink.INDEX, self.processor_id, self.data_classes,
                size_bytes=len((query or "").encode("utf8")))
        except EgressRefused as refused:
            # NOT AN EMPTY RESULT. `CorpusSearch.__post_init__` refuses a
            # NOT_ASSESSED result that carries hits or has no reason, so this
            # cannot be built in a shape that reads as "nothing found".
            return CorpusSearch(
                query=query, index=f"{self.processor_id} (refused)",
                coverage=Coverage.NOT_ASSESSED, why=str(refused))
        return self.inner.search(query, court=court, from_year=from_year,
                                 to_year=to_year, limit=limit)

    # ------------------------------------------------ the P21 surface ------
    #
    # EVERY PORT METHOD IS GATED HERE, BY NAME, and `__getattr__` below refuses
    # to delegate one that is not. Each returns its type's own third state
    # when the policy refuses -- the same rule `search` follows -- because a
    # refused route reported as an empty result is the defect, not the report
    # of it. A locator or a case id is smaller than a query and still says
    # what the advocate is working on, so it leaves under the same class.

    def _permit(self, size: int) -> str | None:
        try:
            self.gate.permit(Sink.INDEX, self.processor_id, self.data_classes,
                             size_bytes=size)
        except EgressRefused as refused:
            return str(refused)
        return None

    def discover(self, query: str, *, court: str | None = None,
                 from_year: int | None = None, to_year: int | None = None,
                 limit: int = 20) -> CaseDiscovery:
        refused = self._permit(len((query or "").encode("utf8")))
        if refused:
            return CaseDiscovery(query=query, index=f"{self.processor_id} (refused)",
                                 coverage=Coverage.NOT_ASSESSED, why=refused)
        return self.inner.discover(query, court=court, from_year=from_year,
                                   to_year=to_year, limit=limit)

    def expand(self, case_id: str, *, query: str | None = None,
               limit: int = 200) -> CaseExpansion:
        refused = self._permit(len(f"{case_id}{query or ''}".encode("utf8")))
        if refused:
            return CaseExpansion(case_id=case_id, index=f"{self.processor_id} (refused)",
                                 coverage=Coverage.NOT_ASSESSED, why=refused)
        return self.inner.expand(case_id, query=query, limit=limit)

    def passage(self, locator: str) -> Paragraph | None:
        if self._permit(len((locator or "").encode("utf8"))):
            return None
        return self.inner.passage(locator)

    def resolve(self, citation: str) -> CitationResolution:
        refused = self._permit(len((citation or "").encode("utf8")))
        if refused:
            return CitationResolution(raw=citation, key="?",
                                      state=ResolutionState.INDEX_UNAVAILABLE,
                                      why=refused)
        return self.inner.resolve(citation)

    def treatment(self, case_id: str) -> Treatment:
        refused = self._permit(len((case_id or "").encode("utf8")))
        if refused:
            return Treatment.not_checked(refused)
        return self.inner.treatment(case_id)

    def case_identity(self, case_id: str):
        if self._permit(len((case_id or "").encode("utf8"))):
            return None
        return self.inner.case_identity(case_id)

    def __getattr__(self, name: str) -> Any:
        """A port method never delegates ungated. See `PolicedStore`."""
        if name in _PORT_METHODS:
            raise NotImplementedError(
                f"{name!r} is declared on CorpusSearchPort and PolicedSearch "
                f"does not gate it, so delegating it would send the query to "
                f"{self.processor_id!r} without consulting the policy.")
        return getattr(self.inner, name)
