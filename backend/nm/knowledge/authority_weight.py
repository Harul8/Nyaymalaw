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
from nm.ports.authority_weight import Standing, Weighing

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


def weigh(locators: tuple[str, ...], index: IdentityIndex,
          ) -> tuple[Weighing, ...]:
    """Every pair of retrieved authorities worth saying something about.

    A pair whose identities the index does not hold at all produces NOTHING --
    there is no case to speak of, and a row saying "these two could not be
    compared" for every unindexed judgment would bury the pairs that matter.
    A pair it DOES hold but cannot rank produces `NOT_RECORDED` with the
    reason, because that is a gap the advocate can close by looking at the
    judgment.
    """
    ids: list[str] = []
    for locator in locators:
        case_id = case_id_of(locator)
        if case_id and case_id not in ids:
            ids.append(case_id)
    if len(ids) < 2:
        return ()

    bounded = ids[:MOST_AUTHORITIES]
    out: list[Weighing] = []
    for left_id, right_id in combinations(bounded, 2):
        left, right = index.case(left_id), index.case(right_id)
        if left is None or right is None:
            continue
        verdict, why = supersedes(left, right)
        if verdict is Precedence.NOT_COMPARABLE:
            # THE TWO SILENCES ARE SEPARATED HERE, and the wording
            # `supersedes` already chose is what separates them: a recorded
            # equality says "co-ordinate", an unrecorded bench says the bench
            # is not recorded. Read from its reason rather than recomputed,
            # so the two cannot drift apart.
            standing = (Standing.CO_ORDINATE if "co-ordinate" in why
                        else Standing.NOT_RECORDED)
            out.append(Weighing(standing=standing, reason=why))
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
    return tuple(out)


__all__ = ["MOST_AUTHORITIES", "case_id_of", "weigh"]
