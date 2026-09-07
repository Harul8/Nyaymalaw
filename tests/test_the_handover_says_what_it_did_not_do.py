"""BK-10 — the four sections Phase 1 built, carried into the handover.

WHAT WAS WRONG, MEASURED
--------------------------
`CASE_SUMMARY_SECTIONS` holds sixteen sections and `CARRIES` held four, so
`handover_blockers` returned ten. That was the same four of sixteen the Phase 1
commit measured — and Phase 1 landed. `Thread` persists `issues`, `theory`,
`proof`, `decisions`, `evidence` and `thresholds_told` across turns; the thread
REMEMBERS. What never happened is the summary CARRYING any of it.

So four of the ten blockers were false statements about the product. A
receiving advocate was told the theory section was never built, on a file where
the theory had been held and revised for four turns.

WHY THE LIFT NEEDED A THIRD STATE FIRST
-----------------------------------------
Every one of those fields persists as an empty tuple until something writes it.
Empty therefore carries two opposite meanings — computed and found nothing, or
never computed. On a turn that is a small ambiguity. **In a handover it is the
dangerous one**, and it is the exact confusion `handover_blockers` already
exists to prevent one level up.

`Thread.assessed` records which sections have been computed, drawn from the
KEYS of the derive phase's `concluded` dict rather than from a list anybody
maintains. One field, not four flags: four booleans would be four copies of one
rule and the fifth section would arrive without its copy.

WHAT IS DELIBERATELY NOT CLAIMED
----------------------------------
`handover_blockers` and the per-thread state answer different questions.
The first says which sections this PRODUCT never builds; the second says what
happened on THIS FILE. A section can be carried by the product and unassessed
on a matter, and collapsing the two is how an advocate ends up reassured by a
contract instead of by the file.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.turn import TurnInput
from nm.domain import summary as summary_mod
from nm.domain.matter import Matter, Thread
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 4)
BRIEF = ("We act for the plaintiff at Hyderabad. The agreement is dated "
         "15 April 2024, possession was handed over on 20 April 2024, and "
         "the defendant has refused to execute the sale deed.")


def _thread_row(out, index: int = 0) -> dict:
    s = summary_mod.build(out.matter)
    return s.threads[index]


# ================= the third state, which is the whole point ==============

def test_a_thread_that_derived_nothing_says_not_assessed_not_none():
    """S1 ON THE MOST EXPENSIVE SURFACE THERE IS.

    A fresh thread has empty `issues`, `theory`, `proof` and `decisions`
    because nothing has run. Reporting that as "none" tells a receiving
    advocate there is nothing to prove on this claim, when what is true is
    that nobody worked out what has to be proved.
    """
    matter = Matter.create(advocate_id="adv_1", title="t")
    matter = matter.with_thread(Thread.create(label="a claim"))

    row = summary_mod.build(matter).threads[0]
    for name in summary_mod.DERIVED_SECTIONS:
        assert row["sections"][name]["state"] == "not_assessed", (
            f"{name} was never computed and the summary reports "
            f"{row['sections'][name]['state']!r}, which a receiving advocate "
            f"reads as a finding about the case")


def test_a_derived_thread_stops_saying_not_assessed(tmp_path):
    """The other direction, and it is the half that makes the first mean
    something: a state that is ALWAYS `not_assessed` is a disclosure that
    cannot be wrong, which is no disclosure at all."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                               today=TODAY))

    row = _thread_row(out)
    ran = [n for n in summary_mod.DERIVED_SECTIONS
           if row["sections"][n]["state"] != "not_assessed"]
    assert ran, (
        "a turn derived on this thread and every section still reports "
        "not_assessed, so the state never changes and proves nothing:\n"
        + repr(row["sections"]))


def test_the_state_survives_the_store(tmp_path):
    """`assessed` is worth nothing if it is rebuilt each turn -- that is the
    defect Phase 1 was about, one field along."""
    engine, store = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                               today=TODAY))

    reloaded = store.load(out.matter.id)
    assert reloaded.threads[0].assessed, (
        "what the turn assessed was not persisted, so the next turn reports "
        "not_assessed on work that has been done")
    assert set(reloaded.threads[0].assessed) == set(out.matter.threads[0].assessed)


# ================= the mechanism, not the four instances ==================

def test_every_carried_derivation_names_a_real_thread_field():
    """WHAT REFUSES THE FIFTH SECTION BEING WRONG.

    A section name in `DERIVED_SECTIONS` is read off the thread by that name.
    If the two ever disagree the section would report `not_assessed` forever --
    a disclosure that cannot fail, which is defect shape S11 wearing the shape
    of honesty.
    """
    fields = set(Thread.create(label="t").__dataclass_fields__)
    missing = [n for n in summary_mod.DERIVED_SECTIONS if n not in fields]
    assert not missing, (
        f"declared as carried and not a field of Thread: {missing}. The "
        f"section would report not_assessed on every file forever.")

    assert set(summary_mod.DERIVED_SECTIONS) <= summary_mod.CARRIES, (
        "a section is derived per thread and not declared as carried, so "
        "`handover_blockers` calls it unbuilt while the summary builds it")


def test_the_assessed_names_come_from_the_derive_phase_and_not_a_second_list():
    """§4: what refuses the second copy?

    `assessed` is written from the KEYS of `concluded`. A hand-maintained list
    beside it is the second owner, and the section added to one and not the
    other is the defect -- which is exactly how `Thread.decisions` came to be
    written by a keyword nothing could read.
    """
    import inspect

    from nm.core.turn import TurnEngine

    src = inspect.getsource(TurnEngine._run)
    assert "assessed=tuple(dict.fromkeys(" in src
    assert "*concluded))" in src, (
        "the assessed names are no longer taken from `concluded`'s keys, so a "
        "section added to the derive phase will be silently unrecorded")


# ================= the two claims are not collapsed ======================

def test_a_carried_section_can_still_be_unassessed_on_a_file():
    """`handover_blockers` says what the PRODUCT builds. The per-thread state
    says what happened on THIS FILE. They are different claims and the summary
    must make both.

    Collapsing them is how an advocate ends up reassured by a contract instead
    of by the file: `theory` is carried, and on a matter nobody has worked it
    is still not assessed.
    """
    matter = Matter.create(advocate_id="adv_1", title="t")
    matter = matter.with_thread(Thread.create(label="a claim"))
    s = summary_mod.build(matter)

    assert "theory" not in s.handover_blockers, (
        "theory is built and persisted; listing it as a blocker tells a "
        "receiving advocate the section does not exist")
    assert s.threads[0]["sections"]["theory"]["state"] == "not_assessed", (
        "the product carries the section and nothing has run on this file, "
        "and the summary says neither")


def test_the_blockers_that_remain_are_the_ones_that_are_really_unbuilt():
    """The count is the evidence that this moved, and the NAMES are the
    evidence that it moved for the right reason. Six remain and each is a
    feature nothing builds yet -- `screens` is B2-B6 at slice 10, `authorities`
    waits on the index build (BK-4), and the rest have no writer at all."""
    blockers = set(summary_mod.MatterSummary(
        matter_id="m", title="t").handover_blockers)

    assert blockers == {"engagement", "screens", "authorities", "deadlines",
                        "reservations", "gaps"}, (
        f"the blocker set changed to {sorted(blockers)} — either a section "
        f"landed, or one regressed, and both need a deliberate edit here "
        f"rather than a silently moving number")

    assert not (blockers & set(summary_mod.DERIVED_SECTIONS)), (
        "a section is derived per thread and still reported as unbuilt")
