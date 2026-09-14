"""THE GOLDEN SET IS WRITTEN DOWN TWICE AND NOTHING COMPARED THEM.

`docs/GOLDEN_SET.md` is PARSED by `assurance/journeys/run_goldens.py` -- it decides which
scenarios exist, which suite each is in, and the earliest slice each can run
at. `assurance/specification/plan/build_plan.py` holds a second copy of the same table, which is
what reaches the PRD and the workbook.

Two owners for one fact, and no check. CLAUDE.md §4 asks what makes a second
copy impossible; the honest answer here is that nothing can, because the two
serve different consumers -- so this refuses the DRIFT instead, in both
directions, which is the arrangement `trace` T8/T9 already uses for the gate
matrix against the code.

WHAT IT FOUND ON ITS FIRST RUN, and the reason it exists
----------------------------------------------------------
GS-03 was tagged `S2` and GS-04 `S1` -- both in the `smoke` suite, which is
declared to run on EVERY COMMIT. Neither can run at all:

    GS-03  needs the jurisdiction boundary. `G-COMPETENCE` is built=False.
    GS-04  needs document intake. `nm.core.intake` is declared UNWIRED in
           `tests/test_reached_from_production.py` and there is no upload
           endpoint in `backend/nm/edge/api.py`.

So the smoke suite has claimed coverage of the jurisdiction boundary and the
prompt-injection defence since slice 1, and had neither. That is worse than an
uncovered principle, because §5 of the set treats a covered principle as done:
an admitted gap is work, and this one was reported as finished.

The tags are now S10. The scenarios stay in the set and stay in `smoke` --
removing them would delete the requirement along with the gap.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "GOLDEN_SET.md"
PLAN = ROOT / "assurance" / "specification" / "plan" / "build_plan.py"

#: `| **GS-03** | scenario | S10 | 1 | must | never |`
_ROW = re.compile(r"^\|\s*\*\*(GS-\d+)\*\*\s*\|([^|]*)\|\s*S(\d+)\s*\|", re.M)


def _from_the_document() -> dict[str, int]:
    text = GOLDEN.read_text(encoding="utf8")
    found = {m.group(1): int(m.group(3)) for m in _ROW.finditer(text)}
    assert len(found) >= 20, (
        f"only {len(found)} scenario row(s) parsed from GOLDEN_SET.md -- the "
        f"table shape changed, and a check that sees nothing passes "
        f"everything")
    return found


def _from_the_plan() -> dict[str, int]:
    src = PLAN.read_text(encoding="utf8")
    block = src[src.index("GS = ["):src.index("ws_gs, hdr_gs")]
    rows = ast.literal_eval(block[block.index("["):block.rindex("]") + 1])
    # id at 0, earliest slice at 3 -- read positionally because the table is
    # a list of lists and has no header at runtime.
    return {r[0]: int(str(r[3]).lstrip("S")) for r in rows}


def test_the_two_copies_of_the_golden_set_agree_on_every_slice():
    doc, plan = _from_the_document(), _from_the_plan()

    assert set(doc) == set(plan), (
        "the two tables do not hold the same scenarios:\n"
        f"  only in GOLDEN_SET.md: {sorted(set(doc) - set(plan))}\n"
        f"  only in build_plan.py: {sorted(set(plan) - set(doc))}")

    drift = {gid: (doc[gid], plan[gid]) for gid in doc if doc[gid] != plan[gid]}
    assert not drift, (
        "these scenarios declare a different earliest slice in each place, so "
        "the runner and the PRD disagree about when they can run:\n  "
        + "\n  ".join(f"{g}: GOLDEN_SET.md says S{d}, build_plan.py says S{p}"
                      for g, (d, p) in sorted(drift.items())))


def test_the_drift_check_can_see_a_disagreement():
    """POSITIVE CONTROL. S11 -- and this check was absent for nine slices
    while the two tables were free to disagree, so it has to prove it can
    fail before it is worth anything."""
    doc = {"GS-01": 1, "GS-02": 2}
    plan = {"GS-01": 1, "GS-02": 9}
    drift = {g: (doc[g], plan[g]) for g in doc if doc[g] != plan[g]}
    assert drift == {"GS-02": (2, 9)}


#: Scenarios whose control is DECLARED unbuilt, with what they wait on.
#:
#: NOT AN EXEMPTION LIST. Every entry here is a scenario that cannot run, and
#: the assertion below is that its slice tag says so. Deleting a row from here
#: without building the control puts the scenario back into a suite it cannot
#: pass.
WAITS_ON: dict[str, str] = {
    "GS-03": "G-COMPETENCE is built=False -- the jurisdiction boundary has no "
             "mechanism, so the corpus limit cannot be named to the advocate",
    "GS-04": "nm.core.intake is declared UNWIRED and backend/nm/edge/api.py has no "
             "upload endpoint, so a document cannot reach the product at all",
}


@pytest.mark.parametrize("gid", sorted(WAITS_ON))
def test_a_scenario_whose_control_is_unbuilt_is_not_tagged_runnable(gid):
    """A scenario in `smoke` is claimed to run on every commit.

    Tagging one earlier than its control exists does not make it run -- it
    makes the set report coverage of a principle nothing exercises, which §5
    of the golden set treats as done.
    """
    doc = _from_the_document()
    assert gid in doc, f"{gid} left the set; the requirement went with it"
    assert doc[gid] >= 10, (
        f"{gid} is tagged S{doc[gid]} and cannot run: {WAITS_ON[gid]}. Either "
        f"build the control and retag it, or leave the tag honest.")
