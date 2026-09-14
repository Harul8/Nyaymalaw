"""ADVICE AT THE MATURITY IT HAS. BK-50-AC1, BK-96-AC2, BK-96-AC3. P26.

WHAT THIS DEFENDS
-------------------
`Recommendation` was carried in `test_reached_from_production.UNTYPED` for as
long as this product has existed:

    E2. BUILT AS A STRING. `turn._recommend` composes prose; the PRD declares
    a record. B-074 is what an untyped recommendation costs -- nothing could
    ask it what it was based on, so it contradicted the finding printed
    beneath it.

So the defect is not that the sentence was wrong. It is that the sentence was
the ONLY thing there: nothing could ask the recommendation what it rested on,
what would change it, or whether its date was attributed to anything. These
tests are about what the record must be able to answer.

THE FABRICATION THIS REFUSES IS THE SUBTLE ONE. A template with seven slots
invites seven plausible sentences, and a plausible owner beside a plausible
date reads exactly like a checked one. Every field this product cannot fill
stays EMPTY and is reported by `absent()` -- being told "no fallback was
established" is useful; being told an invented fallback is worse than silence.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest
from nm.domain import advice
from nm.domain.brief import ORDER, Section

pytestmark = pytest.mark.class_a


# ================================================== 1. maturity is derived ===

def test_maturity_is_derived_and_cannot_be_handed_in():
    """Nothing accepts a maturity. A value a caller can pass is a value a
    caller can get wrong, and the wrong answer here is *this is settled*."""
    names = advice.maturity_of.__code__.co_varnames[
        :advice.maturity_of.__code__.co_argcount
        + advice.maturity_of.__code__.co_kwonlyargcount]
    assert "maturity" not in names, (
        f"`maturity_of` takes a maturity ({names}); it is then a relabelling "
        f"rather than a derivation")


@pytest.mark.parametrize("kw,expected", [
    ({"has_position": False}, advice.Maturity.NOT_ASSESSED),
    ({"has_position": True}, advice.Maturity.SUPPORTED),
    ({"has_position": True, "inferred_support": True},
     advice.Maturity.PROVISIONAL),
    ({"has_position": True, "unmet_prerequisites": ("the signed contract",)},
     advice.Maturity.PROVISIONAL),
    ({"has_position": True, "controlling_question": "who signed it?"},
     advice.Maturity.BLOCKED),
    ({"has_position": True, "withheld": True}, advice.Maturity.NOT_ASSESSED),
])
def test_maturity_follows_the_actual_prerequisites(kw, expected):
    """BK-96-AC3: *maturity follows actual prerequisites*. Each row is one
    fact about the file, not a mood."""
    assert advice.maturity_of(**kw) is expected


def test_withholding_outranks_everything_else():
    """A withheld turn has no maturity to report. Letting it fall through to
    PROVISIONAL is exactly how a gated answer reaches the ordinary renderer
    looking like ordinary advice."""
    assert advice.maturity_of(
        has_position=True, controlling_question="who signed?",
        withheld=True) is advice.Maturity.NOT_ASSESSED


# ============================================ 2. the record and its absences ==

def test_the_record_names_every_one_of_the_seven_obligations():
    """BK-96-AC2 lists seven. The population comes from the module's own
    mapping, so a field added there is counted here the same day."""
    empty = advice.Recommendation()
    missing = empty.absent()
    assert len(missing) == len(advice.REQUIRED_FIELDS) + len(
        advice.REQUIRED_STEP_FIELDS), missing
    for label in (*advice.REQUIRED_FIELDS.values(),
                  *advice.REQUIRED_STEP_FIELDS.values()):
        assert label in missing, f"{label!r} is not reported absent"


def test_an_unattributed_by_when_is_reported_absent_even_though_it_has_text():
    """A date with no basis is a guess wearing a deadline's clothes. The
    product has already been measured telling an advocate to file "within the
    limitation period" while the period had run."""
    step = advice.NextStep(action="file", owner="the advocate",
                           by_when="2026-10-01")
    assert "on whose authority the by-when rests" in step.absent()

    attributed = advice.NextStep(action="file", owner="the advocate",
                                 by_when="2026-10-01",
                                 by_when_basis="the listed hearing")
    assert attributed.absent() == ()


def test_a_complete_record_reports_nothing_absent():
    """THE POSITIVE CONTROL. A rule that reports everything missing is an
    outage, and it would satisfy every assertion above."""
    full = advice.Recommendation(
        position="sue for the price",
        why_alternatives_lose=("arbitration is slower and costs more",),
        next_step=advice.NextStep(action="issue the suit",
                                  owner="the instructing advocate",
                                  by_when="2026-10-01",
                                  by_when_basis="the computed limitation"),
        fallback="a summary application if the defence is filed late",
        changing_fact="a written acknowledgement of the debt")
    assert full.absent() == ()


def test_the_field_names_are_the_prd_contract_and_not_this_module_s_taste():
    """E2 declares `Recommendation { position, why_alternatives_lose[],
    next_step{action, owner, by_when}, fallback, changing_fact }`.

    Typing it under different names would have left the UNTYPED declaration
    true in substance while the checker went quiet -- which is the naming-drift
    entry that sits beside it in that same list for `TurnRoute`.
    """
    import dataclasses
    have = {f.name for f in dataclasses.fields(advice.Recommendation)}
    for declared in ("position", "why_alternatives_lose", "next_step",
                     "fallback", "changing_fact"):
        assert declared in have, f"E2 declares {declared!r} and the type lacks it"
    step = {f.name for f in dataclasses.fields(advice.NextStep)}
    for declared in ("action", "owner", "by_when"):
        assert declared in step, f"E2's next_step declares {declared!r}"


# ================================== 3. what may not reach the renderer =======

@pytest.mark.parametrize("flag", ["withheld", "stale", "truncated"])
def test_failed_or_withheld_analysis_cannot_enter_the_renderer(flag):
    """BK-96-AC3's last clause. The three are reported separately because they
    need different things: a gate cleared, a re-derivation, or a rerun."""
    full = advice.Recommendation(position="sue for the price")
    refused = advice.refuse_release(full, advice.Maturity.SUPPORTED,
                                    **{flag: True})
    assert refused, f"a {flag} analysis was allowed through"


def test_a_recommendation_with_no_position_is_background_and_is_refused():
    """An answer with no position is background, and background is not the top
    of an advice."""
    refused = advice.refuse_release(advice.Recommendation(),
                                    advice.Maturity.SUPPORTED)
    assert "no position" in refused


def test_a_sound_recommendation_is_released():
    """THE NEGATIVE CONTROL for the refusals above."""
    assert advice.refuse_release(
        advice.Recommendation(position="sue for the price"),
        advice.Maturity.PROVISIONAL) == ""


# ========================================== 4. BK-50-AC1: the answer shape ====

def test_the_answer_leads_with_the_position_and_not_with_background():
    """BK-50-AC1 and BK-96-AC3 meet here. The criterion is explicit that this
    is about *the applicable named sections and ordering promised by the advice
    contract, not an arbitrary minimum heading count* -- so it is asserted on
    `brief.ORDER`, which is the contract, rather than on how many headings
    happen to be rendered."""
    assert ORDER[0] is Section.POSITION, (
        f"the answer opens with {ORDER[0].value}; counsel opens an advice "
        f"looking for the position and the step")
    assert ORDER.index(Section.NEXT) < ORDER.index(Section.BECAUSE), (
        "the working is ordered above the step, so the reader reconstructs "
        "the recommendation instead of being told it")
    assert ORDER[-1] is Section.AUDIT


# ================================= 5. the served turn, BK-96-AC2 integration ==

def test_a_served_turn_records_the_typed_recommendation_on_the_thread():
    """THE RECORD REACHES THE FILE, not just the sentence. BK-96-AC2 asks for
    a PERSISTED and served recommendation, and the whole point of B-074 is
    that a recommendation nothing can interrogate is what went wrong."""
    from nm.core.turn import TurnInput

    from tests import test_slice4_closeout as slice4

    engine, _ = slice4.build(pathlib.Path(tempfile.mkdtemp()))
    out = engine.run(TurnInput(advocate_id="adv", message=slice4.DEFENDING,
                               today=slice4.TODAY))
    record = out.matter.threads[0].recommendation
    assert record, "no recommendation was recorded on the thread"
    assert record["position"], record
    assert record["maturity"] in {m.value for m in advice.Maturity}
    assert record["next_step"]["action"], record


def test_the_served_record_reports_what_it_could_not_establish():
    """AND IT DOES NOT INVENT THEM. On a real turn the product cannot say why
    the alternatives lose, what the fallback is, or what would change the view
    -- so those are ABSENT, by name, rather than filled with plausible prose.

    This is the assertion that would fail first if somebody "completed" the
    template to make the record look finished.
    """
    from nm.core.turn import TurnInput

    from tests import test_slice4_closeout as slice4

    engine, _ = slice4.build(pathlib.Path(tempfile.mkdtemp()))
    out = engine.run(TurnInput(advocate_id="adv", message=slice4.DEFENDING,
                               today=slice4.TODAY))
    record = out.matter.threads[0].recommendation
    absent = record["absent"]
    assert absent, "the record claims every obligation is met on a real turn"
    assert record["why_alternatives_lose"] == [], (
        "the product asserted why alternatives lose; nothing on this turn "
        "compared any")
    assert record["fallback"] == "" and record["changing_fact"] == ""


def test_an_attributed_by_when_names_where_the_date_came_from():
    """Where the register holds a dated deadline the record says so; where it
    does not, the by-when is empty and the reason travels as a reservation."""
    from nm.core.turn import TurnInput

    from tests import test_slice4_closeout as slice4

    engine, _ = slice4.build(pathlib.Path(tempfile.mkdtemp()))
    out = engine.run(TurnInput(advocate_id="adv", message=slice4.DEFENDING,
                               today=slice4.TODAY))
    step = out.matter.threads[0].recommendation["next_step"]
    if step["by_when"]:
        assert step["by_when_basis"], (
            "a by-when reached the record with nothing to attribute it to")
    else:
        assert out.matter.threads[0].recommendation["reservations"], (
            "no date and no reason for its absence is the silent third state")
