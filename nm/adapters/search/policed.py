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
from nm.ports.evidence import Coverage
from nm.ports.search import CorpusSearch, CorpusSearchPort

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

    def __getattr__(self, name: str) -> Any:
        """A port method never delegates ungated. See `PolicedStore`."""
        if name in _PORT_METHODS:
            raise NotImplementedError(
                f"{name!r} is declared on CorpusSearchPort and PolicedSearch "
                f"does not gate it, so delegating it would send the query to "
                f"{self.processor_id!r} without consulting the policy.")
        return getattr(self.inner, name)
