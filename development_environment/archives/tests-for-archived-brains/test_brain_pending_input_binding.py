"""Owned pending-input indexing only; no model calls or semantic qualification.

The supplied plan is an interpretation proposal. Missing response units must
not acquire a checked task association, completion, or execution permission.
Existing accepted-unit fixtures exercise projection coexistence, not whether a
real independent reviewer would accept their content.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as turn_owner
from nm.brain import work_state as owner
from nm.brain.conversation import (
    IncompleteConversation,
    OpeningCandidate,
    TurnPlan,
    WorkItem,
)
from nm.work_the_file.matter_contracts import Matter
from tests.test_brain_work_record_outcome import checked_reply

CONTRACT = "accepted_pending_input_v1"
TURN_ID = "pending-input-turn"
WORDS = (
    "  The signed inventory was received on 6 August.\n"
    "Please examine the reported account; preserve its stated uncertainty.  "
)
REQUEST = "Examine the attributed inventory account."
NONE = {"kind": "none", "target_ids": [], "operation": "none", "success_condition": ""}
OMITTED = object()


def matter():
    return Matter(id="pending-input-matter", advocate_id="adv_pending", title="Inventory account")


def item(request=REQUEST, *, intent="request", relation="new", scope="current"):
    return WorkItem(
        request, relation, scope, "ordinary", "answer", intent=intent,
        material_purposes=(), record_requirement=deepcopy(NONE), mutation_scopes=(),
    )


def plan(*items):
    return TurnPlan(items or (item(),), "", OpeningCandidate(False, "", ""), False)


def response(*, peer=False):
    result = (checked_reply(TURN_ID, WORDS, status="none", question=False)
              if peer else {"units": [], "coverage": []})
    result["coverage"] = ([{"request_index": 0, "state": "ok"}] if peer else [])
    result["coverage"].append({"request_index": 1 if peer else 0,
                               "state": "unavailable", "diagnostics": ["Response unavailable"]})
    return result


def receipt(base, routed, continuation):
    result = turn_owner._material_execution(
        turn_owner.BrainTurn(base.advocate_id, WORDS, TURN_ID), base,
        "original-offer-digest", routed,
    )
    empty = {"rows": [], "history": [], "excluded_scope": []}
    result["effects"] = {
        kind: turn_owner._material_effects(empty, empty, [], kind=kind, turn_id=TURN_ID)
        for kind in ("disputes", "details")
    }
    result["record_changes"] = []
    turn_owner._request_fulfillment(result, continuation)
    return result


def seal(*, base=None, routed=None, continuation=None, accepted_message=WORDS,
         execution=None):
    base = base or matter()
    routed = routed or plan()
    continuation = response() if continuation is None else continuation
    execution = receipt(base, routed, continuation) if execution is None else execution
    snapshot = owner.record_result_snapshot(execution_receipt=execution, record_catalogue={})
    kwargs = {} if accepted_message is OMITTED else {"accepted_message": accepted_message}
    result = owner.seal_progress(
        continuation, matter_id=str(base.id), turn_id=TURN_ID, plan=routed,
        prior_progress=owner.project_work(base), execution_receipt=execution,
        record_snapshot=snapshot, **kwargs,
    )
    return result, execution


def stored(base, sealed, execution, *, persistence="committed"):
    # Use the shipped code-owned missing-unit status. An empty element list is
    # not a released conversation and would fail before the pending owner.
    routed = plan(*(item(row["request"], intent=row["intent"], relation=row["relation"],
                         scope=row["matter_scope"]) for row in execution["requests"]))
    elements = turn_owner._continuation_elements(routed, sealed)
    execution = deepcopy(execution)
    execution["persistence"] = persistence
    result = {"turn_id": TURN_ID, "matter_id": str(base.id), "elements": elements,
              "continuation": deepcopy(sealed), "material_coverage": {"execution": execution}}
    row = {"turn_id": TURN_ID, "matter_id": str(base.id), "advocate_id": base.advocate_id,
           "message": WORDS, "elements": deepcopy(elements), "response": result,
           "offer_digest": execution["owner"]["offer_digest"],
           "committed": True, "release_state": "released"}
    version = base.version if persistence == "prepared_for_commit" else base.version + 1
    return replace(base, brain_chat=(*base.brain_chat, row), version=version)


def pending_projection(saved):
    projected = owner.project_work(saved)
    values = projected.get("pending_input")
    assert isinstance(values, list)
    return projected, values


def assert_unreviewed(value, expected, *, index=0):
    assert value["accepted_message"] == WORDS
    assert value["request_index"] == index
    assert value["status"] == "pending"
    assert value["review_status"] == "unreviewed"
    assert value["proposal"] == {
        "request": expected.request, "intent": expected.intent, "relation": expected.relation,
        "matter_scope": expected.matter_scope,
        "record_requirement": deepcopy(expected.record_requirement),
    }
    assert value["owner"] == {
        "matter_id": str(matter().id), "advocate_id": matter().advocate_id,
        "turn_id": TURN_ID, "offer_digest": "original-offer-digest",
    }
    assert value["resulting_version"] == matter().version + 1
    assert isinstance(value["id"], str) and value["id"]
    assert not {"work_selector", "existing_id", "progress_updates", "permission",
                "mutation_authority", "completion", "fulfillment_check"} & value.keys()


def test_default_and_explicit_none_are_identical_without_a_pending_marker():
    default, execution = seal(accepted_message=OMITTED)
    explicit, same_execution = seal(accepted_message=None)
    assert explicit == default and same_execution == execution
    assert "pending_input" not in default
    projected = owner.project_work(stored(matter(), default, execution))
    assert "pending_input" not in projected
    assert projected["rows"] == projected["events"] == [] and projected["active_work"] == ""


def test_unstamped_historical_fallback_preserves_its_original_empty_work_projection():
    sealed, execution = seal(accepted_message=OMITTED)
    projected = owner.project_work(stored(matter(), sealed, execution))
    assert "pending_input" not in sealed and "pending_input" not in projected
    assert execution["requests"][0]["fulfillment"] == "unfinished"
    assert sealed["units"] == []
    assert projected["rows"] == projected["events"] == [] and projected["active_work"] == ""


def test_unstamped_valid_peer_retains_its_original_requested_task_and_status():
    routed = plan(item("Review the account."), item("Examine its chronology."))
    sealed, execution = seal(routed=routed, continuation=response(peer=True),
                             accepted_message=OMITTED)
    projected = owner.project_work(stored(matter(), sealed, execution))
    assert len(projected["rows"]) == len(projected["events"]) == 1
    assert projected["rows"][0]["origin"] == "requested"
    assert projected["rows"][0]["status"] == "pending"
    assert projected["active_work"] == "Review the account."
    assert [row["fulfillment"] for row in execution["requests"]] == ["not_requested", "unfinished"]
    assert "pending_input" not in projected


def test_missing_reply_is_discoverable_as_unreviewed_input_without_a_fabricated_task():
    proposed = response()
    routed = plan()
    execution = receipt(matter(), routed, proposed)
    original_proposal, original_execution = deepcopy(proposed), deepcopy(execution)
    sealed, _ = seal(routed=routed, continuation=proposed, execution=execution)
    assert sealed["units"] == [] and sealed["coverage"] == proposed["coverage"]
    assert proposed == original_proposal and execution == original_execution
    assert execution["requests"][0]["fulfillment"] == "unfinished"
    projected, pending = pending_projection(stored(matter(), sealed, execution))
    assert len(pending) == 1
    assert_unreviewed(pending[0], routed.items[0])
    assert projected["rows"] == projected["events"] == [] and projected["active_work"] == ""
    assert execution["effects"]["disputes"]["operations"] == []
    assert execution["effects"]["details"]["operations"] == []


def test_unknown_and_other_scope_remain_proposals_without_matter_or_task_association():
    routed = plan(item(scope="uncertain", relation="uncertain"),
                  item("Examine the separate account.", scope="other", relation="aside"))
    continuation = {"units": [], "coverage": [
        {"request_index": index, "state": "unavailable"} for index in range(2)]}
    sealed, execution = seal(routed=routed, continuation=continuation)
    projected, pending = pending_projection(stored(matter(), sealed, execution))
    assert len(pending) == 2
    for index, value in enumerate(pending):
        assert_unreviewed(value, routed.items[index], index=index)
    assert pending[0]["id"] != pending[1]["id"]
    assert projected["rows"] == [] and projected["active_work"] == ""


def test_contribution_label_does_not_become_a_confirmed_requested_task():
    routed = plan(item(intent="contribution", relation="continues"))
    sealed, execution = seal(routed=routed)
    projected, pending = pending_projection(stored(matter(), sealed, execution))
    assert len(pending) == 1
    assert_unreviewed(pending[0], routed.items[0])
    assert projected["rows"] == [] and projected["active_work"] == ""


def test_valid_peer_keeps_its_projection_while_only_missing_input_is_indexed():
    routed = plan(item("Review the supplied inventory account."),
                  item("Compare the separately requested chronology."))
    original = response(peer=True)
    legacy, execution = seal(routed=routed, continuation=original, accepted_message=None)
    sealed, same_execution = seal(routed=routed, continuation=original)
    assert execution == same_execution and sealed["units"] == legacy["units"]
    assert sealed["coverage"] == legacy["coverage"]
    baseline = owner.project_work(stored(matter(), legacy, execution))
    projected, pending = pending_projection(stored(matter(), sealed, execution))
    assert len(pending) == 1 and pending[0]["request_index"] == 1
    assert_unreviewed(pending[0], routed.items[1], index=1)
    for field in ("rows", "events", "active_work", "coverage", "diagnostics"):
        assert projected[field] == baseline[field]
    assert baseline["rows"][0]["status"] == "pending"
    assert baseline["rows"][0]["origin"] == "requested"


def test_reopening_and_repeat_sealing_preserve_identity_and_do_not_mutate_saved_words():
    sealed, execution = seal()
    same, same_execution = seal()
    assert same == sealed and same_execution == execution
    saved = stored(matter(), sealed, execution)
    original = deepcopy(saved.brain_chat)
    first, pending = pending_projection(saved)
    second, reopened = pending_projection(replace(saved, brain_chat=deepcopy(saved.brain_chat)))
    assert second == first and reopened[0]["id"] == pending[0]["id"]
    assert saved.brain_chat == original


def test_prepared_projection_requires_exact_current_context_then_survives_commit():
    sealed, execution = seal()
    prepared = stored(matter(), sealed, execution, persistence="prepared_for_commit")
    before_commit = owner.project_work(prepared, allow_prepared_turn_id=TURN_ID)
    with pytest.raises(IncompleteConversation):
        owner.project_work(prepared)
    with pytest.raises(IncompleteConversation):
        owner.project_work(replace(prepared, version=prepared.version + 1),
                           allow_prepared_turn_id=TURN_ID)
    committed, pending = pending_projection(stored(matter(), sealed, execution))
    assert before_commit == committed and len(pending) == 1


@pytest.mark.parametrize("damage", [
    "saved_message", "offer_digest", "receipt_offer", "receipt_advocate", "receipt_matter",
    "receipt_turn", "request_index", "request_boolean_index", "request_text", "request_scope",
    "request_intent", "request_requirement", "request_fulfillment", "resulting_version",
    "contract_version", "marker_version", "unknown_binding_field", "released_index_set",
    "missing_binding", "unconfirmed_save",
])
def test_altered_pending_dependencies_and_unknown_contracts_are_rejected(damage):
    sealed, execution = seal()
    saved = stored(matter(), sealed, execution)
    rows = deepcopy(saved.brain_chat)
    row = rows[-1]
    declared = row["response"]["material_coverage"]["execution"]
    binding = row["response"]["continuation"]["pending_input"]
    if damage == "saved_message":
        row["message"] = WORDS.strip()
    elif damage == "offer_digest":
        row["offer_digest"] = "different-offer"
    elif damage.startswith("receipt_"):
        field = {"receipt_offer": "offer_digest", "receipt_advocate": "advocate_id",
                 "receipt_matter": "matter_id", "receipt_turn": "turn_id"}[damage]
        declared["owner"][field] = "different-owner"
    elif damage == "request_index":
        declared["requests"][0]["request_index"] = 1
    elif damage == "request_boolean_index":
        declared["requests"][0]["request_index"] = False
    elif damage == "request_text":
        declared["requests"][0]["request"] = "A different interpreted outcome."
    elif damage == "request_scope":
        declared["requests"][0]["matter_scope"] = "other"
    elif damage == "request_intent":
        declared["requests"][0]["intent"] = "contribution"
    elif damage == "request_requirement":
        declared["requests"][0]["record_requirement"] = {
            "kind": "review", "target_ids": [], "operation": "none",
            "success_condition": "A changed interpretation goal."}
    elif damage == "request_fulfillment":
        declared["requests"][0]["fulfillment"] = "fulfilled"
    elif damage == "resulting_version":
        declared["resulting_version"] += 1
    elif damage == "contract_version":
        binding["contract"] = "accepted_pending_input_v999"
    elif damage == "marker_version":
        row["response"]["continuation"]["pending_input_contract"] = "accepted_pending_input_v999"
    elif damage == "unknown_binding_field":
        binding["permission"] = "execute without further checked authority"
    elif damage == "released_index_set":
        row["response"]["continuation"]["units"] = checked_reply(
            TURN_ID, WORDS, status="none", question=False)["units"]
    elif damage == "missing_binding":
        row["response"]["continuation"].pop("pending_input")
    elif damage == "unconfirmed_save":
        declared["persistence"] = "unconfirmed"
    with pytest.raises(IncompleteConversation):
        owner.project_work(replace(saved, brain_chat=rows))


@pytest.mark.parametrize("accepted_message", [None, WORDS])
@pytest.mark.parametrize("field", ["pending_input", "pending_input_contract"])
def test_model_cannot_inject_a_pending_input_freshness_marker(accepted_message, field):
    proposed = response()
    proposed[field] = ({"contract": CONTRACT, "status": "complete"}
                       if field == "pending_input" else CONTRACT)
    with pytest.raises(IncompleteConversation):
        seal(continuation=proposed, accepted_message=accepted_message)


@pytest.mark.parametrize("bad_message", ["", "  ", 3, {"text": WORDS}])
def test_accepted_message_needs_complete_nonblank_original_words(bad_message):
    with pytest.raises(IncompleteConversation):
        seal(accepted_message=bad_message)


def test_all_delivered_units_do_not_create_pending_input_for_checked_work():
    routed = plan()
    continuation = checked_reply(TURN_ID, WORDS, status="none", question=False)
    sealed, execution = seal(routed=routed, continuation=continuation)
    saved = stored(matter(), sealed, execution)
    projected = owner.project_work(saved)
    assert projected.get("pending_input", []) == []
    assert len(projected["rows"]) == 1
    assert projected["rows"][0]["origin"] == "requested"
    assert projected["rows"][0]["status"] == "pending"


def test_removing_all_opt_in_markers_is_not_detectable_by_legacy_compatible_projection():
    # Historical absence and simultaneous removal have the same local shape.
    # Public storage/release dependency checks require separate activation
    # evidence; this owner prerequisite cannot honestly certify that boundary.
    legacy, execution = seal(accepted_message=OMITTED)
    baseline = owner.project_work(stored(matter(), legacy, execution))
    sealed, same_execution = seal()
    stripped = deepcopy(sealed)
    stripped.pop("pending_input")
    stripped.pop("pending_input_contract")
    assert owner.project_work(stored(matter(), stripped, same_execution)) == baseline


def test_unsaved_input_does_not_change_the_prior_projection():
    before = owner.project_work(matter())
    seal()
    assert owner.project_work(matter()) == before

