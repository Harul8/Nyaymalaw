"""No recorded event, candidate flag or calculator can author its own review."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from nm.legal_brain.procedure import limitation
from nm.legal_brain.reason import premise
from nm.legal_brain.procedure.calculation_tools import EVENT_VERSION, VERSION, calculation_tools
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind
from nm.legal_brain.procedure.reviewed_limitation_selection import (
    LimitationSelectionReviewService,
    limitation_selection_tools,
    prepare_limitation_selections,
    resolve_limitation_inputs,
    selection_inventory,
)
from nm.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    Boundary,
    ToolContext,
    ToolRefused,
    ToolRegistry,
)
from nm.shared.budget_contracts import Budget
from nm.shared.json_values import same_json_value
from nm.shared.model_port import ProviderUnavailable, SchemaViolation, ToolCall
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.matter_contracts import Basis, Fact, Posture, Provenance, Role, Thread
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import finding, response
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
GENERATION = "generation-1"
RULE = ("The period is ninety days from the described due event. A later writing restarts "
        "that same period when its stated conditions are met. An irrelevant remark has no effect.")
TODAY = date(2026, 9, 27)


def _fixture(tmp_path, *, domain="Recorded dispute", on=date(2023, 2, 28),
             period="ninety days", judged=None, inferred=True, extra=True, one_account=False,
             children=2, empty_premises=False, rule=RULE):
    held = finding(ref="Held primary calculation rule", span=rule.replace("ninety days", period))
    with patch("tests.test_claims_reach_the_independent_review_from_the_saved_loop.finding",
               lambda: held):
        store, brain, setup, judge, _ = _case(tmp_path, judged=judged or response(
            words="The period is " + period), children=children)
    account = f"The client reports the described event on {on.isoformat()}."
    later = "The client describes a later writing on 2024-02-29 and an undated remark."
    if one_account:
        account += " " + later
    first = replace(store.load("mat_loop").facts[0], statement=account,
                    date=None, confirmed=None)
    others = () if not extra or one_account else (Fact("fact_later", later,
                                  Provenance("advocate_statement", "later_input")),)
    facts = (first, *others)
    observations = [EventObservation(first.id, first.version, account,
        f"the described event on {on.isoformat()}", on.isoformat(), TODAY, on)]
    if extra:
        other = first if one_account else others[0]
        observations.extend((EventObservation(other.id, other.version, other.statement,
            "a later writing on 2024-02-29", "2024-02-29", TODAY, date(2024, 2, 29)),
            EventObservation(other.id, other.version, other.statement,
                             "an undated remark", "", TODAY)))
    premises = premise.Premises((
        premise.Premise(premise.Kind.APPLICABLE_LAW, held.ref,
                        premise.Basis.ATTRIBUTED, f"{held.store}:{held.locator}"),
        premise.Premise(premise.Kind.ACCRUAL_RULE, "The described event is the proposed trigger.",
            premise.Basis.INFERRED if inferred else premise.Basis.STATED, first.id,
            inferred_from="The attributed complete account" if inferred else "",
            alternatives=("The later writing may be a competing trigger.",) if extra else ()),
        premise.Premise(premise.Kind.JURISDICTION, "Recorded jurisdiction",
                        premise.Basis.STATED, "recorded advocate instruction")))
    thread = Thread("thr_events", domain, chronology=tuple(row.id for row in facts),
        posture=Posture(Role.PLAINTIFF, Basis.STATED),
        premises=() if empty_premises else premises.as_rows(),
        event_observations=tuple(observations))
    before = store.load("mat_loop")
    matter = store.commit(replace(before, facts=facts, threads=(thread,),
                                 version=before.version + 1), expected_version=before.version)

    def current(source, generation):
        return generation == GENERATION and same_json_value(source.as_record(), held.as_record())

    inventory = selection_inventory(matter, thread, source_generation=GENERATION,
                                    source_current=current)
    clause = {"source_id": inventory["sources"][0]["id"], "start": 0, "end": len(held.span)}
    candidate = {"thread_id": thread.id, "snapshot_id": inventory["snapshot_id"],
        "article": clause, "accrual_observation_id": observations[0].identity,
        "alternative_observation_ids": [observations[1].identity] if extra else [],
        "factors": [], "chronology": [
            {"fact_id": row.id, "state": "applied" if index == 0 else "not_assessed",
             "clause": None, "reason": "Selected source event" if index == 0
             else "Its legal effect is not assessed."} for index, row in enumerate(facts)],
        "events": [{"observation_id": row.identity,
            "state": "applied" if index == 0 else "not_assessed", "clause": None,
            "reason": "Selected trigger" if index == 0 else "Competing or undated event"}
            for index, row in enumerate(observations)],
        "premises": None,
        "reason": "Conditional calculation under the attributed selected event."}
    brain.registry = brain.registry.extend(limitation_selection_tools(store,
        source_generation=GENERATION, source_current=current))
    brain._runner._tools = brain.registry
    return store, brain, setup, judge, thread, candidate, current


def _run(case, *, candidate=None, review=True, turn="event-selection", error=None,
         calls=1, message="Assess the conditional event selection."):
    store, brain, _, judge, thread, original, current = case
    judge.error = error
    candidate = candidate or original
    authored = [ToolCall(f"selection{index}", "propose_limitation_selection", candidate)
                for index in range(calls)]
    authored.append(ToolCall("terminal", "ask_advocate", {
        "question": "Which recorded event should govern the calculation?"}))
    brain.model.tool_call.side_effect = [replace(_response(call), provider="scripted",
                                               model="scripted:author") for call in authored]
    outcome = brain.run(matter_id="mat_loop", turn_id=turn,
        message=message, limits=LoopLimits(
            Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1.0, max_children=2), 8, 500))
    service = LimitationSelectionReviewService(brain.reviewer,
        source_generation=GENERATION, source_current=current)
    checked = service.review(outcome) if review else None
    return outcome, checked, service


def _resolve(case, *, current=None, matter=None, now=None):
    store, _, _, _, thread, _, owner = case
    matter = matter or store.load("mat_loop")
    return resolve_limitation_inputs(matter, matter.thread(thread.id),
        source_generation=GENERATION, source_current=current or owner, now=now)


def _compute(case, selected=None, *, current=None, version=True):
    store, _, setup, _, thread, _, owner = case
    matter = store.load("mat_loop")
    registry = ToolRegistry(calculation_tools(store, source_version=GENERATION,
        current_source_version=lambda: GENERATION, source_current=current or owner,
        resolve=lambda *_: selected if selected is not None else _resolve(case),
        event_selections=version), before=lambda *_: Boundary(True, "Controlled admission"),
        after=lambda *_: Boundary(True, "Controlled receipt"))
    context = ToolContext(setup.record.identity, matter.version)
    return registry.invoke(ToolCall("calculate", "compute_limitation", {
        "thread_id": thread.id, "as_of": "2026-09-27"}), context)


def test_unreviewed_event_selection_cannot_supply_calculation_inputs(tmp_path):
    case = _fixture(tmp_path)
    outcome, _, _ = _run(case, review=False)
    assert not _resolve(case)
    assert not case[3].prompts
    file = case[0].load("mat_loop")
    bindings = prepare_limitation_selections(outcome, file, source_generation=GENERATION,
                                             source_current=case[-1])
    # Even the trusted candidate builder's perfectly typed inputs are not a receipt.
    result = _compute(case, bindings[0].inputs)
    assert result.availability is Availability.UNAVAILABLE and not result.data
    actual = next(event for event in outcome.record.events if event.kind is StepKind.TOOL_RETURNED)
    assert actual.payload["receipt"]["data"]["selection_reviewed"] is False


@pytest.mark.parametrize("domain,on,period,expected", [
    ("Payment dispute", date(2023, 2, 28), "ninety days", date(2023, 5, 29)),
    ("Property dispute", date(2024, 2, 29), "twelve years", date(2036, 2, 29)),
    ("Service dispute", date(2025, 1, 31), "one month", date(2025, 2, 28)),
])
def test_reviewed_event_calculation_never_confirms_or_registers_its_date(
        tmp_path, domain, on, period, expected):
    case = _fixture(tmp_path, domain=domain, on=on, period=period)
    outcome, checked, service = _run(case)
    assert checked.review.result.released and not checked.unresolved
    selected = _resolve(case)
    assert selected and selected.observations[-1].on is None
    result = _compute(case, selected)
    assert result.version == EVENT_VERSION and result.assessment is Assessment.NOT_ASSESSED
    assert result.data["position"]["state"] is limitation.LimitationState.CONDITIONAL
    assert result.data["position"]["expires_on"] == expected
    assert result.data["days_remaining"] == (expected - TODAY).days
    assert len(result.data["position"]["covered"]) == 2
    assert len(result.data["event_coverage"]) == 3
    assert result.data["position"]["premises"][1]["alternatives"]
    assert result.data["position"]["alternatives"][0]["observation_id"]
    assert not result.data["deadline_registered"] and not result.data["factual_truth_established"]
    file = case[0].load("mat_loop")
    assert all(row.date is None and row.confirmed is None for row in file.facts)
    assert not file.threads[0].deadlines
    assert len(case[3].prompts) == 1 and checked.review.budget.spend.children == 1
    assert service.review(outcome).review == checked.review and len(case[3].prompts) == 1


@pytest.mark.parametrize("mutation", ["missing_fact", "duplicate_fact", "missing_event",
    "duplicate_event", "unknown_event", "undated_trigger", "span_bool", "span_float",
    "span_end", "span_foreign_source", "missing_noeffect_source", "noeffect_applied",
    "unassessed_has_source", "author_review_flag", "article_text", "alternative_duplicate",
    "alternative_selected", "missing_coverage", "reordered_coverage"])
def test_event_selection_requires_full_current_chronology_and_exact_primary_spans(
        tmp_path, mutation):
    case = _fixture(tmp_path)
    candidate = deepcopy(case[5])
    if mutation == "missing_fact":
        candidate["chronology"].pop()
    elif mutation == "duplicate_fact":
        candidate["chronology"][1]["fact_id"] = candidate["chronology"][0]["fact_id"]
    elif mutation == "missing_event":
        candidate["events"].pop()
    elif mutation == "duplicate_event":
        candidate["events"][1]["observation_id"] = candidate["events"][0]["observation_id"]
    elif mutation == "unknown_event":
        candidate["accrual_observation_id"] = "foreign-event"
    elif mutation == "undated_trigger":
        candidate["accrual_observation_id"] = candidate["events"][-1]["observation_id"]
    elif mutation in {"span_bool", "span_float", "span_end"}:
        candidate["article"]["end"] = {"span_bool": True, "span_float": 1.0,
                                        "span_end": 10000}[mutation]
    elif mutation == "span_foreign_source":
        candidate["article"]["source_id"] = "foreign-source"
    elif mutation == "missing_noeffect_source":
        candidate["chronology"][1]["state"] = "no_effect"
    elif mutation == "noeffect_applied":
        candidate["chronology"][0].update(state="no_effect", clause=candidate["article"])
    elif mutation == "unassessed_has_source":
        candidate["events"][-1]["clause"] = candidate["article"]
    elif mutation == "author_review_flag":
        candidate["reviewed"] = True
    elif mutation == "article_text":
        candidate["article"]["text"] = "Model-supplied legal text"
    elif mutation == "alternative_duplicate":
        candidate["alternative_observation_ids"] *= 2
    elif mutation == "alternative_selected":
        candidate["alternative_observation_ids"] = [candidate["accrual_observation_id"]]
    elif mutation == "missing_coverage":
        candidate.pop("events")
    else:
        candidate["chronology"].reverse()
    matter = case[0].load("mat_loop")
    tool = limitation_selection_tools(case[0], source_generation=GENERATION,
                                     source_current=case[-1])[1]
    registry = ToolRegistry((tool,), before=lambda *_: Boundary(True, "Controlled admission"),
                            after=lambda *_: Boundary(True, "Controlled receipt"))
    with pytest.raises((ToolRefused, SchemaViolation)):
        registry.invoke(ToolCall("candidate", tool.definition.name, candidate),
                        ToolContext(case[2].record.identity, matter.version))
    assert not case[3].prompts


@pytest.mark.parametrize("criterion,value", [
    ("textual_support", False), ("applicability", False), ("inference", False),
    ("opposition_resolved", False), ("textual_support", None), ("applicability", None),
    ("inference", None), ("opposition_resolved", None),
])
def test_negative_or_ambiguous_independent_selection_does_not_unlock_arithmetic(
        tmp_path, criterion, value):
    judged = response(words="The period is ninety days")
    judged[criterion]["assessed"] = value
    case = _fixture(tmp_path, judged=judged)
    _, checked, _ = _run(case)
    assert checked.unresolved and not _resolve(case)
    assert not _compute(case).data and len(case[3].prompts) == 1


def test_provider_failure_is_saved_on_the_existing_budget_without_approving_selection(tmp_path):
    case = _fixture(tmp_path)
    _, checked, _ = _run(case, error=ProviderUnavailable("The controlled judge is unavailable"))
    assert checked.unresolved and not _resolve(case)
    assert checked.review.budget.spend.children == 1
    assert checked.review.budget.spend.cost_usd >= 0.03
    assert case[0].load("mat_loop").loop_records[-1].terminal


@pytest.mark.parametrize("mutation", ["account", "event_date", "event_reference", "certainty",
    "premise", "premise_alternatives", "chronology", "generation", "withdrawal",
    "fact_confirmed_int", "duplicate_premise", "unknown_premise", "foreign_actor"])
def test_changed_exact_subject_or_source_invalidates_saved_positive_review(tmp_path, mutation):
    case = _fixture(tmp_path)
    _run(case)
    assert _resolve(case)
    file = case[0].load("mat_loop")
    thread = file.threads[0]
    facts = file.facts
    current = case[-1]
    if mutation == "account":
        facts = (replace(facts[0], statement="The described event was denied."), *facts[1:])
    elif mutation in {"event_date", "event_reference"}:
        changes = {"on": date(2025, 1, 1)} if mutation == "event_date" else {
            "reference": date(2026, 9, 26)}
        changed_event = replace(EventObservation.restore(thread.event_observations[0]), **changes)
        thread = replace(thread, event_observations=(changed_event, *thread.event_observations[1:]))
    elif mutation == "certainty":
        from nm.work_the_file.matter_contracts import Certainty

        facts = (replace(facts[0], certainty=Certainty.DOCUMENTED), *facts[1:])
    elif mutation.startswith("premise") or mutation in {"duplicate_premise", "unknown_premise"}:
        rows = deepcopy(list(thread.premises))
        if mutation == "premise":
            rows[1]["statement"] = "A different trigger"
        elif mutation == "premise_alternatives":
            rows[1]["alternatives"] = ("Another material candidate",)
        elif mutation == "duplicate_premise":
            rows.append(rows[0])
        else:
            rows[1]["basis"] = "unknown-authored-basis"
        thread = replace(thread, premises=tuple(rows))
    elif mutation == "chronology":
        thread = replace(thread, chronology=tuple(reversed(thread.chronology)))
    elif mutation in {"generation", "withdrawal"}:
        def current(*_):
            return False
    elif mutation == "fact_confirmed_int":
        facts = (replace(facts[0], confirmed=1), *facts[1:])
    elif mutation == "foreign_actor":
        file = replace(file, advocate_id="foreign-actor")
    changed = replace(file, facts=facts, threads=(thread,))
    assert not _resolve(case, current=current, matter=changed)
    assert len(case[3].prompts) == 1  # No live revalidation call or erased history.


def test_unknown_premise_is_retained_but_cannot_become_a_computed_legal_position(tmp_path):
    case = _fixture(tmp_path)
    file = case[0].load("mat_loop")
    rows = deepcopy(list(file.threads[0].premises))
    rows[1]["basis"] = premise.Basis.UNESTABLISHED.value
    thread = replace(file.threads[0], premises=tuple(rows))
    changed = case[0].commit(replace(file, threads=(thread,), version=file.version + 1),
                            expected_version=file.version)
    inventory = selection_inventory(changed, thread, source_generation=GENERATION,
                                    source_current=case[-1])
    candidate = {**case[5], "snapshot_id": inventory["snapshot_id"]}
    case = (*case[:5], candidate, case[-1])
    _run(case)
    selected = _resolve(case)
    assert selected and selected.premises.unestablished()
    assert not _compute(case, selected).data


def test_full_account_can_bind_distinct_trigger_and_restart_without_fact_date_promotion(tmp_path):
    case = _fixture(tmp_path, one_account=True)
    candidate = deepcopy(case[5])
    candidate["alternative_observation_ids"] = []
    candidate["factors"] = [{"observation_id": candidate["events"][1]["observation_id"],
        "clause": candidate["article"], "kind": "acknowledgment", "effect": "restart",
        "end_observation_id": None, "reason": "The exact reviewed writing restarts the period."}]
    candidate["events"][1].update(state="applied", reason="Reviewed restart event")
    _run(case, candidate=candidate)
    result = _compute(case)
    assert result.data["position"]["expires_on"] == date(2024, 5, 29)
    assert len(result.data["position"]["covered"]) == 1
    assert len(result.data["event_coverage"]) == 3
    assert result.data["event_coverage"][-1]["state"] == "not_assessed"
    assert case[0].load("mat_loop").facts[0].date is None


def test_no_effect_is_an_independently_reviewed_source_event_association(tmp_path):
    case = _fixture(tmp_path)
    candidate = deepcopy(case[5])
    candidate["events"][-1].update(state="no_effect", clause=candidate["article"],
                                  reason="The held clause excludes this attributed remark.")
    outcome, checked, _ = _run(case, candidate=candidate)
    assert checked.review.result.released
    result = _compute(case)
    assert result.data["event_coverage"][-1]["state"] == "no_effect"
    assert "event_quote = an undated remark" in case[3].prompts[0].user
    assert not result.data["factual_truth_established"]
    assert outcome.budget.spend.children == 0 and checked.review.budget.spend.children == 1


def test_no_review_receipt_can_be_borrowed_from_a_future_time_or_competing_candidate(tmp_path):
    case = _fixture(tmp_path)
    _run(case)
    assert _resolve(case)
    assert not _resolve(case, now=datetime(2000, 1, 1, tzinfo=timezone.utc))
    later = datetime.now(timezone.utc) + timedelta(days=365)
    assert _resolve(case, now=later)
    _run(case, turn="another-current-selection")
    assert not _resolve(case)  # Two current positive owners are not resolved by recency.


def test_caller_authored_v2_inputs_do_not_substitute_for_the_sealed_selection(tmp_path):
    case = _fixture(tmp_path)
    _run(case)
    selected = _resolve(case)
    fabricated = replace(selected, accrual=selected.alternatives[0])
    assert not _compute(case, fabricated).data
    with pytest.raises(ValueError, match="typed populations"):
        replace(selected, observations=list(selected.observations))


def test_v1_registry_contract_is_unchanged_without_explicit_v2_enablement(tmp_path):
    case = _fixture(tmp_path)
    tools = calculation_tools(case[0], source_version=GENERATION)
    assert all(row.version == VERSION for row in tools)
    assert tools[0].definition.parameters["required"] == ["thread_id", "as_of"]
    assert EVENT_VERSION != VERSION


def test_stated_premises_do_not_confirm_an_attributed_event_date(tmp_path):
    case = _fixture(tmp_path, inferred=False, extra=False)
    _run(case)
    result = _compute(case)
    assert result.data["position"]["state"] is limitation.LimitationState.CONDITIONAL
    assert result.data["observations"][0]["confirmed"] is False
    assert case[0].load("mat_loop").facts[0].confirmed is None


def test_ambiguous_legal_period_span_is_not_resolved_by_first_number_or_memory(tmp_path):
    case = _fixture(tmp_path, period="ninety days or twelve years")
    _run(case)
    result = _compute(case)
    assert not result.data and "unambiguous" in result.reason


def test_zero_independent_dispatch_allowance_does_not_create_a_hidden_budget(tmp_path):
    case = _fixture(tmp_path)
    outcome, _, service = _run(case, review=False)
    checked = service.review(outcome, max_model_calls=0)
    assert checked.unresolved and not checked.review.result.released
    assert checked.review.budget == outcome.budget and not case[3].prompts
    assert not _resolve(case)


def _actual_prior_reviews(case, outcome, count):
    """Actual sealed same-parent independent dispatches, not authored spend."""
    bindings = prepare_limitation_selections(outcome, case[0].load("mat_loop"),
        source_generation=GENERATION, source_current=case[-1])
    selected = bindings[0].package
    packages = tuple(replace(selected, id=f"prior-independent-{index}") for index in range(count))

    def current(parent, _file, proposed):
        assert parent.record == outcome.record and proposed == packages

    review = case[1].reviewer.review_packages(outcome, packages, current_owner=current,
        current_sources=lambda *_: tuple(dict.fromkeys(span.finding for span in selected.spans)))
    assert review.result.released == packages
    return review


def test_selection_review_forwards_actual_current_budget_without_changing_saved_parent(tmp_path):
    case = _fixture(tmp_path)
    outcome, _checked, service = _run(case, review=False)
    original_record = outcome.record
    earlier = _actual_prior_reviews(case, outcome, 1)
    assert earlier.budget.spend.children == 1
    with patch.object(
        service.reviewer, "review_packages", wraps=service.reviewer.review_packages
    ) as call:
        checked = service.review(outcome, budget=earlier.budget)
    assert call.call_args.args[0] is outcome
    assert call.call_args.kwargs["budget"] is earlier.budget
    assert checked.review.result.released and not checked.unresolved
    assert checked.review.budget.spend.children == 2
    assert outcome.record is original_record and outcome.budget.spend.children == 0
    assert len(case[3].prompts) == 2
    children = case[0].load("mat_loop").loop_records
    child = next(row for row in children if row.identity.turn_id.endswith(
        ":verify:" + checked.bindings[0].package.id))
    assert child.events[0].payload["budget"]["spend"]["children"] == 1
    assert child.events[0].payload["parent"] == outcome.record.identity.fingerprint


def test_actual_earlier_children_exhaustion_prevents_a_selection_dispatch(tmp_path):
    case = _fixture(tmp_path)
    outcome, _checked, service = _run(case, review=False)
    earlier = _actual_prior_reviews(case, outcome, 2)
    checked = service.review(outcome, budget=earlier.budget)
    assert checked.unresolved and not checked.review.result.released
    assert checked.review.budget == earlier.budget
    assert len(case[3].prompts) == 2 and not _resolve(case)


def test_selection_replay_counts_prior_and_selected_actual_children_once(tmp_path):
    case = _fixture(tmp_path)
    outcome, _checked, service = _run(case, review=False)
    earlier = _actual_prior_reviews(case, outcome, 1)
    checked = service.review(outcome, budget=earlier.budget)
    replay = service.review(outcome, budget=checked.review.budget)
    assert replay.review.budget == checked.review.budget
    assert replay.review.result.released == checked.review.result.released
    assert len(case[3].prompts) == 2


def test_actual_source_withdrawal_after_arithmetic_refuses_its_result(tmp_path, monkeypatch):
    case = _fixture(tmp_path)
    _run(case)
    selected = _resolve(case)
    original = limitation.compute
    observed = {"current": True}

    def current(source, generation):
        return observed["current"] and case[-1](source, generation)

    def moved(**kwargs):
        position = original(**kwargs)
        observed["current"] = False
        return position

    monkeypatch.setattr(limitation, "compute", moved)
    with pytest.raises(ToolRefused, match="actual legal source moved"):
        _compute(case, selected, current=current)


def test_copied_positive_verdict_without_its_dispatch_does_not_resolve_inputs(tmp_path):
    case = _fixture(tmp_path)
    _run(case)
    file = case[0].load("mat_loop")
    # The existing independent replay checks actual dispatch/result correlation;
    # neither its positive JSON nor a foreign record-shaped object is a proof.
    from types import SimpleNamespace

    saved = file.loop_records[-1]
    copied = SimpleNamespace(identity=saved.identity, terminal=True,
        events=tuple(event for event in saved.events
                     if event.kind not in (StepKind.MODEL_STARTED, StepKind.MODEL_RETURNED)))
    changed = replace(file, loop_records=(*file.loop_records[:-1], copied))
    assert not _resolve(case, matter=changed)


def _private_candidate(case):
    candidate = deepcopy(case[5])
    candidate["premises"] = [{"kind": row.value,
        "statement": "This is a proposed conditional " + row.value + " selection.",
        "basis": "inferred", "reason": "Inferred from these exact legal and event sources.",
        "alternatives": ["A different legal association remains possible."],
        "source_clauses": [candidate["article"]],
        "observation_ids": [candidate["accrual_observation_id"]], "instruction_span": None}
        for row in premise.REQUIRED]
    return candidate


def test_fresh_file_missing_canonical_premises_can_offer_reviewed_private_inferred_bindings(
        tmp_path):
    case = _fixture(tmp_path, empty_premises=True)
    file = case[0].load("mat_loop")
    inventory = selection_inventory(file, file.threads[0], source_generation=GENERATION,
                                    source_current=case[-1])
    assert inventory["premises"] == []
    assert inventory["missing_canonical_premises"] == [row.value for row in premise.REQUIRED]
    candidate = _private_candidate(case)
    _, checked, _ = _run(case, candidate=candidate)
    assert checked.review.result.released
    selected = _resolve(case)
    assert selected.premise_origin == "private_review_candidate"
    assert all(row.review_state == "not_assessed" and not row.reviewed_by
               for row in selected.premises.items)
    result = _compute(case)
    assert result.data["position"]["state"] is limitation.LimitationState.CONDITIONAL
    assert result.data["premise_origin"] == "private_review_candidate"
    saved = case[0].load("mat_loop")
    assert saved.threads[0].premises == ()
    assert all(row.date is None and row.confirmed is None for row in saved.facts)
    assert not saved.threads[0].deadlines


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "established", "human_review",
    "no_legal_basis", "no_event_basis", "foreign_event", "fake_stated_span",
    "inferred_with_instruction", "unknown_kind", "bool_span", "changed_stated_words"])
def test_private_premise_producer_refuses_missing_authored_or_foreign_basis(tmp_path, mutation):
    case = _fixture(tmp_path, empty_premises=True)
    candidate = _private_candidate(case)
    row = candidate["premises"][0]
    if mutation == "missing":
        candidate["premises"].pop()
    elif mutation == "duplicate":
        candidate["premises"][1]["kind"] = row["kind"]
    elif mutation == "established":
        row["basis"] = "established"
    elif mutation == "human_review":
        row["reviewed_by"] = "an authored advocate approval"
    elif mutation == "no_legal_basis":
        row["source_clauses"] = []
    elif mutation == "no_event_basis":
        row["observation_ids"] = []
    elif mutation == "foreign_event":
        row["observation_ids"] = ["event-from-another-file"]
    elif mutation in {"fake_stated_span", "bool_span", "changed_stated_words"}:
        row["basis"] = "stated"
        row["instruction_span"] = {"start": True if mutation == "bool_span" else 0,
                                   "end": 20}
    elif mutation == "inferred_with_instruction":
        row["instruction_span"] = {"start": 0, "end": 20}
    else:
        row["kind"] = "a fourth implicit premise"
    file = case[0].load("mat_loop")
    registry = ToolRegistry(limitation_selection_tools(case[0], source_generation=GENERATION,
        source_current=case[-1]), before=lambda *_: Boundary(True, "Controlled admission"),
        after=lambda *_: Boundary(True, "Controlled receipt"))
    with pytest.raises((ToolRefused, SchemaViolation)):
        registry.invoke(ToolCall("private", "propose_limitation_selection", candidate),
                        ToolContext(case[2].record.identity, file.version))
    assert not case[3].prompts


def test_stated_private_premise_preserves_whole_negative_instruction_for_independent_review(
        tmp_path):
    judged = response(words="The period is ninety days", inference=False)
    case = _fixture(tmp_path, empty_premises=True, judged=judged)
    candidate = _private_candidate(case)
    message = "I do not know which forum governs. Do not assume the described event is the trigger."
    statement = "which forum governs"
    start = message.index(statement)
    selected_span = {"start": start, "end": start + len(statement)}
    candidate["premises"][2].update(basis="stated", statement=statement,
                                    instruction_span=selected_span)
    _, checked, _ = _run(case, candidate=candidate, message=message)
    assert checked.unresolved and not _resolve(case)
    assert message in case[3].prompts[0].user
    assert not case[0].load("mat_loop").threads[0].premises


def test_exact_stated_private_instruction_is_attribution_not_human_approval_or_fact_truth(tmp_path):
    case = _fixture(tmp_path, empty_premises=True)
    candidate = _private_candidate(case)
    message = "For this conditional question use the recorded jurisdiction."
    statement = "use the recorded jurisdiction"
    start = message.index(statement)
    selected_span = {"start": start, "end": start + len(statement)}
    candidate["premises"][2].update(basis="stated", statement=statement,
                                    instruction_span=selected_span)
    _run(case, candidate=candidate, message=message)
    selected = _resolve(case)
    assert selected.premises.items[2].basis is premise.Basis.STATED
    assert selected.premises.items[2].source.startswith("instruction:")
    assert selected.premises.items[2].review_state == "not_assessed"
    assert _compute(case).data["position"]["state"] is limitation.LimitationState.CONDITIONAL


def test_unknown_competing_date_remains_a_visible_alternative_not_a_default_date(tmp_path):
    case = _fixture(tmp_path)
    candidate = deepcopy(case[5])
    candidate["alternative_observation_ids"].append(candidate["events"][-1]["observation_id"])
    _run(case, candidate=candidate)
    result = _compute(case)
    unknown = result.data["position"]["alternatives"][-1]
    assert unknown["accrual_on"] is None and unknown["expires_on"] is None
    assert unknown["assessment"] == "not_assessed" and unknown["conditional"]
    assert len(result.data["observations"]) == 3


def test_a_resolved_observation_must_reproduce_its_existing_source_date_basis(tmp_path):
    case = _fixture(tmp_path)
    file = case[0].load("mat_loop")
    thread = file.threads[0]
    observations = tuple(EventObservation.restore(row) for row in thread.event_observations)
    corrupted = replace(observations[0], on=date(2025, 1, 1))
    thread = replace(thread, event_observations=(corrupted, *observations[1:]))
    with pytest.raises(ValueError, match="exact current attributed source"):
        selection_inventory(replace(file, threads=(thread,)), thread,
                            source_generation=GENERATION, source_current=case[-1])


def test_reviewed_binding_does_not_escape_the_requested_issue_scope(tmp_path):
    case = _fixture(tmp_path)
    _run(case)
    file = case[0].load("mat_loop")
    context = ToolContext(case[2].record.identity, file.version, issue_ids=("other_dispute",))
    assert not resolve_limitation_inputs(file, file.threads[0], context,
        source_generation=GENERATION, source_current=case[-1])
    registry = ToolRegistry(limitation_selection_tools(case[0], source_generation=GENERATION,
        source_current=case[-1]), before=lambda *_: Boundary(True, "Controlled admission"),
        after=lambda *_: Boundary(True, "Controlled receipt"))
    with pytest.raises(ToolRefused, match="issue scope"):
        registry.invoke(ToolCall("inventory", "read_limitation_candidates", {
            "thread_id": file.threads[0].id}), context)


@pytest.mark.parametrize("effect,extra,expected", [
    ("exclude_elapsed_days", "Its elapsed day count is excluded.", date(2023, 6, 8)),
    ("exclude_inclusive_days", "Both endpoints are included in the excluded day count.",
     date(2023, 6, 9)),
])
def test_exclusion_day_total_is_computed_from_exact_reviewed_event_endpoints(
        tmp_path, effect, extra, expected):
    case = _fixture(tmp_path, rule=RULE + " " + extra)
    file = case[0].load("mat_loop")
    account = ("The described interval began on 2023-03-10 and ended on 2023-03-20. "
               "There is an undated remark.")
    other = replace(file.facts[1], statement=account)
    observations = (EventObservation.restore(file.threads[0].event_observations[0]),
        EventObservation(other.id, other.version, account, "began on 2023-03-10",
                         "2023-03-10", TODAY, date(2023, 3, 10)),
        EventObservation(other.id, other.version, account, "ended on 2023-03-20",
                         "2023-03-20", TODAY, date(2023, 3, 20)),
        EventObservation(other.id, other.version, account, "an undated remark", "", TODAY))
    thread = replace(file.threads[0], event_observations=observations)
    changed = case[0].commit(replace(file, facts=(file.facts[0], other), threads=(thread,),
                                    version=file.version + 1), expected_version=file.version)
    inventory = selection_inventory(changed, thread, source_generation=GENERATION,
                                    source_current=case[-1])
    candidate = deepcopy(case[5])
    candidate["snapshot_id"] = inventory["snapshot_id"]
    candidate["alternative_observation_ids"] = []
    candidate["factors"] = [{"observation_id": observations[1].identity,
        "end_observation_id": observations[2].identity, "clause": candidate["article"],
        "kind": "exclusion", "effect": effect, "reason": "These exact endpoints are excluded."}]
    candidate["chronology"][1].update(state="applied", reason="Reviewed excluded interval")
    candidate["events"] = [{"observation_id": row.identity,
        "state": "not_assessed" if row.on is None else "applied", "clause": None,
        "reason": "Reviewed date endpoint" if row.on is not None else "Unassessed remark"}
        for row in observations]
    _run(case, candidate=candidate)
    result = _compute(case)
    assert result.data["position"]["expires_on"] == expected
    assert result.data["position"]["factors"][0]["adds_days"] == (
        10 if effect == "exclude_elapsed_days" else 11)
    assert result.data["event_coverage"][-1]["state"] == "not_assessed"
    assert "Unassessed source events" in result.reason
    assert all(row.date is None and row.confirmed is None for row in case[0].load("mat_loop").facts)
