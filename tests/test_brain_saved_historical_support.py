"""Retired support keeps original admission proof separate from preservation.

Public fixtures declare independent judgments. These tests certify replay,
source/result ownership and immutable history dependencies, not model quality
or activation of inherited history in fresh coverage or durable replay.
"""

from copy import deepcopy

import pytest

from nm.brain import turn as owner
from nm.brain.conversation import IncompleteConversation
from tests.test_brain_board_proposals import dispute
from tests.test_brain_dispute_transitions import TransitionModel
from tests.test_brain_material import mutation_scope, plan, send
from tests.test_brain_post_application_coverage_public import (
    CHANGED,
    ORIGINAL,
    TARGET,
    WITHDRAWN,
    saved_revision,
)
from tests.test_brain_saved_record_support import (
    altered,
    current,
    expected_sources,
    open_seed,
    reseal,
)

CONTRACT = "inherited_history_dependency_v1"
STAGES = ("dispute_review", "detail_review")


def read(matter, context):
    conversation, disputes, details = context
    return owner._saved_historical_support(
        matter, conversation, disputes=disputes, details=details)


def model_calls(model):
    return len(model.seen if hasattr(model, "seen") else model.calls)


def binding(saved_turn):
    bindings = saved_turn["response"]["material_coverage"]["execution"][
        "coverage_application"]["bindings"]
    assert len(bindings) == 1
    return bindings[0]


def retirement_effect(saved_turn):
    execution = saved_turn["response"]["material_coverage"]["execution"]
    effects = [effect for effect in owner.effect_catalogue(execution).values()
               if TARGET in effect["retired_target_ids"]]
    assert len(effects) == 1
    return effects[0]


def expected_entry(saved, context, stage):
    admission, retirement = saved.brain_chat
    admitted, retired = binding(admission), binding(retirement)
    projection = context[1 if stage == "dispute_review" else 2]
    record = next(row for row in projection["history"] if row["id"] == TARGET)
    support = {"review": admitted["review"], "source_references": expected_sources(admission)}
    effect = retirement_effect(retirement)
    selector = {"admission_turn_id": admission["turn_id"],
                "admission_candidate_id": admitted["candidate_id"],
                "retirement_turn_id": retirement["turn_id"],
                "retirement_result_id": retired["result_id"]}
    payload = {"contract": CONTRACT, "stage": stage, "record_id": TARGET,
               "selector": selector, "record": record, "record_support": support,
               "retirement": {"effect": effect, "proposal": retired["proposal"],
                              "review": retired["review"]}}
    return {"record_support": support,
            "selector": {**selector, "proof_digest": owner._digest(payload)},
            "historical_result": {
                "record": record, "historical_record": record, "effect": effect,
                "proposal": retired["proposal"],
                "review": {**retired["review"], "proposal": retired["proposal"]},
                "original_record_support": support}}


def saved_dispute_revision(client, wired, monkeypatch, relation):
    latest = WITHDRAWN if relation == "withdraws" else CHANGED
    original = dispute("Reported receipt custody", ORIGINAL)
    changed = dispute("Revised reported custody", latest, relation=relation, scope="current",
                      prior=[{"turn_id": "application-original", "role": "advocate",
                              "quoted": ORIGINAL}], related=(TARGET,))
    model = TransitionModel([
        plan(ORIGINAL, candidates=[original], opening=True,
             material_purposes=("account_contribution",)),
        plan(latest, candidates=[changed], material_purposes=("account_contribution",),
             record_disposition="performed",
             mutation_scopes=[mutation_scope(TARGET, relations=(relation,))]),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, ORIGINAL, "application-original")
    assert opened.status_code == 200, opened.text
    reply = send(client, latest, "application-revision", opened=opened.json())
    assert reply.status_code == 200, reply.text
    return model, wired.store.load(opened.json()["matter_id"])


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("relation", ("corrects", "withdraws"))
def test_exact_retired_entry_retains_original_admission_and_owned_retirement(
        client, wired, monkeypatch, stage, relation):
    if stage == "dispute_review":
        model, saved = saved_dispute_revision(client, wired, monkeypatch, relation)
    else:
        model, _, _, _, saved = saved_revision(client, wired, monkeypatch, relation)
    context = current(wired, saved)
    before, calls = deepcopy(saved), model_calls(model)
    expected = {name: {} for name in STAGES}
    expected[stage][TARGET] = expected_entry(saved, context, stage)
    result = read(saved, context)
    assert result == expected
    # Current successor and the withdrawal tombstone are not historical targets.
    retired = binding(saved.brain_chat[-1])
    assert retired["result_id"] not in result[stage]
    assert set(result[stage][TARGET]) == {"record_support", "selector", "historical_result"}
    assert set(result[stage][TARGET]["selector"]) == {
        "admission_turn_id", "admission_candidate_id", "retirement_turn_id",
        "retirement_result_id", "proof_digest"}
    assert saved == before and model_calls(model) == calls
    assert wired.store.load(saved.id) == saved


def test_repeated_local_candidate_and_source_ids_keep_their_original_turn_owners(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    result = read(saved, current(wired, saved))["detail_review"][TARGET]
    assert binding(saved.brain_chat[0])["candidate_id"] == (
        binding(saved.brain_chat[-1])["candidate_id"]) == "D1"
    original = result["record_support"]
    assert original["source_references"]["L1"]["quoted"] == ORIGINAL
    assert original["source_references"]["L1"]["turn_id"] == "application-original"
    assert expected_sources(saved.brain_chat[-1])["L1"]["quoted"] == CHANGED
    assert original["review"] != result["historical_result"]["review"]
    assert result["selector"]["admission_turn_id"] != result["selector"]["retirement_turn_id"]


@pytest.mark.parametrize("scope", ("proposed", "uncertain"))
def test_active_and_held_entries_are_not_inherited_history(client, wired, monkeypatch, scope):
    _, saved, context = open_seed(client, wired, monkeypatch, scope=scope)
    assert read(saved, context) == {stage: {} for stage in STAGES}
    current_support = owner._saved_record_support(
        saved, context[0], disputes=context[1], details=context[2])
    assert bool(current_support["detail_review"]) == (scope == "proposed")


def test_historical_and_current_support_remain_separate_and_do_not_mutate_saved_input(
        client, wired, monkeypatch):
    model, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    context = current(wired, saved)
    before, calls = deepcopy(saved), len(model.seen)
    history = read(saved, context)
    active = owner._saved_record_support(
        saved, context[0], disputes=context[1], details=context[2])
    assert set(history["detail_review"]) == {TARGET}
    assert TARGET not in active["detail_review"] and active["detail_review"]
    assert set(history["detail_review"]).isdisjoint(active["detail_review"])
    history["detail_review"][TARGET]["record_support"]["review"]["reason"] = "Presentation copy"
    history["detail_review"][TARGET]["historical_result"]["record"]["statement"] = "Changed copy"
    assert saved == before and len(model.seen) == calls
    assert read(saved, context)["detail_review"][TARGET] == expected_entry(
        saved, context, "detail_review")


def test_historical_supplier_validation_keeps_original_prefix_and_source_check_order(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    context, calls = current(wired, saved), []
    sources, replay = owner._saved_source_treatments, owner._validate_execution_replay

    def source_check(*args, **kwargs):
        calls.append(("sources",))
        return sources(*args, **kwargs)

    def replay_check(matter, row, *, prior_conversation):
        calls.append(("replay", row["turn_id"], prior_conversation))
        return replay(matter, row, prior_conversation=prior_conversation)

    monkeypatch.setattr(owner, "_saved_source_treatments", source_check)
    monkeypatch.setattr(owner, "_validate_execution_replay", replay_check)
    assert read(saved, context)["detail_review"]
    assert calls[0] == ("sources",)
    assert [row[1] for row in calls if row[0] == "replay"] == [
        row["turn_id"] for row in saved.brain_chat]
    assert all(row[2] == () for row in calls if row[0] == "replay")


@pytest.mark.parametrize("legacy", ("absent_admission", "no_original_portions"))
def test_successor_preservation_cannot_invent_missing_original_admission_support(
        client, wired, monkeypatch, legacy):
    capture = owner._capture_coverage_application

    def legacy_admission(execution, **kwargs):
        receipt = capture(execution, **kwargs)
        if execution["owner"]["turn_id"] != "application-original":
            return receipt
        # Declare older admission evidence before its first durable save/seals.
        # Never alter a saved receipt or regenerate its historical work seal.
        if legacy == "absent_admission":
            return None
        for check in receipt["bindings"][0]["review"]["account_check"]["source_checks"]:
            check.pop("support_spans")
        reseal(receipt)
        return receipt

    monkeypatch.setattr(owner, "_capture_coverage_application", legacy_admission)
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    context = current(wired, saved)
    owner._validate_execution_replay(saved, saved.brain_chat[0], prior_conversation=())
    owner._validate_execution_replay(saved, saved.brain_chat[-1], prior_conversation=())
    assert binding(saved.brain_chat[-1])["review"]["target_checks"][0]["account_preserved"]
    assert read(saved, context) == {stage: {} for stage in STAGES}


@pytest.mark.parametrize("phase", ("admission", "retirement"))
@pytest.mark.parametrize("fault", (
    "unknown_contract", "missing_receipt", "missing_snapshot", "foreign_owner",
    "foreign_result", "source_identity", "foreign_review_source", "bad_explicit_portion",
))
def test_either_modern_execution_must_replay_before_offering_history(
        client, wired, monkeypatch, phase, fault):
    model, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    changed, context = altered(saved), current(wired, saved)
    saved_turn = changed.brain_chat[0 if phase == "admission" else -1]
    response = saved_turn["response"]
    coverage = response["material_coverage"]
    execution = coverage["execution"]
    receipt = execution["coverage_application"]
    if fault == "unknown_contract":
        execution["coverage_application_contract"] = "unknown_history_contract"
    elif fault == "missing_receipt":
        execution.pop("coverage_application")
    elif fault == "missing_snapshot":
        response["continuation"].pop("record_snapshot")
    elif fault == "foreign_owner":
        execution["owner"]["matter_id"] = "foreign-matter"
    elif fault == "foreign_result":
        receipt["bindings"][0]["result_id"] = "foreign-result"
    elif fault == "source_identity":
        coverage["source_treatments"]["L1"]["turn_id"] = "unowned-original-turn"
    elif fault == "foreign_review_source":
        check = receipt["bindings"][0]["review"]["account_check"]
        check["source_ids"] = ["foreign"]
        check["source_checks"][0]["source_id"] = "foreign"
    else:
        receipt["bindings"][0]["review"]["account_check"]["source_checks"][0][
            "support_spans"][0]["end"] = False
    if fault in ("foreign_result", "foreign_review_source", "bad_explicit_portion"):
        reseal(receipt)
    before, calls = deepcopy(changed), len(model.seen)
    failure = owner.BrainRefused if fault == "foreign_owner" else IncompleteConversation
    with pytest.raises(failure):
        read(changed, context)
    assert changed == before and len(model.seen) == calls
    assert wired.store.load(saved.id) == saved


@pytest.mark.parametrize("fault", ("retired_target", "preservation", "operation_source"))
def test_history_requires_exact_retired_target_and_checked_preservation(
        client, wired, monkeypatch, fault):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "withdraws")
    changed, context = altered(saved), current(wired, saved)
    retired = changed.brain_chat[-1]
    execution = retired["response"]["material_coverage"]["execution"]
    receipt = execution["coverage_application"]
    (operation,) = execution["effects"]["details"]["operations"]
    if fault == "retired_target":
        operation["retired_target_ids"] = ["foreign-target"]
    elif fault == "preservation":
        receipt["bindings"][0]["review"]["target_checks"][0]["account_preserved"] = False
        reseal(receipt)
    else:
        operation["source_references"][0]["turn_id"] = "foreign-source-turn"
    with pytest.raises(IncompleteConversation):
        read(changed, context)


def test_default_projection_lookup_matches_owned_historical_projection_inputs(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    context = current(wired, saved)
    assert owner._saved_historical_support(saved, context[0]) == read(saved, context)
