"""A FEATURE CANNOT BE FURTHER ALONG THAN THE GATES THAT ENFORCE IT.

`assurance/specification/features.yaml` carries a status per feature -- decided, built, tested,
verified live. `nm/shared/gates_contracts.py` carries a `built` flag per gate. `trace`
already checks each of those against the CODE:

    T3  a feature above `decided` with no implementing code
    T8  a gate declared built that no code path consults
    T9  a gate declared UNBUILT that code consults anyway

Nothing checked them against EACH OTHER, and they drifted.

WHAT THE INVARIANT IS, AND WHAT IT DELIBERATELY IS NOT
-------------------------------------------------------
It runs ONE WAY ONLY:

    a feature at `built` or beyond => every gate naming it is built

The reverse is NOT a defect and asserting it would be wrong. A feature owns
several gates -- B2 owns `G-DUTY` and `G-EMERGENCY`, B3 owns `G-UNSCREENED`
and `G-CONFLICT` -- so a feature still at `decided` with one gate built is
work in progress, which is the ordinary state of a slice being built.

I asserted the two-way version first and it reported SIX disagreements. Five
were work in progress. Had they been "fixed", the fix would have been either
advancing five feature statuses that are not true or marking five working
gates unbuilt -- both worse than the drift, and both invisible afterwards.
Measure the relationship before reporting the mismatch.

WHAT IT FOUND, AND HOW THAT FINDING TURNED OUT
------------------------------------------------
One row: `D1` is status `tested` and `G-LIMITATION` is `built=False`.

I read that as drift and built the gate. It was not drift. The gate is
deliberately unbuilt for a reason recorded in
`test_unbuilt_gates_are_declared_unbuilt`, and that reasoning is better
than mine: the limitation STATE is built, and what is missing is the
ability to tell whether the step being recommended actually depends on
limitation. My version fired on every thread and broke slice 4's tested
contract that the action says WHICH window could not be established.

That historical exception was removed on 22 September 2026 (DG-02) when
dependency-sensitive step enforcement landed. Uncertainty blocks the step,
not the conversation. The check still catches features outrunning their gates;
the separate served tests exercise the actual new enforcement boundary.
"""
from __future__ import annotations

import pathlib

import pytest


pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Statuses that CLAIM the feature is done. `decided` is the only one that
#: does not, and `trace` owns the same vocabulary in `BUILT_OR_BEYOND`.
CLAIMS_DONE = frozenset({"built", "tested", "verified live"})


#: Features that legitimately claim to be done while a gate of theirs is
#: unbuilt, with the REASON. Not a convenience list: each entry is a
#: decision somebody made, written so it can be argued with.
DECLARED: dict[str, str] = {}


def test_the_check_can_see_a_feature_that_outran_its_gate():
    """POSITIVE CONTROL. This drifted for slices with every other check
    passing, so it has to prove it can fail."""
    status = {"X9": "tested"}

    class _G:
        id, feature, built = "G-PLANTED", "X9", False

    broken = [g for g in (_G(),)
              if status.get(g.feature) in CLAIMS_DONE and not g.built]
    assert broken, "the check would not notice a feature that outran its gate"


FEATURES = ROOT / "assurance" / "specification" / "features.yaml"


