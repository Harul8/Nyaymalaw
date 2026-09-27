"""Rank the authorities ONE TURN retrieved, using the rule that already exists.

LB-122. This module holds NO hierarchy rule of its own. `identity.supersedes`
owns "a larger bench supersedes a smaller one within the same court, and a
senior court supersedes a junior one", and a second statement of it here would
be the defect CLAUDE.md section 4 names -- two owners for one rule, one of them
hardened and the other not.

What this adds is the POPULATION: `supersedes` compares two identities, and
until now nothing handed it the authorities of a served turn. Its only callers
were tests.

WHY PAIRWISE AND WHY BOUNDED. An advocate needs to know which of the
authorities in front of them their court must follow, which is a question about
pairs. The pairs are bounded because a turn retrieves a handful of
authorities and the comparison is quadratic; `MOST_AUTHORITIES` is the bound,
and reaching it is DISCLOSED rather than silently truncated -- a ranking that
stopped early without saying so would look like a ranking that found nothing.
"""
from __future__ import annotations

from itertools import combinations

from nm.knowledge.identity import IdentityIndex, Precedence, supersedes
from nm.ports.authority_weight import Standing, Weighed, Weighing

#: The most authorities compared in one turn. Above this the comparison is
#: reported as bounded rather than run to completion -- see the module
#: docstring. Chosen to cover a realistic authority round, not tuned.
MOST_AUTHORITIES = 8


def case_id_of(locator: str) -> str:
    """The case id a Finding's locator carries, or empty.

    `nm.adapters.evidence.corpus` builds an authority locator as
    `case_id::chunk_id::para_type`. Read HERE rather than in the turn, because
    the locator's shape is the evidence plane's business and a caller that
    parsed it would be a second place that has to change when it does.
    """
    text = (locator or "").strip()
    return text.split("::", 1)[0] if "::" in text else ""


def weigh(locators: tuple[str, ...], index: IdentityIndex) -> Weighed:
    """Every pair of retrieved authorities worth saying something about.

    A pair whose identities the index does not hold at all produces NO ROW --
    there is no case to speak of, and a row saying "these two could not be
    compared" for every unindexed judgment would bury the pairs that matter.
    A pair it DOES hold but cannot rank produces `NOT_RECORDED` with the
    reason, because that is a gap the advocate can close by looking at the
    judgment.

    AND AN EMPTY RESULT SAYS WHY (`Weighed`). It used to be a bare empty tuple
    for four different reasons, which a tool could not tell apart.

    THE STANDING IS READ FROM THE RULE'S VALUE, never from its words. This
    decided CO-ORDINATE by finding "co-ordinate" in `supersedes`' reason -- a
    state that changed the day the sentence was reworded. `Precedence` now
    carries CO_ORDINATE itself.
    """
    ids: list[str] = []
    for locator in locators:
        case_id = case_id_of(locator)
        if case_id and case_id not in ids:
            ids.append(case_id)
    if len(ids) < 2:
        return Weighed(why=(
            "fewer than two distinct judgments were named by these authorities, "
            "so there is no pair to compare"))

    bounded = ids[:MOST_AUTHORITIES]
    out: list[Weighing] = []
    unheld = 0
    for left_id, right_id in combinations(bounded, 2):
        left, right = index.case(left_id), index.case(right_id)
        if left is None or right is None:
            unheld += 1
            continue
        verdict, why = supersedes(left, right)
        if verdict is Precedence.CO_ORDINATE:
            out.append(Weighing(standing=Standing.CO_ORDINATE, reason=why))
            continue
        if verdict is Precedence.NOT_COMPARABLE:
            out.append(Weighing(standing=Standing.NOT_RECORDED, reason=why))
            continue
        higher, lower = ((left, right) if verdict is Precedence.LEFT
                         else (right, left))
        out.append(Weighing(
            standing=Standing.SUPERSEDES, reason=why,
            higher=higher.title or higher.case_id or "the senior authority",
            lower=lower.title or lower.case_id or "the other authority"))

    if len(ids) > MOST_AUTHORITIES:
        out.append(Weighing(
            standing=Standing.NOT_RECORDED,
            reason=(f"{len(ids)} authorities were retrieved and the first "
                    f"{MOST_AUTHORITIES} were compared; the rest were not "
                    f"ranked against each other on this turn")))
    if not out:
        return Weighed(why=(
            f"the identity index holds no record for at least one judgment in "
            f"each of the {unheld} pair(s), so none could be compared"))
    return Weighed(weighings=tuple(out))


__all__ = ["MOST_AUTHORITIES", "case_id_of", "weigh"]
