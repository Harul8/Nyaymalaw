"""Independent admission survives a sibling coverage failure through public saving.

The fixture authors source meaning, support and malformed coverage explicitly.
These checks prove receipt ownership and reuse, not real-model semantic quality.
The actual capture, record application and saved replay are never replaced.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as owner
from tests.test_brain_material import material, mutation_scope, send
from tests.test_brain_material_purpose import PurposeModel, item, open_account, routed, seed_plan
from tests.test_brain_native_coverage_turn import NativeCoverageModel, assert_replay
from tests.test_brain_saved_record_support import current

ORIGINAL = "The custodian stored six marked cylinders in the inspection rack."
CORRECTION = "Correction: the custodian stored seven marked cylinders in the inspection rack."
CURRENT = "The custodian stored seven marked cylinders in the inspection rack."
READ = "Compare the saved quantity with my original and corrected accounts."
TARGET = "admission-original:material:1"
SUCCESSOR = "admission-correction:material:1"
V2 = "owned_coverage_application_v2"
V3 = "owned_coverage_application_v3"


def review_plan():
    return routed(READ, source_purposes={READ: "non_account"},
                  record_disposition="review_no_change", items=[item(
                      READ, CURRENT, purposes=("interpretation_review",),
                      record_requirement={"kind": "review", "target_ids": [SUCCESSOR],
                                          "operation": "none",
                                          "success_condition": "Compare both original accounts."})])


class UnassessedCoverageModel(NativeCoverageModel):
    """A complete positive verdict is independent of a contradictory range status."""

    def __init__(self, plans, *, failed_stages):
        super().__init__(plans, choices={ORIGINAL: TARGET})
        self.account_words = {ORIGINAL, CORRECTION}
        self.failed_stages = set(failed_stages)

    def _decision(self, candidate, references, kind):
        row = super()._decision(candidate, references, kind)
        row["candidate_id"] = candidate["candidate_id"]
        return row

    def _review(self, operation, payload):
        data = super()._review(operation, payload)
        if operation in self.failed_stages:
            for portion in data["coverage"]["dispositions"]:
                if payload["source_treatments"][portion["source_id"]][
                        "quoted"] in self.account_words:
                    portion.update(status="non_account", candidate_ids=[], record_ids=[])
        return data


def save_correction(client, wired, monkeypatch, failed_stages):
    seed = PurposeModel([seed_plan(ORIGINAL)])
    opened = open_account(client, wired, monkeypatch, seed, ORIGINAL,
                          turn_id="admission-original")
    before = wired.store.load(opened["matter_id"])
    revised = material(
        "circumstance", CURRENT, CORRECTION, relation="corrects", scope="current",
        placement="matter", related_material_ids=(TARGET,), references=({
            "turn_id": "admission-original", "role": "advocate", "quoted": ORIGINAL},))
    planned = routed(CORRECTION, candidates=[revised], record_disposition="performed", items=[{
        **item(CORRECTION, CURRENT, purposes=("account_contribution",), intent="contribution"),
        "mutation_scopes": [mutation_scope(TARGET)],
    }])
    model = UnassessedCoverageModel([planned, review_plan()], failed_stages=failed_stages)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    response = send(client, CORRECTION, "admission-correction", opened=opened)
    assert response.status_code == 200, response.text
    return model, opened, before, response.json(), wired.store.load(before.id)


def saved_support(wired, saved):
    conversation, disputes, details = current(wired, saved)
    memo = owner._SavedExecutionMemo(saved)
    return (
        owner._saved_record_support(saved, conversation, disputes=disputes,
                                    details=details, _memo=memo),
        owner._saved_historical_support(saved, conversation, disputes=disputes,
                                        details=details, _memo=memo),
    )


@pytest.mark.parametrize("failed_stages", (
    {"verify_disputes"},
    {"verify_material_grounding"},
    {"verify_disputes", "verify_material_grounding"},
))
def test_public_accepted_correction_keeps_original_support_despite_unassessed_coverage(
        client, wired, monkeypatch, failed_stages):
    model, opened, before, reply, saved = save_correction(
        client, wired, monkeypatch, failed_stages)
    execution = reply["material_coverage"]["execution"]
    receipt = execution["coverage_application"]
    both_failed = len(failed_stages) == 2
    assert receipt["contract"] == execution["coverage_application_contract"] == (
        V3 if both_failed else V2)
    assert receipt["inherited_history"] == {}
    assert execution["semantic_coverage"] == ("unassessed" if both_failed else "partial")
    assert reply["material_coverage"]["state"] == "partial"
    expected_assessments = {
        stage for operation, stage in (("verify_disputes", "dispute_review"),
                                       ("verify_material_grounding", "detail_review"))
        if operation not in failed_stages}
    assert set(receipt["pre_application_assessments"]) == expected_assessments
    for operation, stage in (("verify_disputes", "dispute_review"),
                             ("verify_material_grounding", "detail_review")):
        assert execution["stages"][stage]["account_coverage"]["state"] == (
            "unassessed" if operation in failed_stages else "complete")
    (binding,) = receipt["bindings"]
    assert binding["stage"] == "detail_review" and binding["result_id"] == SUCCESSOR
    assert binding["review"]["verdict"] == "accept"
    assert binding["review"]["operation_supported"] is True
    assert {row["source_id"] for row in binding["review"]["account_check"][
        "source_checks"] if row["supports_proposal"]} == {"L1", "P1S1"}
    assert all(row["support_spans"] for row in binding["review"][
        "account_check"]["source_checks"])
    effect = next(row for row in owner.effect_catalogue(execution).values()
                  if row["result_id"] == SUCCESSOR)
    assert effect["performed"] is True and effect["retired_target_ids"] == [TARGET]
    assert reply["material"][0]["id"] == SUCCESSOR
    assert reply["metrics"]["llm_calls"] == 8 + len(failed_stages)
    assert reply["metrics"]["recovery"]["dispatched_calls"] == len(failed_stages)
    corrections = [payload for operation, payload, _ in model.raw_reviews
                   if operation == "verify_material_grounding"
                   and payload.get("retained_candidate_context")]
    if "verify_material_grounding" in failed_stages:
        assert len(corrections) == 1 and corrections[0]["candidates"] == []
        assert corrections[0]["retained_candidate_context"][0]["candidate_id"] == "D1"
    assert saved.brain_chat[0] == before.brain_chat[0]
    assert [row["message"] for row in saved.brain_chat] == [ORIGINAL, CORRECTION]
    support, history = saved_support(wired, saved)
    assert set(support["detail_review"]) == {SUCCESSOR}
    assert support["detail_review"][SUCCESSOR]["review"] == binding["review"]
    assert {row["quoted"] for row in support["detail_review"][SUCCESSOR][
        "source_references"].values()} == {ORIGINAL, CORRECTION}
    assert set(history["detail_review"]) == {TARGET}
    assert history["detail_review"][TARGET]["record_support"]["review"] == (
        before.brain_chat[0]["response"]["material_coverage"]["execution"][
            "coverage_application"]["bindings"][0]["review"])
    reopened = client.get(f"/api/matters/{saved.id}")
    assert reopened.status_code == 200
    assert [(row["id"], row["statement"]) for row in reopened.json()[
        "material_record"]["rows"]] == [(SUCCESSOR, CURRENT)]
    assert_replay(client, wired, model, opened, CORRECTION, "admission-correction", reply, saved)

    model.failed_stages.clear()
    model.choices = {ORIGINAL: TARGET, CORRECTION: SUCCESSOR}
    response = send(client, READ, "admission-review", opened=opened)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    payload = next(payload for operation, payload, _ in reversed(model.raw_reviews)
                   if operation == "verify_material_grounding")
    for words, identity in ((ORIGINAL, TARGET), (CORRECTION, SUCCESSOR)):
        source = next(source for source, row in payload["source_treatments"].items()
                      if row["quoted"] == words)
        assert identity in payload["coverage_representation_options"][source]["record_ids"]
    assert {row["id"] for row in payload["historical_material"]} == {TARGET}
    assert reviewed["material_coverage"]["execution"]["semantic_coverage"] == "complete"
    assert reviewed["material"] == [] and reviewed["metrics"]["llm_calls"] == 8
    final = wired.store.load(saved.id)
    assert final.brain_chat[:2] == saved.brain_chat
    assert current(wired, final)[1:] == current(wired, saved)[1:]
    assert_replay(client, wired, model, opened, READ, "admission-review", reviewed, final)


def test_failed_coverage_without_a_positive_unit_does_not_create_an_admission_receipt(
        client, wired, monkeypatch):
    seed = PurposeModel([seed_plan(ORIGINAL)])
    opened = open_account(client, wired, monkeypatch, seed, ORIGINAL,
                          turn_id="admission-original")
    before = wired.store.load(opened["matter_id"])
    planned = review_plan()
    planned["_record_disposition"] = "unresolved"
    planned["items"][0]["record_requirement"]["target_ids"] = [TARGET]
    model = UnassessedCoverageModel(
        [planned], failed_stages={"verify_disputes", "verify_material_grounding"})
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    response = send(client, READ, "admission-unresolved", opened=opened)
    assert response.status_code == 200, response.text
    reply, saved = response.json(), wired.store.load(before.id)
    execution = reply["material_coverage"]["execution"]
    assert execution["semantic_coverage"] == "unassessed"
    assert "coverage_application_contract" not in execution
    assert "coverage_application" not in execution and reply["material"] == []
    assert reply["metrics"]["llm_calls"] == 10
    assert current(wired, saved)[1:] == current(wired, before)[1:]
    support, history = saved_support(wired, saved)
    assert set(support["detail_review"]) == {TARGET} and history["detail_review"] == {}
    assert_replay(client, wired, model, opened, READ, "admission-unresolved", reply, saved)


def test_checked_opening_without_material_keeps_its_admission_and_unassessed_gap(
        client, wired, monkeypatch):
    planned = routed(ORIGINAL, opening=True, items=[item(
        ORIGINAL, ORIGINAL, purposes=("account_contribution",),
        intent="contribution", opening=True)])
    model = UnassessedCoverageModel(
        [planned], failed_stages={"verify_disputes", "verify_material_grounding"})
    opened = open_account(client, wired, monkeypatch, model, ORIGINAL,
                          turn_id="admission-heading")
    saved = wired.store.load(opened["matter_id"])
    execution = opened["material_coverage"]["execution"]
    receipt = execution["coverage_application"]
    assert receipt["contract"] == V3 and receipt["pre_application_assessments"] == {}
    assert receipt["bindings"] == [] and receipt["inherited_history"] == {}
    assert receipt["opening"]["review"]["candidate_id"] == "O1"
    assert receipt["opening"]["review"]["operation_supported"] is True
    assert receipt["opening"]["result"]["ready"] is True
    assert execution["semantic_coverage"] == "unassessed" and opened["material"] == []
    assert opened["metrics"]["llm_calls"] == 10
    assert saved.title == receipt["opening"]["result"]["title"]
    support, history = saved_support(wired, saved)
    assert support == history == {"dispute_review": {}, "detail_review": {}}
    assert_replay(client, wired, model, None, ORIGINAL, "admission-heading", opened, saved)


@pytest.mark.parametrize("fault", (
    "source", "target", "empty", "assessment", "stage_complete", "semantic_complete",
    "v1", "v2"))
def test_saved_empty_assessment_receipt_keeps_admission_and_version_gates(
        client, wired, monkeypatch, fault):
    model, opened, _, _, saved = save_correction(
        client, wired, monkeypatch, {"verify_disputes", "verify_material_grounding"})
    changed = replace(saved, brain_chat=deepcopy(saved.brain_chat), version=saved.version + 1)
    execution = changed.brain_chat[-1]["response"]["material_coverage"]["execution"]
    receipt = execution["coverage_application"]
    if fault == "source":
        receipt["bindings"][0]["review"]["account_check"]["source_checks"][0][
            "support_spans"][0]["quoted"] = "An invented original account."
    elif fault == "target":
        receipt["bindings"][0]["proposal"]["related_material_ids"] = ["foreign:material:1"]
    elif fault == "empty":
        receipt["bindings"] = []
    elif fault == "assessment":
        receipt["pre_application_assessments"] = {"detail_review": execution["stages"][
            "detail_review"]["account_coverage"]}
    elif fault == "semantic_complete":
        execution["semantic_coverage"] = "complete"
    elif fault == "stage_complete":
        stage_coverage = execution["stages"]["detail_review"]["account_coverage"]
        assert "selection_contract" not in stage_coverage
        stage_coverage["state"] = "complete"
    else:
        version = "owned_coverage_application_" + fault
        execution["coverage_application_contract"] = receipt["contract"] = version
        if fault == "v1":
            receipt.pop("inherited_history")
    receipt["seal"] = owner._digest({key: value for key, value in receipt.items() if key != "seal"})
    wired.store.commit(changed, expected_version=saved.version)
    changed = wired.store.load(saved.id)
    calls = len(model.seen)
    response = send(client, CORRECTION, "admission-correction", opened=opened)
    assert response.status_code == 409
    assert len(model.seen) == calls and wired.store.load(saved.id) == changed


def test_independent_admission_applies_when_a_mechanical_fallback_remains_partial(
        client, wired, monkeypatch):
    model, _, before, reply, saved = save_correction(
        client, wired, monkeypatch, {"verify_disputes", "verify_material_grounding"})
    execution = deepcopy(reply["material_coverage"]["execution"])
    execution["stages"]["detail_review"]["account_coverage"]["state"] = "partial"
    execution["semantic_coverage"] = "partial"
    assert "selection_contract" not in execution["stages"]["detail_review"]["account_coverage"]
    before_conversation, before_disputes, before_details = current(wired, before)
    _, disputes, details = current(wired, saved)
    _, latest_sources, prior_sources = owner.addressed_sources(
        before_conversation.messages, CORRECTION)
    calls, original = len(model.seen), deepcopy(execution)
    applied = owner._apply_coverage_application(
        execution, execution["coverage_application"], material=reply["material"],
        source_treatments=reply["material_coverage"]["source_treatments"],
        latest_sources=latest_sources, prior_sources=prior_sources,
        before_disputes=before_disputes, before_details=before_details,
        disputes=disputes, details=details, prefix_matter=before,
        _memo=owner._SavedExecutionMemo(before))
    assert applied == {} and execution == original
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved


def test_complete_v2_assessments_cannot_be_erased_by_relabelling_the_receipt_v3(
        client, wired, monkeypatch):
    model, opened, _, _, saved = save_correction(client, wired, monkeypatch, set())
    changed = replace(saved, brain_chat=deepcopy(saved.brain_chat), version=saved.version + 1)
    execution = changed.brain_chat[-1]["response"]["material_coverage"]["execution"]
    receipt = execution["coverage_application"]
    assert receipt["contract"] == V2 and execution["semantic_coverage"] == "complete"
    execution["coverage_application_contract"] = receipt["contract"] = V3
    receipt["pre_application_assessments"] = receipt["inherited_history"] = {}
    receipt["seal"] = owner._digest({key: value for key, value in receipt.items() if key != "seal"})
    wired.store.commit(changed, expected_version=saved.version)
    changed = wired.store.load(saved.id)
    calls = len(model.seen)
    response = send(client, CORRECTION, "admission-correction", opened=opened)
    assert response.status_code == 409
    assert len(model.seen) == calls and wired.store.load(saved.id) == changed

