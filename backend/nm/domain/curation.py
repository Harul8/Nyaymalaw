"""WHETHER A CURATED TABLE COVERS A KEY -- a value every table answers alike.

THE DEFECT THIS REFUSES (measured 26 September 2026, reviewing the tables the
tool layer will wrap). A curated table answers from the rows it holds, and a
key it never examined produced the SAME answer as a key it examined and found
to require nothing:

* the pre-institution table, asked about a cause it has no row for, engaged
  nothing through the cause -- and with the opponent known, the threshold
  read NOT APPLICABLE, "does not arise", for a cause nobody had looked at;
* the procedural-period table, asked about a role it has no row for, listed
  EVERY period as undecided -- as though the role were unknown rather than
  uncurated.

Four tables had four answers to one question -- `why_not`, `test_for` returning
None, an empty tuple, a list of everything -- and a caller could not ask any of
them the question directly. That is defect shape S1 (an absent input reading as
a finding) held in place by S9 (four owners for one truth).

THE RULE. Every curated table answers `coverage(key)` with one of these four
values, and no consumer may render `NOT_CURATED` as "nothing applies". A tool
the model calls (LB-129, LB-159) says "no curated table" from this value and
the model continues with retrieval; the served turn says the same in words.
"""
from __future__ import annotations

from enum import Enum


class Curation(str, Enum):
    """What a curated table can say about ONE key of its closed vocabulary."""

    CURATED = "curated"
    """The table examined this key. Its answer stands -- INCLUDING an empty one,
    which is then a finding that nothing this table holds applies."""

    WITHHELD = "withheld"
    """The table examined this key and deliberately holds no row, for a stated
    reason (the elements table's `WITHHELD`). A decision, not a gap."""

    NOT_CURATED = "not_curated"
    """The table never examined this key. An empty answer from it is SILENCE,
    never a finding; what applies must come from the retrieved law."""

    KEY_NOT_ESTABLISHED = "key_not_established"
    """The key itself is unknown -- the cause, the role, the relief nobody has
    stated. Nothing can be looked up until it is."""

    @property
    def answer_stands(self) -> bool:
        """Only a curated key's answer -- including an empty one -- is a finding."""
        return self is Curation.CURATED


__all__ = ["Curation"]
