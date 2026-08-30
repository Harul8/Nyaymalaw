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

THE REGISTER IS EMPTY, AND THAT IS THE CURRENT ANSWER. No step has been shown
to need the expensive tier, and the hard tier is not configured on this
installation at all. An empty register is a claim -- *nothing has earned it* --
and it is a claim this file makes checkable rather than leaves to memory.
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


#: Empty by design. See the module docstring.
HARD_TIER_STEPS: tuple[HardTierStep, ...] = ()

PERMITTED = {s.step for s in HARD_TIER_STEPS}
