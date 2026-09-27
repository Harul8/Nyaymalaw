"""The model cannot supply formulae or upgrade missing reviewed legal inputs."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from nm.legal_brain import limitation, premise
from nm.legal_brain.calculation_tools import (
    CalculationSource,
    LimitationInputs,
    ReviewedFactor,
    calculation_snapshot,
    calculation_tools,
)
from nm.legal_brain.evidence_port import Coverage, EvidenceResult
from nm.legal_brain.loop_contracts import LoopEvent, LoopIdentity, LoopMode, StepKind, digest
from nm.legal_brain.tool_sources import source_envelope
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    Boundary,
    ToolContext,
    ToolRefused,
    ToolRegistry,
)
from nm.shared.model_port import SchemaViolation, ToolCall
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_loop_log import MatterLoopLog
from nm.work_the_file.matter_contracts import Basis, Fact, Matter, Posture, Provenance, Role, Thread
from tests.test_independent_claim_verifier import finding

pytestmark = pytest.mark.class_a
VERSION = "reviewed-generation-1"


def _case(tmp_path, *, span="The period is twelve years.", extra_facts=()):
    store = FileMatterStore(tmp_path, key="calculation-control-key")
    fact = Fact("fact_accrual", "The recorded refusal occurred on 2023-02-28.",
                Provenance("advocate_statement", "admitted_turn"),
                date=date(2023, 2, 28), confirmed=True)
    primary = finding(ref="Limitation Act, Article recorded", span=span)
    premises = premise.Premises((
        premise.Premise(premise.Kind.APPLICABLE_LAW, primary.ref,
                        premise.Basis.ATTRIBUTED, f"{primary.store}:{primary.locator}"),
        premise.Premise(premise.Kind.ACCRUAL_RULE, "The recorded refusal is the reviewed trigger.",
                        premise.Basis.STATED, fact.id, reviewed_by="adv_calc"),
        premise.Premise(premise.Kind.JURISDICTION, "Recorded jurisdiction",
                        premise.Basis.STATED, "recorded engagement", reviewed_by="adv_calc")))
    thread = Thread("thr_calc", "Recorded claim", posture=Posture(Role.PLAINTIFF, Basis.STATED),
                    chronology=(fact.id, *[row.id for row in extra_facts]),
                    premises=premises.as_rows())
    matter = store.commit(Matter("mat_calc", "adv_calc", "Recorded calculation matter",
                                 threads=(thread,), facts=(fact, *extra_facts), version=1),
                          expected_version=0)
    identity = LoopIdentity(matter.id, matter.advocate_id, "source_turn", digest({"read": 1}),
                            digest({"principles": 1}), digest({"tools": 1}), matter.version,
                            LoopMode.SYNTHETIC)
    log = MatterLoopLog(store, advocate_id=matter.advocate_id)
    previous = identity.fingerprint
    call = {"call_id": "read_article", "name": "read_provision",
            "arguments": {"act": "Recorded instrument", "section": "recorded",
                          "as_of": "2026-01-01"}}
    envelope = source_envelope("read_provision", "source-v1", "held", VERSION, (), {},
                               reason="The candidate's semantic applicability remains unassessed.",
                               primary_reads=(EvidenceResult(Coverage.ANSWERED, (primary,),
                                                             searched_stores=("held",)),))
    for index, (kind, payload) in enumerate((
        (StepKind.START, {"source_owner": "primary evidence port"}),
        (StepKind.TOOL_STARTED, {"call": call}),
        (StepKind.TOOL_RETURNED, {"call_id": call["call_id"],
                                  "receipt": json.loads(envelope.wire())}),
    ), 1):
        event = LoopEvent.create(index, kind, datetime.now(timezone.utc).isoformat(),
                                 payload, previous)
        log.append(identity, event)
        previous = event.fingerprint
    matter = store.load(matter.id)
    selected = LimitationInputs(calculation_snapshot(matter, thread), premises,
                                CalculationSource(identity.turn_id, call["call_id"],
                                                  event.fingerprint, primary), fact)
    return store, selected, ToolContext(identity, matter.version)


def _invoke(store, selected, context, *, resolve=True, current=True,
            args=None, before=None, name="compute_limitation"):
    registry = ToolRegistry(calculation_tools(
        store, source_version=VERSION,
        current_source_version=(lambda: VERSION) if current else None,
        resolve=(lambda *_: selected) if resolve else None),
        before=before or (lambda *_: Boundary(True, "Controlled calculation admission.")),
        after=lambda *_: Boundary(True, "Controlled calculation receipt check."))
    return registry.invoke(ToolCall("calculate", name,
        args if args is not None else ({"thread_id": "thr_calc", "as_of": "2026-02-28"}
                                       if name == "compute_limitation" else {})), context)


def test_compute_limitation_uses_current_fact_and_exact_saved_primary_source(tmp_path):
    store, selected, context = _case(tmp_path)
    result = _invoke(store, selected, context)
    assert result.assessment is Assessment.SUPPORTED
    assert result.data["position"]["state"] == limitation.LimitationState.COMPUTED
    assert result.data["position"]["expires_on"] == date(2035, 2, 28)
    assert result.data["position"]["period_years"] == 12
    assert result.data["accrual_on"] == "2023-02-28"
    assert result.data["days_remaining"] == (date(2035, 2, 28) - date(2026, 2, 28)).days
    assert result.data["arithmetic_verified"] and not result.data["legal_applicability_established"]
    facts = result.receipt["input_receipts"][-1]["facts"]
    assert facts[0]["certainty"].value == "asserted"  # confirmation is not documentation
    assert result.receipt["input_receipts"][2]["event"] == selected.article.event_fingerprint
    assert store.load("mat_calc").version == context.current_version  # read-only


@pytest.mark.parametrize("mutation", ["missing_resolver", "missing_current_source", "wrong_event",
    "wrong_source_words", "wrong_accrual", "undated", "unconfirmed", "superseded",
    "unknown_premise", "wrong_snapshot", "no_period", "missing_article", "missing_accrual"])
def test_missing_or_changed_limitation_inputs_never_produce_a_supported_date(tmp_path, mutation):
    store, selected, context = _case(tmp_path,
                                    span="No numeric period is stated." if mutation == "no_period"
                                    else "The period is twelve years.")
    resolve, current = True, True
    if mutation == "missing_resolver":
        resolve = False
    elif mutation == "missing_current_source":
        current = False
    elif mutation == "wrong_event":
        selected = replace(selected, article=replace(selected.article, event_fingerprint="wrong"))
    elif mutation == "wrong_source_words":
        selected = replace(selected, article=replace(selected.article, finding=replace(
            selected.article.finding, span="The model supplied three years.")))
    elif mutation == "wrong_accrual":
        selected = replace(selected, accrual=replace(selected.accrual, id="foreign_fact"))
    elif mutation in {"undated", "unconfirmed", "superseded"}:
        fields = {"undated": {"date": None}, "unconfirmed": {"confirmed": None},
                  "superseded": {"superseded_by": "replacement_fact"}}[mutation]
        selected = replace(selected, accrual=replace(selected.accrual, **fields))
    elif mutation == "unknown_premise":
        selected = replace(selected, premises=premise.Premises())
    elif mutation == "wrong_snapshot":
        selected = replace(selected, snapshot_id="old_snapshot")
    elif mutation == "missing_article":
        selected = replace(selected, article=None)
    elif mutation == "missing_accrual":
        selected = replace(selected, accrual=None)
    result = _invoke(store, selected, context, resolve=resolve, current=current)
    assert result.assessment is Assessment.NOT_ASSESSED
    assert result.availability is Availability.UNAVAILABLE
    assert result.reason and not result.data


def test_arbitrary_formula_period_law_or_actor_arguments_are_refused(tmp_path):
    store, selected, context = _case(tmp_path)
    for key, value in (("period_years", 3), ("formula", "today plus 3"),
                       ("actor_id", "other_actor"), ("accrual_on", "2000-01-01")):
        with pytest.raises(SchemaViolation):
            _invoke(store, selected, context, args={
                "thread_id": "thr_calc", "as_of": "2026-02-28", key: value})


def test_wrong_actor_stale_file_or_unapproved_call_does_not_reach_arithmetic(tmp_path):
    store, selected, context = _case(tmp_path)
    with pytest.raises(ToolRefused, match="actor"):
        _invoke(store, selected, replace(context, identity=replace(
            context.identity, advocate_id="other_actor")))
    with pytest.raises(ToolRefused, match="moved"):
        _invoke(store, selected, replace(context, observed_version=context.current_version - 1))
    with pytest.raises(ToolRefused, match="not permitted"):
        _invoke(store, selected, context, before=lambda *_: Boundary(False, "not permitted"))


def test_inferred_accrual_remains_conditional_and_competing_dates_remain_visible(tmp_path):
    other = Fact("fact_alternative", "An alternative refusal date is recorded.",
                 Provenance("advocate_statement", "other_turn"), date=date(2024, 2, 29),
                 confirmed=True)
    store, selected, context = _case(tmp_path, extra_facts=(other,))
    changed = premise.Premises(tuple(
        replace(row, basis=premise.Basis.INFERRED,
                inferred_from="Recorded competing factual triggers")
        if row.kind is premise.Kind.ACCRUAL_RULE else row for row in selected.premises.items))
    matter = store.load("mat_calc")
    thread = replace(matter.threads[0], premises=changed.as_rows())
    matter = store.commit(replace(matter, threads=(thread,), version=matter.version + 1),
                          expected_version=matter.version)
    selected = replace(selected, premises=changed, alternatives=(other,),
                       snapshot_id=calculation_snapshot(matter, thread))
    result = _invoke(store, selected, replace(context, observed_version=matter.version))
    assert result.assessment is Assessment.NOT_ASSESSED
    assert result.data["position"]["state"] == limitation.LimitationState.CONDITIONAL
    assert result.data["position"]["conditional_because"]
    assert result.data["position"]["alternatives"][0]["expires_on"] == "2036-02-29"
    assert not result.data["legal_applicability_established"]


def test_unexamined_chronology_is_not_a_no_effect_finding(tmp_path):
    other = Fact("fact_unknown", "An undated possibly material writing is held.",
                 Provenance("advocate_statement", "other_turn"), confirmed=True)
    store, selected, context = _case(tmp_path, extra_facts=(other,))
    result = _invoke(store, selected, context)
    assert result.availability is Availability.PARTIAL
    assert result.assessment is Assessment.NOT_ASSESSED
    assert result.data["position"]["covered"][1]["applied"] == limitation.Applied.NOT_ASSESSED
    assert "fact_unknown" in result.reason


def test_unknown_native_position_is_preserved_not_turned_into_no_limitation(tmp_path):
    store, selected, context = _case(tmp_path)
    position = limitation.not_computed(
        selected.accrual and store.load("mat_calc").threads[0].posture.side,
        "The factual trigger is not established.",
        premises=selected.premises.as_rows(), premise_digest=selected.premises.digest())
    selected = replace(selected, prior_position=position)
    result = _invoke(store, selected, context)
    assert result.assessment is Assessment.NOT_ASSESSED and not result.data
    assert result.receipt["input_receipts"][-1]["position"]["state"] == (
        limitation.LimitationState.NOT_COMPUTED)


def test_native_nonapplicability_is_preserved_without_a_new_arithmetic_or_legal_verdict(tmp_path):
    store, selected, context = _case(tmp_path)
    position = limitation.not_applicable(store.load("mat_calc").threads[0].posture.side,
        "The existing reviewed owner records no period for this position.",
        premises=selected.premises.as_rows(), premise_digest=selected.premises.digest())
    result = _invoke(store, replace(selected, prior_position=position), context)
    assert result.data["position"]["state"] is limitation.LimitationState.NOT_APPLICABLE
    assert result.assessment is Assessment.NOT_ASSESSED
    assert not result.data["arithmetic_verified"] and result.data["days_remaining"] is None


def test_interest_absence_never_becomes_estimated_arithmetic(tmp_path):
    store, selected, context = _case(tmp_path)
    result = _invoke(store, selected, context, name="compute_interest")
    assert result.availability is Availability.UNAVAILABLE
    assert result.assessment is Assessment.NOT_ASSESSED and not result.data
    assert "No rate" in result.reason


def test_a_reviewed_restart_uses_its_exact_fact_and_separate_captured_source(tmp_path):
    writing = Fact("fact_writing", "The later written acknowledgment is recorded.",
                   Provenance("advocate_statement", "writing_turn"),
                   date=date(2024, 6, 12), confirmed=True)
    store, selected, context = _case(tmp_path, extra_facts=(writing,))
    held = finding(ref="Recorded restart provision", locator="held:restart:1",
                   span="The reviewed acknowledgment before expiry starts a fresh period.")
    envelope = source_envelope("read_provision", "source-v1", "held", VERSION, (), {},
        reason="The selected factor's applicability remains subject to independent final review.",
        primary_reads=(EvidenceResult(Coverage.ANSWERED, (held,), searched_stores=("held",)),))
    log = MatterLoopLog(store, advocate_id=context.identity.advocate_id)
    old = log.read(context.identity)
    call = ToolCall("read_restart", "read_provision", {
        "act": "Recorded instrument", "section": "restart", "as_of": "2026-01-01"})
    event = LoopEvent.create(len(old.events) + 1, StepKind.TOOL_STARTED,
        datetime.now(timezone.utc).isoformat(), {"call": {
            "call_id": call.call_id, "name": call.name, "arguments": call.arguments}},
        old.events[-1].fingerprint)
    log.append(context.identity, event)
    returned = LoopEvent.create(event.sequence + 1, StepKind.TOOL_RETURNED,
        datetime.now(timezone.utc).isoformat(), {"call_id": call.call_id,
        "receipt": json.loads(envelope.wire())}, event.fingerprint)
    log.append(context.identity, returned)
    current = store.load("mat_calc")
    factor = ReviewedFactor(limitation.Factor(limitation.FactorKind.ACKNOWLEDGMENT,
        writing.id, held.span, restarts_from=writing.date),
        CalculationSource(context.identity.turn_id, call.call_id, returned.fingerprint, held))
    selected = replace(selected, factors=(factor,),
                       snapshot_id=calculation_snapshot(current, current.threads[0]))
    context = replace(context, observed_version=current.version)
    result = _invoke(store, selected, context)
    assert result.assessment is Assessment.SUPPORTED
    assert result.data["position"]["expires_on"] == date(2036, 6, 12)
    assert result.data["position"]["covered"][1]["applied"] is limitation.Applied.APPLIED
    assert len([row for row in result.receipt["input_receipts"]
                if row["kind"] == "captured_primary_source"]) == 2
    duplicated = _invoke(store, replace(selected, factors=(factor, factor)), context)
    assert duplicated.assessment is Assessment.NOT_ASSESSED and not duplicated.data
    wrong = replace(factor, factor=replace(factor.factor, finding="Remembered extension law."))
    assert _invoke(store, replace(selected, factors=(wrong,)), context).assessment is (
        Assessment.NOT_ASSESSED)


def test_case_or_source_movement_inside_the_resolver_refuses_the_computation(tmp_path):
    store, selected, context = _case(tmp_path)
    generation = VERSION

    def move(matter, _thread, _context):
        nonlocal generation
        generation = "a-new-source-generation"
        return selected

    tools = calculation_tools(store, source_version=VERSION,
                              current_source_version=lambda: generation, resolve=move)
    result = tools[0].handler({"thread_id": "thr_calc", "as_of": "2026-02-28"}, context)
    assert result.assessment is Assessment.NOT_ASSESSED and not result.data


def test_file_movement_during_calculation_refuses_even_an_otherwise_correct_expiry(tmp_path):
    store, selected, context = _case(tmp_path)

    def move(matter, _thread, _context):
        store.commit(replace(matter, version=matter.version + 1),
                     expected_version=matter.version)
        return selected

    tools = calculation_tools(store, source_version=VERSION,
                              current_source_version=lambda: VERSION, resolve=move)
    with pytest.raises(ToolRefused, match="moved during calculation"):
        tools[0].handler({"thread_id": "thr_calc", "as_of": "2026-02-28"}, context)


@pytest.mark.parametrize("when", ["not_a_date", "2026-02-30", "20260228"])
def test_unknown_or_noncanonical_comparison_dates_are_never_estimated(tmp_path, when):
    store, selected, context = _case(tmp_path)
    with pytest.raises(ToolRefused, match="ISO calendar date"):
        _invoke(store, selected, context, args={"thread_id": "thr_calc", "as_of": when})
