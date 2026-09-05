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


#: One entry. See the module docstring.
HARD_TIER_STEPS: tuple[HardTierStep, ...] = (
    HardTierStep(
        # THE FILE, because that is the granularity the check can see:
        # it scans for `Tier.HARD` and knows the path it found it in.
        # `nm.core.turn._tier` is the ONLY site in this file, which is
        # the whole design -- one place turns "is this read decisive"
        # into a tier, so a second site would be a second owner.
        step="nm/core/turn.py",
        measurement=(
            "B-088. The correction read fired on one run of GS-15 and returned "
            "NOTHING on the next, on identical input -- so the answer computed "
            "a limitation period from a date the advocate had explicitly "
            "withdrawn, and reported a claim as expired in 1987 for an "
            "agreement dated 2024. Every citation on that turn was verbatim "
            "and the arithmetic was correct. Two runs, same code, same "
            "sentence, opposite answers: that is a read that is not reliable "
            "enough at the cheap tier for an output nothing downstream can "
            "check."),
        measured_at="2026-09-05",
        delta=(
            "COST, measured on GS-15's own transcripts before the switch: the "
            "decisive reads are 3 calls of 10 and 1611 in / 115 out tokens, "
            "which is 35% of a turn's input and 10% of its output. Escalating "
            "ONLY them takes a turn from $0.001449 to $0.003353 (+131%); "
            "escalating everything would be roughly 600%. gpt-5.2 direct at "
            "0.875/7.00 per Mtok is cheaper than the judge (gpt-5.1, "
            "1.25/10.00), which is what made it affordable. "
            "QUALITY IS NOT YET MEASURED, and this entry says so rather than "
            "implying it. B-088 measures what the CHEAP tier costs when it "
            "fails; whether the expensive one fails less often on the same "
            "input is a rerun of GS-15 that has not happened. The promotion "
            "rests on the failure being unacceptable, not on the replacement "
            "being proven -- and that distinction belongs in the register "
            "rather than in a commit message."),
    ),
)

PERMITTED = {s.step for s in HARD_TIER_STEPS}
