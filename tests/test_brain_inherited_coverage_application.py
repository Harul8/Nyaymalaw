"""V2 receipts resolve selected history from the exact before-prefix.

Seeded public fixtures declare independent judgments. Fresh unit fixtures test
receipt/version ownership, source support and replay reuse; producer integration
and real-model semantic quality remain separate work.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import record_review
from nm.brain import turn as owner
from nm.brain.conversation import OpeningCandidate
from nm.brain.execution_contracts import ExecutionEvidenceInvalid
from tests.test_brain_material import send
from tests.test_brain_post_application_coverage_public import TARGET, saved_revision
from tests.test_brain_saved_historical_support import saved_dispute_revision
from tests.test_brain_saved_record_support import current, reseal
from tests.test_brain_source_support_verifiers import coverage, disposition

V1 = "owned_coverage_application_v1"
V2 = "owned_coverage_application_v2"
STAGES = ("dispute_review", "detail_review")


def history_fixture(client, wired, monkeypatch, *, stage="detail_review", relation="corrects"):
    if stage == "dispute_review":
        model, saved = saved_dispute_revision(client, wired, monkeypatch, relation)
    else:
        model, _, _, _, saved = saved_revision(client, wired, monkeypatch, relation)
    context = current(wired, saved)
    memo = owner._SavedExecutionMemo(saved)
    history = owner._saved_historical_support(
        saved, context[0], disputes=context[1], details=context[2], _memo=memo)
    return model, saved, context, memo, history


def selectors(history):
    return {stage: {identity: deepcopy(entry["selector"]) for identity, entry in rows.items()}
            for stage, rows in history.items() if rows}


def fresh_application(saved, context, history, *, stage="detail_review", represented=True):
    sources = deepcopy(saved.brain_chat[-1]["response"]["material_coverage"]["source_treatments"])
    original = history[stage][TARGET]["record_support"]
    primary = next(iter(original["source_references"].values()))
    selected_sources = {identity for identity, source in sources.items()
                        if all(source[key] == primary[key]
                               for key in ("turn_id", "role", "quoted"))}
    assert selected_sources
    raw = coverage(sources, dispositions=[
        disposition(identity, source,
                    status="represented" if represented and identity in selected_sources
                    else "outside_scope",
                    record_ids=(TARGET,) if represented and identity in selected_sources else ())
        for identity, source in sources.items()])
    assessment = record_review.checked_coverage(
        raw, tuple(sources), source_references=sources, record_ids=(TARGET,),
        record_support={TARGET: original})
    identity = {"matter_id": str(saved.id), "advocate_id": saved.advocate_id,
                "turn_id": "inherited-reading", "offer_digest": "fixture-inherited-offer"}
    scope = {"owner": identity, "requests": []}
    assessment.update(contract=record_review.ACCOUNT_COVERAGE_CONTRACT,
                      review_scope=scope, missing_sources=[])
    execution = {"contract": "material_execution_v1", "owner": identity,
                 "id": "mex_" + owner._digest(identity)[:32],
                 "expected_version": saved.version, "resulting_version": saved.version + 1,
                 "persistence": "prepared_for_commit", "requests": [], "review_scope": scope,
                 "stages": {name: {"state": "checked", "account_coverage":
                                   assessment if name == stage else {}} for name in STAGES},
                 "effects": {}}
    for kind, projection in (("disputes", context[1]), ("details", context[2])):
        execution["effects"][kind] = owner._material_effects(
            projection, projection, [], kind=kind, turn_id=identity["turn_id"])
        execution["stages"]["dispute_extraction" if kind == "disputes" else "detail_extraction"] = {
            "state": "returned", "proposals": 0, "admissible_proposals": 0}
    capture = {"states": {}, "proposals": {name: () for name in STAGES}, "candidates": (),
               "material": [], "opening": OpeningCandidate(False, "", ""),
               "opening_supported": False, "sources": sources,
               "latest_sources": {}, "prior_sources": {}, "opening_result": {}}
    apply = {"material": [], "source_treatments": sources, "latest_sources": {},
             "prior_sources": {}, "before_disputes": context[1], "before_details": context[2],
             "disputes": context[1], "details": context[2]}
    return execution, capture, apply


def capture_inherited(execution, capture, saved, memo, history):
    return owner._capture_coverage_application(
        execution, **capture, inherited_history=history, prefix_matter=saved, _memo=memo)


def apply_inherited(execution, receipt, apply, saved, memo):
    stamped = deepcopy(execution)
    stamped.setdefault("coverage_application_contract", receipt["contract"])
    return owner._apply_coverage_application(
        stamped, receipt, **apply, prefix_matter=saved, _memo=memo)


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("relation", ("corrects", "withdraws"))
def test_resolver_reconstructs_only_selected_stage_history_from_original_saved_proofs(
        client, wired, monkeypatch, stage, relation):
    model, saved, _, memo, history = history_fixture(
        client, wired, monkeypatch, stage=stage, relation=relation)
    selected = selectors(history)
    before = deepcopy((saved, selected))
    calls = len(model.seen if hasattr(model, "seen") else model.calls)
    result = owner._resolve_inherited_history(saved, selected, _memo=memo)
    assert result == {stage: {TARGET: history[stage][TARGET]["historical_result"]}}
    assert (saved, selected) == before
    assert len(model.seen if hasattr(model, "seen") else model.calls) == calls
    assert wired.store.load(saved.id) == saved
    result[stage][TARGET]["original_record_support"]["review"]["reason"] = "Presentation copy"
    assert owner._resolve_inherited_history(saved, selected, _memo=memo) == {
        stage: {TARGET: history[stage][TARGET]["historical_result"]}}


@pytest.mark.parametrize("fault", (
    "not_map", "unknown_stage", "not_stage_map", "current_record", "foreign_record",
    "wrong_admission_turn", "wrong_admission_candidate", "wrong_retirement_turn",
    "wrong_retirement_result", "wrong_digest", "missing_field", "extra_field", "boolean_field",
))
def test_resolver_cannot_use_current_foreign_or_changed_history_selector(
        client, wired, monkeypatch, fault):
    _, saved, _, memo, history = history_fixture(client, wired, monkeypatch)
    selected = selectors(history)
    selector = selected["detail_review"][TARGET]
    if fault == "not_map":
        selected = []
    elif fault == "unknown_stage":
        selected["legal_review"] = selected.pop("detail_review")
    elif fault == "not_stage_map":
        selected["detail_review"] = []
    elif fault == "current_record":
        identity = saved.brain_chat[-1]["response"]["material"][0]["id"]
        selected["detail_review"][identity] = selected["detail_review"].pop(TARGET)
    elif fault == "foreign_record":
        selected["detail_review"]["foreign-record"] = selected["detail_review"].pop(TARGET)
    elif fault == "missing_field":
        selector.pop("proof_digest")
    elif fault == "extra_field":
        selector["review"] = history["detail_review"][TARGET]["record_support"]["review"]
    elif fault == "boolean_field":
        selector["admission_candidate_id"] = True
    else:
        field = {"wrong_admission_turn": "admission_turn_id",
                 "wrong_admission_candidate": "admission_candidate_id",
                 "wrong_retirement_turn": "retirement_turn_id",
                 "wrong_retirement_result": "retirement_result_id",
                 "wrong_digest": "proof_digest"}[fault]
        selector[field] = "foreign-selector-value"
    before = deepcopy((saved, selected))
    with pytest.raises(ExecutionEvidenceInvalid):
        owner._resolve_inherited_history(saved, selected, _memo=memo)
    assert (saved, selected) == before


def test_future_retirement_and_withdrawal_tombstone_cannot_supply_before_prefix_history(
        client, wired, monkeypatch):
    _, saved, _, memo, history = history_fixture(
        client, wired, monkeypatch, relation="withdraws")
    first = replace(saved, brain_chat=saved.brain_chat[:1], version=1)
    with pytest.raises(ExecutionEvidenceInvalid):
        owner._resolve_inherited_history(first, selectors(history), _memo=memo)
    tombstone = saved.brain_chat[-1]["response"]["material"][0]["id"]
    selected = {"detail_review": {tombstone: history["detail_review"][TARGET]["selector"]}}
    with pytest.raises(ExecutionEvidenceInvalid):
        owner._resolve_inherited_history(saved, selected, _memo=memo)


@pytest.mark.parametrize("stage", STAGES)
def test_fresh_capture_seals_only_selected_selectors_and_applies_exact_original_support(
        client, wired, monkeypatch, stage):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch, stage=stage)
    execution, capture, apply = fresh_application(saved, context, history, stage=stage)
    before = deepcopy((saved, execution, capture, history))
    receipt = capture_inherited(execution, capture, saved, memo, history)
    assert receipt["contract"] == V2 and receipt["inherited_history"] == selectors(history)
    assert set(receipt) == {"contract", "owner", "expected_version", "pre_application_assessments",
                           "bindings", "opening", "seal", "inherited_history"}
    assert receipt["seal"] == owner._digest({key: value for key, value in receipt.items()
                                             if key != "seal"})
    result = apply_inherited(execution, receipt, apply, saved, memo)[stage]
    assert result["state"] == "complete" and result["missing_source_ids"] == []
    represented = [row for row in result["dispositions"] if row["status"] == "represented"]
    assert represented and all(row["record_ids"] == [] for row in represented)
    assert all(row["historical_representations"][0]["record_id"] == TARGET for row in represented)
    assert result["post_application_contract"] == V2
    assert (saved, execution, capture, history) == before


@pytest.mark.parametrize("offered", (None, "empty", "unselected"))
def test_no_selected_inherited_history_keeps_existing_v1_capture(
        client, wired, monkeypatch, offered):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch)
    execution, capture, _ = fresh_application(saved, context, history, represented=False)
    original = owner._capture_coverage_application(execution, **capture)
    proposed = None if offered is None else {} if offered == "empty" else history
    receipt = capture_inherited(execution, capture, saved, memo, proposed)
    assert receipt == original and receipt["contract"] == V1
    assert "inherited_history" not in receipt


def test_fresh_capture_rejects_wrong_selected_selector_before_minting_receipt(
        client, wired, monkeypatch):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch)
    execution, capture, _ = fresh_application(saved, context, history)
    changed = deepcopy(history)
    changed["detail_review"][TARGET]["selector"]["proof_digest"] = "unverified-history"
    before = deepcopy((execution, changed, saved))
    with pytest.raises(ExecutionEvidenceInvalid):
        capture_inherited(execution, capture, saved, memo, changed)
    assert (execution, changed, saved) == before


def test_v2_requires_explicit_matching_execution_stamp_while_v1_keeps_missing_stamp_compatibility(
        client, wired, monkeypatch):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch)
    execution, capture, apply = fresh_application(saved, context, history)
    receipt = capture_inherited(execution, capture, saved, memo, history)
    assert "coverage_application_contract" not in execution
    with pytest.raises(ExecutionEvidenceInvalid):
        owner._apply_coverage_application(
            execution, receipt, **apply, prefix_matter=saved, _memo=memo)
    assert apply_inherited(execution, receipt, apply, saved, memo)["detail_review"]["state"] == (
        "complete")
    v1_execution, v1_capture, v1_apply = fresh_application(
        saved, context, history, represented=False)
    v1 = owner._capture_coverage_application(v1_execution, **v1_capture)
    assert v1["contract"] == V1 and "coverage_application_contract" not in v1_execution
    assert owner._apply_coverage_application(v1_execution, v1, **v1_apply)["detail_review"][
        "state"] == "complete"


@pytest.mark.parametrize("projection", ("before_disputes", "before_details"))
def test_v2_before_projection_must_equal_the_actual_prefix_projection(
        client, wired, monkeypatch, projection):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch)
    execution, capture, apply = fresh_application(saved, context, history)
    receipt = capture_inherited(execution, capture, saved, memo, history)
    changed = deepcopy(apply)
    changed[projection]["foreign_projection_metadata"] = True
    before = deepcopy((saved, execution, receipt, changed))
    with pytest.raises(ExecutionEvidenceInvalid):
        apply_inherited(execution, receipt, changed, saved, memo)
    assert (saved, execution, receipt, changed) == before


def fresh_observed_operation(client, wired, monkeypatch, *, relation, opening=False):
    observed, capture_owner = [], owner._capture_coverage_application

    def observe(execution, **kwargs):
        # Keep original fresh inputs before the public fixture mints/saves seals.
        observed.append(deepcopy((execution, kwargs)))
        return capture_owner(execution, **kwargs)

    monkeypatch.setattr(owner, "_capture_coverage_application", observe)
    _, saved = saved_dispute_revision(client, wired, monkeypatch, relation)
    execution, capture = observed[0 if opening else -1]
    length = 0 if opening else 1
    before = replace(saved, brain_chat=saved.brain_chat[:length],
                     version=execution["expected_version"])
    after = replace(saved, brain_chat=saved.brain_chat[:length + 1],
                    version=execution["resulting_version"])
    before_disputes, before_details = owner._record_projections(before, ())
    disputes, details = owner._record_projections(after, ())
    receipt = capture_owner(execution, **capture)
    # This is a fresh known-v2 fixture; the actual saved v1 history is untouched.
    receipt.update(contract=V2, inherited_history={})
    apply = {"material": capture["material"], "source_treatments": capture["sources"],
             "latest_sources": capture["latest_sources"], "prior_sources": capture["prior_sources"],
             "before_disputes": before_disputes, "before_details": before_details,
             "disputes": disputes, "details": details,
             "opening_result": capture["opening_result"] if opening else None}
    return saved, before, execution, receipt, apply


@pytest.mark.parametrize("domain", ("current", "history", "candidate", "retirement", "opening"))
def test_v2_stage_cannot_borrow_another_stages_owned_representation(
        client, wired, monkeypatch, domain):
    relation = "withdraws" if domain == "retirement" else "corrects"
    saved, before, execution, receipt, apply = fresh_observed_operation(
        client, wired, monkeypatch, relation=relation, opening=domain == "opening")
    faulty_stage = "dispute_review" if domain == "opening" else "detail_review"
    source_stage = "detail_review" if domain == "opening" else "dispute_review"
    reseal(receipt)
    memo = owner._SavedExecutionMemo(saved)
    baseline = apply_inherited(execution, receipt, apply, before, memo)
    original_opening = deepcopy(receipt["opening"])
    assessment = deepcopy(receipt["pre_application_assessments"][source_stage])
    identity = "O1" if domain == "opening" else "C1"
    result_id = receipt["bindings"][0]["result_id"]
    selected = []
    for portion in assessment["dispositions"]:
        choose = portion["source_id"] != "L1" if domain == "history" else (
            portion["source_id"] == "L1")
        portion.update(status="represented" if choose else "outside_scope",
                       record_ids=([TARGET if domain == "history" else result_id]
                                   if choose and domain in ("current", "history") else []),
                       candidate_ids=([identity]
                                      if choose and domain not in ("current", "history") else []))
        if choose:
            selected.append(portion["source_id"])
    assert selected
    receipt["pre_application_assessments"][faulty_stage] = assessment
    reseal(receipt)
    result = apply_inherited(execution, receipt, apply, before, memo)
    assert result[source_stage] == baseline[source_stage]
    if domain == "opening":
        # A checked heading survives, while actual detail coverage stays partial.
        assert result[source_stage]["state"] == "partial"
        assert receipt["opening"] == original_opening
        assert original_opening["review"]["verdict"] == "accept"
        assert original_opening["result"] == saved.brain_chat[0]["opening_result"]
    else:
        assert result[source_stage]["state"] == "complete"
    assert result[faulty_stage]["state"] == "partial"
    assert set(result[faulty_stage]["missing_source_ids"]) == set(selected)
    held = [row for row in result[faulty_stage]["dispositions"] if row["source_id"] in selected]
    assert all(row["status"] == "unresolved" and not row["record_ids"]
               and not row["candidate_ids"] and "historical_representations" not in row
               and "operation_representations" not in row for row in held)
    assert wired.store.load(saved.id) == saved


@pytest.mark.parametrize("boundary", ("capture", "apply"))
@pytest.mark.parametrize("fault", ("missing_prefix", "version", "owner", "self_turn"))
def test_selected_inherited_history_requires_owned_strict_before_prefix(
        client, wired, monkeypatch, boundary, fault):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch)
    execution, capture, apply = fresh_application(saved, context, history)
    receipt = capture_inherited(execution, capture, saved, memo, history)
    prefix = saved
    if fault == "missing_prefix":
        prefix = None
    elif fault == "version":
        execution["expected_version"] += 1
        execution["resulting_version"] += 1
    elif fault == "owner":
        execution["owner"]["matter_id"] = "foreign-owner"
    else:
        execution["owner"]["turn_id"] = saved.brain_chat[-1]["turn_id"]
    if boundary == "apply":
        # This receipt is still fresh declared input, never saved historical proof.
        receipt["owner"] = deepcopy(execution["owner"])
        receipt["expected_version"] = execution["expected_version"]
        reseal(receipt)
    with pytest.raises(ExecutionEvidenceInvalid):
        if boundary == "capture":
            capture_inherited(execution, capture, prefix, memo, history)
        else:
            apply_inherited(execution, receipt, apply, prefix, memo)


@pytest.mark.parametrize("fault", (
    "unknown_contract", "v1_inherited_field", "v2_missing_inherited", "extra_field",
    "inherited_review_field", "wrong_stage", "unselected_history", "execution_contract",
))
def test_saved_version_and_closed_receipt_fields_cannot_bypass_admission(
        client, wired, monkeypatch, fault):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch)
    execution, capture, apply = fresh_application(saved, context, history)
    receipt = capture_inherited(execution, capture, saved, memo, history)
    if fault == "unknown_contract":
        receipt["contract"] = "unknown_coverage_application"
    elif fault == "v1_inherited_field":
        receipt["contract"] = V1
    elif fault == "v2_missing_inherited":
        receipt.pop("inherited_history")
    elif fault == "extra_field":
        receipt["record_support"] = history["detail_review"][TARGET]["record_support"]
    elif fault == "inherited_review_field":
        receipt["inherited_history"]["detail_review"][TARGET]["review"] = {}
    elif fault == "wrong_stage":
        receipt["inherited_history"]["dispute_review"] = receipt["inherited_history"].pop(
            "detail_review")
    elif fault == "unselected_history":
        for portion in receipt["pre_application_assessments"]["detail_review"]["dispositions"]:
            portion.update(status="outside_scope", record_ids=[])
    else:
        execution["coverage_application_contract"] = V1
    reseal(receipt)
    with pytest.raises(ExecutionEvidenceInvalid):
        apply_inherited(execution, receipt, apply, saved, memo)


def test_empty_known_v2_history_is_harmless_and_does_not_invent_representations(
        client, wired, monkeypatch):
    _, saved, context, memo, history = history_fixture(client, wired, monkeypatch)
    execution, capture, apply = fresh_application(saved, context, history, represented=False)
    receipt = owner._capture_coverage_application(execution, **capture)
    expected = owner._apply_coverage_application(execution, receipt, **apply)
    receipt.update(contract=V2, inherited_history={"detail_review": {}})
    reseal(receipt)
    assert owner._resolve_inherited_history(saved, {}, _memo=memo) == {}
    assert owner._resolve_inherited_history(saved, {"detail_review": {}}, _memo=memo) == {
        "detail_review": {}}
    assert apply_inherited(execution, receipt, apply, saved, memo) == expected


def test_saved_v1_public_replay_remains_exact_without_inherited_fields_or_new_calls(
        client, wired, monkeypatch):
    capture = owner._capture_coverage_application

    def legacy_capture(execution, **kwargs):
        # Mint the explicit old contract before the first durable save. The
        # ordinary producer remains native; saved rows and seals are untouched.
        assert not any(kwargs.get("inherited_history", {}).values())
        kwargs["native_record_support"] = False
        return capture(execution, **kwargs)

    monkeypatch.setattr(owner, "_capture_coverage_application", legacy_capture)
    model, opened, latest, reply, saved = saved_revision(client, wired, monkeypatch, "corrects")
    receipt = reply["material_coverage"]["execution"]["coverage_application"]
    assert receipt["contract"] == V1 and "inherited_history" not in receipt
    calls = len(model.seen)
    replay = send(client, latest, "application-revision", opened=opened)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] and replay.json()["metrics"]["llm_calls"] == 0
    assert replay.json()["material_coverage"]["execution"] == (
        reply["material_coverage"]["execution"])
    assert replay.json()["continuation"] == reply["continuation"]
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved
