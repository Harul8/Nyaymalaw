"""WHICH OF TWO AUTHORITIES PREVAILS: the shapes. LB-122.

WHAT WAS ALREADY BUILT, AND WHAT WAS NOT. Measured 25 September 2026 before
anything here was written, because the plan row was drafted from a count of
mentions in the plan and not from the code:

    binding by court      `nm.knowledge.jurisdiction.binding_status`   BUILT
    subsequent treatment  `nm.knowledge.citator`                       BUILT
    ratio versus obiter   `Finding` / G-ATTRIB                         BUILT
    bench strength        `nm.knowledge.identity.supersedes`           BUILT
    ANY OF IT REACHING THE ADVOCATE WHEN TWO AUTHORITIES DISAGREE      NOT

`supersedes` implements the rule -- a larger bench supersedes a smaller one
within the same court, a senior court supersedes a junior one -- and its only
callers were tests. Every authority a turn retrieved was rendered with its own
bench inside its `ref`, and nothing compared them. An advocate reading two
authorities on one point was left to work out for themselves which one their
court has to follow, which is the question the rule exists to answer.

THIS PORT DOES NOT RESTATE THE RULE. It asks the knowledge plane to apply the
rule it already owns to the authorities one turn actually retrieved. A second
statement of "a larger bench supersedes a smaller one" is exactly the shape
CLAUDE.md section 4 refuses.

THE THIRD STATE IS MOST OF THE ANSWER HERE, and that is not a weakness. Bench
size is recorded for a minority of held judgments, so two authorities are often
not comparable at all -- and co-ordinate benches that disagree are ALSO not
comparable, for a completely different reason: neither supersedes the other,
and the conflict is resolved by reference to a larger bench rather than by
ranking. Collapsing those two into one silence would say nothing in the first
case and mislead in the second, so they are separate members below.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from nm.domain.text import refuses_blank_text


class Standing(str, Enum):
    """What the comparison established about two authorities.

    `CO_ORDINATE` AND `NOT_RECORDED` ARE NOT THE SAME FACT and must never be
    merged. The first is a finding -- these two benches are equal, and a
    conflict between them goes to a larger bench. The second is a gap: the
    bench is not recorded for at least one of them, so the rule cannot run.
    An advocate acts differently on each.
    """

    SUPERSEDES = "supersedes"
    CO_ORDINATE = "co_ordinate"
    NOT_RECORDED = "not_recorded"

    @classmethod
    def not_established(cls) -> "Standing":
        return cls.NOT_RECORDED


@refuses_blank_text("higher", "lower")
@dataclass(frozen=True)
class Weighing:
    """One comparison between two retrieved authorities, and WHY.

    `higher` and `lower` are EXEMPT FROM THE BLANK RULE on purpose: where the
    benches are co-ordinate, or the rule could not run at all, there is no
    higher authority and naming one would be the answer this class exists to
    avoid. `reason` is never blank, because a ranking an advocate cannot check
    is one they have to take on trust -- the argument `BindingRuling.rule`
    already makes one layer down.
    """

    standing: Standing
    reason: str
    higher: str = ""
    lower: str = ""


class AuthorityWeightPort(Protocol):
    """The knowledge plane, asked to rank the authorities of one turn.

    Takes the findings' LOCATORS rather than the findings, because the case
    identity is what the rule needs and the locator is where the turn carries
    it. Returns one `Weighing` per pair worth saying something about; a pair
    the rule cannot reach at all produces nothing, and a pair it can reach but
    cannot rank produces `NOT_RECORDED` with the reason.
    """

    def weigh(self, locators: tuple[str, ...]) -> tuple[Weighing, ...]: ...


__all__ = ["Standing", "Weighing", "AuthorityWeightPort"]
