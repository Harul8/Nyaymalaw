"""Saved support is offered only from checked active record-result bindings.

Public fixtures declare semantic judgments; these tests exercise persistence,
original-prefix replay, provenance ownership and current supplier selection.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as owner
from nm.brain.conversation import IncompleteConversation
from tests.test_brain_material import material
from tests.test_brain_material_purpose import item, open_account, routed, seed_plan
from tests.test_brain_post_application_coverage_public import (
    ORIGINAL,
    TARGET,
    RawApplicationModel,
    saved_revision,
)


def current(wired, matter):
    return owner._current_records(wired.store, matter)


def read(matter, context):
    conversation, disputes, details = context
    return owner._saved_record_support(
        matter, conversation, disputes=disputes, details=details)


def reseal(receipt):
    receipt["seal"] = owner._digest({key: value for key, value in receipt.items() if key != "seal"})


def altered(matter):
    return replace(matter, brain_chat=deepcopy(matter.brain_chat))


def open_seed(client, wired, monkeypatch, *, mixed=False, scope="proposed"):
    if mixed:
        account = "The sender reports delivery but the recipient denies receiving the parcel."
        candidates = [material("dispute", account, account),
                      material("circumstance", account, account, placement="matter")]
        planned = routed(account, candidates=candidates, opening=True, items=[
            item(account, account, purposes=("account_contribution",),
                 intent="contribution", opening=True)])
    elif scope != "proposed":
        account = ORIGINAL
        planned = routed(account, candidates=[
            material("circumstance", account, account, scope=scope, placement="unresolved")],
            opening=True, items=[item(account, account, purposes=("account_contribution",),
                                     intent="contribution", opening=True)])
    else:
        account, planned = ORIGINAL, seed_plan(ORIGINAL)
    model = RawApplicationModel([planned])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="application-original")
    saved = wired.store.load(opened["matter_id"])
    return model, saved, current(wired, saved)


def expected_sources(saved_turn):
    return {identity: {field: treatment[field] for field in ("turn_id", "role", "quoted")}
            for identity, treatment in saved_turn["response"]["material_coverage"][
                "source_treatments"].items()}


def test_active_record_uses_its_original_saved_review_and_source_ids_without_new_calls(
        client, wired, monkeypatch):
    model, saved, context = open_seed(client, wired, monkeypatch)
    before, calls = deepcopy(saved), len(model.seen)
    result = read(saved, context)
    (binding,) = saved.brain_chat[0]["response"]["material_coverage"]["execution"][
        "coverage_application"]["bindings"]
    assert result == {"dispute_review": {}, "detail_review": {
        binding["result_id"]: {"review": binding["review"],
                               "source_references": expected_sources(saved.brain_chat[0])}}}
    assert saved == before and len(model.seen) == calls
    result["detail_review"][binding["result_id"]]["review"]["reason"] = "Presentation mutation"
    assert saved == before
    restored = read(saved, context)["detail_review"][binding["result_id"]]
    assert restored["review"] == binding["review"]


def test_both_record_stages_keep_their_actual_result_owners(client, wired, monkeypatch):
    _, saved, context = open_seed(client, wired, monkeypatch, mixed=True)
    result = read(saved, context)
    receipt = saved.brain_chat[0]["response"]["material_coverage"]["execution"][
        "coverage_application"]
    assert set(result["dispute_review"]) == {row["id"] for row in context[1]["rows"]}
    assert set(result["detail_review"]) == {row["id"] for row in context[2]["rows"]}
    assert result["dispute_review"] and result["detail_review"]
    for binding in receipt["bindings"]:
        assert result[binding["stage"]][binding["result_id"]]["review"] == binding["review"]


@pytest.mark.parametrize("relation", ("corrects", "withdraws"))
def test_superseded_and_withdrawn_entries_are_not_current_support_suppliers(
        client, wired, monkeypatch, relation):
    model, _, _, _, saved = saved_revision(client, wired, monkeypatch, relation)
    context = current(wired, saved)
    before, calls = deepcopy(saved), len(model.seen)
    result = read(saved, context)
    assert TARGET not in result["detail_review"]
    assert set(result["detail_review"]) == {row["id"] for row in context[2]["rows"]}
    if relation == "withdraws":
        assert result == {"dispute_review": {}, "detail_review": {}}
    else:
        (binding,) = saved.brain_chat[-1]["response"]["material_coverage"]["execution"][
            "coverage_application"]["bindings"]
        assert result["detail_review"][binding["result_id"]] == {
            "review": binding["review"],
            "source_references": expected_sources(saved.brain_chat[-1])}
    assert saved == before and len(model.seen) == calls


def test_held_scope_is_not_offered_as_current_record_support(client, wired, monkeypatch):
    _, saved, context = open_seed(client, wired, monkeypatch, scope="uncertain")
    assert context[2]["excluded_scope"]
    assert read(saved, context) == {"dispute_review": {}, "detail_review": {}}


def test_source_catalogue_is_checked_first_and_execution_uses_original_prefix(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    context = current(wired, saved)
    calls = []
    source_check, replay_check = owner._saved_source_treatments, owner._validate_execution_replay

    def sources(*args, **kwargs):
        calls.append(("sources",))
        return source_check(*args, **kwargs)

    def replay(matter, row, *, prior_conversation, **kwargs):
        calls.append(("replay", row["turn_id"], prior_conversation))
        return replay_check(matter, row, prior_conversation=prior_conversation, **kwargs)

    monkeypatch.setattr(owner, "_saved_source_treatments", sources)
    monkeypatch.setattr(owner, "_validate_execution_replay", replay)
    result = read(saved, context)
    assert result["detail_review"] and calls[0] == ("sources",)
    assert [row[1] for row in calls if row[0] == "replay"] == [
        row["turn_id"] for row in saved.brain_chat]
    assert all(row[2] == () for row in calls if row[0] == "replay")


@pytest.mark.parametrize("fault", (
    "unknown_contract", "missing_receipt", "missing_snapshot", "foreign_owner",
    "foreign_result", "wrong_stage", "source_identity", "review_source", "explicit_bad_range",
))
def test_claimed_modern_support_cannot_bypass_replay_or_original_source_ownership(
        client, wired, monkeypatch, fault):
    model, saved, context = open_seed(client, wired, monkeypatch)
    changed = altered(saved)
    response = changed.brain_chat[0]["response"]
    coverage = response["material_coverage"]
    execution = coverage["execution"]
    receipt = execution["coverage_application"]
    if fault == "unknown_contract":
        execution["coverage_application_contract"] = "unsupported_application_version"
    elif fault == "missing_receipt":
        del execution["coverage_application"]
    elif fault == "missing_snapshot":
        del response["continuation"]["record_snapshot"]
    elif fault == "foreign_owner":
        execution["owner"]["matter_id"] = "another-matter"
    elif fault == "foreign_result":
        receipt["bindings"][0]["result_id"] = "unowned-result"
    elif fault == "wrong_stage":
        receipt["bindings"][0]["stage"] = "dispute_review"
    elif fault == "source_identity":
        coverage["source_treatments"]["L1"]["quoted"] = "Another original account."
    elif fault == "review_source":
        account = receipt["bindings"][0]["review"]["account_check"]
        account["source_ids"] = ["foreign"]
        account["source_checks"][0]["source_id"] = "foreign"
    else:
        receipt["bindings"][0]["review"]["account_check"]["source_checks"][0][
            "support_spans"][0]["start"] = False
    if fault not in ("missing_receipt", "unknown_contract", "missing_snapshot", "foreign_owner"):
        reseal(receipt)
    before, calls = deepcopy(changed), len(model.seen)
    failure = owner.BrainRefused if fault == "foreign_owner" else IncompleteConversation
    with pytest.raises(failure):
        read(changed, context)
    assert changed == before and len(model.seen) == calls and wired.store.load(saved.id) == saved


def test_legacy_absent_result_proof_remains_readable_but_unoffered(client, wired, monkeypatch):
    _, saved, context = open_seed(client, wired, monkeypatch)
    changed = altered(saved)
    response = changed.brain_chat[0]["response"]
    response["material_coverage"].pop("execution")
    response["continuation"].pop("record_snapshot")
    assert read(changed, context) == {"dispute_review": {}, "detail_review": {}}


def test_legacy_review_without_explicit_portions_is_readable_but_not_new_certified_support(
        client, wired, monkeypatch):
    _, saved, context = open_seed(client, wired, monkeypatch)
    changed = altered(saved)
    receipt = changed.brain_chat[0]["response"]["material_coverage"]["execution"][
        "coverage_application"]
    for check in receipt["bindings"][0]["review"]["account_check"]["source_checks"]:
        del check["support_spans"]
    reseal(receipt)
    owner._validate_execution_replay(changed, changed.brain_chat[0], prior_conversation=())
    assert read(changed, context) == {"dispute_review": {}, "detail_review": {}}


def test_default_projection_lookup_matches_checked_supplied_projections(client, wired, monkeypatch):
    _, saved, context = open_seed(client, wired, monkeypatch)
    assert owner._saved_record_support(saved, context[0]) == read(saved, context)
