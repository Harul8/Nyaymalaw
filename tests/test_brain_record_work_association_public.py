"""Public task identity, exact completion evidence and immutable replay.

The scenario author supplies all meanings, source decisions and reviewer
judgments. The deliberately wrong acceptance exercises mechanical enforcement;
these tests do not measure whether a real model recognizes the scope mismatch.
Actual producer schemas, application, capture, save and replay remain in use.
"""

import json
from copy import deepcopy

import pytest

from nm.brain.execution_contracts import effect_catalogue
from nm.brain.work_state import project_work
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage, require_schema
from tests.brain_reader_fixture import fresh_review_reply
from tests.test_brain_material import material, mutation_scope, send
from tests.test_brain_material_purpose import PurposeModel, item, open_account, routed
from tests.test_brain_source_support_verifiers import coverage, disposition, verdict

FIRST = "On 7 September 2026, the warehouse keeper received two sealed inventory lists."
SECOND = (
    "On 9 September 2026, the keeper sent copies of those lists to the stock auditor "
    "for internal review."
)
RECORD = "Please record both reported events."
ORIGINAL = f"{FIRST} {SECOND} {RECORD}"
CORRECTION = "Correction: the keeper received three sealed inventory lists, not two."
LIMIT = "Update only that quantity and preserve the two dates and the later sending event."
CHANGE = f"{CORRECTION} {LIMIT}"
CHANGED = FIRST.replace("two sealed", "three sealed")
CONTRIBUTION = "Keep the earlier recording task unchanged; I am adding no new event."
REVIEW = "Review both saved events against my original account and leave correct entries unchanged."
TARGET = "association-original:material:1"
PEER = "association-original:material:2"
RESULT = "association-correction:material:1"


def requirement(kind, operation, targets, success):
    return {"kind": kind, "operation": operation, "target_ids": list(targets),
            "success_condition": success}


ORIGINAL_REQUIREMENT = requirement(
    "change", "new", (), "Record both reported events with their dates and recipients.")
CHANGE_REQUIREMENT = requirement(
    "change", "corrects", (TARGET,),
    "Change only the receipt quantity and preserve the other event.")
REVIEW_REQUIREMENT = requirement(
    "review", "none", (TARGET, PEER), "Check both saved events against the original account.")


def original_plan():
    result = routed(ORIGINAL, opening=True, source_purposes={RECORD: "non_account"},
                    candidates=[material("event", words, words, placement="matter")
                                for words in (FIRST, SECOND)], items=[item(
                        RECORD, "", purposes=("account_contribution",), opening=True,
                        record_requirement=deepcopy(ORIGINAL_REQUIREMENT))])
    result["opening"]["summary"] = f"{FIRST} {SECOND}"
    result["items"][0]["mutation_scopes"] = [mutation_scope(
        relations=("new",), source_ids=("L3",))]
    return result


def correction_plan():
    proposed = material(
        "event", CHANGED, CORRECTION, relation="corrects", scope="current", placement="matter",
        related_material_ids=(TARGET,), references=({
            "turn_id": "association-original", "role": "advocate", "quoted": FIRST},))
    result = routed(CHANGE, source_purposes={LIMIT: "non_account"}, candidates=[proposed],
                    items=[item(LIMIT, "", purposes=("account_contribution",),
                                record_requirement=deepcopy(CHANGE_REQUIREMENT))])
    result["items"][0]["mutation_scopes"] = [mutation_scope(TARGET, source_ids=("L2",))]
    return result


def unchanged_plan(message, *, review=False):
    return routed(message, source_purposes={message: "non_account"}, items=[item(
        message, "", intent="request" if review else "contribution",
        purposes=("interpretation_review",) if review else (),
        record_requirement=deepcopy(REVIEW_REQUIREMENT) if review else None)])


class AssociationModel(PurposeModel):
    """Scripted judgments with references drawn from the actual owned catalogues."""

    def __init__(self, plans, *, correction_choices=("new",)):
        super().__init__(plans)
        self.correction_choices = iter(correction_choices)
        self.raw_calls = []
        self.original_task_id = None

    def context_budget(self, tier):
        return 100_000

    def _review(self, operation, payload):
        references = payload["source_treatments"]
        phase = len(self.calls)
        words_to_sources = {reference["quoted"].strip(): identity
                            for identity, reference in references.items()}
        decisions = []
        for candidate in payload["candidates"]:
            identity = candidate["candidate_id"]
            words = ((FIRST, SECOND) if identity == "O1" else
                     (FIRST,) if phase == 1 and identity == "D1" else
                     (SECOND,) if phase == 1 and identity == "D2" else
                     (FIRST, CORRECTION))
            selected = [words_to_sources[text] for text in words]
            assert set(selected) <= set(candidate["allowed_account_source_ids"])
            row = verdict("material", references[selected[0]], source_id=selected[0])
            row["candidate_id"] = identity
            row["account_check"]["source_ids"] = selected
            row["account_check"]["source_checks"] = [{
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True,
                "support_spans": [{"start": 0, "end": len(references[source]["quoted"])}],
                "reason": "This selected original report supports this expressly authored account.",
            } for source in selected]
            row["target_checks"] = [{
                "target_id": target, "identity_relation": "same_underlying_account",
                "account_preserved": True, "required_peer_ids": [],
                "reason": "The correction changes only the quantity in this receipt event.",
            } for target in candidate.get("related_material_ids", [])]
            decisions.append(row)
        portions, purposes = [], {}
        for source, reference in references.items():
            words = reference["quoted"].strip()
            is_account = words in (FIRST, SECOND, CORRECTION)
            purposes[source] = "account" if is_account else "non_account"
            if not is_account:
                selected = disposition(source, reference, status="non_account")
            elif operation == "verify_disputes":
                selected = disposition(source, reference, status="outside_scope")
            elif phase == 1:
                selected = disposition(source, reference, status="represented",
                                       candidate_ids=("D1" if words == FIRST else "D2",))
            elif words == CORRECTION:
                selected = disposition(source, reference, status="represented",
                                       candidate_ids=("D1",))
            else:
                selected = disposition(source, reference, status="represented",
                                       record_ids=(TARGET if words == FIRST else PEER,))
            portions.append(selected)
        return fresh_review_reply(payload, {"verdicts": decisions, "coverage": coverage(
            references, purposes=purposes, dispositions=portions)})

    def _write(self, payload):
        phase = len(self.calls)
        request = payload["work_items"][0]
        selected = "$new_task"
        if phase == 2 and request["record_requirement"]["kind"] == "change":
            choice = next(self.correction_choices)
            selected = self.original_task_id if choice == "old" else "$new_task"
        elif request["intent"] == "contribution":
            selected = self.original_task_id
        status = ("none" if request["record_requirement"]["kind"] == "none" else
                  "review_no_change" if request["record_requirement"]["kind"] == "review" else
                  "performed")
        block = {"id": "result", "kind": "acknowledgment" if status == "none" else "completion",
                 "uncertainty": "none",
                 "evidence_expression": {
                     "operator": "acknowledgment" if status == "none" else "record_result",
                     "source_ids": [],
                     "record_ids": [], "focus": "none"}}
        outcome = {"status": status, "block_id": "" if status == "none" else "result",
                   "effect_ids": [identity for identity, effect in
                                  payload["record_effect_catalogue"].items() if effect["performed"]]
                   if status == "performed" else [],
                   "current_record_ids": [TARGET, PEER] if status == "review_no_change" else [],
                   "reason": "The scenario author explicitly declares this requested outcome."}
        progress = [] if status == "none" else [{
            "target_id": "$work", "status": "complete", "block_id": "result",
            "reason": "The scenario author proposes completion of the selected requested work.",
            "span_ids": ["L3" if phase == 1 else "L2" if status == "performed" else "L1"],
        }]
        return {"units": [{
            "request_index": 0, "blocks": [block], "questions": [], "next_work": [],
            "work_selector": selected, "progress_updates": progress, "record_outcome": outcome,
            "sufficiency": {"status": "complete", "block_id": "result"},
        }]}

    def _check(self, payload):
        unit, = payload["units"]
        # The bad association receives an intentionally wrong semantic verdict.
        # Exact operation and target enforcement must still withhold completion.
        outcome = {"none": "not_requested", "performed": "fulfilled",
                   "review_no_change": "no_change_justified"}[unit["record_outcome"]["status"]]
        return {"accepted_units": [{
            "request_index": 0, "block_checks": [{
                "block_id": "result", "requires_legal_support": False, "verdict": "accept",
                "reason": "The fixture author declares the selected checked status relevant."}],
            "proposal_checks": [], "work_check": {
                "existing_id": unit["work"]["existing_id"], "scope_preserved": True,
                "verdict": "accept",
                "reason": "Explicit fixture verdict, wrong in the adversarial case."},
            "progress_checks": [{
                "target_id": update["target_id"], "status": update["status"],
                "scope_preserved": True, "result_supported": True, "verdict": "accept",
                "reason": "Explicit verdict, wrong when old new-work is completed by correction.",
            } for update in unit["progress_updates"]], "question_resolutions": [],
            "record_check": {"outcome": outcome, "reason": "This outcome is expressly scripted."},
            "reason": "The scenario author supplies this verdict for enforcement testing.",
        }], "rejected_units": []}

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        if prompt.operation in ("verify_material_grounding", "verify_disputes"):
            data = self._review(prompt.operation, payload)
        elif prompt.operation == "continue_conversation":
            data = self._write(payload)
        elif prompt.operation == "verify_continuation":
            data = self._check(payload)
        else:
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            require_schema(result.data, schema)
            return result
        require_schema(data, schema)
        self.seen.append((prompt.operation, deepcopy(payload)))
        self.raw_calls.append((prompt.operation, deepcopy(payload), deepcopy(data)))
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="scripted-association", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def seed(client, wired, monkeypatch, model):
    opened = open_account(client, wired, monkeypatch, model, ORIGINAL,
                          turn_id="association-original")
    saved = wired.store.load(opened["matter_id"])
    task, = project_work(saved)["rows"]
    assert task["status"] == "complete"
    assert task["record_requirement"] == ORIGINAL_REQUIREMENT
    model.original_task_id = task["id"]
    return opened, saved, deepcopy(task)


def assert_replay(client, wired, model, opened, message, turn_id, first, saved):
    calls = len(model.seen)
    response = send(client, message, turn_id, opened=opened)
    assert response.status_code == 200, response.text
    replay = response.json()
    assert replay["replayed"] and replay["metrics"]["llm_calls"] == 0
    assert replay["elements"] == first["elements"]
    assert replay["continuation"] == first["continuation"]
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved


@pytest.mark.parametrize("choices", [("new",), ("old", "new")])
def test_correction_completes_its_own_task_and_preserves_broader_original(
        client, wired, monkeypatch, choices):
    model = AssociationModel([original_plan(), correction_plan()], correction_choices=choices)
    opened, before, original_task = seed(client, wired, monkeypatch, model)
    response = send(client, CHANGE, "association-correction", opened=opened)
    assert response.status_code == 200, response.text
    reply = response.json()
    saved = wired.store.load(opened["matter_id"])
    tasks = {task["id"]: task for task in project_work(saved)["rows"]}
    assert tasks.pop(original_task["id"]) == original_task
    corrected, = tasks.values()
    assert corrected["status"] == "complete"
    assert corrected["record_requirement"] == CHANGE_REQUIREMENT
    assert corrected["record_requirement_origin"]["turn_id"] == "association-correction"
    assert saved.brain_chat[0] == before.brain_chat[0]
    unit, = reply["continuation"]["units"]
    assert unit["work"]["create"] and unit["work"]["existing_id"] == ""
    assert unit["record_outcome"]["status"] == "performed"
    effect, = effect_catalogue(reply["material_coverage"]["execution"]).values()
    assert effect["relation"] == "corrects" and effect["target_record_ids"] == [TARGET]
    assert effect["performed"]
    record = client.get(f"/api/matters/{saved.id}").json()["material_record"]
    assert {row["id"]: row["statement"] for row in record["rows"]} == {
        RESULT: CHANGED, PEER: SECOND}
    historical = {row["id"]: row for row in record["history"]}
    assert historical[TARGET]["statement"] == FIRST
    assert historical[RESULT]["relation"] == "corrects"
    assert historical[RESULT]["related_material_ids"] == [TARGET]
    assert saved.brain_chat[-1]["response"]["continuation"] == reply["continuation"]
    assert reply["metrics"]["llm_calls"] == (10 if choices[0] == "old" else 8)
    if choices[0] == "old":
        retry = [payload for operation, payload, _ in model.raw_calls
                 if operation == "continue_conversation" and "correction" in payload]
        assert len(retry) == 1
        issue = json.dumps(retry[0]["correction"])
        assert original_task["id"] in issue and "exact target set and operation" in issue
    assert_replay(client, wired, model, opened, CHANGE, "association-correction", reply, saved)


def test_repeated_wrong_acceptance_cannot_complete_the_earlier_broader_task(
        client, wired, monkeypatch):
    model = AssociationModel([original_plan(), correction_plan()],
                             correction_choices=("old", "old"))
    opened, before, original_task = seed(client, wired, monkeypatch, model)
    response = send(client, CHANGE, "association-correction", opened=opened)
    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["continuation"]["units"] == []
    assert reply["continuation"]["coverage"][0]["state"] == "unavailable"
    saved = wired.store.load(opened["matter_id"])
    assert project_work(saved)["rows"] == [original_task]
    assert saved.brain_chat[0] == before.brain_chat[0]
    assert reply["material"][0]["id"] == RESULT
    assert reply["metrics"]["llm_calls"] == 10
    assert_replay(client, wired, model, opened, CHANGE, "association-correction", reply, saved)


def test_same_scoped_contribution_can_select_existing_task_without_recompleting_it(
        client, wired, monkeypatch):
    model = AssociationModel([original_plan(), unchanged_plan(CONTRIBUTION)])
    opened, before, original_task = seed(client, wired, monkeypatch, model)
    response = send(client, CONTRIBUTION, "association-contribution", opened=opened)
    assert response.status_code == 200, response.text
    reply = response.json()
    saved = wired.store.load(opened["matter_id"])
    assert project_work(saved)["rows"] == [original_task]
    assert saved.brain_chat[0] == before.brain_chat[0]
    unit, = reply["continuation"]["units"]
    assert unit["work"]["existing_id"] == original_task["id"]
    assert not unit["work"]["create"] and unit["progress_updates"] == []
    assert unit["record_outcome"]["status"] == "none" and reply["material"] == []
    assert reply["metrics"]["llm_calls"] == 3
    assert_replay(client, wired, model, opened, CONTRIBUTION,
                  "association-contribution", reply, saved)


def test_already_correct_review_completes_without_inventing_a_write(
        client, wired, monkeypatch):
    model = AssociationModel([original_plan(), unchanged_plan(REVIEW, review=True)])
    opened, before, original_task = seed(client, wired, monkeypatch, model)
    response = send(client, REVIEW, "association-review", opened=opened)
    assert response.status_code == 200, response.text
    reply = response.json()
    saved = wired.store.load(opened["matter_id"])
    tasks = {task["id"]: task for task in project_work(saved)["rows"]}
    assert tasks.pop(original_task["id"]) == original_task
    reviewed, = tasks.values()
    assert reviewed["status"] == "complete" and reviewed["record_requirement"] == REVIEW_REQUIREMENT
    assert saved.brain_chat[0] == before.brain_chat[0]
    unit, = reply["continuation"]["units"]
    assert unit["record_outcome"]["status"] == "review_no_change"
    assert unit["record_outcome"]["effect_ids"] == []
    assert unit["record_outcome"]["current_record_ids"] == [TARGET, PEER]
    assert reply["material"] == []
    assert effect_catalogue(reply["material_coverage"]["execution"]) == {}
    assert reply["material_coverage"]["execution"]["semantic_coverage"] == "complete"
    assert reply["metrics"]["llm_calls"] == 8
    assert_replay(client, wired, model, opened, REVIEW, "association-review", reply, saved)
