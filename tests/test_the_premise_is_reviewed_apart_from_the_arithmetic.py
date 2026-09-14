"""CORRECT ARITHMETIC ON AN UNSUPPORTED PREMISE IS NOT A PARTIAL PASS.
BK-67-AC1 to AC4, BK-91-AC4. P35.

WHAT THESE DEFEND
-------------------
BK-67-AC3's negative control is the sharpest sentence in the backlog: *supply
correct date arithmetic with an unsupported accrual rule, or treat a historical
court cohort label as proof of binding status* -> *the legal-premise gate fails
even though the deterministic calculation and source counts pass.*

The calculation passing is the most convincing possible evidence for the wrong
thing. So an arithmetic verdict names the premise it assumed, and where that
premise is unsupported the calculation is not a verdict at all -- not a pass at
lower confidence, which is the reading that puts the wrong date in a cause
list.

WHAT THIS SUITE DOES NOT DO
-----------------------------
It does not review anything, and nothing in it is a legal opinion. Every
`Verdict` below is a fixture proving what the machinery accepts and refuses.
BK-67-AC1 to AC4 and BK-91-AC4 all require `counsel_review` and `model_eval`;
both are NOT RUN, neither is closed by this file, and no test here asserts
otherwise.
"""
from __future__ import annotations

import pytest
from nm.domain.legal_review import (
    Approval,
    Arithmetic,
    Comparison,
    LegalReviewRecord,
    Premise,
    PremiseKind,
    Verdict,
    critical,
    projection,
    refuse_approval,
    withdraw,
)
from nm.domain.review import (
    Freeze,
    Observation,
    Observer,
    Severity,
    Stratum,
    Study,
)

pytestmark = pytest.mark.class_a

TASKS = ("identify the applicable law", "assess the accrual",
         "check the binding authority")


def _study(**kw) -> Study:
    freeze = Freeze(
        protocol_id="REVIEW-LEGAL", tasks=TASKS,
        strata=("recovery suits", "cheque dishonour"),
        rubric=("outcome support", "adverse case", "source treatment"),
        thresholds={"critical_failures": 0},
        frozen_at="2026-09-14T09:00:00Z", frozen_by="the review owner")
    base = dict(
        study_id="lr_study_1", protocol_id="REVIEW-LEGAL", freeze=freeze,
        observations=tuple(
            Observation(task=t, by=Observer.QUALIFIED_REVIEWER,
                        stratum=Stratum.REPRESENTATIVE, succeeded=True)
            for t in TASKS),
        reviewers=({"identity": "A. Advocate",
                    "qualification": "practising advocate, Telangana",
                    "evidence": "enrolment AP/1234/2011",
                    "conflict_declaration": "none"},),
        product_identity="tree 76587a28",
        scored_at="2026-09-14T17:00:00Z", scoring_manifest=freeze.manifest)
    base.update(kw)
    return Study(**base)


def _premise(kind=PremiseKind.ACCRUAL, **kw) -> Premise:
    base = dict(
        kind=kind, statement="time runs from the date of dishonour",
        source_id="ni_act", locator="s.138 proviso (c)",
        source_version="as amended to 2018", verdict=Verdict.SOUND,
        reviewed_by="A. Advocate")
    if kind is PremiseKind.BINDING_AUTHORITY:
        base["binding_basis"] = ("a Division Bench of the High Court for the "
                                 "State of Telangana, not since doubted")
    base.update(kw)
    return Premise(**base)


def _record(**kw) -> LegalReviewRecord:
    base = dict(
        review_id="lr_1", study=_study(),
        premises=(_premise(), _premise(kind=PremiseKind.APPLICABLE_LAW),
                  _premise(kind=PremiseKind.BINDING_AUTHORITY)),
        arithmetic=(Arithmetic(what="the limitation date",
                               assessed_on=PremiseKind.ACCRUAL,
                               verdict=Verdict.SOUND,
                               reviewed_by="A. Advocate"),))
    base.update(kw)
    return LegalReviewRecord(**base)


# ================ 1. the premise, separately from the sum ===================

def test_a_complete_review_approves():
    """THE POSITIVE CONTROL."""
    assert refuse_approval(_record()) == ()
    assert projection(_record())["approves"] is True


def test_correct_arithmetic_on_an_unsupported_premise_is_not_a_verdict():
    """BK-67-AC3'S NEGATIVE CONTROL, verbatim. The calculation is right and
    answers nothing, and reporting it as passing is how the wrong date reaches
    a cause list."""
    record = _record(premises=(
        _premise(verdict=Verdict.UNSUPPORTED),
        _premise(kind=PremiseKind.APPLICABLE_LAW),
        _premise(kind=PremiseKind.BINDING_AUTHORITY)))
    got = refuse_approval(record)
    assert any("is not a verdict about the answer" in why for why in got)
    shown = projection(record)
    assert shown["arithmetic"][0]["verdict"] == "sound"
    assert shown["arithmetic"][0]["stands"] is False


def test_an_arithmetic_verdict_on_a_premise_nobody_recorded_is_refused():
    record = _record(premises=(_premise(kind=PremiseKind.APPLICABLE_LAW),))
    assert any("this review does not record" in why
               for why in refuse_approval(record))


def test_a_court_name_is_not_a_reason_an_authority_binds():
    """BK-67-AC3's other control: *treat a historical court cohort label as
    proof of binding status*."""
    record = _record(premises=(
        _premise(),
        _premise(kind=PremiseKind.APPLICABLE_LAW),
        _premise(kind=PremiseKind.BINDING_AUTHORITY, binding_basis="")))
    assert any("A court's name is not a basis" in why
               for why in refuse_approval(record))


def test_a_premise_that_does_not_name_its_source_version_is_refused():
    """A premise resting on "the Act" rests on whichever version the reviewer
    had, and an amendment since is invisible."""
    record = _record(premises=(_premise(source_version=""),))
    assert any("which version of its source" in why
               for why in refuse_approval(record))


def test_a_premise_nobody_assessed_is_not_a_sound_one():
    record = _record(premises=(_premise(verdict=Verdict.NOT_ASSESSED),))
    assert any("nobody assessed" in why for why in refuse_approval(record))
    assert Verdict.not_established() is Verdict.NOT_ASSESSED
    assert Verdict.NOT_ASSESSED.supports_reliance is False


def test_the_five_governing_premises_are_five():
    """They fail independently and are found by different work."""
    assert {p.value for p in PremiseKind} == {
        "applicable_law", "accrual", "jurisdiction", "binding_authority",
        "role_restriction"}


def test_a_review_with_no_premise_at_all_approves_nothing():
    assert any("no governing legal premise was reviewed" in why
               for why in refuse_approval(_record(premises=(),
                                                  arithmetic=())))


# ============= 2. critical failures, and the average that hides them ========

def test_a_critical_legal_failure_blocks_however_high_the_average():
    """BK-67-AC2'S NEGATIVE CONTROL: *average away invented authority,
    material confidentiality failure or unsupported decisive advice*."""
    record = _record(critical_failures=(
        "an authority was cited that does not exist",))
    got = refuse_approval(record)
    assert any("blocks conformance regardless of the average" in why
               for why in got)
    assert critical(record)


def test_a_critical_failure_recorded_on_a_task_counts_too():
    """TWO PLACES ONE CAN BE RECORDED, and `critical` reads both. A reviewer
    can find one inside a matter they otherwise scored well."""
    study = _study(observations=(
        Observation(task=TASKS[0], by=Observer.QUALIFIED_REVIEWER,
                    stratum=Stratum.REPRESENTATIVE, succeeded=False,
                    severity=Severity.CRITICAL,
                    note="confidential material from another matter appeared"),
        *(Observation(task=t, by=Observer.QUALIFIED_REVIEWER,
                      stratum=Stratum.REPRESENTATIVE, succeeded=True)
          for t in TASKS[1:])))
    assert critical(_record(study=study))


def test_an_inadmissible_study_cannot_confer_approval():
    """The seven refusals are REUSED rather than restated -- a second copy of
    the thing most likely to be relaxed is the thing that gets relaxed."""
    assert any("average of no tasks" in why
               for why in refuse_approval(_record(study=_study(
                   observations=()))))


def test_a_reviewer_with_no_evidenced_qualification_is_not_a_reviewer():
    record = _record(study=_study(reviewers=(
        {"identity": "Someone", "qualification": "", "evidence": "",
         "conflict_declaration": "none"},)))
    assert any("evidenced qualification" in why
               for why in refuse_approval(record))


def test_this_product_cannot_supply_the_reviewer():
    """Stated in the refusal itself, so a reader of a blocked review sees
    what is actually missing."""
    record = _record(study=_study(reviewers=()))
    assert any("this product cannot supply one" in why
               for why in refuse_approval(record))


# ================= 3. approval is scoped and does not travel ================

def _approval(**kw) -> Approval:
    base = dict(
        approval_id="ap_1", covers=("cheque dishonour",),
        corpus_identity="corpus-7", model_identity="model-3",
        prompt_identity="prompt-11", product_identity="tree 76587a28",
        approved_by="A. Advocate", approved_at="2026-09-14",
        valid_until="2027-03-14")
    base.update(kw)
    return Approval(**base)


def _current(approval, **kw):
    args = dict(covering="cheque dishonour", corpus="corpus-7",
                model="model-3", prompt="prompt-11",
                product="tree 76587a28", today="2026-09-14")
    args.update(kw)
    return approval.still_current(**args)


def test_an_approval_covers_what_it_says_and_nothing_else():
    assert _current(_approval()) == ""
    assert "not among the matter families" in _current(
        _approval(), covering="land acquisition")


@pytest.mark.parametrize("field,value", [
    ("corpus", "corpus-8"), ("model", "model-4"), ("prompt", "prompt-12"),
    ("product", "tree deadbeef"),
])
def test_approval_is_not_inherited_across_a_changed_configuration(field, value):
    """BK-67-AC4, and the model case is the one that gets assumed: a model
    that scores better on average can fail differently on the cases that
    matter."""
    why = _current(_approval(), **{field: value})
    assert why and "not inherited across it" in why


def test_an_expired_approval_is_not_current():
    assert "ran out on" in _current(_approval(), today="2027-04-01")


def test_a_withdrawn_approval_says_so_first():
    withdrawn = withdraw(_approval(), at="2026-10-01",
                         because="the accrual premise was overruled")
    assert "was withdrawn" in _current(withdrawn)
    assert "overruled" in " ".join(withdrawn.reservations)


def test_withdrawing_twice_keeps_the_first_record():
    once = withdraw(_approval(), at="2026-10-01", because="a")
    assert withdraw(once, at="2026-11-01", because="b").withdrawn_at == "2026-10-01"


def test_a_withdrawal_records_when_and_why():
    with pytest.raises(ValueError, match="when and why"):
        withdraw(_approval(), at="2026-10-01", because="")


def test_reservations_travel_with_the_projection():
    """BK-67-AC1 asks for material reservations kept VISIBLE. A reservation
    filed behind a green verdict is one nobody reads."""
    record = _record(approval=_approval(
        reservations=("the binding point was not argued below",)))
    assert "not argued below" in " ".join(projection(record)["reservations"])


# ============ 4. BK-91-AC4 -- the comparison, and its three cheats ==========

def _comparison(**kw) -> Comparison:
    base = dict(
        families=("cheque dishonour", "recovery"),
        planned_families=("cheque dishonour", "recovery"),
        adaptive_families=("cheque dishonour", "recovery"),
        planned_spend={"cost_usd": 1.0, "tokens": 100, "elapsed_ms": 900},
        adaptive_spend={"cost_usd": 0.8, "tokens": 90, "elapsed_ms": 700},
        runs_each=3, judged_by="B. Advocate", judged_model="judge-1",
        tested_model="model-3")
    base.update(kw)
    return Comparison(**base)


def test_a_matched_repeated_independently_judged_comparison_stands():
    assert _comparison().problems() == ()
    assert _comparison().refuses_improvement_claim() == ""


def test_omitting_a_difficult_family_from_one_arm_is_refused():
    """*omit difficult matter families*, which is the cheat that costs
    nothing and changes everything."""
    got = _comparison(adaptive_families=("cheque dishonour",)).problems()
    assert any("did not run the same families" in why for why in got)


def test_the_tested_model_cannot_grade_itself():
    """*grade the tested model with itself* -- a comparison of a model with
    its own opinion of itself."""
    got = _comparison(judged_model="model-3").problems()
    assert any("its own opinion of itself" in why for why in got)


def test_one_run_each_cannot_separate_an_improvement_from_a_difference():
    got = _comparison(runs_each=1).problems()
    assert any("difference between two runs" in why for why in got)


def test_a_spend_recorded_for_only_one_arm_is_refused():
    """*present a larger spend as proof of architectural improvement*: if the
    spend is not recorded for both, a bigger one cannot be told from a better
    result."""
    got = _comparison(adaptive_spend={"cost_usd": 0.8}).problems()
    assert any("larger spend cannot be told" in why for why in got)


def test_an_unjudged_comparison_supports_no_claim():
    why = _comparison(judged_by="").refuses_improvement_claim()
    assert "cannot support an improvement claim" in why


def test_the_projection_says_what_a_review_record_is():
    shown = projection(_record())
    assert "never one this product produced" in shown["said"]
