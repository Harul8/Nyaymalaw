"""What a cause of action REQUIRES: the types, and who answers.

THE TABLE IS NOT HERE. `nm/knowledge/elements.py` holds the curated element
lists and `nm/adapters/knowledge/elements.py` serves them through this port.
The split is the one the evidence plane already uses: the port declares the
shape, the knowledge plane holds the curation, and `nm.core` sees neither.

WHY THE ELEMENT LIST IS CURATED AND NOT READ, stated here because this is
where a future caller looks first. D5 says every element carries who must
prove it, to what standard, and with what material. The STATUS is a question
about one file and a model answers it; the ELEMENT LIST is a question about
the law and a model must not.

A model asked for "the elements of specific performance" returns four or five
plausible items, most of them right, in a wording that changes between calls.
Every proof position downstream would then rest on a list nobody authored,
`uncovered` would report complete coverage of whatever came back, and D5's
third NEVER -- the coverage gate may not certify itself -- would be defeated
one layer above where it looks. It is CLAUDE.md §5 reaching somewhere the rule
does not obviously go: fuzzy matching may rank, never identify, and the thing
being identified here is what the advocate has to prove.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nm.domain.matter import CauseOfAction, Side
from nm.domain.proof import Burden, Standard
from nm.domain.text import refuses_blank_text


@refuses_blank_text()
@dataclass(frozen=True)
class Ingredient:
    """One thing that must be established, and who must establish it."""

    element: str
    """In the advocate's words, as a thing to be PROVED and not as a question.

    "The agreement to sell, and its terms" and not "was there an agreement?".
    An element is what goes in a list of what the file must carry; a question
    belongs to D9's issue register, which is a different list with a different
    job, and merging the two produces a document that is neither."""

    on: Side
    """Which side bears it. MOVING for the party asserting the claim."""

    serves: str = ""
    """What the element is FOR, where that is not obvious from its name.

    Rendered beside the element so an advocate can see why a gap matters
    before deciding whether to close it."""


@refuses_blank_text()
@dataclass(frozen=True)
class Elements:
    """The ingredients of one cause, and the standard they are proved to."""

    cause: CauseOfAction
    standard: Standard
    curated_from: str
    ingredients: tuple[Ingredient, ...] = ()

    def burden(self, ingredient: Ingredient) -> Burden:
        """The burden for one ingredient. Built here so no caller assembles
        it from parts and gets the side wrong on the way."""
        return Burden(on=ingredient.on)


class ElementsPort(Protocol):
    """The knowledge plane, asked what a cause requires.

    TWO METHODS, AND THE SECOND IS NOT OPTIONAL. `elements_for` returning
    `None` says only that there is no list; `why_not` says whether that is a
    decision with a reason or a gap in the product, and those call for
    different things from the advocate -- supply the missing route, or wait.
    An absent input must never read as a verdict.
    """

    def elements_for(self, cause: CauseOfAction) -> Elements | None: ...

    def why_not(self, cause: CauseOfAction) -> str: ...
