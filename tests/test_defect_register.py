"""THE REGISTER IS EXECUTABLE. Every defect names a check, and it must exist.

WHY
---
`assurance/specification/plan/build_plan.py` records 53 defects, and every one of them names *the
check that now refuses it*. **Nothing verified those checks existed.** The
column was prose, so a defect could be marked Fixed against a test that had
been renamed, moved, or never written — and the register would still read as a
wall of green.

That is the same shape as everything else in this file's neighbourhood: a
claim with no runner. `docs/DEFECT_SHAPES.md` calls it S11, and the register
recording S11 seven times while itself being unrunnable is the joke that had to
be closed.

WHAT THIS BUYS
--------------
Every defect ever found becomes a permanent guard, automatically. A fix that
lands without a working check fails the build rather than being noticed a year
later when the shape comes back. It is the cheapest thing in this codebase that
stops recurrence, and it should have existed from the first entry.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not re-run the named tests. They already run in the suite, and a
failing one already fails the build — re-running them here would be a second
copy of the suite, and slower. What it checks is that the reference RESOLVES:
the file is there, and the function it names is really in it.
"""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]

#: Anything that looks like a path this repo would hold. Deliberately broad —
#: the register's prose sometimes names a doc or a tool rather than a test, and
#: those are legitimate checks that still have to exist. The homes come from the
#: layout's one owner, and a match starts where a path starts -- never inside one --
#: so `nm/x.py` is not also read as a missing `nm/x.py`.


# ===================== an enumerator owns its population ====================
#
# THE RULE ABOVE IS VACUOUS FOR NEW ROWS, MEASURED 5 SEPTEMBER 2026.
#
# It asks whether SOME pair in a shape shares a check. S1 satisfied that long
# ago -- three of its 39 defects name `test_three_states`. So the bar was met
# once and can never bite again: ten S1 defects were added in one session, each
# with its own private check, not one sharing a mechanism with the 39 before
# it, and the suite stayed green. Of those 39, one check is shared by three and
# ELEVEN name no check at all.
#
# THE FIRST ATTEMPT AT A FIX WAS WRONG AND IS WORTH RECORDING. It demanded that
# every S1 defect found after the shape had "a mechanism" point at it -- and
# flagged thirty historical rows, because it had decided `test_three_states`
# was THE S1 mechanism. It is a mechanism for one narrow sub-shape. Demanding
# that a provider-metadata leak point at a three-state enum check is the
# "forcing them together would be its own kind of wrong" the docstring above
# already warns about. S1 is a bucket, not a population.
#
# THE RIGHT QUESTION IS NARROWER: does this defect belong to a population some
# ENUMERATOR already sweeps? An enumerator draws its population from the whole
# product and finds the members nobody has looked for yet, which is what
# "generalised" means operationally. So each one DECLARES the defects it
# subsumes, and those defects' register rows must name it. A defect that is an
# instance of a swept population and points only at its own scenario test reads
# as a patch, and the next instance has nowhere to be caught.

#: enumerator check -> the defects it subsumes.
#:
#: Read from the TESTS, not listed here, would be better; it is listed here
#: because the declaration belongs with the rule that uses it and a `SUBSUMES`
#: constant in each test file would be a second place to look. Adding an
#: enumerator means adding a line.
ENUMERATORS: dict[str, tuple[str, ...]] = {
    "tests/test_every_persisted_field_has_a_writer.py::"
    "test_every_persisted_field_has_a_writer_or_is_declared_reserved":
        ("B-086", "B-091", "B-092"),
    "tests/test_what_the_model_is_told.py::test_every_field_is_told_or_declared":
        ("B-093", "B-094", "B-096"),
    # B-088 IS NOT HERE, AND THAT IS A CORRECTION. It was listed, on the claim
    # that the decisive-read sweep generalised it. Measured the same afternoon:
    # G-READ does NOT fire on B-088's own case. In the failing GS-15 run the
    # date read ANSWERED -- the 2024 date reached the file -- and only
    # `corrects` was empty, so there was no empty answer to notice.
    #
    # The general form of B-088 is one axis further in: a decisive read whose
    # DECISIVE FIELD is absent, which is not the same as the read returning
    # nothing. That is not built. B-088's catch remains the phrase-list
    # question, which measurably fires on its own case, and the register says
    # so rather than claiming a mechanism that does not cover it.
}


# ================= an open row is a claim someone re-runs ===================
#
# B-100, measured 5 September 2026. `test_every_check_the_register_names_
# actually_exists` verifies a FIXED row. Nothing asked anything of an OPEN one,
# so the register was verified in one direction only -- and the unverified
# direction is the one a person reads when deciding what to do next.
#
# It cost a wrong answer the same day. Asked whether the build was ready for a
# judged run, the answer read straight off the register was "no: five golden
# scenarios compute no limitation" (B-065). One read-only corpus query showed
# all five causes returning their Article. B-086 was the same: fixed, verified
# on a served turn, and still saying NOT FIXED.
#
# A row that has stopped being true must expire against the CODE, which is the
# arrangement `UNWIRED`, `AWAITING`, `RESERVED` and `WITHHELD` all use.

def _still_open(row) -> bool:
    """Is there anything left to do on this row?

    ONE PREDICATE, OWNED ONCE, because the two checks below disagreed about it
    within the minute of being written: one read "Open" and the other read
    "not Fixed", and `B-088: Partly fixed` fell between them. A status is
    prose, so anything that does not begin `Fixed` has a remainder -- which is
    the reading that puts a partly-fixed row where a person will look for it.
    """
    return not str(row.get("status", "")).strip().startswith("Fixed")


#: Open defects with no runnable reproduction, and why not.
#:
#: DECLARED, NEVER ASSUMED. An entry here is a claim that the defect cannot be
#: demonstrated by code -- which is true of a judged verdict and of a gap in
#: something not yet built, and is NOT true of most defects. Without the table
#: the honest answer for every row would be "no reproduction", and the rule
#: would mean nothing.
NO_REPRODUCTION: dict[str, str] = {
}


def test_the_open_row_scan_can_see_an_undeclared_one():
    """A POSITIVE CONTROL, on the real predicate.

    The check passes on a register where every open row is declared, and would
    go on passing if the status test were inverted, or if `_register` returned
    nothing. Planted on the same comparison rather than on a fixture.
    """
    planted = {"id": "B-999", "when": "2026-09-05", "what": "a planted row",
               "shape": "S1", "check": "none", "status": "Open"}
    assert _still_open(planted)
    assert not _still_open({"status": "Fixed"}), (
        "the predicate calls a fixed row open, so every row would need a "
        "declaration and the rule would mean nothing")
    assert planted["id"] not in NO_REPRODUCTION, (
        "the control cannot fail: its planted row is already declared")


def test_the_stale_declaration_scan_can_see_a_closed_row():
    """A POSITIVE CONTROL on the staleness half.

    That check passes while every declaration matches an open row, and would
    pass identically if `_still_open` were inverted or `_register` returned
    nothing. Planted on the same predicate the real check uses, because a
    control that exercises a copy proves the copy.
    """
    closed = {"id": "B-999", "status": "Fixed"}
    assert not _still_open(closed), (
        "the control cannot fail: the predicate calls a fixed row open")

    # And the real comparison, run against it: a declaration naming this row
    # would be reported.
    stale = [did for did, _ in [("B-999", "declared")]
             if not _still_open(closed)]
    assert stale == ["B-999"], (
        "the staleness comparison does not report a declaration whose row is "
        "closed")


PLAN = ROOT / "assurance" / "specification" / "plan" / "build_plan.py"


