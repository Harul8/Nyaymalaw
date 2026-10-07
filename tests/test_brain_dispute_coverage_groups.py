"""Fresh dispute groups preserve original support, scoped gaps and durable replay.

Explicit scripted meanings and verdicts qualify mechanical producer/consumer
handoffs. They are not evidence of real-model dispute classification quality.
Native group outputs are authored directly, without fixture group transport.
"""

import json
from copy import deepcopy

import pytest

from nm.brain import dispute_verification as owner
from nm.brain import record_review as record
from nm.brain import turn
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow,
    ModelResult,
    SchemaViolation,
    Usage,
    estimate_tokens,
    on_the_wire,
    require_schema,
)
from tests.test_brain_dispute_coverage_choices import (
    ACCOUNT,
    EARLIER,
    OMITTED,
    REQUEST,
    check,
    record_row,
)
from tests.test_brain_material import material, send
from tests.test_brain_material_coverage_choices import proof
from tests.test_brain_material_coverage_groups import (
    account_group,
    groups,
    portion,
    raw_judge,
    scripted_public_review,
)
from tests.test_brain_material_purpose import PurposeModel, item, open_account, routed
from tests.test_brain_source_support_verifiers import (
    RawJudge,
    coverage,
    disposition,
    proposal,
    source_catalogue,
    verdict,
)


def reply(rows, judgment):
    """Select exactly the explicitly authored dispute checks under the fresh wire."""
    native = deepcopy(rows)
    for row in native:
        row["account_check"].pop("source_ids")
    return {"verdicts": native, "coverage": deepcopy(judgment)}


def assert_group_offer(call):
    payload = call["payload"]
    assert payload["coverage_group_contract"] == record.COVERAGE_GROUP_CONTRACT
    assert payload["coverage_extent_contract"] == record.COVERAGE_EXTENT_CONTRACT
    assert "coverage_record_support" not in payload
    assert on_the_wire(call["schema"]["properties"]["coverage"]) == on_the_wire(
        record.coverage_schema(
            tuple(payload["coverage_source_ids"]), source_references=payload["source_treatments"],
            record_ids=tuple(payload["coverage_record_ids"]),
            candidate_ids=tuple(payload["coverage_candidate_ids"]),
            representation_options=payload["coverage_representation_options"],
            native_extents=True, native_groups=True))


@pytest.mark.parametrize("support", (OMITTED, None), ids=("default", "explicit-none"))
def test_default_dispute_generation_remains_flat_without_new_markers_or_calls(support):
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("dispute", ACCOUNT)
    judgment = coverage(references, dispositions=[disposition(
        "L1", references["L1"], status="represented", candidate_ids=("C1",))])
    model = RawJudge([{"verdicts": [verdict("dispute", references["L1"])],
                       "coverage": judgment}])
    result, assessed, _, _ = check(
        model, latest=ACCOUNT, earlier=(), candidates=(candidate,), support=support)
    assert result == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 1
    payload = model.calls[0]["payload"]
    assert "coverage_group_contract" not in payload and "coverage_extent_contract" not in payload
    assert "source_groups" not in model.calls[0]["schema"]["properties"]["coverage"]["properties"]
    require_schema(model.calls[0]["output"], on_the_wire(model.calls[0]["schema"]))


@pytest.mark.parametrize("explicit_false", (False, True), ids=("omitted", "explicit-false"))
def test_dispute_private_schema_preserves_extent_only_mode(explicit_false):
    references, _ = source_catalogue(ACCOUNT)
    kwargs = {"native_coverage_groups": False} if explicit_false else {}
    offered = owner._schema(
        (), tuple(references), coverage_ids=tuple(references), source_references=references,
        coverage_candidate_ids=("C1",), native_coverage_extents=True, wire=True, **kwargs)
    assert offered["properties"]["coverage"] == record.coverage_schema(
        tuple(references), source_references=references, candidate_ids=("C1",), native_extents=True)
    assert "source_groups" not in offered["properties"]["coverage"]["properties"]


def test_explicit_empty_owned_proof_activates_groups_with_actual_positive_candidate_support():
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("dispute", ACCOUNT)
    judgment = groups(references, selected={"L1": account_group(portion(
        status="represented", candidates=("C1",)))})
    authored = reply([verdict("dispute", references["L1"])], judgment)
    model = raw_judge(authored, authored)
    state = {}
    result, assessed, _, _ = check(
        model, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={}, state=state)
    assert result == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 1
    assert_group_offer(model.calls[0])
    require_schema(authored, on_the_wire(model.calls[0]["schema"]))
    canonical = state["cache"].decisions["C1"]
    original_check, = canonical["account_check"]["source_checks"]
    assert original_check["source_id"] == "L1"
    assert [(span["start"], span["end"]) for span in original_check["support_spans"]] == [
        (0, len(ACCOUNT))]
    assert canonical["verdict"] == "accept"
    assert assessed["selection_contract"] == record.COVERAGE_SELECTION_CONTRACT
    assert assessed["dispositions"][0]["quoted"] == ACCOUNT
    assert "source_groups" not in assessed and "extent" not in repr(assessed)
    assert "coverage_group_contract" not in state["cache"].context


@pytest.mark.parametrize("domain", ("current", "held", "historical"))
def test_current_held_and_historical_records_use_independent_original_admission_proof(domain):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row(state="superseded" if domain == "historical" else domain)
    support = {row["id"]: proof(references["P1S1"])}
    judgment = groups(references, selected={
        "P1S1": account_group(portion(status="represented", records=(row["id"],))),
        "L1": {"content_purpose": "non_account", "reason": "Explicit review authority only."}})
    authored = reply([], judgment)
    model = raw_judge(authored, authored)
    before = deepcopy((row, support))
    result, assessed, _, _ = check(
        model, records=() if domain == "historical" else (row,),
        history=(row,) if domain == "historical" else (), support=support)
    assert result == () and assessed["state"] == "complete" and len(model.calls) == 1
    assert (row, support) == before
    call = model.calls[0]
    assert_group_offer(call)
    assert call["payload"]["coverage_representation_options"] == {
        "P1S1": {"record_ids": [row["id"]], "candidate_ids": []},
        "L1": {"record_ids": [], "candidate_ids": []}}
    assert "original-local-source" not in repr(call["payload"])
    assert call["payload"]["active_disputes"] == (
        [] if domain == "historical" else [record.derived_record(row)])
    if domain == "historical":
        assert call["payload"]["historical_disputes"] == [record.derived_record(row)]
    require_schema(authored, on_the_wire(call["schema"]))
    assert assessed["dispositions"][0]["quoted"] == ACCOUNT


@pytest.mark.parametrize("status", ("missing", "outside_scope"))
def test_unrepresented_account_is_not_relabelled_non_account_for_empty_dispute_extraction(status):
    latest = ACCOUNT if status == "missing" else "The courier delivered the cylinder."
    references, _ = source_catalogue(latest)
    judgment = groups(references, state="partial" if status == "missing" else "complete",
                      selected={"L1": account_group(portion(status=status))})
    authored = reply([], judgment)
    model = raw_judge(authored, authored)
    result, assessed, _, _ = check(model, latest=latest, earlier=(), support={})
    assert result == () and len(model.calls) == 1
    assert assessed["state"] == judgment["state"]
    assert assessed["source_checks"][0]["content_purpose"] == "account"
    assert assessed["dispositions"][0]["status"] == status
    assert assessed["missing_source_ids"] == (["L1"] if status == "missing" else [])
    assert model.calls[0]["payload"]["coverage_representation_options"] == {
        "L1": {"record_ids": [], "candidate_ids": []}}
    assert_group_offer(model.calls[0])
    require_schema(authored, on_the_wire(model.calls[0]["schema"]))


def test_rejected_candidate_cannot_represent_account_despite_initial_native_eligibility():
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("dispute", ACCOUNT)
    bad = groups(references, selected={"L1": account_group(portion(
        status="represented", candidates=("C1",)))})
    good = groups(references, state="partial", selected={"L1": account_group(portion(
        status="missing"))})
    negative = verdict("dispute", references["L1"], accept=False)
    negative["candidate_role"] = "supporting_premise"
    negative["reason"] = "The fixture independently rejects this proposed dispute role."
    model = raw_judge(reply([negative], bad), reply([], good))
    result, assessed, _, _ = check(
        model, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={})
    assert result == () and assessed["state"] == "partial" and len(model.calls) == 2
    assert assessed["missing_source_ids"] == ["L1"]
    assert model.calls[0]["payload"]["coverage_representation_options"]["L1"][
        "candidate_ids"] == ["C1"]
    assert model.calls[1]["payload"]["coverage_representation_options"]["L1"][
        "candidate_ids"] == []
    assert model.calls[1]["payload"]["candidates"] == []
    assert model.calls[1]["payload"]["retained_candidate_context"][0]["decision"][
        "verdict"] == "reject"
    require_schema(model.calls[0]["output"], on_the_wire(model.calls[0]["schema"]))
    require_schema(model.calls[1]["output"], on_the_wire(model.calls[1]["schema"]))


def test_positive_candidate_source_cannot_fill_another_original_sources_missing_dispute():
    first = "The recipient denies receipt of the north cylinder."
    latest = first + " The sender contests the charge for the south cylinder."
    references, _ = source_catalogue(latest)
    candidate = proposal("dispute", first)
    bad = groups(references, selected={"L2": account_group(portion(
        status="represented", candidates=("C1",)))})
    good = groups(references, state="partial", selected={"L2": account_group(portion(
        status="missing"))})
    model = raw_judge(reply([verdict("dispute", references["L1"])], bad), reply([], good))
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert result == (candidate,) and assessed["state"] == "partial" and len(model.calls) == 2
    assert assessed["missing_source_ids"] == ["L2"]
    assert model.calls[0]["payload"]["coverage_representation_options"]["L2"][
        "candidate_ids"] == ["C1"]
    assert model.calls[1]["payload"]["coverage_representation_options"]["L2"][
        "candidate_ids"] == []
    require_schema(model.calls[0]["output"], on_the_wire(model.calls[0]["schema"]))


def test_saved_dispute_choice_requires_checked_support_overlapping_its_selected_portion():
    first = "The recipient denies receipt,"
    latest = first + " and contests the carrier's separate storage charge."
    references, _ = source_catalogue(latest)
    split = len(first)
    row = record_row(words=first, turn="current")
    support = {row["id"]: proof(references["L1"], portions=[{"start": 0, "end": split}])}
    bad = groups(references, selected={"L1": account_group(
        portion(bounds=(0, split)), portion(status="represented", records=(row["id"],),
                                           bounds=(split, len(latest))))})
    good = deepcopy(bad)
    good["state"] = "partial"
    good["source_groups"]["L1"]["account_portions"][1].update(status="missing", record_ids=[])
    model = raw_judge(reply([], bad), reply([], good))
    _, assessed, _, _ = check(model, latest=latest, earlier=(), records=(row,), support=support)
    assert assessed["state"] == "partial" and assessed["missing_source_ids"] == ["L1"]
    assert len(model.calls) == 2
    require_schema(model.calls[0]["output"], on_the_wire(model.calls[0]["schema"]))
    assert assessed["dispositions"][1]["quoted"] == latest[split:]


@pytest.mark.parametrize("fault", ("foreign_source", "omitted_source", "foreign_record",
                                    "purpose_fields", "account_context_overlap"))
def test_invalid_group_retries_coverage_and_retains_valid_dispute_peer(fault):
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("dispute", ACCOUNT)
    good = groups(references, selected={"L1": account_group(portion(
        status="represented", candidates=("C1",)))})
    bad = deepcopy(good)
    if fault == "foreign_source":
        bad["source_groups"]["foreign"] = bad["source_groups"].pop("L1")
    elif fault == "omitted_source":
        bad["source_groups"].clear()
    elif fault == "foreign_record":
        bad["source_groups"]["L1"]["account_portions"][0].update(
            record_ids=["other-matter:dispute"], candidate_ids=[])
    elif fault == "purpose_fields":
        bad["source_groups"]["L1"]["content_purpose"] = "non_account"
    else:
        bad["source_groups"]["L1"]["non_account_portions"] = [
            {"extent": "whole_source", "reason": "Deliberately contradictory source purpose."}]
    first = reply([verdict("dispute", references["L1"])], bad)
    second = reply([], good)
    model = raw_judge(first, second)
    result, assessed, _, _ = check(
        model, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={})
    assert result == (candidate,) and assessed["state"] == "complete" and len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert correction["candidates"] == [] and correction["pending_review_keys"] == ["$coverage"]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == ["C1"]
    assert correction["coverage_validation_issue"]
    require_schema(second, on_the_wire(model.calls[1]["schema"]))
    if fault == "account_context_overlap":
        require_schema(first, on_the_wire(model.calls[0]["schema"]))
    else:
        with pytest.raises(SchemaViolation):
            require_schema(first, on_the_wire(model.calls[0]["schema"]))


def test_actual_grouped_strict_wire_schema_is_budgeted_before_dispute_dispatch():
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("dispute", ACCOUNT)
    judgment = groups(references, selected={"L1": account_group(portion(
        status="represented", candidates=("C1",)))})
    authored = reply([verdict("dispute", references["L1"])], judgment)
    probe = raw_judge(authored, authored)
    check(probe, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={})
    call = probe.calls[0]
    assert_group_offer(call)
    prompt_only_budget = estimate_tokens(call["prompt"].system + call["prompt"].user) + (
        call["max_tokens"])
    bounded = raw_judge(authored)
    bounded.context_budget = lambda tier: prompt_only_budget
    with pytest.raises(ContextOverflow):
        check(bounded, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={})
    assert bounded.calls == []


def test_unrequested_coverage_does_not_add_group_markers_or_a_new_stage():
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("dispute", ACCOUNT)
    model = raw_judge({"verdicts": reply([verdict("dispute", references["L1"])], {})["verdicts"]})
    result, assessed, _, _ = check(
        model, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={}, scope=None)
    assert result == (candidate,) and assessed["state"] == "unassessed" and len(model.calls) == 1
    assert "coverage" not in model.calls[0]["schema"]["properties"]
    assert "coverage_group_contract" not in model.calls[0]["payload"]
    assert "coverage_extent_contract" not in model.calls[0]["payload"]


class PublicDisputeGroupsModel(PurposeModel):
    """Raw dispute judgments coexist with independently scripted material work."""

    def __init__(self, *, repair=False):
        seed = routed(ACCOUNT, opening=True, candidates=[
            material("dispute", ACCOUNT, ACCOUNT),
            material("circumstance", ACCOUNT, ACCOUNT, placement="matter")], items=[item(
                ACCOUNT, ACCOUNT, purposes=("account_contribution",),
                intent="contribution", opening=True)])
        seed["opening"]["summary"] = ACCOUNT
        seed["_dispute_scope"] = {ACCOUNT: "account"}
        review = routed(REQUEST, record_disposition="review_no_change",
                        source_purposes={REQUEST: "non_account"}, items=[item(
                            REQUEST, ACCOUNT, purposes=("interpretation_review",),
                            record_requirement={
                                "kind": "review", "operation": "none",
                                "target_ids": ["dispute-group-original:material:1"],
                                "success_condition": (
                                    "The dispute preserves the attributed positions.")})])
        review["_response_expressions"] = {0: {
            "operator": "source_account", "source_ids": [],
            "record_ids": ["dispute-group-original:material:1"], "focus": "none"}}
        review["_coverage_links"] = {
            ACCOUNT: {"record_ids": ["dispute-group-original:material:2"], "candidate_ids": []}}
        super().__init__([seed, review])
        self.repair = repair
        self.group_calls = []

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation == "verify_continuation":
            payload = json.loads(prompt.user)
            data = scripted_public_review(
                payload, outcome="no_change_justified"
                if self.current_record_disposition == "review_no_change" else "not_requested")
            require_schema(data, schema)
            self.seen.append((prompt.operation, deepcopy(payload)))
            return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                               model="scripted-public-group-review", usage=Usage(0, 0, 0),
                               latency_ms=0, completion=Completion.COMPLETE)
        if prompt.operation != "verify_disputes":
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            require_schema(result.data, schema)
            return result
        payload = json.loads(prompt.user)
        references = payload["source_treatments"]
        original = "".join(row["text"] for row in payload["latest_message_spans"]) == ACCOUNT
        rows = []
        for candidate in payload["candidates"]:
            row = verdict("dispute", references["L1"])
            row["candidate_id"] = candidate["candidate_id"]
            rows.append(row)
        selected = ({"L1": account_group(portion(status="represented", candidates=("C1",)))}
                    if original else {
                        "P1S1": account_group(portion(
                            status="represented", records=("dispute-group-original:material:1",))),
                        "L1": {"content_purpose": "non_account",
                               "reason": (
                                   "Original review authority supplies no new party position.")}})
        judgment = groups(references, selected=selected)
        if original and self.repair and not self.group_calls:
            judgment["source_groups"]["L1"]["non_account_portions"] = [{
                "extent": "whole_source", "reason": "Deliberately contradictory purpose range."}]
        data = reply(rows, judgment)
        self.seen.append((prompt.operation, deepcopy(payload)))
        self.group_calls.append({"payload": deepcopy(payload), "schema": deepcopy(schema),
                                 "output": deepcopy(data)})
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="scripted-dispute-groups", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


@pytest.mark.parametrize("repair", (False, True), ids=("ordinary", "conditional-coverage-repair"))
def test_public_dispute_groups_save_positive_original_proof_and_replay_no_change_without_calls(
        client, wired, monkeypatch, repair):
    model = PublicDisputeGroupsModel(repair=repair)
    supplied = []
    original_verify = turn.verify_disputes

    def observed_verify(*args, **kwargs):
        supplied.append(deepcopy(kwargs["coverage_record_support"]))
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(turn, "verify_disputes", observed_verify)
    opened = open_account(client, wired, monkeypatch, model, ACCOUNT,
                          turn_id="dispute-group-original")
    assert opened["metrics"]["llm_calls"] == 8 + int(repair)
    assert opened["metrics"]["recovery"]["dispatched_calls"] == int(repair)
    assert supplied == [{}] and len(model.group_calls) == 1 + int(repair)
    first_saved = deepcopy(wired.store.load(opened["matter_id"]))
    first_execution = first_saved.brain_chat[0]["response"]["material_coverage"]["execution"]
    dispute_binding, = [row for row in first_execution["coverage_application"]["bindings"]
                        if row["stage"] == "dispute_review"]
    assert dispute_binding["review"]["verdict"] == "accept"
    original_check, = dispute_binding["review"]["account_check"]["source_checks"]
    assert original_check["source_id"] == "L1"
    assert [(span["start"], span["end"]) for span in original_check["support_spans"]] == [
        (0, len(ACCOUNT))]
    assert first_saved.brain_chat[0]["response"]["material_coverage"][
        "source_treatments"]["L1"]["quoted"] == ACCOUNT
    board = client.get(f"/api/matters/{opened['matter_id']}").json()
    before_disputes = deepcopy(board["proposed_disputes"])
    before_details = deepcopy(board["material_record"])
    assert [row["id"] for row in before_disputes["rows"]] == ["dispute-group-original:material:1"]
    assert [row["id"] for row in before_details["rows"]] == ["dispute-group-original:material:2"]

    response = send(client, REQUEST, "dispute-group-review", opened=opened)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["metrics"]["llm_calls"] == 8
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 0
    assert len(supplied) == 2 and set(supplied[1]) == {"dispute-group-original:material:1"}
    assert supplied[1]["dispute-group-original:material:1"]["review"] == dispute_binding["review"]
    assert supplied[1]["dispute-group-original:material:1"]["source_references"] == {
        "L1": {"turn_id": "dispute-group-original", "role": "advocate", "quoted": ACCOUNT}}
    assert len(model.group_calls) == 2 + int(repair)
    for call in model.group_calls:
        assert_group_offer(call)
        require_schema(call["output"], on_the_wire(call["schema"]))
    review_call = model.group_calls[-1]
    assert review_call["payload"]["candidates"] == []
    assert review_call["payload"]["coverage_representation_options"]["P1S1"] == {
        "record_ids": ["dispute-group-original:material:1"], "candidate_ids": []}
    if repair:
        assert model.group_calls[1]["payload"]["candidates"] == []
        assert [row["candidate_id"] for row in model.group_calls[1]["payload"][
            "retained_candidate_context"]] == ["C1"]
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[0] == first_saved.brain_chat[0]
    assert [row["message"] for row in saved.brain_chat] == [ACCOUNT, REQUEST]
    reopened = client.get(f"/api/matters/{saved.id}").json()
    assert reopened["proposed_disputes"] == before_disputes
    assert reopened["material_record"] == before_details
    assert saved.brain_chat[-1]["elements"] == answer["elements"]
    assert answer["continuation"]["units"][0]["record_outcome"]["status"] == "review_no_change"
    execution = answer["material_coverage"]["execution"]
    assert execution["coverage_application_contract"] == "owned_coverage_application_v2"
    assessment = execution["coverage_application"]["pre_application_assessments"]["dispute_review"]
    assert assessment["selection_contract"] == record.COVERAGE_SELECTION_CONTRACT
    assert "source_groups" not in assessment and "extent" not in repr(assessment)
    calls = len(model.seen)

    replay = send(client, REQUEST, "dispute-group-review", opened=opened)

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] and replay.json()["metrics"]["llm_calls"] == 0
    assert replay.json()["elements"] == answer["elements"]
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved

