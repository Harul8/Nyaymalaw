"""Exact premise evidence governs labels; scripted judgments are not semantic acceptance."""
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
    COMMUNICATION_PREMISE_REVIEW_SCHEMA,
    CRITERIA,
    InteractionReviewService,
    MalformedInteractionReview,
    PremiseInteractionReview,
    build_premise_prompt,
    communication_contract,
    communication_requires_work,
    communication_subject,
    interpret_premise_review,
    whole_text_unit,
)
from nm.legal_brain.loop_contracts import LoopLimits
from nm.legal_brain.preview_display import interaction_text
from nm.legal_brain.verifier import IndependentVerifier
from nm.shared.budget_contracts import Budget, Completion, Spend
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_port import ModelResult, Prompt, Tier, ToolCall, Usage, require_schema
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_communication_evidence_roles_are_owned import _v3_case
from tests.test_communication_quotes_are_words_not_selectors import _quote_case
from tests.test_communication_reviews_see_actual_work import _work_case
from tests.test_interaction_review_units_are_server_owned import _v2_case
from tests.test_interaction_words_require_an_independent_exact_review import _case
from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    path,
    request,
)
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview
from tests.test_structured_work_references_are_actual_receipts import (
    ReferenceJudge,
    _reference,
    _reference_case,
    _reference_judgment,
)
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def _premise_judgment(packet):
    raw = _reference_judgment(packet)
    raw["premise_inventory"] = {"unit_id": packet["review_units"][0]["unit_id"],
        "assessed": True, "reason": "No material premise in this controlled neutral wording.",
        "premises": []}
    return raw


def _premise(packet, *, text=None, kind="factual", form="presupposed", assessed=False,
             words=(), references=()):
    proposed = packet["subject"]["proposed_text"]
    text = proposed if text is None else text
    start = proposed.index(text)
    return {"start": start, "end": start + len(text), "text": text, "form": form,
        "kind": kind, "assessed": assessed,
        "reason": "Controlled material premise lacks a supported supplied basis.",
        "supporting_words": list(words), "work_references": list(references)}


class PremiseJudge(ReferenceJudge):
    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_PREMISE_REVIEW_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        packet = json.loads(prompt.user)
        assert packet["protocol_version"] == 7
        data = self.reference_mutation(deepcopy(_premise_judgment(packet)), packet)
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def _premise_case(tmp_path, *, mutation=lambda raw, _packet: raw, **kwargs):
    store, brain, outcome, _, old = _work_case(tmp_path, **kwargs)
    judge = PremiseJudge(mutation)
    old.reader.model = judge
    service = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=7)
    return store, brain, outcome, judge, service


def _packet(store, outcome, service):
    subject = communication_subject(service.owner, outcome, store.load("mat_loop"), 7)
    return subject, json.loads(build_premise_prompt(
        subject, service.owner.principles.load().text).user)


def _interpret(subject, raw, outcome):
    return interpret_premise_review(subject, CheckRead(raw, "Completed", Spend(), 1),
                                    outcome.budget, "controlled-premise-check")


@pytest.mark.parametrize("text", [
    "Understood.", "What happened next?", "Which records are available?",
    "क्या कोई दस्तावेज उपलब्ध है? 👩🏽‍⚖️ e\u0301", "What does the term ‘Kestrel’ mean here?",
])
def test_complete_empty_inventory_keeps_neutral_words_eligible_and_replays_saved_review(tmp_path,
                                                                                      text):
    store, _, outcome, judge, service = _premise_case(tmp_path, text=text)
    reviewed = service.review(outcome)
    assert reviewed.checked and reviewed.candidate_text == text
    assert isinstance(reviewed, PremiseInteractionReview)
    assert reviewed.premise_inventory == () and reviewed.premise_inventory_assessed is True
    assert not reviewed.client_ready and not reviewed.released
    subject, packet = _packet(store, outcome, service)
    assert packet["review_units"] == [whole_text_unit(subject)]
    assert packet["subject"]["work_receipts"]["count"] == 1
    assert service.recorded(outcome) == reviewed and service.review(outcome) == reviewed
    proof = store.load("mat_loop").loop_records[-1]
    assert interaction_text(outcome.record, proof)[0] == text
    assert len(judge.prompts) == 1
    assert not store.load("mat_loop").facts and not store.load("mat_loop").turn_receipts


@pytest.mark.parametrize("kind,text", [
    ("legal", "Which remedy under the Arbor regime will protect your title?"),
    ("applicability", "How will your admitted entitlement affect the requested recovery?"),
    ("action", "After I filed the request, which date should we use?"),
    ("permission", "Since you authorized publication, which address should receive it?"),
])
@pytest.mark.parametrize("unit_kind", ["question", "interaction", "attributed_fact"])
def test_every_material_legal_or_action_premise_overrides_six_true_harmless_unit_labels(
        tmp_path, kind, text, unit_kind):
    def mutation(raw, packet):
        raw["units"][0]["kind"] = unit_kind
        raw["premise_inventory"]["premises"] = [_premise(packet, kind=kind)]
        return raw
    store, _, outcome, _, service = _premise_case(tmp_path, text=text, mutation=mutation)
    reviewed = service.review(outcome)
    assert reviewed.clauses_complete and not reviewed.checked and not reviewed.candidate_text
    assert reviewed.judgments[0].assessed is False
    assert kind == reviewed.premise_inventory[0].kind
    saved = store.load("mat_loop").loop_records[-1].events[-1].payload["data"]
    assert all(saved[name]["assessed"] is True for name in CRITERIA)
    assert saved["units"][0]["kind"] == unit_kind  # Derived refusal does not rewrite the judge.


@pytest.mark.parametrize("form", ["stated", "presupposed"])
def test_unsupported_factual_premise_fails_faithfulness_without_forcing_merits(tmp_path, form):
    def mutation(raw, packet):
        raw["units"][0]["kind"] = "question"
        raw["premise_inventory"]["premises"] = [_premise(packet, form=form)]
        return raw
    _, _, outcome, _, service = _premise_case(tmp_path, mutation=mutation,
        text="Which record confirms the payment you made?")
    reviewed = service.review(outcome)
    assert reviewed.judgments[0].assessed is True
    assert reviewed.judgments[1].assessed is False and not reviewed.checked
    assert "Unsupported factual premises" in reviewed.judgments[1].reason


def test_supplied_attribution_can_support_a_factual_question_without_establishing_truth(tmp_path):
    instruction = "I say I paid on Tuesday; the other party denies payment."
    def mutation(raw, packet):
        raw["premise_inventory"]["premises"] = [_premise(packet,
            text="you say you paid", assessed=True, words=[{
                "source_id": "original_instruction", "quote": "I say I paid on Tuesday"}])]
        return raw
    store, _, outcome, _, service = _premise_case(tmp_path, message=instruction,
        text="Which record supports the payment you say you paid?", mutation=mutation)
    reviewed = service.review(outcome)
    assert reviewed.checked and reviewed.judgments[0].assessed is True
    assert reviewed.premise_inventory[0].supporting_words == (
        ("original_instruction", "I say I paid on Tuesday"),)
    assert not store.load("mat_loop").facts


@pytest.mark.parametrize("kind", ["legal", "applicability", "action"])
def test_supported_owned_premise_still_requires_its_separate_review(tmp_path, kind):
    def mutation(raw, packet):
        law_id = packet["premise_evidence_roles"]["legal_source_ids"][0]
        law = next(row["text"] for row in packet["subject"]["quote_sources"]
                   if row["id"] == law_id)
        words = [] if kind == "action" else [{"source_id": law_id, "quote": law}]
        if kind == "applicability":
            words.append({"source_id": "original_instruction", "quote":
                          packet["subject"]["original_instruction"]})
        references = [_reference(packet, "/attempts/0/result")] if kind == "action" else []
        raw["premise_inventory"]["premises"] = [_premise(packet, kind=kind,
            assessed=True, words=words, references=references)]
        return raw
    _, _, outcome, _, service = _premise_case(tmp_path, read_source=True, mutation=mutation)
    reviewed = service.review(outcome)
    assert reviewed.premise_inventory[0].assessed is True
    assert reviewed.judgments[0].assessed is False and not reviewed.checked


@pytest.mark.parametrize("bad", [
    "missing_inventory", "missing_completeness", "missing_premises", "wrong_unit", "blank_reason",
    "span_start", "span_end", "span_text", "blank_text", "float_offset", "missing_basis",
    "unknown_kind", "unknown_form", "duplicate_premise", "response_as_fact", "guide_as_fact",
    "work_as_fact", "instruction_as_law", "law_as_fact", "missing_positive_fact",
    "missing_positive_law", "applicability_without_law", "applicability_without_fact",
    "action_without_work", "permission_positive", "unknown_positive", "partial_work",
    "wrong_work_type", "duplicate_work_keys", "invented_source", "fabricated_quote",
])
def test_missing_malformed_or_wrong_role_premise_evidence_never_clears_wording(tmp_path, bad):
    store, _, outcome, _, service = _premise_case(tmp_path, read_source=True)
    subject, packet = _packet(store, outcome, service)
    raw = _premise_judgment(packet)
    row = _premise(packet)
    inventory = raw["premise_inventory"]
    inventory["premises"] = [row]
    law_id = packet["premise_evidence_roles"]["legal_source_ids"][0]
    if bad == "missing_inventory":
        del raw["premise_inventory"]
    elif bad in {"missing_completeness", "missing_premises"}:
        del inventory["assessed" if bad == "missing_completeness" else "premises"]
    elif bad == "wrong_unit":
        inventory["unit_id"] = "foreign"
    elif bad == "blank_reason":
        inventory["reason"] = " "
    elif bad == "span_start":
        row["start"] += 1
    elif bad == "span_end":
        row["end"] -= 1
    elif bad == "span_text":
        row["text"] = "Not the actual words"
    elif bad == "blank_text":
        row["text"] = " "
    elif bad == "float_offset":
        row["start"] = 0.0
    elif bad == "missing_basis":
        del row["assessed"]
    elif bad == "unknown_kind":
        row["kind"] = "harmless_question"
    elif bad == "unknown_form":
        row["form"] = "implied_by_question_mark"
    elif bad == "duplicate_premise":
        inventory["premises"].append(deepcopy(row))
    elif bad in {"response_as_fact", "guide_as_fact", "work_as_fact", "law_as_fact",
                 "instruction_as_law"}:
        ident = {"response_as_fact": "proposed_text", "guide_as_fact": "principles",
            "work_as_fact": "work_receipts", "law_as_fact": law_id,
            "instruction_as_law": "original_instruction"}[bad]
        row["supporting_words"] = [{"source_id": ident, "quote": subject.sources[ident]}]
        if bad == "instruction_as_law":
            row["kind"] = "legal"
    elif bad in {"missing_positive_fact", "missing_positive_law", "action_without_work",
                 "permission_positive", "unknown_positive"}:
        row["kind"] = {"missing_positive_fact": "factual", "missing_positive_law": "legal",
            "action_without_work": "action", "permission_positive": "permission",
            "unknown_positive": "unknown"}[bad]
        row["assessed"] = True
    elif bad in {"applicability_without_law", "applicability_without_fact"}:
        row.update(kind="applicability", assessed=True)
        ident = "original_instruction" if bad == "applicability_without_law" else law_id
        row["supporting_words"] = [{"source_id": ident, "quote": subject.sources[ident]}]
    elif bad in {"partial_work", "wrong_work_type", "duplicate_work_keys"}:
        row.update(kind="action", assessed=True)
        row["work_references"] = [{"pointer": "/attempts/0/result", "value_json": "{}"}]
        if bad == "wrong_work_type":
            row["work_references"] = [{"pointer": "/count", "value_json": "2.0"}]
        elif bad == "duplicate_work_keys":
            row["work_references"][0]["value_json"] = '{"state": 1, "state": 1}'
    elif bad == "invented_source":
        row["supporting_words"] = [{"source_id": "fact:invented", "quote": "Invented"}]
    elif bad == "fabricated_quote":
        row["supporting_words"] = [{"source_id": "original_instruction", "quote": "Invented"}]
    with pytest.raises(MalformedInteractionReview):
        _interpret(subject, raw, outcome)


@pytest.mark.parametrize("ambiguity", ["inventory_false", "inventory_null", "basis_null",
                                       "kind_unknown", "missing_dispatch"])
def test_incomplete_or_ambiguous_premise_assessment_is_pending_and_never_repair_permission(
        tmp_path, ambiguity):
    def mutation(raw, packet):
        if ambiguity.startswith("inventory_"):
            raw["premise_inventory"]["assessed"] = (
                False if ambiguity == "inventory_false" else None)
        else:
            raw["premise_inventory"]["premises"] = [_premise(packet,
                kind="unknown" if ambiguity == "kind_unknown" else "factual", assessed=None)]
        return raw
    _, brain, outcome, judge, service = _premise_case(tmp_path, mutation=mutation)
    if ambiguity == "missing_dispatch":
        reviewed = service.review(outcome, max_model_calls=0)
        assert reviewed.premise_inventory_assessed is None and not judge.prompts
    else:
        brain.interaction_review = service
        evaluator = EvaluationService(brain, Mock())
        result = evaluator.run(matter_id="mat_loop", turn_id=outcome.record.identity.turn_id,
            message="Thank you.", limits=LoopLimits(outcome.budget, 20, 400), max_repairs=1)
        assert result.stop == "interaction_checks_missing" and len(result.attempts) == 1
        reviewed = result.interaction_reviews[0]
        assert len(judge.prompts) == 1
    assert not reviewed.checked and not reviewed.candidate_text
    assert any(row.assessed is None for row in reviewed.judgments)


@pytest.mark.parametrize("criterion", CRITERIA)
@pytest.mark.parametrize("verdict", [False, None])
def test_complete_premise_inventory_never_upgrades_independent_negative_or_null_criteria(
        tmp_path, criterion, verdict):
    def mutation(raw, _packet):
        raw[criterion]["assessed"] = verdict
        return raw
    _, _, outcome, _, service = _premise_case(tmp_path, mutation=mutation)
    reviewed = service.review(outcome)
    assert next(row.assessed for row in reviewed.judgments if row.name == criterion) is verdict
    assert not reviewed.checked


def test_premise_negative_enters_the_existing_bounded_repair_without_rewriting_original_judge(
        tmp_path):
    first, corrected = "Which record confirms that you paid?", "Are there any payment records?"
    calls = []
    def mutation(raw, packet):
        calls.append(packet["subject_identity"])
        if len(calls) == 1:
            raw["premise_inventory"]["premises"] = [_premise(packet, text="that you paid")]
        return raw
    store, brain, outcome, judge, service = _premise_case(tmp_path, text=first,
        message="Ask for the relevant available records.", mutation=mutation)
    brain.interaction_review = service
    author_prompts = []
    def repaired(prompt, _tools, _tier, *, messages, **_kwargs):
        author_prompts.append(prompt)
        feedback = [json.loads(row.text) for row in messages
                    if "harness_check_feedback" in row.text]
        assert len(feedback) == 1
        assert feedback[0]["data"]["failures"][0][0] == "communication:faithfulness"
        assert "Unsupported factual premises" in feedback[0]["data"]["failures"][0][1]
        return _response(ToolCall("repair", "ask_advocate", {"question": corrected}))
    brain.model.tool_call.side_effect = repaired
    assessment = Mock()
    result = EvaluationService(brain, assessment).run(matter_id="mat_loop",
        turn_id=outcome.record.identity.turn_id, message="Ask for the relevant available records.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 20, 400),
        max_repairs=1)
    assert result.stop == "interaction_checks_complete_private_candidate"
    assert len(result.attempts) == 2 and len(judge.prompts) == 2 and len(author_prompts) == 1
    assert result.interaction_reviews[0].judgments[1].assessed is False
    assert result.interaction_reviews[1].checked
    original = next(row for row in store.load("mat_loop").loop_records
        if row.identity.turn_id == result.interaction_reviews[0].check_turn_id)
    assert original.events[-1].payload["data"]["faithfulness"]["assessed"] is True
    assert result.budget.spend.cost_usd == pytest.approx(0.06)
    assert not result.client_ready and not result.publications
    assert not store.load("mat_loop").facts and not store.load("mat_loop").asked
    assessment.assess.assert_not_called()


@pytest.mark.parametrize("version,fixture", [(1, _case), (2, _v2_case), (3, _v3_case),
    (4, _work_case), (5, _quote_case), (6, _reference_case)])
def test_protocol_seven_reads_old_proofs_with_original_prompt_schema_and_result_shape(
        tmp_path, version, fixture):
    store, _, outcome, judge, old = fixture(tmp_path)
    reviewed = old.review(outcome)
    prior = deepcopy(asdict(store.load("mat_loop").loop_records[-1]))
    new = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=7)
    assert new.recorded(outcome) == reviewed
    assert "premise_inventory" not in asdict(reviewed)
    assert "premise_inventory" not in communication_contract(version)[1]["properties"]
    assert "premise_evidence_roles" not in json.loads(judge.prompts[0].user)
    with pytest.raises(ReviewRefused, match="upgraded"):
        new.review(outcome)
    assert len(judge.prompts) == 1 and asdict(store.load("mat_loop").loop_records[-1]) == prior


def test_new_prompt_and_schema_keep_one_registry_and_bounded_verifier_permissions(tmp_path):
    store, _, outcome, _, service = _premise_case(tmp_path)
    subject, packet = _packet(store, outcome, service)
    previous = communication_contract(6)[2](subject, service.owner.principles.load().text)
    prompt = build_premise_prompt(subject, service.owner.principles.load().text)
    assert prompt.system.startswith(previous.system)
    assert packet["subject"] == json.loads(previous.user)["subject"]
    assert packet["premise_evidence_roles"]["factual_source_ids"] == ["original_instruction"]
    assert packet["premise_evidence_roles"]["legal_source_ids"] == []
    assert packet["premise_evidence_roles"]["permission_source_ids"] == []
    assert "Do not route all questions to legal review" in prompt.system
    assert communication_contract(7) == (
        "communication_premises", COMMUNICATION_PREMISE_REVIEW_SCHEMA,
        build_premise_prompt, interpret_premise_review)
    assert communication_requires_work(7) is True
    raw = _premise_judgment(packet)
    require_schema(raw, COMMUNICATION_PREMISE_REVIEW_SCHEMA)
    inner = Mock()
    verifier = VerifierOnly(inner)
    verifier.structured(Prompt("Exact premise review"), COMMUNICATION_PREMISE_REVIEW_SCHEMA,
                        Tier.JUDGE)
    assert inner.structured.call_args.kwargs == {"max_tokens": 2048}
    inner.reset_mock()
    relaxed = deepcopy(COMMUNICATION_PREMISE_REVIEW_SCHEMA)
    relaxed["required"].remove("premise_inventory")
    with pytest.raises(ModelPermissionRefused):
        verifier.structured(Prompt("Missing population"), relaxed, Tier.JUDGE)
    assert not inner.mock_calls


@pytest.mark.parametrize("verdict", ["neutral", "factual", "legal", "unassessed"])
def test_actual_private_wire_shows_only_complete_nonmerits_premise_reviews(client, verdict):
    app, matter, author, _ = approved(client)
    judges = []
    def mutation(raw, packet):
        if verdict == "unassessed":
            raw["premise_inventory"]["assessed"] = None
        elif verdict != "neutral":
            raw["premise_inventory"]["premises"] = [_premise(packet, kind=verdict)]
        return raw
    def reviewer(application, scope, current):
        judge = PremiseJudge(mutation)
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling)
    grant = app.controlled_evaluations[0]
    app.controlled_evaluations = (replace(grant, reviewer_factory=reviewer,
        interaction_protocol_version=7, limits=replace(grant.limits,
            budget=replace(grant.limits.budget, max_tokens=100000))),)
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200 and PRIVATE not in posted.text
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    if verdict == "neutral":
        assert shown.json()["paragraphs"] == [{"text": PRIVATE, "references": []}]
        assert client.post(f"{preview(matter)}/seen", json={}).status_code == 200
    else:
        assert shown.json()["paragraphs"] == [] and PRIVATE not in shown.text
        expected = "wording_review_pending" if verdict == "unassessed" else "wording_review_failed"
        assert shown.json()["result_state"] == expected
        assert client.post(f"{preview(matter)}/seen", json={}).status_code == 409
    assert shown.json()["released"] is shown.json()["client_ready"] is False
    assert author.tool_call.call_count == 1 and sum(len(judge.prompts) for judge in judges) == 1
    assert not app.store.load(matter.id).facts and not app.store.load(matter.id).turn_receipts
