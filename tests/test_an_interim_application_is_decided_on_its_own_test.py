"""LB-123. THE INTERIM APPLICATION IS NOT DECIDED ON THE MERITS OF THE SUIT.

THE DEFECT THIS FILE IS ABOUT. An advocate asking "can I get an injunction on
Monday" is asking a different question from "will this suit succeed", and the
product had only the second. `nm.core.relief` read the FINAL relief on five
coordinates -- available, valuable, timely, enforceable, proportionate -- and
nothing anywhere set out the test an interim order is actually measured
against. A confident answer to the wrong question is the shape CLAUDE.md
records the whole product against.

WHAT IS AND IS NOT CLAIMED HERE. This slice sets out the TEST: the rule the
order is sought under, its limbs, the higher threshold where there is one, and
the statutory bar. Whether the advocate's material MAKES OUT a limb is a
question about their own affidavit that nothing yet reads, so every limb comes
back NOT ASSESSED, named, with what would answer it. These tests hold that line
in both directions -- a limb is never called made out, and never called weak.
"""
from __future__ import annotations

import dataclasses

import pytest
from nm.core import relief as relief_mod
from nm.core.premise import Basis
from nm.knowledge import interim_relief as curated
from nm.ports.interim_relief import InterimRelief, LimbState

pytestmark = pytest.mark.class_a


# ======================================== the table, and what it may not do ==

def test_every_curated_test_says_where_it_came_from():
    """`curated_from` IS THE WHOLE ARGUMENT FOR A CURATED TABLE.

    A threshold that cannot say where it came from is one somebody remembered,
    and a remembered interim test measures an application against a standard no
    one can check. The population is read rather than the type, so a row added
    tomorrow is covered.
    """
    assert curated.TESTS, "the table is empty, so this checks nothing"
    for relief, test in curated.TESTS.items():
        assert test.relief is relief, f"{relief}: keyed under another relief"
        assert test.curated_from.strip(), relief
        assert test.source.strip(), relief
        assert test.limbs, f"{relief}: a test with no limbs shows nothing"
        for limb in test.limbs:
            assert limb.what_would_answer_it.strip(), (relief, limb.name)


def test_a_test_is_reached_by_an_exact_key_and_never_by_words():
    """CLAUDE.md section 5. Which threshold an application is measured against
    is decided by membership of the closed `InterimRelief` vocabulary. There is
    no route by which a pleading that merely reads like an injunction reaches
    the mandatory threshold."""
    for relief in curated.TESTS:
        assert isinstance(relief, InterimRelief)
    assert curated.test_for(InterimRelief.NOT_STATED) is None


def test_the_mandatory_threshold_is_higher_and_says_so():
    """THE DISTINCTION THE ROW EXISTS FOR. An interlocutory mandatory
    injunction is not granted on the showing that carries a prohibitory one.
    A product that served one test for both would tell an advocate their
    mandatory application was on the ordinary footing."""
    prohibitory = curated.TESTS[InterimRelief.PROHIBITORY_INJUNCTION]
    mandatory = curated.TESTS[InterimRelief.MANDATORY_INJUNCTION]
    assert not prohibitory.threshold_note
    assert mandatory.threshold_note.strip()
    assert mandatory.threshold_note != prohibitory.threshold_note


def test_the_two_injunction_tests_share_one_set_of_limbs():
    """CLAUDE.md section 4 -- what refuses the second copy. Two literal copies
    of the three limbs is two places one of them can be corrected and the
    other not. They are the SAME tuple object, so there is nothing to drift."""
    assert (curated.TESTS[InterimRelief.PROHIBITORY_INJUNCTION].limbs
            is curated.TESTS[InterimRelief.MANDATORY_INJUNCTION].limbs)


def test_the_statutory_bar_is_named_on_every_injunction():
    """AN ADVOCATE WHO READS THREE SUPPORTED LIMBS AND THEN MEETS s.41 HAS
    READ THEM FOR NOTHING. The bar is carried on the test, not left to the
    advocate to remember."""
    for relief in (InterimRelief.PROHIBITORY_INJUNCTION,
                   InterimRelief.MANDATORY_INJUNCTION):
        assert "41" in curated.TESTS[relief].bar


# ============================================================ the assessment ==

def test_not_one_limb_is_ever_called_made_out_or_wanting():
    """THE HONEST POSITION OF THIS SLICE, held as an invariant rather than as
    a comment. Nothing here reads the affidavit, so no limb can be SUPPORTED
    and none can be WEAK. A limb reported weak by something that never looked
    at the file would tell an advocate their application is poor on the
    strength of not having read it."""
    for relief in curated.TESTS:
        assessment = curated.assess(relief)
        assert assessment.states, relief
        for name, state in assessment.states:
            assert state is LimbState.NOT_ASSESSED, (relief, name, state)


def test_every_limb_of_the_test_gets_a_state_and_none_is_dropped():
    for relief, test in curated.TESTS.items():
        assessment = curated.assess(relief)
        assert [name for name, _ in assessment.states] == \
            [limb.name for limb in test.limbs], relief


def test_a_relief_nobody_stated_is_not_an_application_that_failed():
    """THREE STATES. `NOT_STATED` produces an assessment with no test and a
    sentence saying nobody has said which order is sought -- never an empty
    assessment that reads like one that was run and found nothing."""
    assessment = curated.assess(InterimRelief.NOT_STATED)
    assert not assessment.established
    assert not assessment.states
    assert "no interim relief has been stated" in assessment.because


def test_a_relief_with_no_curated_test_names_the_gap_and_infers_nothing():
    """B-163's SHAPE. A zero from one table must name the table it came from.
    `STAY` is deliberately uncurated -- what a stay must show depends on what
    is being stayed -- and the honest answer names that gap rather than
    borrowing the injunction test next to it."""
    assert InterimRelief.STAY not in curated.TESTS
    assessment = curated.assess(InterimRelief.STAY)
    assert not assessment.established
    assert not assessment.states
    assert "no interim test is held" in assessment.because
    # AND IT SAYS WHAT IT DOES HOLD, so the advocate can tell a gap in this
    # table from a proposition of law about stays.
    assert "prohibitory injunction" in assessment.because


# ================================================ kept apart from the merits ==

def test_the_interim_kind_is_not_read_by_the_final_relief_verdict():
    """NEITHER QUESTION ANSWERS THE OTHER. `delivers` reads the four
    load-bearing coordinates; adding an interim kind to a relief must not move
    it in either direction, or the product would be inferring the strength of
    an injunction application from the merits of the suit and back again."""
    base = relief_mod.Relief(
        remedy="a decree for possession", objective="recover the shop",
        availability=relief_mod.Availability.AVAILABLE,
        value=relief_mod.Value.SUBSTANTIAL,
        timing=relief_mod.Timing.TIMELY,
        enforceability=relief_mod.Enforceability.ENFORCEABLE)
    with_interim = dataclasses.replace(
        base, interim=InterimRelief.PROHIBITORY_INJUNCTION)
    assert base.delivers and with_interim.delivers
    assert base.shortfalls == with_interim.shortfalls


def test_the_interim_kind_survives_a_round_trip_through_the_file():
    """It is stored on the thread and read back by the next turn, so a
    statement that does not survive the store is a statement the advocate
    makes once and never sees again."""
    relief = relief_mod.Relief(
        remedy="a decree for possession", objective="recover the shop",
        interim=InterimRelief.MANDATORY_INJUNCTION)
    back = relief_mod.Relief.from_stored(relief.as_dict())
    assert back is not None
    assert back.interim is InterimRelief.MANDATORY_INJUNCTION


def test_an_unreadable_interim_value_reads_as_not_stated_never_as_a_kind():
    """A STORED ROW FROM ANOTHER VERSION must not be guessed at. An
    unrecognised value falls to NOT_STATED, which sets out no test, rather
    than to the first member of the vocabulary, which would set out the wrong
    one."""
    back = relief_mod.Relief.from_stored(
        {"remedy": "x", "objective": "y", "interim": "an_interim_order"})
    assert back is not None
    assert back.interim is InterimRelief.NOT_STATED


# ===================================================== on the served turn ====

BRIEF = ("We act for the plaintiff at Hyderabad. The defendant is putting up a "
         "wall on our client's land and we want it stopped.")


def _client(tmp_path):
    from fastapi.testclient import TestClient

    from assurance.journeys.served import PASSWORD, served

    box = served(tmp_path / "store")
    advocate = box.enrol("adv_interim")
    c = TestClient(box.app)

    def carry(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            request.headers.setdefault("origin", str(c.base_url).rstrip("/"))
            v = c.cookies.get("nm_csrf")
            if v and "x-nm-csrf" not in request.headers:
                request.headers["x-nm-csrf"] = v
    c.event_hooks["request"].append(carry)
    assert c.post("/api/login", json={"advocate_id": advocate,
                                      "password": PASSWORD}).status_code == 200
    return c


def _open_matter(c):
    r = c.post("/api/turn", json={
        "message": BRIEF, "today": "2026-09-25",
        "parties": {"A Rao": "client", "B Reddy": "adverse"},
        "release": {"scope": "recover"},
        "capacity": {
            "state": "not_in_doubt",
            "basis": "The advocate assessed that the client instructs directly.",
        }})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"], r.json()["matter_version"]


def _state(c, mid, tid, version, interim):
    return c.post(f"/api/matters/{mid}/threads/{tid}/relief", json={
        "remedy": "a decree for a permanent injunction",
        "objective": "stop the construction on the client's land",
        "availability": "available", "value": "substantial", "timing": "timely",
        "enforceability": "enforceable", "proportionality": "proportionate",
        "interim": interim,
        "reason": "stated by the advocate",
        "expected_version": version})


def test_the_route_refuses_an_interim_order_outside_the_vocabulary(tmp_path):
    """CLAUDE.md section 5, at the door. An unknown value is REJECTED rather
    than blanked -- blanking it would silently decide that no interim order was
    sought, which is a different statement from the one the advocate made."""
    c = _client(tmp_path)
    mid, ver = _open_matter(c)
    tid = c.get(f"/api/matters/{mid}").json()["threads"][0]["thread_id"]
    r = _state(c, mid, tid, ver, "an urgent injunction please")
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "INVALID_REQUEST"
    assert "interim" in r.json()["detail"]["why"]


def test_the_advocate_is_given_the_interim_test_and_not_the_merits(tmp_path):
    """A GUARD THAT IS RIGHT IN THE KNOWLEDGE PLANE AND NEVER REACHES THE
    ANSWER IS NOT A GUARD (CLAUDE.md section 8). The rule, the limbs and the
    bar have to arrive on a served turn."""
    c = _client(tmp_path)
    mid, ver = _open_matter(c)
    tid = c.get(f"/api/matters/{mid}").json()["threads"][0]["thread_id"]
    assert _state(c, mid, tid, ver, "prohibitory_injunction").status_code == 201

    out = c.post("/api/turn", json={
        "matter_id": mid, "thread_id": tid,
        "message": "Where does the application for interim injunction stand?",
        "today": "2026-09-25"})
    assert out.status_code == 200, out.text
    said = " ".join(e["text"] for e in out.json()["elements"])
    assert "Order XXXIX" in said, said[-1200:]
    assert "not on the strength of the suit" in said
    assert "prima facie case" in said
    assert "balance of convenience" in said
    assert "irreparable injury" in said
    assert "Specific Relief Act, 1963, s.41" in said


def test_the_served_turn_never_reports_a_limb_as_made_out(tmp_path):
    """THE ABSENT-INPUT SHAPE, held on the served path. The advocate must not
    read anything that suggests this product looked at their affidavit."""
    c = _client(tmp_path)
    mid, ver = _open_matter(c)
    tid = c.get(f"/api/matters/{mid}").json()["threads"][0]["thread_id"]
    assert _state(c, mid, tid, ver, "mandatory_injunction").status_code == 201
    out = c.post("/api/turn", json={
        "matter_id": mid, "thread_id": tid,
        "message": "Where does the application stand?", "today": "2026-09-25"})
    said = " ".join(e["text"] for e in out.json()["elements"])
    assert "higher standard than a prima facie case" in said, said[-1200:]
    # THE HONEST SENTENCE IS PRESENT, and it is what makes the silence about
    # the limbs readable rather than invisible.
    assert "which nothing here has seen" in said
    # AND NO LIMB CARRIES A VERDICT. Read off the vocabulary rather than off a
    # list of phrases, so a state added to `LimbState` tomorrow is covered.
    for state in LimbState:
        if state is LimbState.NOT_ASSESSED:
            continue
        for limb in curated.TESTS[InterimRelief.MANDATORY_INJUNCTION].limbs:
            assert f"{limb.name} is {state.value}" not in said
            assert f"{limb.name}: {state.value}" not in said


def _seeded(tmp_path, *, wired: bool):
    """A thread carrying a stated prohibitory injunction, run twice.

    THE A/B IS THE POINT. An unwired test on a matter that states no interim
    relief would pass with the port removed AND with it present, which is a
    test that cannot fail -- exactly the "asserts current behaviour" shape
    CLAUDE.md section 2 names. So the same file is served both ways and the
    difference is what is asserted.
    """
    from nm.core.turn import TurnInput

    from tests.test_turn_contract import build

    engine, store = build(tmp_path)
    if not wired:
        engine._interim_relief = None
    first = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    matter = store.load(first.matter.id)
    (thread,) = matter.threads
    relief = relief_mod.Relief(
        remedy="a decree for a permanent injunction",
        objective="stop the construction on the client's land",
        availability=relief_mod.Availability.AVAILABLE,
        value=relief_mod.Value.SUBSTANTIAL,
        timing=relief_mod.Timing.TIMELY,
        enforceability=relief_mod.Enforceability.ENFORCEABLE,
        interim=InterimRelief.PROHIBITORY_INJUNCTION,
        basis=Basis.STATED, source="the advocate",
        reason="stated by the advocate")
    objective = relief_mod.Objective(
        "stop the construction on the client's land",
        basis=Basis.STATED, source="the advocate")
    store.commit(matter.with_thread(dataclasses.replace(
        thread, reliefs=(relief.as_dict(),), objective=objective.as_dict())),
        expected_version=matter.version)
    out = engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                               thread_id=thread.id,
                               message="Where does the application stand?"))
    return " ".join(e.text for e in out.answer.elements)


def test_the_stated_interim_order_reaches_the_advocate_on_the_engine(tmp_path):
    """The positive half of the A/B below: with the port wired, the same file
    gets the rule and the limbs."""
    said = _seeded(tmp_path, wired=True)
    assert "Order XXXIX" in said, said[-1200:]
    assert "prima facie case" in said


def test_an_unwired_installation_sets_out_no_test_and_claims_no_gap(tmp_path):
    """AN ABSENT PORT IS NOT A FINDING (CLAUDE.md section 9). On the SAME file
    that gets the test above, an installation with no curated table must say
    nothing at all -- not that no test is held for the relief the advocate
    asked about, which reads as a fact about the law rather than about this
    deployment."""
    said = _seeded(tmp_path, wired=False)
    assert "Order XXXIX" not in said, said[-1200:]
    assert "no interim test is held" not in said
    assert "decided on its own test" not in said


def test_a_matter_with_no_interim_order_stated_says_nothing_about_one(tmp_path):
    """THE QUIET CASE. Most matters carry no interim application, and a
    product that announced the injunction test on every turn would bury the
    turns where it matters."""
    from nm.core.turn import TurnInput

    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    said = " ".join(e.text for e in out.answer.elements)
    assert "Order XXXIX" not in said
    assert "no interim relief has been stated" not in said
