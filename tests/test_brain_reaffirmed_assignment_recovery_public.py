"""A recovered withdrawal holds only details whose assignment disappeared.

Source meaning and independent verdicts are scripted. The real public service,
shared retry ledger, admission capture, saving and replay retain their owners.
This proves mechanical preservation, not real-model semantic qualification.
"""

import json
from copy import deepcopy

from nm.brain import turn as owner
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage, require_schema
from tests.brain_reader_fixture import fresh_review_reply, source_portion_reply
from tests.test_brain_evidence_rendering_public import raw_unit
from tests.test_brain_material import material, mutation_scope, send
from tests.test_brain_material_purpose import PurposeModel, item, open_account, routed
from tests.test_brain_native_coverage_turn import assert_replay
from tests.test_brain_saved_record_support import current
from tests.test_brain_source_support_verifiers import coverage, disposition, verdict

ORIGINAL = "The parties dispute who retained the entry card."
WITHDRAWAL = "I withdraw my earlier account about retention of the entry card."
INDEPENDENT = "The custodian confirms that the register remains sealed."
OTHER_DISPUTE = "The parties disagree whether a duplicate card was issued."
INSTRUCTION = "Check the earlier formulation against its source."
MESSAGE = " ".join((WITHDRAWAL, INDEPENDENT, OTHER_DISPUTE, INSTRUCTION))
TARGET = "assignment-original:material:1"


class AssignmentModel(PurposeModel):
    def __init__(self):
        references = ({"turn_id": "assignment-original", "role": "advocate",
                       "quoted": ORIGINAL},)
        withdrawal = material("dispute", WITHDRAWAL, WITHDRAWAL, relation="withdraws",
                              scope="current", references=references)
        withdrawal["related_dispute_ids"] = [TARGET]
        linked = material("circumstance", ORIGINAL, INSTRUCTION, scope="current",
                          placement="disputes", dispute_ids=(TARGET,), references=references)
        independent = material("event", INDEPENDENT, INDEPENDENT,
                               scope="current", placement="matter")
        peer = material("dispute", OTHER_DISPUTE, OTHER_DISPUTE, scope="current")
        planned = routed(MESSAGE, candidates=[peer, withdrawal, linked, independent],
                         source_purposes={INSTRUCTION: "non_account"}, items=[{
                             **item(MESSAGE, "", intent="contribution",
                                    purposes=("account_contribution", "interpretation_review")),
                             "mutation_scopes": [mutation_scope(TARGET, relations=("withdraws",))],
                         }])
        super().__init__([planned])
        self.reaffirmed = False
        self.raw_reviews = []

    def context_budget(self, tier):
        return 100_000

    def _review(self, operation, payload):
        references = payload["source_treatments"]
        is_dispute = operation == "verify_disputes"
        rows = []
        for candidate in payload["candidates"]:
            identity = candidate["candidate_id"]
            words = (OTHER_DISPUTE if identity == "C1" else WITHDRAWAL if is_dispute
                     else ORIGINAL if identity == "D1" else INDEPENDENT)
            sources = [source for source, reference in references.items()
                       if reference["quoted"] == words]
            if identity == "C2":
                sources += [source for source, reference in references.items()
                            if reference["quoted"] == ORIGINAL]
            row = verdict("dispute" if is_dispute else "material", references[sources[0]],
                          source_id=sources[0])
            row["candidate_id"] = identity
            row["account_check"]["source_ids"] = sources
            row["account_check"]["source_checks"] = [{
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True,
                "support_spans": [{"start": 0, "end": len(references[source]["quoted"])}],
                "reason": "The fixture declares these original reported words as support.",
            } for source in sources]
            row["target_checks"] = [{
                "target_id": target, "identity_relation": "same_underlying_account",
                "account_preserved": True, "required_peer_ids": [],
                "reason": "The fixture authorises retirement of this exact prior account.",
            } for target in candidate.get("related_dispute_ids", [])]
            rows.append(row)
        purposes = {source: "non_account" if reference["quoted"] == INSTRUCTION else "account"
                    for source, reference in references.items()}
        portions = []
        for source, reference in references.items():
            if purposes[source] == "non_account":
                selected = disposition(source, reference, status="non_account")
            elif is_dispute:
                selected = disposition(source, reference, status="outside_scope")
            else:
                selected = disposition(source, reference, status="represented", candidate_ids=(
                    "D1" if reference["quoted"] == ORIGINAL else "D2",))
                if reference["quoted"] not in (ORIGINAL, INDEPENDENT):
                    selected = disposition(source, reference, status="outside_scope")
            portions.append(selected)
        data = fresh_review_reply(payload, {"verdicts": rows, "coverage": coverage(
            references, purposes=purposes, dispositions=portions)})
        if is_dispute and not self.reaffirmed:
            faulty = next(row for row in data["verdicts"] if row["candidate_id"] == "C2")
            source = next(source for source, ref in references.items()
                          if ref["quoted"] == INSTRUCTION)
            faulty["account_check"]["source_checks"].append({
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True,
                "support_spans": [{"start": 0, "end": len(INSTRUCTION)}],
                "reason": "Deliberately malformed authority-as-fact review field.",
            })
        return data

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        if prompt.operation == "reconsider_account_sources":
            self.reaffirmed = True
            assert payload["source_ids"] == ["L4"]
            data = source_portion_reply(payload, {"source_treatments": {"L4": {
                "content_role": "work_instruction",
                "reason": "The fixture reaffirms the unchanged instruction purpose."}}})
        elif prompt.operation in ("verify_disputes", "verify_material_grounding"):
            data = self._review(prompt.operation, payload)
            self.raw_reviews.append((prompt.operation, self.reaffirmed, deepcopy(payload)))
        elif prompt.operation == "continue_conversation":
            data = {"units": [raw_unit(payload, record_status="unresolved")]}
        elif prompt.operation == "verify_continuation":
            unit, = payload["units"]
            data = {"accepted_units": [{
                "request_index": 0, "block_checks": [{
                    "block_id": block["id"], "requires_legal_support": False,
                    "verdict": "accept", "reason": "The fixture selects original account words."}
                    for block in unit["blocks"]], "proposal_checks": [], "progress_checks": [],
                "question_resolutions": [], "work_check": {
                    "existing_id": unit["work"]["existing_id"], "scope_preserved": True,
                    "verdict": "accept", "reason": "This contribution claims no completed task."},
                "record_check": {"outcome": "unfinished",
                                 "reason": "The assigned detail review remains unfinished."},
                "reason": "Scripted relevance decision for mechanical receipt testing.",
            }], "rejected_units": []}
        else:
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        require_schema(data, schema)
        self.seen.append((prompt.operation, deepcopy(payload)))
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="scripted-assignment-recovery", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def test_recovered_unread_withdrawal_preserves_unrelated_positive_proof_when_detail_retry_is_denied(
        client, wired, monkeypatch):
    from nm.app import api

    seed = routed(ORIGINAL, opening=True,
                  candidates=[material("dispute", ORIGINAL, ORIGINAL)], items=[item(
                      ORIGINAL, ORIGINAL, opening=True, intent="contribution",
                      purposes=("account_contribution",))])
    opened = open_account(client, wired, monkeypatch, PurposeModel([seed]), ORIGINAL,
                          turn_id="assignment-original")
    before = wired.store.load(opened["matter_id"])

    class LimitedService(owner.BrainService):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, recovery_limit=5)

    monkeypatch.setattr(api, "BrainService", LimitedService)
    model = AssignmentModel()
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    response = send(client, MESSAGE, "assignment-recovery", opened=opened)
    assert response.status_code == 200, response.text
    reply, saved = response.json(), wired.store.load(before.id)
    execution = reply["material_coverage"]["execution"]
    assert execution["semantic_recovery"]["source_reconsideration"]["state"] == "partial"
    assert execution["semantic_recovery"]["source_reconsideration"]["changed_source_ids"] == []
    assert reply["metrics"]["llm_calls"] == 11
    recovery = reply["metrics"]["recovery"]
    assert recovery["dispatched_calls"] == 3 and recovery["reply_reserve"] == 2, recovery
    assert any(row["phase"] == "source_reconsideration:detail_review"
               and row["state"] == "budget_exhausted" for row in recovery["events"])
    reread = next(payload for operation, after_owner, payload in model.raw_reviews
                  if operation == "verify_disputes" and after_owner)
    assert [row["candidate_id"] for row in reread["candidates"]] == ["C2"]
    assert [row["candidate_id"] for row in reread["retained_candidate_context"]] == ["C1"]
    assert not any(operation == "verify_material_grounding" and after_owner
                   for operation, after_owner, _ in model.raw_reviews)
    assert execution["stages"]["detail_review"]["unread"] == 1
    assert {row["statement"] for row in reply["material"]} == {
        WITHDRAWAL, OTHER_DISPUTE, INDEPENDENT}
    assert {row["candidate_id"] for row in execution["coverage_application"]["bindings"]} == {
        "C1", "C2", "D2"}
    conversation, disputes, details = current(wired, saved)
    assert TARGET not in {row["id"] for row in disputes["rows"]}
    assert [row["statement"] for row in details["rows"]] == [INDEPENDENT]
    support = owner._saved_record_support(saved, conversation, disputes=disputes, details=details)
    (independent_id,) = support["detail_review"]
    assert support["detail_review"][independent_id]["review"]["candidate_id"] == "D2"
    assert saved.brain_chat[0] == before.brain_chat[0]
    assert_replay(client, wired, model, opened, MESSAGE, "assignment-recovery", reply, saved)
