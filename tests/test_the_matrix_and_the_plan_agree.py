"""A FEATURE CANNOT BE FURTHER ALONG THAN THE GATES THAT ENFORCE IT.

`assurance/specification/features.yaml` carries a status per feature -- decided, built, tested,
verified live. `backend/nm/domain/gates.py` carries a `built` flag per gate. `trace`
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

So the row is DECLARED below rather than fixed, carrying the argument.
The check still earns its place: it would catch the next feature that
outran its gate without anybody deciding to let it.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml
from nm.domain.gates import GATES

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEATURES = ROOT / "assurance" / "specification" / "features.yaml"

#: Statuses that CLAIM the feature is done. `decided` is the only one that
#: does not, and `trace` owns the same vocabulary in `BUILT_OR_BEYOND`.
CLAIMS_DONE = frozenset({"built", "tested", "verified live"})


def _status() -> dict[str, str]:
    doc = yaml.safe_load(FEATURES.read_text(encoding="utf8"))
    feats = doc["features"] if isinstance(doc, dict) and "features" in doc else doc
    if isinstance(feats, dict):
        feats = list(feats.values())
    found = {f["id"]: f.get("status") for f in feats if f.get("id")}
    assert len(found) > 30, (
        f"only {len(found)} feature(s) read from features.yaml -- the shape "
        f"changed, and a check that sees nothing passes everything")
    return found


#: Features that legitimately claim to be done while a gate of theirs is
#: unbuilt, with the REASON. Not a convenience list: each entry is a
#: decision somebody made, written so it can be argued with.
DECLARED: dict[str, str] = {
    "G-LIMITATION":
        "D1 is `tested` and this gate is deliberately unbuilt, per "
        "`test_unbuilt_gates_are_declared_unbuilt`. D2 computes the "
        "position and D1 renders it BLOCKED with the reason, so the STATE "
        "is built. What is not built is the other half of the condition: "
        "whether the step being recommended is merits work that DEPENDS "
        "on limitation. `Obtain the sale deed` does not; `file the suit` "
        "does, and nothing before D5 tells them apart. Firing on the "
        "whole set applies a gate to cases it was not written for, which "
        "is G-POSTURE's recorded defect. I BUILT IT AND BACKED IT OUT: "
        "it suppressed the action on every uncomputed thread and broke "
        "slice 4's tested contract that the action says WHICH window "
        "could not be established, collapsing `assessed, no dated "
        "deadline` and `nobody computed one` into one silence.",
}


def test_no_feature_claims_to_be_done_while_a_gate_of_its_own_is_unbuilt():
    status = _status()
    broken = [
        (g.id, g.feature, status[g.feature])
        for g in sorted(GATES, key=lambda x: x.id)
        if g.feature in status
        and status[g.feature] in CLAIMS_DONE
        and not g.built
        and g.id not in DECLARED
    ]
    assert not broken, (
        "these features are declared done and carry a gate that is not "
        "built, so the plan says the control exists and the matrix says it "
        "does not:\n  "
        + "\n  ".join(f"{gid}: feature {feat} is {st!r} and the gate is "
                      f"built=False" for gid, feat, st in broken)
        + "\n\nBuild the gate, or lower the feature's status. A feature is "
          "not done while the thing that refuses on its behalf is missing.")


def test_the_check_can_see_a_feature_that_outran_its_gate():
    """POSITIVE CONTROL. This drifted for slices with every other check
    passing, so it has to prove it can fail."""
    status = {"X9": "tested"}

    class _G:
        id, feature, built = "G-PLANTED", "X9", False

    broken = [g for g in (_G(),)
              if status.get(g.feature) in CLAIMS_DONE and not g.built]
    assert broken, "the check would not notice a feature that outran its gate"


def test_a_feature_still_being_built_may_have_some_gates_built():
    """THE REVERSE IS NOT A DEFECT, asserted so nobody 'tightens' this later.

    B2 owns G-DUTY (built) and G-EMERGENCY (not). A slice under construction
    looks exactly like this, and a check that failed on it would be a check
    that fails on ordinary work.
    """
    status = _status()
    wip = [g.id for g in GATES
           if g.built and status.get(g.feature) not in CLAIMS_DONE
           and g.feature in status]
    assert wip, (
        "no gate is built on a feature still 'decided' -- if that is really "
        "true this test is now vacuous, but it was 5 gates when written, and "
        "a vacuous test here would let the two-way version back in")
