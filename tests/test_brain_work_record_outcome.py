"""Offline scripted persistence contracts; no semantic model qualification."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import work_state as state
from nm.brain.conversation import IncompleteConversation
from nm.brain.execution_contracts import RECORD_OUTCOME_CONTRACT, effect_catalogue
from nm.brain.source_snapshots import source_snapshots
from nm.work_the_file.matter_contracts import Matter
from tests.test_brain_work_state import proposed, scope, transition


def requirement(kind="change", *, target="material-old", operation="corrects"):
    return {"kind": kind, "target_ids": [target] if target else [],
            "operation": operation if kind == "change" else "none",
            "success_condition": ("The sourced saved date is Tuesday."
                                  if kind == "change" else
                                  "The saved account faithfully preserves the attributed original."
                                  if kind == "review" else "")}


def record(identity, turn_id, words):
    return {"id": identity, "type": "material", "record": {
        "id": identity, "statement": words, "matter_scope": "current",
        "source_turn_id": turn_id, "quoted": words, "prior_references": [],
        "record_role": "nm_interpretation"}}


def evidence(matter, turn_id, words, declared, *, before=(), after=(), operation=None,
             target="material-old", checked_requirement=None, coverage_state="complete",
             checked_task_id=None):
    kinds = {kind: {"activated_record_ids": [], "retired_record_ids": [],
                    "operations": [], "held_record_ids": [], "outside_owned_record_ids": [],
                    "before_record_ids": [], "after_record_ids": [],
                    "before_held_record_ids": [], "after_held_record_ids": []}
             for kind in ("disputes", "details")}
    details = kinds["details"]
    details.update(before_record_ids=list(before), after_record_ids=list(after),
                   activated_record_ids=sorted(set(after) - set(before)),
                   retired_record_ids=sorted(set(before) - set(after)))
    if operation:
        details["operations"] = [{
            "result_id": next(iter(set(after) - set(before))), "relation": operation,
            "target_record_ids": [target],
            "retired_target_ids": [target] if target in set(before) - set(after) else [],
            "source_references": [{"turn_id": turn_id, "role": "advocate", "quoted": words}]}]
    checked = deepcopy(checked_requirement if checked_requirement is not None else declared)
    audit = {"contract": "independent_account_coverage_v1", "state": coverage_state,
             "reason": "The scripted assessment examined the full declared source scope.",
             "missing_source_ids": [] if coverage_state == "complete" else ["L1"],
             "review_scope": {"requests": [{
                 "request_index": 0,
                 "record_requirement": deepcopy(declared) if checked_task_id else checked}]}}
    if checked_task_id is not None:
        audit["review_scope"]["requests"].append({
            "request_index": 0, "record_requirement": deepcopy(checked),
            "task_id": checked_task_id})
    owner = {"matter_id": str(matter.id), "advocate_id": matter.advocate_id,
             "turn_id": turn_id, "offer_digest": "offer:" + turn_id}
    return {"contract": "material_execution_v1", "id": "mex_" + turn_id,
            "owner": owner, "expected_version": matter.version,
            "resulting_version": matter.version + 1, "persistence": "prepared_for_commit",
            "semantic_coverage": "unassessed",
            "requests": [{"request_index": 0, "request": words,
                          "record_requirement": deepcopy(declared), "fulfillment": "unassessed"}],
            "stages": {name: {"state": "returned" if name.endswith("extraction")
                              or name == "source_classification" else
                              "checked" if operation and name == "detail_review" else
                              "no_candidates",
                              **({"account_coverage": deepcopy(audit)}
                                 if name in ("detail_review", "dispute_review") else {})}
                       for name in ("source_classification", "dispute_extraction", "dispute_review",
                                    "detail_extraction", "detail_review")},
            "effects": kinds, "review_scope": deepcopy(audit["review_scope"])}


def save(matter, turn_id, words, continuation, declared, receipt, records):
    plan = scope(words, intent="request" if continuation["units"][0]["work"]["create"]
                 or continuation["units"][0]["work"]["existing_id"] else "contribution")
    plan = replace(plan, items=(replace(plan.items[0], record_requirement=deepcopy(declared)),))
    snapshot = state.record_result_snapshot(execution_receipt=receipt, record_catalogue=records)
    sealed = state.seal_progress(
        continuation, matter_id=str(matter.id), turn_id=turn_id, plan=plan,
        prior_progress=state.project_work(matter), execution_receipt=receipt,
        record_snapshot=snapshot)
    elements = []
    for unit in sealed["units"]:
        for block in unit["blocks"]:
            sources = source_snapshots(block["references"])
            elements.append({"text": block["text"], "sources": sources,
                             "source": sources[0] if sources else None,
                             "refs": [source["locator"] for source in sources],
                             "continuation_request_index": unit["request_index"],
                             "continuation_block_id": block["id"]})
    committed = deepcopy(receipt)
    committed["persistence"] = "committed"
    response = {"turn_id": turn_id, "matter_id": str(matter.id), "elements": elements,
                "continuation": sealed, "material_coverage": {"execution": committed}}
    row = {"turn_id": turn_id, "matter_id": str(matter.id), "advocate_id": matter.advocate_id,
           "message": words, "elements": deepcopy(elements), "response": response,
           "offer_digest": receipt["owner"]["offer_digest"],
           "committed": True, "release_state": "released"}
    return replace(matter, brain_chat=(*matter.brain_chat, row), version=matter.version + 1)


def checked_reply(turn_id, words, *, status="unresolved", effect_ids=(), current_ids=(),
                  existing="", question=False, updates=(), create=True, sufficiency="needs_input"):
    result = proposed(turn_id, words, create=create, existing=existing,
                      question=question, updates=list(updates), sufficiency=sufficiency)
    unit = result["units"][0]
    unit["record_outcome"] = {"status": status, "block_id": "" if status == "none" else "response",
                              "effect_ids": list(effect_ids),
                              "current_record_ids": list(current_ids),
                              "reason": "The requested result has the declared evidence."}
    unit["record_outcome_contract"] = RECORD_OUTCOME_CONTRACT
    unit["record_check"] = {
        "outcome": {"none": "not_requested", "performed": "fulfilled",
                    "already_current": "fulfilled", "review_no_change": "no_change_justified",
                    "unresolved": "unfinished"}[status],
        "reason": "The independent scripted review checked the stated condition and full purpose."}
    unit["progress_checks"] = [
        {"target_id": update["target_id"], "status": update["status"],
         "scope_preserved": True, "result_supported": True, "verdict": "accept",
         "reason": "This exact lifecycle transition has independent support."}
        for update in updates]
    return result


def started(kind="change", *, question=False):
    matter = Matter(id="outcome-matter", advocate_id="adv_owner", title="Record work")
    words = "The date is Monday. Please check and correct the saved date to Tuesday."
    declared = requirement(kind)
    receipt = evidence(matter, "start", words, declared,
                       before=("material-old",), after=("material-old",))
    original = record("material-old", "start", words)
    saved = save(matter, "start", words, checked_reply("start", words, question=question),
                 declared, receipt, {"material-old": original})
    return saved, declared, original


def completed_change(matter, original_requirement, *, wrong_target=False, operation="corrects"):
    task = state.project_work(matter)["rows"][0]
    words = "The date is Tuesday. Use my earlier requested correction."
    declared = requirement("none", target="")
    target = "material-unrelated" if wrong_target else "material-old"
    before = (target,)
    receipt = evidence(matter, "change", words, declared, before=before,
                       after=("material-new",), target=target, operation=operation)
    effects = list(effect_catalogue(receipt))
    result = checked_reply("change", words, status="performed", effect_ids=effects,
                           existing=task["id"], create=False, question=False,
                           updates=[transition(task["id"], "complete", spans=False)],
                           sufficiency="complete")
    records = {"material-new": record("material-new", "change", words)}
    return save(matter, "change", words, result, declared, receipt, records)


def test_new_task_copies_full_requirement_and_inherited_narrow_request_never_overwrites_it():
    matter, original, _ = started()
    task = state.project_work(matter)["rows"][0]
    stored = deepcopy(matter.brain_chat)
    original["success_condition"] = "A narrower unsupported replacement."
    declared = requirement("none", target="")
    words = "Repeat the current record heading."
    receipt = evidence(matter, "recap", words, declared,
                       before=("material-old",), after=("material-old",))
    snapshot = matter.brain_chat[0]["response"]["continuation"][
        "record_snapshot"]["record_catalogue"]
    continued = save(matter, "recap", words, checked_reply(
        "recap", words, status="none", existing=task["id"], create=False),
        declared, receipt, snapshot)

    after = state.project_work(continued)["rows"][0]
    assert after["record_requirement"] == task["record_requirement"]
    assert after["record_requirement_origin"] == task["record_requirement_origin"]
    assert matter.brain_chat == stored
    assert after["status"] == "pending"
    assert continued.brain_chat[-1]["response"]["continuation"]["units"][0][
        "work"]["record_requirement"] == task["record_requirement"]


def test_inherited_change_completes_only_with_its_relevant_owned_operation_and_review():
    matter, required, _ = started()
    completed = completed_change(matter, required)
    task = state.project_work(completed)["rows"][0]

    assert task["status"] == "complete"
    assert task["record_requirement"] == required
    assert task["record_outcome_coverage"] == "checked"
    seal = task["record_outcome_seal"]
    assert seal["requirements"][1]["record_requirement"] == required
    assert seal["requirements"][0]["record_requirement"]["kind"] == "none"
    assert seal["receipt_id"] == "mex_change"


@pytest.mark.parametrize("damage", ["unrelated", "wrong_operation", "missing_check"])
def test_inherited_change_cannot_complete_with_irrelevant_effect_or_missing_independent_check(
        damage):
    matter, required, _ = started()
    if damage == "missing_check":
        rows = deepcopy(matter.brain_chat)
        rows[0]["response"]["continuation"]["units"][0]["record_check"] = {}
        with pytest.raises(IncompleteConversation, match="independent review owner"):
            state.project_work(replace(matter, brain_chat=rows))
        return
    with pytest.raises(IncompleteConversation, match="exact targets"):
        completed_change(matter, required, wrong_target=damage == "unrelated",
                         operation="adds" if damage == "wrong_operation" else "corrects")


@pytest.mark.parametrize("coverage", ["complete", "partial", "unassessed"])
def test_inherited_review_no_change_requires_independent_full_original_scope(coverage):
    matter, required, old = started("review")
    task = state.project_work(matter)["rows"][0]
    words = "Check the earlier saved account; it needs no change."
    receipt = evidence(matter, "review", words, required,
                       before=("material-old",), after=("material-old",),
                       checked_requirement=required, coverage_state=coverage,
                       checked_task_id=task["id"])
    result = checked_reply("review", words, status="review_no_change",
                           current_ids=("material-old",),
                           existing=task["id"], create=False,
                           updates=[transition(task["id"], "complete", spans=False)],
                           sufficiency="complete")
    if coverage != "complete":
        with pytest.raises(IncompleteConversation, match="partial/unassessed"):
            save(matter, "review", words, result, required, receipt, {"material-old": old})
    else:
        saved = save(matter, "review", words, result, required, receipt, {"material-old": old})
        assert state.project_work(saved)["rows"][0]["status"] == "complete"
        assert saved.brain_chat[-1]["response"]["continuation"]["record_snapshot"][
            "record_catalogue"] == {"material-old": old}


def test_independent_prior_question_can_complete_while_record_edit_remains_pending():
    matter, _, old = started(question=True)
    before = state.project_work(matter)
    task, question = before["rows"]
    declared = requirement("none", target="")
    words = "The outcome I want is recovery of the reported deposit."
    receipt = evidence(matter, "answer", words, declared,
                       before=("material-old",), after=("material-old",))
    result = checked_reply("answer", words, status="unresolved", create=False,
                           updates=[transition(question["id"], "complete")])
    saved = save(matter, "answer", words, result, declared, receipt, {"material-old": old})

    after = state.project_work(saved)
    assert after["rows"][0] == task
    assert after["rows"][1]["status"] == "complete"
    assert after["rows"][0]["status"] == "pending"


@pytest.mark.parametrize("damage", ["seal", "condition", "outcome", "snapshot_owner", "source",
                                    "progress_check", "receipt", "drop_seal", "downgrade",
                                    "strip_proofs"])
def test_saved_result_tampering_cannot_replay_as_verified_completion(damage):
    matter, required, _ = started()
    saved = completed_change(matter, required)
    rows = deepcopy(saved.brain_chat)
    row = rows[-1]
    unit = row["response"]["continuation"]["units"][0]
    if damage == "seal":
        unit["record_outcome_seal"]["digest"] = "fabricated"
    elif damage == "condition":
        unit["work"]["record_requirement"]["success_condition"] = "Only write a reply."
    elif damage == "outcome":
        unit["record_outcome"]["reason"] = "A substituted completion claim."
    elif damage == "snapshot_owner":
        row["response"]["continuation"]["record_snapshot"]["owner"]["advocate_id"] = "foreign"
    elif damage == "source":
        row["response"]["continuation"]["record_snapshot"]["record_catalogue"][
            "material-new"]["record"]["quoted"] = "Invented Tuesday account."
    elif damage == "progress_check":
        unit["progress_checks"][0]["result_supported"] = False
    elif damage == "receipt":
        row["response"]["material_coverage"]["execution"]["persistence"] = "prepared_for_commit"
    elif damage == "drop_seal":
        unit.pop("record_outcome_seal")
    elif damage == "strip_proofs":
        unit["progress_version"] = 2
        for key in ("record_outcome", "record_outcome_contract", "record_outcome_seal",
                    "record_requirement", "record_check", "progress_checks"):
            unit.pop(key, None)
        unit["work"].pop("record_requirement", None)
        unit["work"].pop("record_requirement_origin", None)
    else:
        unit["progress_version"] = 2
    with pytest.raises(IncompleteConversation):
        state.project_work(replace(saved, brain_chat=rows))


def test_earlier_committed_result_stays_valid_after_a_later_correction_supersedes_it():
    matter, required, _ = started()
    saved = completed_change(matter, required)
    old_proof = deepcopy(saved.brain_chat[-1])
    declared = requirement("none", target="")
    words = "Correction: the date is Thursday."
    receipt = evidence(saved, "later", words, declared, before=("material-new",),
                       after=("material-later",), operation="corrects", target="material-new")
    later = save(saved, "later", words, checked_reply("later", words, status="none", create=False),
                 declared, receipt, {"material-later": record("material-later", "later", words)})
    projected = state.project_work(later)

    assert projected["rows"][0]["status"] == "complete"
    assert projected["rows"][0]["record_outcome_seal"]["receipt_id"] == "mex_change"
    assert later.brain_chat[1] == old_proof
    assert later.brain_chat[1]["response"]["continuation"]["record_snapshot"][
        "record_catalogue"]["material-new"]["record"]["statement"].startswith("The date is Tuesday")


def test_legacy_task_proof_is_untracked_and_courtesy_does_not_change_projection():
    from tests.test_brain_work_state import opened
    legacy = opened()
    before = state.project_work(legacy)
    assert before["rows"][0]["record_requirement"] is None
    assert before["rows"][0]["record_outcome_coverage"] == "untracked"
    row = {"turn_id": "courtesy", "message": "Hello again.", "advocate_id": legacy.advocate_id,
           "matter_id": str(legacy.id), "committed": True, "release_state": "released",
           "elements": [{"text": "Hello."}],
           "response": {"turn_id": "courtesy", "elements": [{"text": "Hello."}]}}
    assert state.project_work(replace(legacy, brain_chat=(*legacy.brain_chat, row))) == before


def test_structurally_recorded_legacy_work_without_continuation_discloses_unknown_progress():
    from tests.test_brain_work_state import opened
    legacy = opened()
    before = state.project_work(legacy)
    row = {"turn_id": "legacy-work", "message": "Please continue the earlier work.",
           "advocate_id": legacy.advocate_id, "matter_id": str(legacy.id),
           "committed": True, "release_state": "released", "active_work_after": "Continue review.",
           "elements": [{"text": "The review remains pending."}],
           "response": {"turn_id": "legacy-work",
                        "elements": [{"text": "The review remains pending."}]}}
    saved = replace(legacy, brain_chat=(*legacy.brain_chat, row))
    after = state.project_work(saved)

    assert after["coverage"]["older_progress"] == "untracked"
    assert after["rows"] == before["rows"] and after["events"] == before["events"]
    assert saved.brain_chat[-1]["message"] == row["message"]
    assert saved.brain_chat[-1]["elements"] == row["elements"]


def test_version_two_keeps_owned_intent_but_no_record_completion_proof_is_fabricated():
    from tests.test_brain_work_state import opened
    matter = opened()
    rows = deepcopy(matter.brain_chat)
    unit = rows[0]["response"]["continuation"]["units"][0]
    unit["progress_version"] = 2
    unit.pop("record_requirement")
    unit["work"].pop("record_requirement")
    unit["work"].pop("record_requirement_origin")

    progress = state.project_work(replace(matter, brain_chat=rows))

    assert progress["rows"][0]["origin"] == "requested"
    assert progress["rows"][0]["record_requirement"] is None
    assert progress["rows"][0]["record_outcome_coverage"] == "untracked"
    unit["work"].pop("intent")
    with pytest.raises(IncompleteConversation, match="intent"):
        state.project_work(replace(matter, brain_chat=rows))


def test_inherited_review_can_complete_independently_of_the_new_selected_ordinary_task():
    matter, original, old = started("review")
    task = state.project_work(matter)["rows"][0]
    current = requirement("none", target="")
    words = "Repeat the current record heading."
    receipt = evidence(matter, "inherited-review", words, current,
                       before=("material-old",), after=("material-old",),
                       checked_requirement=original, checked_task_id=task["id"])
    result = checked_reply(
        "inherited-review", words, status="review_no_change", current_ids=("material-old",),
        updates=[transition(task["id"], "complete", spans=False)], sufficiency="needs_input")
    saved = save(matter, "inherited-review", words, result, current,
                 receipt, {"material-old": old})

    after = state.project_work(saved)
    assert after["rows"][0]["status"] == "complete"
    assert after["rows"][0]["record_requirement"] == original
    assert after["rows"][1]["status"] == "pending"
    assert after["rows"][1]["record_requirement"] == current


def test_authorized_collateral_target_does_not_discard_the_supported_requested_change():
    matter, original, _ = started()
    task = state.project_work(matter)["rows"][0]
    current = requirement("none", target="")
    words = "Correct the saved date and the linked duplicate against this Tuesday account."
    receipt = evidence(matter, "collateral", words, current,
                       before=("material-old", "material-collateral"), after=("material-new",),
                       operation="corrects")
    operation = receipt["effects"]["details"]["operations"][0]
    operation["target_record_ids"].append("material-collateral")
    operation["retired_target_ids"].append("material-collateral")
    result = checked_reply(
        "collateral", words, status="performed", effect_ids=tuple(effect_catalogue(receipt)),
        create=False, existing=task["id"],
        updates=[transition(task["id"], "complete", spans=False)], sufficiency="complete")
    saved = save(matter, "collateral", words, result, current, receipt,
                 {"material-new": record("material-new", "collateral", words)})

    after = state.project_work(saved)
    assert after["rows"][0]["status"] == "complete"
    assert after["rows"][0]["record_requirement"] == original


def test_already_correct_owned_state_can_complete_an_edit_goal_without_inventing_a_new_operation():
    matter = Matter(id="current-state", advocate_id="adv_owner", title="Existing correct date")
    words = "The handover date is Tuesday. Please set the saved handover date to Tuesday."
    original = requirement()
    receipt = evidence(matter, "original", words, original,
                       before=("material-old",), after=("material-old",))
    old = record("material-old", "original", words)
    pending = save(matter, "original", words, checked_reply("original", words),
                   original, receipt, {"material-old": old})
    task = state.project_work(pending)["rows"][0]
    current = requirement("none", target="")
    followup = "Repeat the record heading."
    receipt = evidence(pending, "satisfied", followup, current,
                       before=("material-old",), after=("material-old",))
    # Present state can establish the condition; it does not claim that NM
    # performed a historical or new edit on this turn.
    receipt["stages"] = {name: {"state": "not_run"} for name in receipt["stages"]}
    reply = checked_reply(
        "satisfied", followup, status="already_current", current_ids=("material-old",),
        create=False, existing=task["id"],
        updates=[transition(task["id"], "complete", spans=False)], sufficiency="complete")
    saved = save(pending, "satisfied", followup, reply, current, receipt, {"material-old": old})

    assert state.project_work(saved)["rows"][0]["status"] == "complete"
    assert saved.brain_chat[-1]["response"]["material_coverage"]["execution"][
        "effects"]["details"]["operations"] == []
    assert saved.brain_chat[-1]["response"]["continuation"]["units"][0][
        "record_outcome"]["effect_ids"] == []


def test_new_current_review_can_create_and_complete_its_task_without_a_prior_task_id():
    matter = Matter(id="fresh-review", advocate_id="adv_owner", title="Current review")
    words = "Review the saved record formulations; if none exist, say so."
    current = requirement("review", target="")
    current["success_condition"] = (
        "The review establishes whether any saved formulation needs reconciliation.")
    receipt = evidence(matter, "review-now", words, current)
    reply = checked_reply(
        "review-now", words, status="review_no_change", create=True,
        updates=[transition("$work", "complete", spans=False)], sufficiency="complete")
    saved = save(matter, "review-now", words, reply, current, receipt, {})

    task = state.project_work(saved)["rows"][0]
    assert task["status"] == "complete"
    assert task["record_requirement"] == current
    assert task["record_outcome_coverage"] == "checked"
    assert receipt["effects"]["details"]["operations"] == []


def test_only_exact_current_inmemory_context_can_project_the_prepared_result():
    matter, required, _ = started()
    committed = completed_change(matter, required)
    rows = deepcopy(committed.brain_chat)
    rows[-1]["response"]["material_coverage"]["execution"]["persistence"] = "prepared_for_commit"
    pending = replace(committed, brain_chat=rows, version=matter.version)

    projection = state.project_work(pending, allow_prepared_turn_id="change")

    assert projection["rows"][0]["status"] == "complete"
    with pytest.raises(IncompleteConversation, match="uncommitted receipt"):
        state.project_work(pending)
    with pytest.raises(IncompleteConversation, match="final constructed"):
        state.project_work(pending, allow_prepared_turn_id="start")
    with pytest.raises(IncompleteConversation, match="exact current matter version"):
        state.project_work(replace(pending, version=pending.version + 1),
                           allow_prepared_turn_id="change")
