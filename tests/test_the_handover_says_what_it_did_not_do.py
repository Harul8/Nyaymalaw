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
    evidence that it moved for the right reason.

    TWO remain after Phase 4, and each genuinely has no writer:
    `engagement` is B5/G-SCOPE, declared unbuilt in the gate matrix, and
    `reservations` is E5 -- *a disagreement the advocate overruled stays
    visible and reactivates on a changed fact* -- which nothing in `nm/`
    produces.

    THE OTHER FOUR WERE NEVER UNBUILT. `deadlines` and `gaps` ran on every
    turn and threw the result away; `screens` built five states and kept
    none; `authorities` were retrieved and discarded. Reading the NAMES
    rather than the count is what told those apart from these two, and it
    is the whole point of this file.

    `screens` is worth the extra line, because it looks like slice-10 work
    and is not. RUNNING the conflict, competence and scope checks is
    B3-B5; carrying five states that say `not_run` is what Appendix E
    requires so their absence is visible at all. R-8 is untouched.
    """
    blockers = set(summary_mod.MatterSummary(
        matter_id="m", title="t").handover_blockers)

    # PHASE 3 REMOVED `deadlines` AND `gaps` FROM THIS SET, and this
    # assertion is what made that a deliberate act rather than a number that
    # moved. Both modules had been running on every turn since slice 6 --
    # `deadlines` reached ten times from the turn engine, `gaps` four -- and
    # neither result survived the turn, so the handover carried no section
    # for either on a file where both had been computed for four turns.
    assert blockers == set(), (
        f"the blocker set changed to {sorted(blockers)} — either a section "
        f"landed, or one regressed, and both need a deliberate edit here "
        f"rather than a silently moving number")

    assert not (blockers & set(summary_mod.DERIVED_SECTIONS)), (
        "a section is derived per thread and still reported as unbuilt")


# ================= Phase 3 — a derivation, not a reading ==================

def test_a_computed_register_reaches_the_handover(tmp_path):
    """PHASE 3'S WHOLE CLAIM, on a served turn.

    `nm/core/deadlines.py` is reached ten times from the turn engine and
    `nm/core/gaps.py` four. Neither result survived the turn, so the handover
    carried no deadlines and no gaps section on a file where both had been
    computed every turn since the brief arrived. Not unbuilt -- built, run,
    and thrown away.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                               today=TODAY))

    row = _thread_row(out)
    # ALL THREE, AND NAMED. A loop over `DERIVED_SECTIONS` asserting that
    # SOME ran is what let `authorities` be added and then taken away
    # again with nothing going red -- caught by mutation, which was the
    # only thing that could have caught it.
    for name in ("deadlines", "gaps", "authorities"):
        assert row["sections"][name]["state"] != "not_assessed", (
            f"{name} ran on this turn and the handover reports it as never "
            f"computed:\n" + repr(row["sections"]))


def test_an_empty_queue_is_a_finding_and_an_absent_one_is_not(tmp_path):
    """`gaps` is written even when EMPTY, and that is the point of the phase.

    # `authorities` must HOLD something on this brief: the fixture
    # retrieves Limitation Act Article 65 and the answer rests on it, so
    # `none` here would mean the findings were recorded empty rather
    # than recorded at all.
    assert row["sections"]["authorities"]["state"] == "held", (
        "the answer relied on retrieved provisions and the handover "
        "carries none of them:
" + repr(row["sections"]))

    Nothing missing is a real answer. Nobody having looked is not. Inferring
    one from the other at read time -- treating an empty tuple as "no gaps" --
    is the confusion the whole handover contract exists against, and it is
    only avoidable because the key is written whether or not the queue holds
    anything.
    """
    import inspect

    from nm.core.turn import TurnEngine

    src = inspect.getsource(TurnEngine._derive)
    assert 'concluded["gaps"] = tuple(gaps)' in src, (
        "the gap queue is no longer recorded unconditionally, so an empty "
        "queue and an unrun one are about to become indistinguishable")

    # And the register is the OTHER case: written only when computed, because
    # `register is None` already means the turn could not compute one.
    assert "if register is not None:" in src, (
        "the deadline register is recorded unconditionally, so a side-blind "
        "turn would report an assessed register it never built")


def test_the_persisted_derivation_is_replaced_and_never_merged(tmp_path):
    """A PERSISTED DERIVATION THAT CAN DISAGREE WITH ITS COMPUTATION IS THE
    THREE-STORES DEFECT.

    `theory` and `issues` are MERGED across turns because they are model
    readings and a read that forgets something must not lose it. A register is
    not a reading: it is recomputed from the limitation position every turn,
    so it is REPLACED whole. Merging it would let a stale entry outlive the
    facts it was derived from, with nothing able to tell.
    """
    import inspect

    from nm.core.turn import TurnEngine

    # WHITESPACE-COLLAPSED. `authorities=` wraps across two lines, and a
    # line-exact match reported it missing when it was there -- an assertion
    # that fails on a line break is checking the formatter, not the rule.
    src = " ".join(inspect.getsource(TurnEngine._run).split())
    for name in ("deadlines", "gaps", "authorities"):
        wrapped = f'{name}=concluded.get( "{name}", thread.{name}),'
        inline = f'{name}=concluded.get("{name}", thread.{name}),'
        assert wrapped in src or inline in src, (
            f"{name} is not written by name, or is being combined with the "
            f"standing value rather than replacing it")


# ================= Phase 4 — a section the FILE owns ======================

def test_the_screens_carry_five_states_on_every_matter(tmp_path):
    """Appendix E: *each carries its own state, INCLUDING `not_run`. A2 forbids
    showing a not_assessed screen as clear, and that is only possible if the
    summary distinguishes them.*

    Five states, from `ScreenKind`. Four rows would let a receiving advocate
    believe the fifth was checked, which is `unscreened`'s own argument for
    drawing from the vocabulary, arriving at the handover.
    """
    from nm.core.screens import ScreenKind, ScreenState

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                               today=TODAY))

    assert len(out.matter.screens) == len(list(ScreenKind)), (
        f"{len(out.matter.screens)} screens on the file and "
        f"{len(list(ScreenKind))} kinds exist")
    assert {s.kind for s in out.matter.screens} == set(ScreenKind)
    for screen in out.matter.screens:
        # ANY STATE, AND ALL FIVE PRESENT. BK-34 gave the screens producers, so
        # they now answer CLEAR, BLOCKED, INCOMPLETE or NOT_ASSESSED
        # depending on the file -- and pinning NOT_ASSESSED here would
        # assert that the screens never run, which is the thing that was
        # fixed. What the handover needs is that all five are CARRIED and
        # each says something: a missing kind is invisible, and a state
        # with no reason cannot be acted on by whoever receives the file.
        assert screen.state in set(ScreenState)
        # EVERY SCREEN SAYS SOMETHING, in whichever field its state uses.
        # `not_assessed_because` is the right question for a screen that did
        # not run and the wrong one for a screen that did -- the type refuses
        # a NOT_ASSESSED with no reason, and refuses a CLEAR that carries one
        # in the release field. What the handover needs is that no screen is
        # silent, which is what this asks.
        assert screen.detail or screen.not_assessed_because, (
            f"the {screen.kind.value} screen says nothing at all, so whoever "
            f"receives this file cannot tell what it found")

    s = summary_mod.build(out.matter)
    assert s.sections["screens"]["state"] == "held", (
        "the screens ran and the summary reports the section as never built")
    assert s.sections["screens"]["count"] == len(list(ScreenKind))


def test_the_screens_are_recorded_even_when_they_refuse_the_matter():
    """The file a receiving advocate MOST needs the states for is the one the
    screens refused, so they are recorded before the blocked branch and not
    after it."""
    import inspect

    from nm.core.turn import TurnEngine

    src = inspect.getsource(TurnEngine._run)
    landed = src.index("matter, screens=screens.screens")
    blocked = src.index("if not screens.clear:")
    assert landed < blocked, (
        "the screens are recorded after the `clear` check, so a matter that "
        "was refused carries no screen states at all")


def test_the_matter_level_sections_use_the_same_helper():
    """§4 again. Two tuples and ONE `_states`; a second state helper for
    matter-level sections is the copy that drifts, and it would have drifted
    on the first section added to either list."""
    import inspect

    src = inspect.getsource(summary_mod)
    assert src.count("def _states(") == 1, (
        "there is more than one state helper, so a matter-level section and a "
        "thread-level one can disagree about what `not_assessed` means")
    assert "_states(t, DERIVED_SECTIONS)" in src
    assert "_states(matter, MATTER_SECTIONS)" in src


def test_the_store_round_trips_a_set_in_both_directions():
    """`Screen.covers` is a `frozenset[str]`, and persisting screens sent it
    through a codec that handled dataclasses, enums, dates, lists, tuples and
    dicts and fell through on everything else -- so it reached `json.dumps`
    and raised. Twelve served-path tests, every one a TypeError from inside
    starlette and none of them naming the cause.

    ASSERTED AT THE CODEC, both ways. Encoding a set as a list is half a fix:
    a field declared `frozenset[str]` that comes back a list is the shape
    `_decode` was rewritten to prevent -- faithful on the way out, something
    else on the way back, and nothing failing until a set operation far away.

    SORTED ON THE WAY OUT so a set writes the same bytes every time. Two
    identical matters that differ on disk produce a diff nobody can explain,
    and a diff nobody can explain is one nobody trusts.
    """
    from nm.adapters.store.file_store import _decode, _enc

    out = _enc(frozenset({"Rao", "Anand"}))
    assert out == ["Anand", "Rao"], f"not sorted, so not stable: {out}"

    back = _decode(frozenset[str], out)
    assert isinstance(back, frozenset), (
        f"a frozenset came back as {type(back).__name__}")
    assert back == frozenset({"Rao", "Anand"})

    assert isinstance(_decode(set[str], ["a"]), set)
    # And the neighbours are untouched: a change to the sequence branch that
    # turned every tuple into a set would pass everything above.
    assert _decode(tuple[str, ...], ["a", "b"]) == ("a", "b")
    assert _decode(list[str], ["a", "b"]) == ["a", "b"]


def test_a_screen_reloads_as_data_like_every_other_untyped_field(tmp_path):
    """`Matter.screens` is `tuple[object, ...]` for the cycle reason, so it
    reloads as dicts -- exactly as `issues`, `proof` and `evidence` do.

    NO `from_stored` READER IS ADDED, because nothing would call it: the turn
    rebuilds the screens from `ScreenKind` every time, and the summary needs
    only whether the section ran and how many rows it holds, which `bool` and
    `len` answer on a dict. Writing one now would be a complete module with no
    production caller, which is B-079 and B-116 and the shape this project has
    paid for twice.

    Recorded rather than left to be discovered: the day something needs a
    `Screen` back, this is the line that says where the reader goes.
    """
    from nm.adapters.store.file_store import FileMatterStore
    from tests.test_turn_contract import KEY

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                               today=TODAY))

    back = FileMatterStore(tmp_path, key=KEY).load(out.matter.id)
    assert len(back.screens) == len(out.matter.screens), (
        "the screens did not survive the store at all")
    assert summary_mod.build(back).sections["screens"]["state"] == "held", (
        "the summary cannot read the reloaded screens, so the handover loses "
        "the section on every file that is opened a second time")


# ============ the last two sections, and the claim that replaced them =====

def test_the_engagement_records_who_and_what_and_names_what_it_lacks(tmp_path):
    """Tenet 4: *a handover without it hands over work with no authority to do
    it.*

    Built from what the product had already read -- the client description and
    the disputes -- so no new read and no new gate. `G-SCOPE` refusing a step
    is B5 at slice 10 and stays there; this is the disclosure that makes its
    absence visible.
    """
    from nm.domain.engagement import NOT_RECORDED, from_stored

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF,
                               today=TODAY))

    engaged = from_stored(out.matter.engagement)
    assert engaged is not None, "no engagement was recorded on the file"
    assert engaged.covers, "the engagement covers no dispute on a file with one"

    # THE HALF THAT MAKES IT HONEST. An engagement record presenting
    # client-and-disputes as a complete engagement reads as authority to act
    # that nobody granted.
    assert engaged.not_recorded == NOT_RECORDED, (
        "the engagement does not name what it lacks, so it reads as complete")
    assert engaged.not_recorded, (
        "the list is empty, so the engagement claims to record everything an "
        "engagement needs -- which it does not")

    # THE COUNT IS NOT ASSERTED, AND USED TO BE. `len(...) == 5` was a
    # snapshot of current behaviour rather than an invariant, and
    # `engagement.py` promises the opposite: *the day one of these is
    # recorded, it comes off this list and the diff says so.* P13 recorded
    # who decides as distinct from who instructs, so the list is shorter by
    # one and the test that pinned the number was the thing in the way.
    #
    # What IS invariant is that the list stops naming what is now recorded.
    assert not any("who decides" in entry for entry in engaged.not_recorded), (
        "a commission records who decides as distinct from who instructs, so "
        "the engagement must no longer list it as missing")

    s = summary_mod.build(out.matter)
    assert s.sections["engagement"]["state"] != "not_assessed"


def test_a_reservation_is_reactivated_by_a_fact_and_never_by_a_turn():
    """E5's Class A eval, and the type is what enforces it.

    Almost everything this product derives is recomputed each turn, so a
    reservation keyed on re-derivation would come back on EVERY turn -- which
    is E5's counterexample arriving by construction: *the same objection
    restated on every turn after the advocate went the other way.*

    `reactivate` takes fact ids. There is no parameter that could carry a turn.
    """
    import inspect

    from nm.domain import reservation as res

    r = res.Reservation(position="the provision this rests on: Article 54",
                        because="the cause read as specific performance",
                        stated_at="turn_1", overruled_at="turn_3")
    assert not r.live, "a reservation is live before anything reactivated it"

    # A turn passing is not a fact.
    assert res.live(res.reactivate((r,), frozenset(), {})) == ()

    back = res.reactivate((r,), frozenset({"f_9"}),
                          {r.position: "f_9"})
    assert back[0].live and back[0].reactivated_by == "f_9"

    # THE SIGNATURE IS THE ENFORCEMENT. A `turn_id` parameter here would make
    # the rule a convention that the next caller can decline.
    params = set(inspect.signature(res.reactivate).parameters)
    assert "turn" not in " ".join(params), (
        f"`reactivate` can be handed a turn: {sorted(params)}")


def test_an_overruled_position_is_recorded_once_and_not_restated():
    """*Disagree once, clearly, then drop it.* The counterexample is the same
    objection on every turn, so recording it twice is the defect in the
    summary rather than in the answer."""
    from nm.domain import reservation as res

    r = res.Reservation(position="p", because="b", stated_at="t1",
                        overruled_at="t2")
    again = res.Reservation(position="p", because="b", stated_at="t1",
                            overruled_at="t5")
    assert len(res.record(res.record((), r), again)) == 1


def test_a_reservation_that_was_never_overruled_cannot_be_built():
    """A live disagreement filed as a reservation is one the advocate never
    saw the product drop -- and it would then be silently excluded from the
    answer, which is the opposite of E5."""
    from nm.domain import reservation as res

    with pytest.raises(ValueError, match="overruled_at"):
        res.Reservation(position="p", because="b", stated_at="t1",
                        overruled_at="")


def test_an_unreactivated_reservation_refuses_to_state_itself():
    """The tone rule has one owner. A reservation that nothing brought back
    has no current finding, and rendering one anyway IS the restatement."""
    from nm.domain import reservation as res

    r = res.Reservation(position="p", because="b", stated_at="t1",
                        overruled_at="t2")
    with pytest.raises(ValueError, match="restatement"):
        r.as_current_finding()


def test_an_empty_matter_is_not_a_complete_handover():
    """THE DEFECT THE LAST BLOCKER CLOSING EXPOSED.

    `handover_complete` was `not handover_blockers` -- true the moment the
    product built every section, and it returned True for a matter with no
    client, no thread and no fact. That is `handover_blockers`'s own
    counterexample one level up, and it was invisible for as long as some
    section was unbuilt: the first half was doing the second half's job by
    accident.
    """
    empty = summary_mod.MatterSummary(matter_id="m", title="t")

    assert empty.handover_blockers == (), (
        "a section is unbuilt again; this test is about the OTHER half")
    assert empty.not_assessed_here, (
        "an empty matter reports nothing unassessed")
    assert not empty.handover_complete, (
        "a file with no client, no thread and no fact reads as a complete "
        "handover")

    # THE POPULATION IS THE CONTRACT, not the dict. The first version read
    # `self.sections.items()` and returned nothing for an empty matter,
    # because a section absent from the dict was never asked about.
    assert set(empty.not_assessed_here) >= set(summary_mod.MATTER_SECTIONS)
    assert set(empty.not_assessed_here) >= set(summary_mod.DERIVED_SECTIONS)
