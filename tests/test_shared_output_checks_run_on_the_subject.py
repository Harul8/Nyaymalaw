"""The eighteen output and six boundary checks must inspect real typed subjects."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.advise.answer_contracts import Answer, Element, ElementKind, Mode, Route
from nm.legal_brain.verify import consistency, duty, grounding
from nm.legal_brain.retrieve.coverage_contracts import CoveragePosition, CoverageState
from nm.legal_brain.retrieve.evidence_port import (
    Binding,
    Coverage,
    EvidenceNeed,
    EvidenceResult,
    ParaKind,
    SourceKind,
)
from nm.legal_brain.verify.output_checks import (
    BoundarySubjects,
    CheckReceipt,
    OutputSubjects,
    ReadPopulation,
    admission_policy,
    competence_screen,
    duty_check,
    measured_coverage,
    observe_reads,
    retrieval_failure,
    run_boundary_checks,
    run_output_checks,
)
from nm.open_matter import screens
from nm.shared import authority_contracts as authority
from nm.shared.gates_contracts import Response, Scope
from nm.work_the_file import cascade, dependency
from tests.test_independent_claim_verifier import finding, package, verify

pytestmark = pytest.mark.class_a

OUTPUT_IDS = {
    "G-GROUND",
    "G-QUOTE",
    "G-ATTRIB",
    "G-INFORCE",
    "G-BINDING",
    "G-DATE",
    "G-CONSISTENT",
    "G-CONSERVE",
    "G-CASCADE",
    "G-CURRENCY",
    "G-STALE",
    "G-NOTHELD",
    "G-HELDNOTFOUND",
    "G-NOTASSESSED",
    "G-READ",
    "G-MODEL",
    "G-COVERAGE",
    "G-COMPETENCE",
}
BOUNDARY_IDS = {
    "G-EMERGENCY",
    "G-CONFLICT",
    "G-SCOPE",
    "G-CAPACITY",
    "G-DUTY",
    "G-UNSCREENED",
}


def answer(subject, *, extra=(), refs=None):
    return Answer(
        Route.MATTER,
        Mode.ASSESSMENT,
        "Assess the submitted claim",
        (
            Element(
                ElementKind.FINDING,
                subject.claim,
                refs=refs
                if refs is not None
                else tuple(span.finding.locator for span in subject.spans),
            ),
            *extra,
        ),
    )


def captured_output():
    subject = package()
    record = verify(subject)
    source = subject.spans[0].finding
    derived = (cascade.Derived("benefit", "not established", ("fact_1",)),)
    ledger = dependency.Ledger(
        tracked=(dependency.Tracked(dependency.InputKind.FACT, "fact_1", 1),),
        nodes=(
            dependency.Node(
                "benefit",
                "not established",
                (dependency.Rest(dependency.InputKind.FACT, "fact_1", 1),),
            ),
        ),
    )
    coverage = CoveragePosition(CoverageState.MET, "Recorded jurisdiction", "Measured coverage")
    return OutputSubjects(
        answer=answer(subject),
        relied_on=(source,),
        retrieved=(source,),
        evidence_needs=(EvidenceNeed("Read the recorded rule", date(2026, 1, 1)),),
        consistency_verdict=consistency.Verdict(),
        previous_derived=derived,
        derived=derived,
        ledger=ledger,
        dependency_names=("benefit",),
        expected_version=1,
        observed_version=1,
        retrieval_results=(EvidenceResult(Coverage.ANSWERED, (source,)),),
        empty_reads=ReadPopulation(()),
        refused_reads=ReadPopulation(()),
        coverage=coverage,
        competence=screens.Screen(
            screens.ScreenKind.COMPETENCE,
            screens.ScreenState.CLEAR,
            detail="Measured jurisdiction coverage",
        ),
        independent_packages=(subject,),
        independent_records=(record,),
    )


def receipts(subject):
    return {row.gate_id: row for row in run_output_checks(subject)}


def boundaries(**updates):
    fields = dict(
        screens=tuple(
            screens.Screen(
                kind,
                screens.ScreenState.CLEAR,
                detail="Actual clear screen",
                covers=frozenset({"client", "opponent"}),
            )
            for kind in screens.ScreenKind
        ),
        parties=frozenset({"client", "opponent"}),
        duty=duty.Refusal(duty.Ground.CLEAR),
        authority=authority.permits("advocate", authority.ActingAs.ADVISING, authority.Act.ADVISE),
    )
    fields.update(updates)
    return BoundarySubjects(**fields)


def boundary_receipts(subject):
    return {row.gate_id: row for row in run_boundary_checks(subject)}


def test_empty_subjects_are_eighteen_named_non_assessments_never_a_clean_population():
    actual = receipts(OutputSubjects())
    assert set(actual) == OUTPUT_IDS and len(actual) == 18
    assert all(row.assessed is None and row.reason for row in actual.values())


def test_each_output_owner_checks_actual_captured_positive_inputs():
    subject = captured_output()
    actual = receipts(subject)
    assert set(actual) == OUTPUT_IDS and all(row.assessed is True for row in actual.values())
    assert subject.relied_on[0].supports is None
    assert actual["G-GROUND"].response is Response.WITHHOLD
    assert actual["G-NOTHELD"].scope is Scope.NEED


@pytest.mark.parametrize(
    "field, ids",
    [
        ("answer", {"G-GROUND", "G-QUOTE", "G-ATTRIB", "G-INFORCE", "G-BINDING"}),
        ("relied_on", {"G-GROUND", "G-QUOTE", "G-ATTRIB", "G-INFORCE", "G-BINDING"}),
        ("retrieved", {"G-GROUND", "G-QUOTE", "G-ATTRIB", "G-INFORCE", "G-BINDING"}),
        ("evidence_needs", {"G-DATE"}),
        ("consistency_verdict", {"G-CONSISTENT"}),
        ("previous_derived", {"G-CONSERVE", "G-CASCADE"}),
        ("derived", {"G-CONSERVE", "G-CASCADE"}),
        ("ledger", {"G-CURRENCY"}),
        ("dependency_names", {"G-CURRENCY"}),
        ("expected_version", {"G-STALE"}),
        ("observed_version", {"G-STALE"}),
        ("retrieval_results", {"G-NOTHELD", "G-HELDNOTFOUND", "G-NOTASSESSED"}),
        ("empty_reads", {"G-READ"}),
        ("refused_reads", {"G-MODEL"}),
        ("coverage", {"G-COVERAGE"}),
        ("competence", {"G-COMPETENCE"}),
    ],
)
def test_removing_each_real_input_cannot_leave_that_check_passed(field, ids):
    actual = receipts(replace(captured_output(), **{field: None}))
    assert all(actual[id].assessed is None for id in ids)


@pytest.mark.parametrize(
    "extra",
    [
        Element(ElementKind.FINDING, "An unchecked further inference."),
        Element(ElementKind.GROUND, "An unchecked further inference.", disclosure=True),
        Element(ElementKind.QUESTION, "The claim is certainly established, isn't it?"),
    ],
)
def test_independent_receipts_do_not_whitelist_extra_visible_or_mislabelled_text(extra):
    subject = captured_output()
    changed = replace(subject, answer=answer(subject.independent_packages[0], extra=(extra,)))
    assert receipts(changed)["G-GROUND"].assessed is not True


def test_receipts_are_exact_to_claim_source_window_and_captured_source_not_just_locator():
    subject = captured_output()
    pkg = subject.independent_packages[0]
    for changed in (
        replace(pkg, claim="A different claim using the same source."),
        replace(pkg, spans=(replace(pkg.spans[0], end=pkg.spans[0].end - 1),)),
    ):
        actual = replace(subject, answer=answer(changed), independent_packages=(changed,))
        assert receipts(actual)["G-GROUND"].assessed is not True
    altered = replace(pkg.spans[0].finding, span="A new version of this same source.")
    assert receipts(replace(subject, retrieved=(altered,)))["G-GROUND"].assessed is not True


def test_an_extra_reference_cannot_borrow_a_verified_claims_support():
    subject = captured_output()
    alternate = finding(locator="other:source")
    changed = replace(
        subject,
        retrieved=(*subject.retrieved, alternate),
        answer=answer(
            subject.independent_packages[0], refs=(subject.relied_on[0].locator, alternate.locator)
        ),
    )
    assert receipts(changed)["G-GROUND"].assessed is not True


def test_the_old_grounding_default_still_refuses_a_semantically_unassessed_candidate():
    subject = captured_output()
    report = grounding.verify(subject.answer, subject.relied_on, subject.retrieved)
    assert report.withholding and subject.relied_on[0].supports is None
    assert (
        receipts(replace(subject, independent_packages=(), independent_records=()))[
            "G-GROUND"
        ].assessed
        is None
    )


def test_known_negative_support_is_not_replaced_by_an_independent_positive_record():
    subject = captured_output()
    unsupported = replace(subject.relied_on[0], supports=False)
    changed = replace(subject, relied_on=(unsupported,), retrieved=(unsupported,))
    assert receipts(changed)["G-GROUND"].assessed is False


def test_previously_supported_premises_do_not_certify_extra_final_inference():
    subject = captured_output()
    source = replace(subject.relied_on[0], supports=True)
    proposed = replace(subject.independent_packages[0], spans=(replace(
        subject.independent_packages[0].spans[0], finding=source),))
    recorded = verify(proposed)
    changed = replace(subject, relied_on=(source,), retrieved=(source,),
                      independent_packages=(proposed,), independent_records=(recorded,),
                      answer=answer(proposed, extra=(Element(
                          ElementKind.FINDING, "An additional unverified final inference."),)))
    assert receipts(changed)["G-GROUND"].assessed is False


def test_source_in_force_and_binding_checks_do_not_hide_behind_semantic_unknown():
    subject = captured_output()
    expired = replace(subject.relied_on[0], valid_to=date(2020, 1, 1))
    assert (
        receipts(replace(subject, relied_on=(expired,), retrieved=(expired,)))["G-INFORCE"].assessed
        is False
    )
    undated = replace(subject.relied_on[0], governing_date=None)
    assert (
        receipts(replace(subject, relied_on=(undated,), retrieved=(undated,)))["G-INFORCE"].assessed
        is None
    )
    unbound = replace(
        subject.relied_on[0],
        source_kind=SourceKind.AUTHORITY,
        para_kind=ParaKind.ATTRIBUTABLE,
        binding=Binding.NOT_ASSESSED,
    )
    assert (
        receipts(replace(subject, relied_on=(unbound,), retrieved=(unbound,)))["G-BINDING"].assessed
        is None
    )


@pytest.mark.parametrize(
    "coverage, id",
    [
        (Coverage.NOT_HELD, "G-NOTHELD"),
        (Coverage.HELD_NOT_FOUND, "G-HELDNOTFOUND"),
        (Coverage.NOT_ASSESSED, "G-NOTASSESSED"),
    ],
)
def test_real_retrieval_failures_remain_distinct_and_named(coverage, id):
    result = EvidenceResult(coverage, missing="A named retrieval requirement")
    failure = retrieval_failure(result)
    assert failure.gate_id == id and failure.text and failure.reason
    assert receipts(replace(captured_output(), retrieval_results=(result,)))[id].assessed is False


def test_a_real_no_match_does_not_claim_the_law_is_not_held_or_that_search_did_not_run():
    result = EvidenceResult(
        Coverage.SEARCHED_NO_MATCH, missing="No relevant hit in the searched index"
    )
    assert retrieval_failure(result) is None
    actual = receipts(replace(captured_output(), retrieval_results=(result,)))
    assert all(
        actual[id].assessed is True for id in ("G-NOTHELD", "G-HELDNOTFOUND", "G-NOTASSESSED")
    )


def test_cascade_carries_the_prior_and_loss_is_not_called_complete():
    subject = captured_output()
    moved = (replace(subject.derived[0], value="A changed position"),)
    actual = receipts(replace(subject, derived=moved))
    assert actual["G-CASCADE"].assessed is False
    assert "was not established, now A changed position" in actual["G-CASCADE"].reason
    assert actual["G-CASCADE"].response is Response.DISCLOSE
    assert receipts(replace(subject, derived=()))["G-CONSERVE"].assessed is False


def test_stale_actual_version_or_dependency_stays_nonpresentable():
    subject = captured_output()
    assert receipts(replace(subject, observed_version=2))["G-STALE"].assessed is False
    ledger = replace(
        subject.ledger,
        nodes=(
            replace(
                subject.ledger.nodes[0],
                currency=dependency.Currency.STALE,
                stale_because="The source moved",
            ),
        ),
    )
    assert receipts(replace(subject, ledger=ledger))["G-CURRENCY"].assessed is False


@pytest.mark.parametrize(
    "verdict",
    [
        consistency.UNVERIFIED,
        consistency.Verdict(ran=False, why="No computed claims were captured"),
        consistency.Verdict(refused="An invented claim"),
    ],
)
def test_a_consistency_check_that_did_not_certify_anything_never_passes(verdict):
    assert (
        receipts(replace(captured_output(), consistency_verdict=verdict))["G-CONSISTENT"].assessed
        is None
    )


def test_a_contradiction_is_refused_instead_of_styled_as_a_successful_check():
    actual = receipts(
        replace(
            captured_output(),
            consistency_verdict=consistency.Verdict(
                claim_id="computed_fact",
                quoted="Contradictory recommendation",
                why="The result differs",
            ),
        )
    )
    assert actual["G-CONSISTENT"].assessed is False


def test_read_observer_missing_failed_or_empty_are_three_distinct_actual_inputs():
    missing = observe_reads(object(), "empty_decisive")
    assert missing.values is None

    class Traced:
        def empty_decisive(self):
            return ()

        def refused_reads(self):
            raise RuntimeError("Trace could not be read")

    assert observe_reads(Traced(), "empty_decisive").values == ()
    failed = observe_reads(Traced(), "refused_reads")
    assert failed.values is None and "RuntimeError" in failed.error
    subject = captured_output()
    assert receipts(replace(subject, empty_reads=missing))["G-READ"].assessed is None
    assert (
        receipts(replace(subject, empty_reads=ReadPopulation(("dates",))))["G-READ"].assessed
        is False
    )
    assert receipts(replace(subject, refused_reads=failed))["G-MODEL"].assessed is None


@pytest.mark.parametrize("state", list(CoverageState))
def test_coverage_uses_its_existing_measured_three_state_owner(state):
    class Measured:
        def position(self, jurisdiction):
            return CoveragePosition(state, jurisdiction, "Actual measured coverage reason")

    actual = receipts(
        replace(
            captured_output(),
            coverage=measured_coverage(Measured(), "Telangana"),
            competence=competence_screen(Measured(), "Telangana"),
        )
    )
    expected = None if state is CoverageState.NOT_MEASURED else state is CoverageState.MET
    assert actual["G-COVERAGE"].assessed is expected
    assert actual["G-COMPETENCE"].assessed is expected
    assert competence_screen(Measured(), "Telangana").clears


def test_an_absent_coverage_installation_remains_a_visible_nonassessment():
    assert measured_coverage(None, "Telangana").discloses
    assert screens.gate_for(competence_screen(None, "Telangana")) == (
        "G-COMPETENCE",
        "not_assessed",
    )


def test_six_boundary_subjects_absent_are_six_named_nonassessments():
    actual = boundary_receipts(BoundarySubjects())
    assert set(actual) == BOUNDARY_IDS and all(row.assessed is None for row in actual.values())


def test_actual_complete_current_screen_duty_and_operation_authority_population_passes():
    actual = boundary_receipts(boundaries())
    assert set(actual) == BOUNDARY_IDS and all(row.assessed is True for row in actual.values())


@pytest.mark.parametrize(
    "kind",
    [
        screens.ScreenKind.EMERGENCY,
        screens.ScreenKind.CONFLICT,
        screens.ScreenKind.SCOPE,
        screens.ScreenKind.CAPACITY,
    ],
)
def test_missing_each_boundary_screen_is_named_and_cannot_authorise_admission(kind):
    subject = boundaries()
    actual = boundary_receipts(
        replace(subject, screens=tuple(row for row in subject.screens if row.kind is not kind))
    )
    assert actual[screens.GATE_FOR[kind][0]].assessed is None
    assert actual["G-UNSCREENED"].assessed is False


def test_party_changes_stale_both_the_conflict_clearance_and_substantive_admission():
    subject = boundaries(parties=frozenset({"client", "opponent", "guarantor"}))
    actual = boundary_receipts(subject)
    assert actual["G-CONFLICT"].assessed is False and actual["G-CONFLICT"].state == "incomplete"
    assert actual["G-UNSCREENED"].assessed is False
    assert not admission_policy(subject.screens, parties=subject.parties)[0]


def test_no_current_party_set_is_not_a_clean_conflict_or_admission_check():
    actual = boundary_receipts(boundaries(parties=None))
    assert actual["G-CONFLICT"].assessed is None and actual["G-UNSCREENED"].assessed is None


def test_missing_or_refused_operation_authority_is_not_supplied_by_a_scope_statement():
    actual = boundary_receipts(boundaries(authority=None))
    assert actual["G-SCOPE"].assessed is None
    denied = authority.permits("advocate", authority.ActingAs.ADVISING, authority.Act.CONCEDE)
    assert boundary_receipts(boundaries(authority=denied))["G-SCOPE"].assessed is False


@pytest.mark.parametrize(
    "state", [screens.ScreenState.NOT_ASSESSED, screens.ScreenState.UNAVAILABLE]
)
def test_an_unavailable_boundary_is_not_clear_despite_a_recorded_scope(state):
    subject = boundaries()
    conflict = screens.Screen(
        screens.ScreenKind.CONFLICT, state, not_assessed_because="The registry cannot be checked"
    )
    changed = replace(
        subject,
        screens=tuple(conflict if row.kind is conflict.kind else row for row in subject.screens),
    )
    actual = boundary_receipts(changed)
    assert actual["G-CONFLICT"].assessed is None and actual["G-UNSCREENED"].assessed is False


def test_unknown_duty_and_prohibited_instruction_are_not_plain_clearance():
    assert (
        duty_check(duty.UNREAD).assessed is None and duty_check(duty.UNREAD).state == "not_assessed"
    )
    refused = duty.Refusal(
        duty.Ground.FALSE_DOCUMENT,
        quoted="An exact prohibited instruction",
        why="A stated professional reason",
    )
    assert duty_check(refused).assessed is False and duty_check(refused).state == "refused"
    assert boundary_receipts(boundaries(duty=refused))["G-DUTY"].assessed is False


def test_a_model_label_cannot_supply_subjects_or_invent_a_gate_state():
    with pytest.raises(ValueError):
        run_output_checks({"all_checks_passed": True})
    with pytest.raises(ValueError):
        run_boundary_checks({"all_checks_passed": True})
    with pytest.raises(ValueError):
        CheckReceipt("G-DUTY", True, "The model says it passed", "anything_goes")
