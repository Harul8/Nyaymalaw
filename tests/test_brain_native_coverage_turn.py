"""Native coverage reaches real reviewers, record application, saving and replay.

Source purposes, support and coverage meanings are expressly scripted. These
tests exercise the shipped public boundary and mechanical evidence ownership;
they make no claim about a real model's semantic accuracy. Capture is never
replaced and saved ancestors are never rewritten to manufacture support.
"""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as owner
from nm.brain.conversation import IncompleteConversation
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage, require_schema
from tests.brain_reader_fixture import fresh_review_reply, source_portion_reply
from tests.test_brain_material import material, mutation_scope, send
from tests.test_brain_material_purpose import PurposeModel, item, open_account, routed, seed_plan
from tests.test_brain_post_application_coverage_public import (
    CHANGED,
    ORIGINAL,
    TARGET,
    saved_revision,
)
from tests.test_brain_saved_record_support import current
from tests.test_brain_source_support_verifiers import coverage, disposition, verdict

V2 = "owned_coverage_application_v2"
REVISION = "application-revision:material:1"
READ = "Check the saved description against all my original reported words."
FIRST_REPAIR = "Please restate the custody description using my earlier reported account."
SECOND_REPAIR = "Restore the exact original custody wording in the saved description."
FIRST_RESULT = "native-first-repair:material:1"
EXTRA = "The dispatcher reports that a second parcel remains uncollected."


def review_plan(message=READ):
    return routed(message, source_purposes={message: "non_account"},
                  record_disposition="review_no_change", items=[item(
                      message, ORIGINAL, purposes=("interpretation_review",),
                      record_requirement={"kind": "review", "target_ids": [REVISION],
                                          "operation": "none",
                                          "success_condition": "Review all original accounts."})])


def repair_plan(message, target, statement):
    proposed = material(
        "circumstance", statement, message, relation="corrects", scope="current",
        placement="matter", related_material_ids=(target,),
        references=({"turn_id": "application-original", "role": "advocate",
                     "quoted": ORIGINAL},))
    return routed(message, candidates=[proposed], source_purposes={message: "non_account"},
                  record_disposition="performed", items=[{
                      **item(message, ORIGINAL, purposes=("interpretation_review",),
                             record_requirement={"kind": "change", "target_ids": [target],
                                                 "operation": "corrects",
                                                 "success_condition": "Restore original wording."}),
                      "mutation_scopes": [mutation_scope(
                          target, authority_kind="interpretation_review")],
                  }])


class NativeCoverageModel(PurposeModel):
    """Author original support and record selections inside actual reviewer calls."""

    def __init__(self, plans, *, choices, omission=False, reconsider=False):
        super().__init__(plans)
        self.choices = dict(choices)
        self.account_words = {ORIGINAL, CHANGED, EXTRA}
        self.omission = omission
        self.reconsider = reconsider
        self.raw_reviews = []

    def _decision(self, candidate, references, kind):
        identity = candidate["candidate_id"]
        selected = candidate["allowed_account_source_ids"]
        account = next(source for source in selected
                       if references[source]["quoted"] in self.account_words)
        row = verdict(kind, references[account], source_id=account, index=int(identity[1:]))
        row["account_check"]["source_ids"] = list(selected)
        row["account_check"]["source_checks"] = [{
            "source_id": source,
            "supplies_account_content": references[source]["quoted"] in self.account_words,
            "supports_proposal": references[source]["quoted"] in self.account_words,
            "support_spans": [{"start": 0, "end": len(references[source]["quoted"])}]
            if references[source]["quoted"] in self.account_words else [],
            "reason": "Original reported words supply content; instructions supply authority.",
        } for source in selected]
        targets = candidate.get("related_material_ids", candidate.get("related_dispute_ids", []))
        row["target_checks"] = [{
            "target_id": target, "identity_relation": "same_underlying_account",
            "account_preserved": True, "required_peer_ids": [],
            "reason": "The fixture declares that this wording repair preserves the account.",
        } for target in targets]
        return row

    def _review(self, operation, payload):
        references = payload["source_treatments"]
        kind = "material" if operation == "verify_material_grounding" else "dispute"
        peers = [*payload["candidates"], *payload.get("retained_candidate_context", [])]
        represented = {}
        for candidate in peers:
            for source in candidate["allowed_account_source_ids"]:
                represented.setdefault(source, []).append(candidate["candidate_id"])
        purposes = {source: "account" if reference["quoted"] in self.account_words
                    else "non_account" for source, reference in references.items()}
        portions, missing = [], False
        for source, reference in references.items():
            words = reference["quoted"]
            if purposes[source] == "non_account":
                selected = disposition(source, reference, status="non_account")
            elif kind == "dispute":
                selected = disposition(source, reference, status="outside_scope")
            elif words in self.choices:
                selected = disposition(source, reference, status="represented",
                                       record_ids=(self.choices[words],))
            elif source in represented:
                selected = disposition(source, reference, status="represented",
                                       candidate_ids=represented[source])
            else:
                selected = disposition(source, reference)
                missing = True
            portions.append(selected)
        return {
            "verdicts": [self._decision(candidate, references, kind)
                         for candidate in payload["candidates"]],
            "coverage": coverage(references, state="partial" if missing else "complete",
                                 purposes=purposes, dispositions=portions),
        }

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        if prompt.operation in {"verify_disputes", "verify_material_grounding"}:
            self.seen.append((prompt.operation, deepcopy(payload)))
            data = fresh_review_reply(payload, self._review(prompt.operation, payload))
            self.raw_reviews.append((prompt.operation, deepcopy(payload), deepcopy(data)))
        elif (self.omission and prompt.operation == "extract_legal_details"
              and "recovery_scope" not in payload):
            self.seen.append((prompt.operation, deepcopy(payload)))
            data = {"new_items": [], "changes": []}
        elif self.reconsider and prompt.operation in {
                "classify_account_sources", "reconsider_account_sources"}:
            self.seen.append((prompt.operation, deepcopy(payload)))
            data = source_portion_reply(payload, {"source_treatments": {
                source: {
                    "content_role": "examination_material"
                    if prompt.operation == "classify_account_sources" and source == "L1"
                    else "reported_matter_account"
                    if reference["quoted"] in self.account_words else "work_instruction",
                    "reason": "The fixture declares a changed source-purpose judgment.",
                } for source, reference in payload["original_source_catalogue"].items()}})
        else:
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        require_schema(data, schema)
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="fabricated-native-coverage", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def saved_read(client, wired, monkeypatch):
    _, opened, _, _, before = saved_revision(client, wired, monkeypatch, "corrects")
    model = NativeCoverageModel([review_plan()], choices={ORIGINAL: TARGET, CHANGED: REVISION})
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    response = send(client, READ, "native-history-reading", opened=opened)
    assert response.status_code == 200, response.text
    return model, opened, before, response.json(), wired.store.load(before.id)


def assert_native_reviews(model, *, count=1):
    for operation in ("verify_disputes", "verify_material_grounding"):
        rows = [(payload, data) for name, payload, data in model.raw_reviews if name == operation]
        assert len(rows) == count
        for payload, data in rows:
            assert payload["coverage_extent_contract"] == "coverage_source_extents_v1"
            assert set(payload["coverage_representation_options"]) == set(
                payload["source_treatments"])
            assert all(portion["extent"] == "whole_source"
                       for check in data["coverage"]["source_checks"]
                       for portion in check["substantive_spans"])
            assert all(portion["extent"] == "whole_source"
                       for portion in data["coverage"]["dispositions"])


def assert_replay(client, wired, model, opened, message, identity, first, saved):
    calls = len(model.seen)
    replay = send(client, message, identity, opened=opened)
    assert replay.status_code == 200, replay.text
    result = replay.json()
    assert result["replayed"] and result["metrics"]["llm_calls"] == 0
    assert result["elements"] == first["elements"]
    assert result["material_coverage"]["execution"] == first["material_coverage"]["execution"]
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved


def test_public_review_selects_current_and_archived_original_through_real_producers(
        client, wired, monkeypatch):
    model, opened, before, reply, saved = saved_read(client, wired, monkeypatch)
    assert_native_reviews(model)
    payload = next(payload for name, payload, _ in model.raw_reviews
                   if name == "verify_material_grounding")
    assert {row["id"] for row in payload["active_material"]} == {REVISION}
    assert {row["id"] for row in payload["historical_material"]} == {TARGET}
    assert all("original_record_support" not in row for row in payload["historical_material"])
    execution = reply["material_coverage"]["execution"]
    receipt = execution["coverage_application"]
    assert receipt["contract"] == execution["coverage_application_contract"] == V2
    assert set(receipt["inherited_history"]["detail_review"]) == {TARGET}
    assert receipt["bindings"] == [] and reply["material"] == []
    assert execution["semantic_coverage"] == "complete"
    assert reply["metrics"]["llm_calls"] == 8
    assert reply["metrics"]["recovery"]["dispatched_calls"] == 0
    assessment = execution["stages"]["detail_review"]["account_coverage"]
    original = next(row for row in assessment["dispositions"] if row["quoted"] == ORIGINAL)
    successor = next(row for row in assessment["dispositions"] if row["quoted"] == CHANGED)
    assert original["record_ids"] == []
    assert original["historical_representations"][0]["record_id"] == TARGET
    assert successor["record_ids"] == [REVISION]
    assert all("extent" not in row for row in assessment["dispositions"])
    assert saved.brain_chat[:2] == before.brain_chat
    assert current(wired, saved)[1:] == current(wired, before)[1:]
    reopened = client.get(f"/api/matters/{saved.id}")
    assert reopened.status_code == 200
    assert reopened.json()["material_record"]["rows"][0]["id"] == REVISION
    assert_replay(client, wired, model, opened, READ, "native-history-reading", reply, saved)


def test_authorised_earlier_account_repairs_keep_v2_when_only_a_current_target_is_retired(
        client, wired, monkeypatch):
    seed = seed_plan(ORIGINAL)
    seed["material"][0]["statement"] = "The keeper reports receipt custody."
    # Seed admission uses the existing independently authored fixture path.
    seed_model = PurposeModel([seed])
    opened = open_account(client, wired, monkeypatch, seed_model, ORIGINAL,
                          turn_id="application-original")
    before = wired.store.load(opened["matter_id"])
    model = NativeCoverageModel([
        repair_plan(FIRST_REPAIR, TARGET, "The keeper reports holding the signed parcel receipt."),
        repair_plan(SECOND_REPAIR, FIRST_RESULT, ORIGINAL),
    ], choices={})
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    replies = []
    for message, identity, target in (
            (FIRST_REPAIR, "native-first-repair", TARGET),
            (SECOND_REPAIR, "native-second-repair", FIRST_RESULT)):
        model.choices = {ORIGINAL: target}
        response = send(client, message, identity, opened=opened)
        assert response.status_code == 200, response.text
        reply = response.json()
        execution = reply["material_coverage"]["execution"]
        assert execution["coverage_application"]["contract"] == V2
        assert execution["coverage_application"]["inherited_history"] == {}
        assert execution["semantic_coverage"] == "complete"
        original = next(row for row in execution["stages"]["detail_review"][
            "account_coverage"]["dispositions"] if row["quoted"] == ORIGINAL)
        historical = original["historical_representations"][0]
        assert historical["record_id"] == target
        assert historical["original_source"]["turn_id"] == "application-original"
        assert reply["metrics"]["llm_calls"] == 8
        assert reply["metrics"]["recovery"]["dispatched_calls"] == 0
        replies.append(reply)
    assert_native_reviews(model, count=2)
    saved = wired.store.load(before.id)
    assert saved.brain_chat[0] == before.brain_chat[0]
    assert [row["message"] for row in saved.brain_chat] == [ORIGINAL, FIRST_REPAIR, SECOND_REPAIR]
    _, _, record = current(wired, saved)
    assert record["rows"][0]["statement"] == ORIGINAL
    first = next(row for row in record["history"] if row["id"] == FIRST_RESULT)
    assert first["source_turn_id"] == "native-first-repair" and first["quoted"] == FIRST_REPAIR
    assert_replay(client, wired, model, opened, SECOND_REPAIR, "native-second-repair",
                  replies[-1], saved)


@pytest.mark.parametrize("recovery", ("omission", "source_purpose"))
def test_existing_recovery_review_calls_keep_current_and_historical_support(
        client, wired, monkeypatch, recovery):
    _, opened, _, _, before = saved_revision(client, wired, monkeypatch, "corrects")
    added = material("event", EXTRA, EXTRA, scope="current", placement="matter")
    planned = routed(EXTRA, candidates=[added], items=[
        item(EXTRA, EXTRA, purposes=("account_contribution",), intent="contribution")])
    model = NativeCoverageModel([planned], choices={ORIGINAL: TARGET, CHANGED: REVISION},
                                omission=recovery == "omission",
                                reconsider=recovery == "source_purpose")
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    identity = "native-" + recovery
    response = send(client, EXTRA, identity, opened=opened)
    assert response.status_code == 200, response.text
    reply, saved = response.json(), wired.store.load(before.id)
    material_reviews = [payload for name, payload, _ in model.raw_reviews
                        if name == "verify_material_grounding"]
    assert len(material_reviews) == (2 if recovery == "omission" else 3)
    for payload in material_reviews:
        assert payload["coverage_extent_contract"] == "coverage_source_extents_v1"
        assert {row["id"] for row in payload["historical_material"]} == {TARGET}
        original = next(source for source, row in payload["source_treatments"].items()
                        if row["quoted"] == ORIGINAL)
        assert TARGET in payload["coverage_representation_options"][original]["record_ids"]
    execution = reply["material_coverage"]["execution"]
    assert execution["semantic_coverage"] == "complete"
    assert execution["coverage_application"]["contract"] == V2
    assert len(reply["material"]) == 1 and reply["material"][0]["statement"] == EXTRA
    assert saved.brain_chat[:2] == before.brain_chat
    if recovery == "omission":
        assert execution["semantic_recovery"]["omission_recovery"]["state"] == "reviewed"
        assert reply["metrics"]["recovery"]["dispatched_calls"] == 2
        assert reply["metrics"]["llm_calls"] == 10
    else:
        assert execution["semantic_recovery"]["source_reconsideration"]["state"] == "changed"
        assert reply["metrics"]["recovery"]["dispatched_calls"] == 4
        assert reply["metrics"]["llm_calls"] == 12
        assert [row["phase"] for row in reply["metrics"]["recovery"]["events"]] == [
            "verify_material_grounding:correction", "source_reconsideration:source_owner",
            "source_reconsideration:dispute_review", "source_reconsideration:detail_review"]
        dispute_reviews = [payload for name, payload, _ in model.raw_reviews
                           if name == "verify_disputes"]
        assert len(dispute_reviews) == 2
        assert all(payload["coverage_extent_contract"] == "coverage_source_extents_v1"
                   for payload in dispute_reviews)
    assert_replay(client, wired, model, opened, EXTRA, identity, reply, saved)


@pytest.mark.parametrize("fault", ("selector", "prefix_version", "owner"))
def test_saved_native_receipt_cannot_borrow_other_target_prefix_or_owner(
        client, wired, monkeypatch, fault):
    model, opened, _, _, saved = saved_read(client, wired, monkeypatch)
    changed = replace(saved, brain_chat=deepcopy(saved.brain_chat), version=saved.version + 1)
    receipt = changed.brain_chat[-1]["response"]["material_coverage"]["execution"][
        "coverage_application"]
    if fault == "selector":
        receipt["inherited_history"]["detail_review"][TARGET]["admission_candidate_id"] = "D99"
    elif fault == "prefix_version":
        receipt["expected_version"] += 1
    else:
        receipt["owner"]["advocate_id"] = "another-advocate"
    receipt["seal"] = owner._digest({key: value for key, value in receipt.items() if key != "seal"})
    wired.store.commit(changed, expected_version=saved.version)
    changed = wired.store.load(saved.id)
    calls = len(model.seen)
    response = send(client, READ, "native-history-reading", opened=opened)
    assert response.status_code == 409
    assert len(model.seen) == calls and wired.store.load(saved.id) == changed


def test_loaded_prefix_memo_is_shared_but_saved_replay_uses_its_own_snapshot(
        client, wired, monkeypatch):
    _, opened, _, _, before = saved_revision(client, wired, monkeypatch, "corrects")
    require, calls = owner._SavedExecutionMemo.require, []

    def observe(memo, matter, prior):
        result = require(memo, matter, prior)
        calls.append((id(memo), len(memo.snapshot.brain_chat), memo.snapshot.version,
                      len(matter.brain_chat), matter.version))
        return result

    monkeypatch.setattr(owner._SavedExecutionMemo, "require", observe)
    model = NativeCoverageModel([review_plan()], choices={ORIGINAL: TARGET, CHANGED: REVISION})
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    response = send(client, READ, "native-memo-reading", opened=opened)
    assert response.status_code == 200, response.text
    saved = wired.store.load(before.id)
    assert_replay(client, wired, model, opened, READ, "native-memo-reading",
                  response.json(), saved)
    loaded_ids = {identity for identity, size, version, _, _ in calls
                  if size == len(before.brain_chat) and version == before.version}
    replay_ids = {identity for identity, size, _, _, _ in calls
                  if size == len(before.brain_chat) + 1}
    assert len(loaded_ids) == 1 and replay_ids and loaded_ids.isdisjoint(replay_ids)
    original_memo = owner._SavedExecutionMemo(before)
    assert original_memo.require(before, ()) == (len(before.brain_chat), before.version)
    with pytest.raises(IncompleteConversation):
        original_memo.require(saved, ())


@pytest.mark.parametrize("fault", ("stage", "missing_stage", "container", "overlap"))
def test_coverage_input_handoff_rejects_wrong_stage_maps_before_returning_payload(
        client, wired, monkeypatch, fault):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    conversation, disputes, details = current(wired, saved)
    memo = owner._SavedExecutionMemo(saved)
    support = owner._saved_record_support(
        saved, conversation, disputes=disputes, details=details, _memo=memo)
    history = owner._saved_historical_support(
        saved, conversation, disputes=disputes, details=details, _memo=memo)
    stage = "detail_review"
    if fault == "stage":
        stage = "other_review"
    elif fault == "missing_stage":
        support.pop("dispute_review")
    elif fault == "container":
        history["detail_review"] = []
    else:
        support[stage][TARGET] = deepcopy(history[stage][TARGET]["record_support"])
    before = deepcopy((support, history))
    with pytest.raises(owner.ExecutionEvidenceInvalid):
        owner._coverage_review_inputs(stage, support, history)
    assert (support, history) == before


def test_coverage_input_handoff_keeps_legacy_default_and_detaches_fresh_presentation(
        client, wired, monkeypatch):
    assert owner._coverage_review_inputs("detail_review", None, None) == {}
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    conversation, disputes, details = current(wired, saved)
    memo = owner._SavedExecutionMemo(saved)
    support = owner._saved_record_support(
        saved, conversation, disputes=disputes, details=details, _memo=memo)
    history = owner._saved_historical_support(
        saved, conversation, disputes=disputes, details=details, _memo=memo)
    before = deepcopy((support, history))
    result = owner._coverage_review_inputs("detail_review", support, history)
    assert set(result["coverage_record_support"]) == {TARGET, REVISION}
    assert [row["id"] for row in result["historical_material"]] == [TARGET]
    result["historical_material"][0]["statement"] = "Presentation-only mutation"
    result["coverage_record_support"][TARGET]["review"]["reason"] = "Presentation-only mutation"
    assert (support, history) == before
