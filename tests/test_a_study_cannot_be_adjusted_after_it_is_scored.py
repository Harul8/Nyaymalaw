"""A STUDY CANNOT BE ADJUSTED AFTER IT IS SCORED. BK-66-AC1/AC2/AC3. P34.

WHAT THESE DEFEND
-------------------
`docs/blueprint/evaluations.json` already declares REVIEW-USABILITY for
BK-66-AC3, with its reviewer role, required inputs, tasks, failure conditions
and required output fields. It declares them in prose and nothing runs them --
which is the failure this repository opens by describing: *a hundred good rules
with no runner. A rule you cannot run is not a requirement.*

This is the runner, and it decides exactly one thing: whether a study is
ADMISSIBLE. Whether the product is actually comprehensible is what a
representative advocate is for, and no test in this file claims otherwise.

    NO OBSERVATION IN THIS SUITE IS A REAL ONE. Every `Observation` below is a
    fixture proving what the machinery accepts and refuses. BK-66-AC1's
    `model_eval` and `counsel_review` and BK-66-AC2's and AC3's
    `counsel_review` are NOT RUN and are not closed by anything here.

THE SEVEN REFUSALS ARE SEVEN TESTS, and each is a different way to produce a
favourable number from an unfavourable run.
"""
from __future__ import annotations

import pytest

from nm.domain.review import (
    INVALIDATED_BY,
    Disagreement,
    Freeze,
    Observation,
    Observer,
    Severity,
    Stratum,
    Study,
    invalidated,
    projection,
    refuse_average,
    refuse_conclusion,
    supersede,
)

pytestmark = pytest.mark.class_a

#: BK-66-AC1's list, verbatim: *what NM understood, used, assumed, changed,
#: still needs and will do next* -- plus the four control tasks BK-66-AC2 adds.
TASKS: tuple[str, ...] = (
    "say what NM understood",
    "say what material it used",
    "say what it assumed",
    "say what is disputed or unknown",
    "say what changed",
    "say what has become stale",
    "say what needs your decision",
    "say what it recommends next",
    "correct something",
    "pause and come back",
    "reach the source behind a statement",
)


def _freeze(**kw) -> Freeze:
    base = dict(
        protocol_id="REVIEW-USABILITY",
        tasks=TASKS,
        strata=("practising advocate, 2-10 years",
                "practising advocate, 10+ years"),
        rubric=("unassisted success", "time to answer", "retyping"),
        thresholds={"unassisted_success": 0.8},
        frozen_at="2026-09-14T09:00:00Z", frozen_by="the study owner")
    base.update(kw)
    return Freeze(**base)


def _observation(task: str, **kw) -> Observation:
    base = dict(task=task, by=Observer.ADVOCATE,
                stratum=Stratum.REPRESENTATIVE, succeeded=True)
    base.update(kw)
    return Observation(**base)


def _study(**kw) -> Study:
    freeze = kw.pop("freeze", None) or _freeze()
    base = dict(
        study_id="st_1", protocol_id="REVIEW-USABILITY", freeze=freeze,
        observations=tuple(_observation(t) for t in TASKS),
        reviewers=({"identity": "A. Reviewer", "qualification": "advocate",
                    "evidence": "enrolment 1234/2011",
                    "conflict_declaration": "none"},),
        product_identity="tree 76587a28",
        scored_at="2026-09-14T17:00:00Z",
        scoring_manifest=freeze.manifest)
    base.update(kw)
    return Study(**base)


# ==================== 1. the study that IS admissible =======================

def test_a_frozen_observed_attributed_study_is_admissible():
    """THE POSITIVE CONTROL. A machine that refused everything would be
    switched off, and the seven refusals below would go with it."""
    assert refuse_conclusion(_study()) == ()
    assert projection(_study())["admissible"] is True


def test_the_frozen_tasks_are_the_criterion_s_own_list():
    """BK-66-AC1 names what an advocate must be able to identify. The frozen
    task list is that list, so a study cannot quietly measure something
    easier."""
    joined = " | ".join(TASKS)
    for needed in ("understood", "used", "assumed", "changed", "stale",
                   "decision", "recommends", "correct", "pause", "source"):
        assert needed in joined, needed


# ======================= 2. the seven refusals ==============================

def test_an_empty_population_is_not_a_high_score():
    got = refuse_conclusion(_study(observations=()))
    assert any("average of no tasks" in why for why in got)


def test_a_task_observed_that_was_not_frozen_is_a_different_question():
    got = refuse_conclusion(_study(observations=(
        *(_observation(t) for t in TASKS),
        _observation("something easier nobody froze"))))
    assert any("not one of the frozen tasks" in why for why in got)


def test_moving_the_threshold_after_scoring_is_visible():
    """THE BAR DRAWN ROUND THE RESULT. The manifest hashes tasks, strata,
    rubric and thresholds together, and the study records which manifest it
    was scored against."""
    study = _study()
    moved = _study(freeze=_freeze(thresholds={"unassisted_success": 0.2}),
                   scoring_manifest=study.freeze.manifest)
    got = refuse_conclusion(moved)
    assert any("changed after scoring began" in why for why in got)


def test_a_study_that_does_not_say_what_it_scored_against_is_refused():
    got = refuse_conclusion(_study(scoring_manifest=""))
    assert any("which frozen manifest was scored against" in why
               for why in got)


def test_an_unresolved_disagreement_blocks_the_conclusion():
    """*records material disagreement*, and `evaluations.json` adds:
    adjudicate without deleting the original labels."""
    got = refuse_conclusion(_study(disagreements=(
        Disagreement(task="say what changed", between=("A", "B"),
                     about="whether the stale note was findable"),)))
    assert any("unresolved and no adjudication" in why for why in got)


def test_an_adjudicated_disagreement_does_not_block_and_is_kept():
    study = _study(disagreements=(
        Disagreement(task="say what changed", between=("A", "B"),
                     about="whether the stale note was findable",
                     adjudicated_by="C", outcome="findable, but not named"),))
    assert refuse_conclusion(study) == ()
    assert study.disagreements[0].about  # the original label survives


def test_a_model_judge_alone_cannot_stand_in_for_an_advocate():
    """THE CHEAPEST SUBSTITUTION AVAILABLE, and the one that looks identical
    in a report."""
    got = refuse_conclusion(_study(observations=tuple(
        _observation(t, by=Observer.MODEL_JUDGE) for t in TASKS)))
    assert any("is useful and is not an advocate" in why for why in got)


def test_a_demo_fixture_alone_is_not_a_representative_user():
    got = refuse_conclusion(_study(observations=tuple(
        _observation(t, stratum=Stratum.DEMO_FIXTURE) for t in TASKS)))
    assert any("not a representative user" in why for why in got)


def test_an_observation_that_does_not_say_who_produced_it_is_refused():
    got = refuse_conclusion(_study(observations=(
        *(_observation(t) for t in TASKS[:-1]),
        _observation(TASKS[-1], by=Observer.NOT_RECORDED))))
    assert any("do not record who produced them" in why for why in got)


def test_a_critical_failure_blocks_however_good_the_rest_was():
    """BK-66-AC3's negative control: *report an average without failed
    tasks*. A critical failure is not a low score on a scale."""
    study = _study(observations=(
        *(_observation(t) for t in TASKS[:-1]),
        _observation(TASKS[-1], succeeded=False, severity=Severity.CRITICAL,
                     note="the advocate acted on a stale conclusion")))
    assert any("blocks regardless of the average" in why
               for why in refuse_conclusion(study))
    assert "critical failure is not a low score" in refuse_average(study)


# ================== 3. the freeze, and what it must contain =================

@pytest.mark.parametrize("missing,expected", [
    ("tasks", "nothing to have measured"),
    ("strata", "who or what this was meant to represent"),
    ("rubric", "what counts as success was decided somewhere else"),
    ("thresholds", "the bar can be drawn round"),
])
def test_a_freeze_missing_any_of_its_four_parts_is_named(missing, expected):
    empty = {} if missing == "thresholds" else ()
    got = _freeze(**{missing: empty}).problems()
    assert any(expected in why for why in got), got


def test_a_freeze_nobody_signed_is_a_claim_rather_than_a_fact():
    got = _freeze(frozen_by="").problems()
    assert any("'before scoring' is a claim" in why for why in got)


def test_the_manifest_moves_when_any_of_the_four_moves():
    base = _freeze()
    for changed in (dict(tasks=TASKS[:-1]), dict(strata=("x",)),
                    dict(rubric=("y",)), dict(thresholds={"a": 1})):
        assert _freeze(**changed).manifest != base.manifest


def test_the_manifest_does_not_move_on_a_re_freeze_of_the_same_thing():
    """A POSITIVE CONTROL ON THE HASH. One that moved every time would make
    every study look tampered with, and the real signal would be lost."""
    assert _freeze().manifest == _freeze().manifest


# ============= 4. the rate, and the number that must not be zero ============

def test_a_study_with_no_human_observations_has_no_rate_rather_than_zero():
    """Section 9. Zero would be arithmetically indistinguishable from
    everybody having failed."""
    study = _study(observations=tuple(
        _observation(t, by=Observer.MODEL_JUDGE) for t in TASKS))
    assert study.success_rate() is None
    assert projection(study)["success_rate"] is None


def test_assisted_completion_is_not_an_unassisted_success():
    """A task somebody had to be helped through is not a task the product
    supported."""
    study = _study(observations=(
        *(_observation(t) for t in TASKS[:-1]),
        _observation(TASKS[-1], assisted=True)))
    assert study.success_rate() is not None
    assert study.success_rate() < 1.0


def test_the_projection_carries_the_blockers_and_says_what_it_is():
    shown = projection(_study(observations=()))
    assert shown["admissible"] is False
    assert shown["blockers"]
    assert "not a review" in shown["said"]


def test_retyping_is_measured_rather_than_asserted():
    """BK-66-AC2's *without compulsory repetitive typing*. A field that is
    counted can fail; a sentence in a report cannot."""
    assert Observation(task="t", retyped=4).retyped == 4


# =================== 5. invalidation, and superseding =======================

def test_every_classified_change_invalidates():
    for what in INVALIDATED_BY:
        assert invalidated(_study(), changed=(what,))


def test_an_unclassified_change_is_not_assumed_harmless():
    """A change nobody classified is a change nobody assessed."""
    got = invalidated(_study(), changed=("we swapped the retrieval index",))
    assert got and "not a classified kind of change" in got[0]


def test_no_change_invalidates_nothing():
    assert invalidated(_study(), changed=()) == ()


def test_superseding_keeps_the_earlier_review():
    """*Superseded reviews remain historical evidence.* A deleted review makes
    the work it approved look unreviewed."""
    first = _study()
    later = supersede(first, by="st_2")
    assert later.superseded_by == "st_2"
    assert later.observations == first.observations
    assert projection(later)["superseded_by"] == "st_2"


def test_a_superseding_review_names_itself():
    with pytest.raises(ValueError, match="names itself"):
        supersede(_study(), by="")


# ============ 6. the protocol this runs is the declared one ================

def test_the_protocol_id_is_one_the_blueprint_declares():
    """ONE OWNER. `docs/blueprint/evaluations.json` declares the protocols;
    a study naming one this repository never declared is a study of a
    procedure nobody wrote down."""
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    declared = {row["id"] for row in json.loads(
        (root / "docs" / "blueprint" / "evaluations.json").read_text(
            encoding="utf-8"))["manual_review_protocols"]}
    assert "REVIEW-USABILITY" in declared
    assert _study().protocol_id in declared


def test_the_usability_protocol_owns_the_criterion_this_packet_closes():
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    rows = json.loads((root / "docs" / "blueprint" / "evaluations.json")
                      .read_text(encoding="utf-8"))["manual_review_protocols"]
    usability = next(r for r in rows if r["id"] == "REVIEW-USABILITY")
    assert "BK-66-AC3" in usability["owner_criteria"]
    # AND ITS APPROVALS AND EVIDENCE ARE STILL EMPTY, which is the honest
    # state: no representative advocate study has been run.
    assert usability["approvals"] == []
    assert usability["evidence"] == []


# ======= 7. the control on the browser suite's phrase list ==================

def test_a_screen_saying_none_of_these_is_caught():
    """A POSITIVE CONTROL ON `MUST_BE_SAYABLE`, which lives in the browser
    suite and is therefore not exercised by Class-A.

    The list was written twice. The first version came from the criterion's
    own vocabulary, reported two categories missing that were on the screen in
    the product's better words, and would have been "fixed" by widening it
    until it passed -- which is how a check stops being able to fail. This is
    what stops the second version going the same way: a page saying none of
    these must still be reported as saying none of them.
    """
    from tests.test_the_journey_of_comprehension import MUST_BE_SAYABLE

    empty = "an entirely blank page with no words on it at all"
    missing = [name for name, phrases in MUST_BE_SAYABLE
               if not any(p in empty for p in phrases)]
    assert len(missing) == len(MUST_BE_SAYABLE), missing

    # AND EVERY CATEGORY IS SATISFIABLE. A phrase nothing could ever match
    # would make its category permanently missing, which reads as a product
    # defect and is a typing error.
    for name, phrases in MUST_BE_SAYABLE:
        assert phrases, name
        for phrase in phrases:
            assert phrase == phrase.lower(), (name, phrase)
