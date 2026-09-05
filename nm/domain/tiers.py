"""Which steps may use the expensive tier, and the measurement that earned it.

WHY A REGISTER RATHER THAN A CONVENTION
----------------------------------------
The cheap tier is the default and the expensive one is a decision. Left to
judgement at each call site, a step gets promoted because its output "read
better" on a sample of one — which is not a measurement, costs real money on
every turn thereafter, and is invisible in review because a tier argument looks
like configuration rather than a choice.

So a step that wants the `hard` tier declares itself here WITH THE MEASUREMENT
THAT JUSTIFIES IT, and `tests/test_slice0_foundations.py` fails the build on
any `Tier.HARD` in `nm/` that is not declared.

THE REGISTER WAS EMPTY UNTIL 5 SEPTEMBER 2026, and one step has now earned an
entry. It is the SIX DECISIVE READS, promoted together because they are one
population and not six decisions -- `nm/domain/reads.py` decides which reads
are decisive, and `nm.core.turn._tier` is the only place that turns that answer
into a tier.

An empty register was a claim -- *nothing has earned it* -- and it stayed empty
for ten slices, which is the point of writing it down.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.text import refuses_blank_text


@refuses_blank_text()
@dataclass(frozen=True)
class HardTierStep:
    """A step permitted to run on the expensive tier."""

    step: str
    measurement: str
    measured_at: str
    delta: str

    def __post_init__(self) -> None:
        if not self.measurement.strip() or not self.delta.strip():
            raise ValueError(
                f"{self.step}: a hard-tier promotion needs the measurement that "
                f"justifies it and the difference it made. 'It read better' is "
                f"not a measurement.")


#: EMPTY AGAIN, AND THE ROUND TRIP IS THE POINT.
#:
#: One entry was added on 5 September 2026 and withdrawn on 6 September when it
#: was measured. Both belong in the history: an escalation that was taken and
#: reversed on evidence is a different thing from one that was never taken, and
#: a register that only records the promotions is a register that reads as
#: though every promotion held.
#:
#: WHAT WAS CLAIMED. B-088 -- the correction read fired on one run of GS-15 and
#: returned nothing on the next -- with the cost measured at +131% a turn for
#: the six decisive reads.
#:
#: WHAT MEASURING IT SHOWED, replaying the recorded prompts 30 times each:
#:
#:     correction read   30/30 on gpt-5.2 AND 30/30 on gpt-4o-mini
#:     cause read        10/30 on gpt-5.2, 29/30 on gpt-4o-mini
#:     cause at temp 0    2/30 on gpt-5.2
#:
#: The first line says the escalation bought nothing: B-088 had been observed
#: on a SECOND correction read that B-086 deleted, so the justification rested
#: on code that no longer runs. The second says it cost something real -- the
#: cause read got three times worse. The third says it is not sampling noise:
#: at temperature 0 the stronger model settles deterministically on the wrong
#: answer.
#:
#: WHY THE STRONGER MODEL IS WORSE HERE, which is the part worth keeping.
#: gpt-5.2 quotes the whole relevant block of the account; the verbatim guard
#: demands a span that is in the advocate's own words, and the account carries
#: our date stamps and notes. The model is not being stupid -- it is using the
#: context it was given, and OUR PROMPT DOES NOT SAY WHICH PART MAY BE QUOTED.
#: A better model exploits that ambiguity harder. Fixing the prompt (B-108) may
#: make gpt-5.2 viable; until then the measurement says what it says.
#:
#: The other four decisive reads -- posture, role, factors and the date read's
#: own extraction -- were NOT measured, and reverting all six on evidence from
#: two is deliberate: no read showed a benefit, one showed serious harm, and
#: the cost was real.
HARD_TIER_STEPS: tuple[HardTierStep, ...] = ()

PERMITTED = {s.step for s in HARD_TIER_STEPS}
