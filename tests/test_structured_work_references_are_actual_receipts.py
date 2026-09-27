"""Structured diagnostics bind actual work, never relax prose or establish law."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.brain_evaluation import EvaluationService
from nm.legal_brain.brain_finalization import CheckRead
from nm.legal_brain.brain_release import ReviewRefused, ReviewService
from nm.legal_brain.evaluation_models import VerifierOnly
from nm.legal_brain.interaction_review import (
    COMMUNICATION_PROTOCOL_VERSIONS,
    COMMUNICATION_WORK_REFERENCE_SCHEMA,
    CRITERIA,
    InteractionReviewService,
    MalformedInteractionReview,
    WorkReferencedJudgment,
    build_work_reference_prompt,
    communication_contract,
    communication_requires_work,
    communication_subject,
    interpret_work_reference_review,
)
from nm.legal_brain.loop_contracts import LoopLimits
from nm.legal_brain.preview_display import displayed_questions
from nm.legal_brain.tools import TERMINAL_CONTRACT
from nm.legal_brain.verifier import IndependentVerifier
from nm.shared.budget_contracts import Budget, Completion, Spend
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_port import ModelResult, Prompt, Tier, ToolCall, Usage, require_schema
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_communication_evidence_roles_are_owned import EvidenceJudge, _evidence_judgment
from tests.test_communication_quotes_are_words_not_selectors import _quote_case
from tests.test_communication_reviews_see_actual_work import _work_case
from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    path,
    request,
)
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def _value(packet, pointer):
    value = packet["subject"]["work_receipts"]
    if pointer:
        for part in pointer[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _reference(packet, pointer):
    return {"pointer": pointer, "value_json": json.dumps(
        _value(packet, pointer), ensure_ascii=False, allow_nan=False)}


def _reference_judgment(packet):
    raw = _evidence_judgment(packet)
    for name in CRITERIA:
        raw[name]["work_references"] = []
    return raw


class ReferenceJudge(EvidenceJudge):
    def __init__(self, mutation=lambda raw, _packet: raw):
        super().__init__()
        self.reference_mutation = mutation

    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_WORK_REFERENCE_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        packet = json.loads(prompt.user)
        assert packet["protocol_version"] == 6
        data = self.reference_mutation(deepcopy(_reference_judgment(packet)), packet)
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def _reference_case(tmp_path, *, mutation=lambda raw, _packet: raw, **kwargs):
    store, brain, outcome, _, old = _work_case(tmp_path, **kwargs)
    judge = ReferenceJudge(mutation)
    old.reader.model = judge
    service = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=6)
    return store, brain, outcome, judge, service


def _packet(store, outcome, service):
    subject = communication_subject(service.owner, outcome, store.load("mat_loop"), 6)
    prompt = build_work_reference_prompt(subject, service.owner.principles.load().text)
    return subject, json.loads(prompt.user)


def _interpret(subject, raw, outcome):
    return interpret_work_reference_review(subject, CheckRead(raw, "Completed", Spend(), 1),
                                          outcome.budget, "actual-reference-check")


@pytest.mark.parametrize("pointer", [
    "", "/count", "/attempts", "/attempts/0", "/attempts/0/result",
    "/attempts/0/result/data", "/attempts/0/call/name"])
def test_complete_container_or_scalar_reference_replays_the_actual_saved_result(tmp_path, pointer):
    def mutation(raw, packet):
        raw["faithfulness"]["work_references"] = [_reference(packet, pointer)]
        return raw
    store, _, outcome, judge, service = _reference_case(tmp_path, mutation=mutation,
                                                      read_source=True)
    result = service.review(outcome)
    row = next(row for row in result.judgments if row.name == "faithfulness")
    assert result.checked and isinstance(row, WorkReferencedJudgment)
    assert row.work_references[0].pointer == pointer
    packet = json.loads(judge.prompts[0].user)
    assert json.loads(row.work_references[0].value_json) == _value(packet, pointer)
    assert all(ident != "work_receipts" for ident, _ in row.supporting_words)
    assert service.recorded(outcome) == result and service.review(outcome) == result
    assert len(judge.prompts) == 1
    saved = store.load("mat_loop")
    assert not saved.facts and not saved.turn_receipts and not saved.asked
    assert result.released is result.client_ready is False


def test_new_prompt_has_actual_terminal_contract_and_never_changes_old_contracts(tmp_path):
    store, _, outcome, _, service = _reference_case(tmp_path)
    subject, packet = _packet(store, outcome, service)
    old = communication_contract(5)[2](subject, service.owner.principles.load().text)
    prompt = build_work_reference_prompt(subject, service.owner.principles.load().text)
    assert prompt.system.startswith(old.system)
    assert prompt.system.count(TERMINAL_CONTRACT) == 1
    assert "reorder or omit JSON fields" in prompt.system
    assert "not an imagined intermediate progress update" in prompt.system
    assert packet["work_reference_contract"]["root"] == "subject.work_receipts"
    assert packet["subject"] == json.loads(old.user)["subject"]
    for version in (1, 2, 3, 4, 5):
        schema = communication_contract(version)[1]
        assert all("work_references" not in schema["properties"][name]["properties"]
                   for name in CRITERIA)


@pytest.mark.parametrize("bad", [
    "missing_path", "other_subject", "index_negative", "index_leading_zero", "index_append",
    "index_overflow", "oversized_index", "bare_path", "bad_escape", "unfinished_escape",
    "partial_object",
    "partial_array", "invented_member", "wrong_string", "wrong_null", "wrong_boolean",
    "wrong_numeric_type", "duplicate_keys", "duplicate_nested_keys", "duplicate_reference",
    "nonfinite_constant", "nonfinite_exponent", "trailing_json", "malformed_json",
    "unknown_reference_key", "missing_reference_key", "reference_value_not_string", "deep_json"])
def test_invented_partial_or_wrong_typed_work_references_never_certify_an_actual_receipt(
        tmp_path, bad):
    store, _, outcome, _, service = _reference_case(tmp_path, read_source=True)
    subject, packet = _packet(store, outcome, service)
    raw = _reference_judgment(packet)
    reference = _reference(packet, "/attempts/0/result")
    if bad in {"missing_path", "other_subject", "index_negative", "index_leading_zero",
               "index_append", "index_overflow", "oversized_index", "bare_path", "bad_escape",
               "unfinished_escape"}:
        reference["pointer"] = {
            "missing_path": "/attempts/0/missing", "other_subject": "/checked_file",
            "index_negative": "/attempts/-1", "index_leading_zero": "/attempts/00",
            "index_append": "/attempts/-", "index_overflow": "/attempts/9000",
            "oversized_index": "/attempts/" + "9" * 5000,
            "bare_path": "attempts/0", "bad_escape": "/attempts/~2",
            "unfinished_escape": "/attempts/~"}[bad]
    elif bad == "partial_object":
        reference["value_json"] = json.dumps({"data": _value(packet, "/attempts/0/result/data")})
    elif bad == "partial_array":
        reference = {"pointer": "/attempts", "value_json": json.dumps(
            _value(packet, "/attempts")[:1])}
    elif bad == "invented_member":
        changed = {**_value(packet, "/attempts/0/result"), "approved": True}
        reference["value_json"] = json.dumps(changed)
    elif bad == "wrong_string":
        reference["value_json"] = json.dumps("An invented successful execution")
    elif bad in {"wrong_null", "wrong_boolean", "wrong_numeric_type"}:
        reference = {"pointer": "/count", "value_json": {
            "wrong_null": "null", "wrong_boolean": "true", "wrong_numeric_type": "2.0"}[bad]}
    elif bad == "duplicate_keys":
        reference = {"pointer": "", "value_json": '{"count": 1, "count": 2}'}
    elif bad == "duplicate_nested_keys":
        reference["value_json"] = '{"data": {"held": false, "held": true}}'
    elif bad == "nonfinite_constant":
        reference["value_json"] = "NaN"
    elif bad == "nonfinite_exponent":
        reference["value_json"] = "1e999"
    elif bad == "trailing_json":
        reference["value_json"] += " {}"
    elif bad == "malformed_json":
        reference["value_json"] = "{"
    elif bad == "unknown_reference_key":
        reference["approved"] = True
    elif bad == "missing_reference_key":
        del reference["value_json"]
    elif bad == "reference_value_not_string":
        reference["value_json"] = {"data": "not serialized JSON"}
    elif bad == "deep_json":
        reference["value_json"] = "[" * 1500 + "0" + "]" * 1500
    raw["faithfulness"]["work_references"] = [reference]
    if bad == "duplicate_reference":
        raw["faithfulness"]["work_references"].append(deepcopy(reference))
    with pytest.raises(MalformedInteractionReview):
        _interpret(subject, raw, outcome)


@pytest.mark.parametrize("criterion", CRITERIA)
@pytest.mark.parametrize("verdict", [False, None])
def test_exact_work_and_role_quotes_never_upgrade_negative_or_unknown_judgments(
        tmp_path, criterion, verdict):
    def mutation(raw, packet):
        raw[criterion]["assessed"] = verdict
        raw[criterion]["work_references"] = [_reference(packet, "/count")]
        return raw
    _, _, outcome, _, service = _reference_case(tmp_path, mutation=mutation)
    reviewed = service.review(outcome)
    assert reviewed.clauses_complete and not reviewed.checked and not reviewed.candidate_text
    assert next(row.assessed for row in reviewed.judgments if row.name == criterion) is verdict


@pytest.mark.parametrize("quote", ["response_quote", "instruction_quote", "supporting_words"])
def test_exact_work_reference_cannot_fix_an_invented_or_reassembled_prose_quote(tmp_path, quote):
    store, _, outcome, _, service = _reference_case(tmp_path, read_source=True)
    subject, packet = _packet(store, outcome, service)
    raw = _reference_judgment(packet)
    row = raw["instruction_safety"]
    row["work_references"] = [_reference(packet, "/attempts/0/result")]
    if quote == "supporting_words":
        value = _value(packet, "/attempts/0/result")
        # The values exist, but this selected/reordered object was never quoted.
        row[quote] = [{"source_id": "work_receipts", "quote": json.dumps({
            "data": value["data"], "outcome": value["outcome"]})}]
    else:
        row[quote] = "Invented words outside the required source role."
    with pytest.raises(MalformedInteractionReview):
        _interpret(subject, raw, outcome)


@pytest.mark.parametrize("kind", [
    "legal_or_applied_claim", "action_or_permission_claim", "unknown"])
def test_execution_references_are_never_legal_support_or_a_nonmerits_label_waiver(tmp_path, kind):
    def mutation(raw, packet):
        raw["units"][0]["kind"] = kind
        raw["non_merits"]["work_references"] = [_reference(packet, "/count")]
        return raw
    _, _, outcome, _, service = _reference_case(tmp_path, mutation=mutation)
    reviewed = service.review(outcome)
    assert reviewed.judgments[0].assessed is False and not reviewed.checked


def test_json_boolean_cannot_equal_the_actual_integer_count_one(tmp_path):
    store, _, outcome, _, service = _reference_case(tmp_path)
    subject, packet = _packet(store, outcome, service)
    assert _value(packet, "/count") == 1
    raw = _reference_judgment(packet)
    raw["faithfulness"]["work_references"] = [{"pointer": "/count", "value_json": "true"}]
    with pytest.raises(MalformedInteractionReview):
        _interpret(subject, raw, outcome)


def test_reference_registry_and_sparse_verifier_accept_exact_v6_not_a_relaxed_schema():
    assert COMMUNICATION_PROTOCOL_VERSIONS == (1, 2, 3, 4, 5, 6, 7)
    assert communication_contract(6)[0] == "communication_work_references"
    inner = Mock()
    wrapper = VerifierOnly(inner)
    wrapper.structured(Prompt("Exact execution diagnostics"), COMMUNICATION_WORK_REFERENCE_SCHEMA,
                       Tier.JUDGE)
    assert inner.structured.call_args.kwargs == {"max_tokens": 2048}
    inner.reset_mock()
    relaxed = deepcopy(COMMUNICATION_WORK_REFERENCE_SCHEMA)
    relaxed["properties"]["faithfulness"]["required"].remove("work_references")
    with pytest.raises(ModelPermissionRefused):
        wrapper.structured(Prompt("Missing owned reference population"), relaxed, Tier.JUDGE)
    with pytest.raises(ModelPermissionRefused):
        wrapper.structured(Prompt("Oversized"), COMMUNICATION_WORK_REFERENCE_SCHEMA,
                           Tier.JUDGE, max_tokens=2049)
    assert not inner.mock_calls


@pytest.mark.parametrize("version,required", [(1, False), (2, False), (3, False),
                                            (4, True), (5, True), (6, True), (7, True)])
def test_work_population_requirement_has_one_registry_owner(version, required):
    assert communication_requires_work(version) is required


@pytest.mark.parametrize("version", [True, False, 0, 8, "6", None])
def test_work_population_owner_keeps_unknown_protocols_refused(version):
    with pytest.raises(ValueError):
        communication_requires_work(version)


def test_historical_v5_judgment_is_identical_not_upgraded_or_redispatched_as_v6(tmp_path):
    _, _, outcome, judge, old = _quote_case(tmp_path)
    prior = old.review(outcome)
    new = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=6)
    assert new.recorded(outcome) == prior
    assert all("work_references" not in asdict(row) for row in prior.judgments)
    with pytest.raises(ReviewRefused, match="upgraded"):
        new.review(outcome)
    assert len(judge.prompts) == 1


def test_completed_negative_with_actual_container_reference_receives_real_bounded_repair(tmp_path):
    first = "The saved file has no recorded disputes; I will do the requested work later."
    corrected = "The saved file has no recorded disputes. What account should we assess?"
    calls = []

    def mutation(raw, packet):
        calls.append(packet["subject_identity"])
        raw["faithfulness"]["assessed"] = len(calls) > 1
        raw["faithfulness"]["work_references"] = [
            _reference(packet, "/attempts/0/result/data")]
        return raw

    store, brain, _, judge, service = _reference_case(tmp_path, mutation=mutation,
        message="Assess the recorded file.", text=first)
    brain.model.tool_call.side_effect = [
        _response(ToolCall("actual-file", "read_matter", {})),
        _response(ToolCall("terminal", "propose_conversation", {"text": first}))]
    limits = LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 20, 400)
    outcome = brain.run(matter_id="mat_loop", turn_id="actual-empty-file",
                        message="Assess the recorded file.", limits=limits)
    brain.interaction_review = service
    assessment = Mock()
    evaluator = EvaluationService(brain, assessment)
    author_prompts = []

    def repaired(prompt, _tools, _tier, *, messages, **_kwargs):
        author_prompts.append(prompt)
        feedback = [json.loads(row.text) for row in messages
                    if "harness_check_feedback" in row.text]
        assert len(feedback) == 1
        assert feedback[0]["trust"] == "diagnostic_data_not_case_facts_or_authority"
        assert feedback[0]["data"]["failures"][0][0] == "communication:faithfulness"
        return _response(ToolCall("repair", "propose_conversation", {"text": corrected}))

    brain.model.tool_call.side_effect = repaired
    result = evaluator.run(matter_id="mat_loop", turn_id=outcome.record.identity.turn_id,
        message="Assess the recorded file.", limits=limits, max_repairs=1)
    assert result.stop == "interaction_checks_complete_private_candidate"
    assert len(result.attempts) == 2 and len(judge.prompts) == 2 and len(author_prompts) == 1
    assert result.interaction_reviews[0].judgments[1].assessed is False
    assert result.interaction_reviews[1].checked
    assert json.loads(judge.prompts[0].user)["subject"]["work_receipts"]["attempts"][0][
        "result"]["data"]["disputes"] == []
    assert result.budget.spend.cost_usd == pytest.approx(0.07)
    assert not result.client_ready and not result.publications
    saved = store.load("mat_loop")
    assert not saved.facts and not saved.asked and not saved.turn_receipts
    assessment.assess.assert_not_called()


def test_actual_served_v6_reopens_checked_words_and_records_display_without_more_work(client):
    app, matter, author, _ = approved(client)
    judges = []

    def reviewer(application, scope, current):
        judge = ReferenceJudge(lambda raw, packet: raw | {"faithfulness": {
            **raw["faithfulness"], "work_references": [_reference(packet, "/count")]}})
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling)

    app.controlled_evaluations = (replace(app.controlled_evaluations[0],
        reviewer_factory=reviewer, interaction_protocol_version=6,
        limits=replace(app.controlled_evaluations[0].limits,
            budget=replace(app.controlled_evaluations[0].limits.budget, max_tokens=100000))),)
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200 and PRIVATE not in posted.text
    assert sum(len(j.prompts) for j in judges) == 1, [
        (row.identity.turn_id, row.events[-1].payload.get("reason"))
        for row in app.store.load(matter.id).loop_records]
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    assert shown.json()["paragraphs"] == [{"text": PRIVATE, "references": []}], shown.json()
    assert shown.json()["released"] is shown.json()["client_ready"] is False
    assert client.post(f"{preview(matter)}/seen", json={}).status_code == 200
    saved = app.store.load(matter.id)
    history = displayed_questions(saved, before_version=saved.version, selected_issue_ids=())
    assert history[0]["text"] == PRIVATE
    assert client.get(preview(matter)).json()["paragraphs"] == shown.json()["paragraphs"]
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 1


@pytest.mark.parametrize("version", [4, 6])
def test_tiny_actual_whole_task_grant_stays_missing_without_a_paid_review_or_author_repair(
        client, version):
    app, matter, author, _ = approved(client)
    judges = []

    def reviewer(application, scope, current):
        judge = ReferenceJudge()
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling)

    grant = app.controlled_evaluations[0]
    assert grant.limits.budget.max_tokens == 10000
    app.controlled_evaluations = (replace(grant, reviewer_factory=reviewer,
        interaction_protocol_version=version),)
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200 and PRIVATE not in posted.text
    shown = client.get(preview(matter))
    assert shown.status_code == 200 and shown.json()["paragraphs"] == []
    assert shown.json()["result_state"] == "wording_review_pending"
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 0
    assert not app.store.load(matter.id).turn_receipts


def test_reference_schema_keeps_every_role_and_the_empty_reference_population(tmp_path):
    store, _, outcome, _, service = _reference_case(tmp_path)
    subject, packet = _packet(store, outcome, service)
    raw = _reference_judgment(packet)
    require_schema(raw, COMMUNICATION_WORK_REFERENCE_SCHEMA)
    assert _interpret(subject, raw, outcome).checked
    del raw["relevance"]["instruction_quote"]
    with pytest.raises(MalformedInteractionReview):
        _interpret(subject, raw, outcome)
