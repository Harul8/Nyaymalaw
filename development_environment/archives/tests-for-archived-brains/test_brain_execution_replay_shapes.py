"""Saved code-owned JSON cannot escape the replay integrity refusal boundary.

The public tests corrupt confirmed offline receipts without touching sources,
records or replies. These are storage-shape tests, not semantic-model claims.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn
from nm.brain.conversation import IncompleteConversation
from tests.test_brain_mutation_saved_replay import saved_correction

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("fault", [
    "requests_absent", "requests_null", "requests_object", "request_null", "request_list",
    "request_number", "request_missing_index", "request_bool_index", "request_string_index",
    "request_negative_index", "request_skipped_index", "duplicate_request_index",
    "requirement_absent", "requirement_list", "requirement_missing_kind",
    "scope_absent", "scope_null", "scope_list", "scope_missing_owner", "scope_wrong_owner",
    "scope_missing_requests", "scope_null_requests", "scope_object_requests",
    "scope_missing_base", "scope_base_null", "scope_wrong_requirement",
    "scope_alias_null", "scope_alias_list", "scope_alias_bool_index",
    "scope_alias_unknown_index", "scope_alias_missing_task",
])
def test_malformed_saved_execution_refuses_public_replay_before_consumers_or_calls(
    client, wired, monkeypatch, fault
):
    identity = "saved-request-shape-" + fault
    model, opened, _, saved, _, _, _ = saved_correction(client, wired, monkeypatch, identity)
    changed = deepcopy(saved.brain_chat)
    execution = changed[-1]["response"]["material_coverage"]["execution"]
    scope = execution["review_scope"]
    if fault == "requests_absent":
        execution.pop("requests")
    elif fault in ("requests_null", "requests_object"):
        execution["requests"] = None if fault.endswith("null") else {}
    elif fault in ("request_null", "request_list", "request_number"):
        execution["requests"][0] = {"request_null": None, "request_list": [],
                                     "request_number": 7}[fault]
    elif fault == "request_missing_index":
        execution["requests"][0].pop("request_index")
    elif fault in ("request_bool_index", "request_string_index", "request_negative_index",
                   "request_skipped_index"):
        execution["requests"][0]["request_index"] = {
            "request_bool_index": False, "request_string_index": "0",
            "request_negative_index": -1, "request_skipped_index": 2,
        }[fault]
    elif fault == "duplicate_request_index":
        execution["requests"].append(deepcopy(execution["requests"][0]))
    elif fault == "requirement_absent":
        execution["requests"][0].pop("record_requirement")
    elif fault in ("requirement_list", "requirement_missing_kind"):
        execution["requests"][0]["record_requirement"] = [] if fault.endswith("list") else {}
    elif fault == "scope_absent":
        execution.pop("review_scope")
    elif fault in ("scope_null", "scope_list"):
        execution["review_scope"] = None if fault.endswith("null") else []
    elif fault == "scope_missing_owner":
        scope.pop("owner")
    elif fault == "scope_wrong_owner":
        scope["owner"]["turn_id"] = "another-owned-instruction"
    elif fault == "scope_missing_requests":
        scope.pop("requests")
    elif fault in ("scope_null_requests", "scope_object_requests"):
        scope["requests"] = None if fault == "scope_null_requests" else {}
    elif fault == "scope_missing_base":
        scope["requests"] = []
    elif fault == "scope_base_null":
        scope["requests"][0] = None
    elif fault == "scope_wrong_requirement":
        scope["requests"][0]["record_requirement"] = None
    else:
        alias = {"request_index": 0, "record_requirement":
                 deepcopy(execution["requests"][0]["record_requirement"]),
                 "task_id": "prior-task", "request": "Review the original account.",
                 "matter_scope": "current"}
        if fault == "scope_alias_null":
            alias = None
        elif fault == "scope_alias_list":
            alias = []
        elif fault == "scope_alias_bool_index":
            alias["request_index"] = True
        elif fault == "scope_alias_unknown_index":
            alias["request_index"] = 1
        elif fault == "scope_alias_missing_task":
            alias.pop("task_id")
        scope["requests"].append(alias)
    wired.store.commit(replace(saved, brain_chat=changed, version=saved.version + 1),
                       expected_version=saved.version)
    before = deepcopy(wired.store.load(opened["matter_id"]))
    calls = len(model.seen)
    checked = turn._checked_execution_requests
    issues = []

    def trace(receipt):
        try:
            return checked(receipt)
        except IncompleteConversation as exc:
            issues.append(str(exc))
            raise

    monkeypatch.setattr(turn, "_checked_execution_requests", trace)
    response = client.post("/api/turn", json={
        "message": model.dossier.message, "turn_id": identity,
        "matter_id": opened["matter_id"], "chat_id": opened["chat_id"],
    })
    assert response.status_code == 409, response.text
    assert issues, "The owning shape preflight must fire before result-seal consumers"
    assert response.json()["detail"]["code"] == "brain_refused"
    assert "elements" not in response.json()
    assert len(model.seen) == calls
    assert wired.store.load(opened["matter_id"]) == before


def test_owned_review_scope_preserves_multiple_inherited_aliases_and_legacy_empty_requests():
    requirement = {"kind": "review", "target_ids": [], "operation": "none",
                   "success_condition": "Review the complete attributed account."}
    execution = {"owner": {"turn_id": "current"}, "requests": [{
        "request_index": 0, "record_requirement": requirement, "relation": "continues",
        "intent": "request", "matter_scope": "current",
    }]}
    progress = {"rows": [{"id": identity, "kind": "task", "text": "Review saved account.",
                           "matter_scope": "current", "record_requirement": requirement}
                          for identity in ("prior-a", "prior-b")]}
    execution["review_scope"] = turn._execution_review_scope(execution, progress)
    original = deepcopy(execution)
    assert len(execution["review_scope"]["requests"]) == 3
    assert turn._checked_execution_requests(execution) == execution["requests"]
    assert execution == original
    assert turn._checked_execution_requests({"owner": {}, "requests": []}) == []
    assert turn._checked_execution_requests({"owner": {}, "requests": [],
                                            "review_scope": {"owner": {}, "requests": []}}) == []
    legacy = {"owner": {}, "requests": [{"request_index": 0, "record_requirement": None}]}
    assert turn._checked_execution_requests(legacy) == legacy["requests"]


def test_historical_request_metadata_is_preserved_without_inventing_typed_requirements():
    legacy = {"owner": {}, "requests": [{
        "request_index": 0, "request": "Review this original account.",
        "material_purposes": ["account_contribution"], "fulfillment": "unassessed",
    }]}
    original = deepcopy(legacy)
    assert turn._checked_execution_requests(legacy) is legacy["requests"]
    assert legacy == original
    assert "record_requirement" not in legacy["requests"][0]
    for stamp in ("mutation_authority_contract", "mutation_authorities", "review_scope"):
        changed = deepcopy(legacy)
        changed[stamp] = None
        with pytest.raises(IncompleteConversation, match="record requirement is unreadable"):
            turn._checked_execution_requests(changed)
        with pytest.raises(IncompleteConversation):
            turn._checked_execution_requests({"owner": {}, "requests": [], stamp: None})
    for malformed in ([], {}, {"target_ids": []}):
        changed = deepcopy(legacy)
        changed["requests"][0]["record_requirement"] = malformed
        with pytest.raises(IncompleteConversation, match="record requirement is unreadable"):
            turn._checked_execution_requests(changed)


def test_public_historical_receipt_replays_original_untyped_requests_without_calls_or_write(
    client, wired, monkeypatch
):
    from tests.test_brain_material import send
    from tests.test_brain_material_purpose import PurposeModel, open_account, seed_plan

    account = "The freight was delivered on 11 August."
    model = PurposeModel([seed_plan(account)])
    opened = open_account(client, wired, monkeypatch, model, account,
                          turn_id="untyped-historical-original")
    saved = wired.store.load(opened["matter_id"])
    changed = deepcopy(saved.brain_chat)
    row = changed[0]
    execution = row["response"]["material_coverage"]["execution"]
    # The first material_execution_v1 contract carried these four request
    # fields. Typed requirements, review scopes and result snapshots arrived
    # later without changing that receipt's contract name.
    execution["requests"] = [{key: request[key] for key in (
        "request_index", "request", "material_purposes", "fulfillment")}
        for request in execution["requests"]]
    for field in ("mutation_authority_contract", "mutation_authorities", "review_scope", "display"):
        execution.pop(field, None)
    row["response"].pop("continuation")
    expected_execution = deepcopy(execution)
    expected_elements = deepcopy(row["response"]["elements"])
    wired.store.commit(replace(saved, brain_chat=changed, version=saved.version + 1),
                       expected_version=saved.version)
    before = deepcopy(wired.store.load(opened["matter_id"]))
    calls = len(model.seen)

    response = send(client, account, "untyped-historical-original")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["replayed"] is True
    assert result["material_coverage"]["execution"] == expected_execution
    assert result["elements"] == expected_elements
    assert "record_requirement" not in result["material_coverage"]["execution"]["requests"][0]
    assert len(model.seen) == calls
    assert wired.store.load(opened["matter_id"]) == before


def test_valid_saved_scoped_correction_still_replays_exactly_without_calls_or_write(
    client, wired, monkeypatch
):
    identity = "saved-request-shape-valid"
    model, opened, reply, saved, _, _, _ = saved_correction(client, wired, monkeypatch, identity)
    calls = len(model.seen)
    response = client.post("/api/turn", json={
        "message": model.dossier.message, "turn_id": identity,
        "matter_id": opened["matter_id"], "chat_id": opened["chat_id"],
    })
    assert response.status_code == 200, response.text
    assert response.json()["replayed"] is True
    assert response.json()["elements"] == reply["elements"]
    assert (response.json()["material_coverage"]["execution"]
            == reply["material_coverage"]["execution"])
    assert len(model.seen) == calls
    assert wired.store.load(opened["matter_id"]) == saved


def test_scope_held_dispute_is_in_receipt_without_losing_independent_material(
    client, wired, monkeypatch
):
    from tests.brain_golden_pressure_fixture import (
        GoldenModel,
        ThreadGoldenModel,
        composite,
        release,
    )
    from tests.test_brain_golden_boundaries import owned_outcome

    dossier = composite(0)
    seeded = ThreadGoldenModel(dossier)
    opened, _, previous = release(
        client, wired, monkeypatch, seeded, "scope-dispute-telemetry-seed")
    assert len(previous.open_disputes) >= 2
    allowed, wrong_target = previous.open_disputes[:2]
    template = deepcopy(seeded.issue_rows[1])
    prior_quote = dossier.source_quotes[template["source_id"]]
    standard = owned_outcome("none", linked=True)
    selected_support = {}

    def wrong_owned_target(operation, payload, schema, data, model):
        data = standard(operation, payload, schema, data, model)
        original = payload.get("original_input", payload)
        if operation == "extract_disputes":
            matches = [span["id"] for message in original["earlier_conversation"]
                       if message["role"] == "advocate"
                       for span in message["source_spans"]
                       if span["text"].strip() == prior_quote]
            assert len(matches) == 1
            selected_support["source_id"] = matches[0]
            return {"new_items": [], "changes": [{
                **template, "source_id": "L1", "prior_source_ids": matches,
                "matter_scope": "current", "relation": "corrects",
                "related_dispute_ids": [wrong_target["id"]],
            }]}
        if operation == "verify_disputes":
            for verdict in data["verdicts"]:
                support = selected_support["source_id"]
                verdict.update(verdict="accept", operation_supported=True,
                               candidate_role="independent_dispute")
                verdict["account_check"].update(
                    content_role="reported_matter_account", supported=True,
                    source_ids=[support], source_checks=[{
                        "source_id": support, "supplies_account_content": True,
                        "supports_proposal": True,
                        "support_spans": [{"start": 0, "end": len(
                            original["source_treatments"][support]["quoted"])}],
                        "reason": "The scripted original account supports this formulation.",
                    }])
                verdict["target_checks"] = [{
                    "target_id": wrong_target["id"],
                    "identity_relation": "same_underlying_account", "account_preserved": True,
                    "required_peer_ids": [],
                    "reason": "The scripted Judge incorrectly approves this owned target.",
                }]
        return data

    model = GoldenModel(dossier, mutation_scopes=[{
        "authority_kind": "interpretation_review", "authority_source_ids": ["L1"],
        "target_scope": "exact", "target_ids": [allowed["id"]],
        "permitted_relations": ["corrects"],
    }], hook=wrong_owned_target)
    model.semantic_decisions[template["statement"]] = True
    model.semantic_sources[template["statement"]] = "L1"
    for attributes in model.semantic_attributes.values():
        attributes["matter_scope"] = "current"
    reply, saved, conversation = release(
        client, wired, monkeypatch, model, "scope-dispute-telemetry", opened=opened)
    execution = reply["material_coverage"]["execution"]
    assert execution["withheld_proposals"]["disputes"] == ["C1"]
    assert execution["rejected_proposals"]["disputes"] == []
    assert execution["unread_proposals"]["disputes"] == []
    assert conversation.open_disputes == previous.open_disputes
    assert len(reply["material"]) == len(dossier.details)
    assert all(row["kind"] != "dispute" for row in reply["material"])
    assert saved.brain_chat[-1]["response"]["material_coverage"]["execution"] == execution
    assert model.operation_counts["verify_disputes"] == 1
