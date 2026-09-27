"""Scripted actual loops/check transports, not proof of live wording quality."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.verify.brain_finalization import SavedCheckReader
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, SourceDocument, SourceKind
from nm.legal_brain.verify.interaction_review import (
    COMMUNICATION_REVIEW_SCHEMA,
    CRITERIA,
    InteractionReviewService,
)
from nm.legal_brain.verify.interaction_subject import InteractionSubjectOwner
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, LoopMode, StepKind
from nm.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.legal_brain.retrieve.tool_sources import capture_document, source_envelope
from nm.legal_brain.orchestrate.tools import (
    Boundary,
    OfferRole,
    RegisteredTool,
    ToolKind,
    foundation_tools,
    object_schema,
)
from nm.shared.budget_contracts import Budget, Completion
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import (
    ModelResult,
    ProviderUnavailable,
    Tier,
    ToolCall,
    ToolDefinition,
    Usage,
)
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import AskedQuestion, Thread
from tests.test_independent_claim_verifier import finding, premise
from tests.test_the_loop_records_work_before_using_it import _response, _setup

pytestmark = pytest.mark.class_a


def _judgment(subject):
    text = subject["subject"]["proposed_text"]
    original = subject["subject"]["original_instruction"]
    words = [{"source_id": "proposed_text", "quote": text},
             {"source_id": "original_instruction", "quote": original}]
    return {"subject_identity": subject["subject_identity"],
        "clauses": [{"start": 0, "end": len(text), "kind": "interaction",
                     "reason": "Only interaction wording in this controlled response",
                     "supporting_words": [words[0]]}],
        **{name: {"assessed": True, "reason": "Controlled independent criterion assessment",
                  "supporting_words": words} for name in CRITERIA}}


class InteractionJudge(ScriptedModelAdapter):
    def __init__(self, mutation=lambda raw: raw):
        super().__init__(ModelConfig({Tier.JUDGE: TierConfig(
            Tier.JUDGE, "scripted", "interaction-judge", None, None)}))
        self.prompts, self.mutation = [], mutation

    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_REVIEW_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        data = self.mutation(deepcopy(_judgment(json.loads(prompt.user))))
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def _case(tmp_path, *, text="Understood; we can pause here.", message="Thank you.",
          kind="propose_conversation", mutation=lambda raw: raw, read_source=False,
          source_current=lambda *_: True, facts=(), threads=(), asked=(), read_raw=False,
          window_current=None):
    store, identity, log, author, _ = _setup(tmp_path)
    matter = store.load(identity.matter_id)
    store.commit(replace(matter, facts=facts, threads=threads, asked=asked,
                         version=matter.version + 1), expected_version=matter.version)
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED, (finding(),), searched_stores=("held",))
    registry = foundation_tools(store, evidence, manifest=Mock(), source_version="actual-test-gen",
        before=lambda *_: Boundary(True, "Controlled admission"),
        after=lambda *_: Boundary(True, "Controlled result boundary"))
    if read_raw:
        raw = SourceDocument("read", snapshot_id="exact-raw-snapshot",
            segments=(("held:raw:1", "Exact raw court words without assessed treatment."),),
            locator="held:raw:1", kind="authority", target=0)
        registry = registry.extend((RegisteredTool(
            ToolDefinition("read_raw", "Controlled raw reader", object_schema({})),
            ToolKind.SOURCE, "v1", False, ("raw_window_control",),
            lambda *_: source_envelope("read_raw", "v1", "held", "actual-test-gen", (), {},
                capture=capture_document(raw, kind=SourceKind.AUTHORITY),
                reason="The raw source reader has not assessed legal metadata"),
            offer_role=OfferRole.INITIAL),))
    author.context_budget.return_value = 100000
    calls = []
    if read_source:
        calls.append(_response(ToolCall("law", "read_provision", {
            "act": "Recorded rule", "section": "1", "as_of": "2026-01-01"})))
    if read_raw:
        calls.append(_response(ToolCall("raw", "read_raw", {})))
    calls.append(_response(ToolCall("interaction", kind,
                                  {"question" if kind == "ask_advocate" else "text": text})))
    author.tool_call.side_effect = calls
    principles = FilePrinciples()
    brain = ControlledBrain(store=store, model=author, principles=principles, log=log,
        registry=registry, scope=EvaluationScope("OWNER-CONTROLLED", identity.advocate_id,
            frozenset({identity.matter_id}), LoopMode.SYNTHETIC),
        cost_ceiling=lambda *_: 0.03, session_current=lambda: True)
    outcome = brain.run(matter_id=identity.matter_id, turn_id="interaction-parent",
        message=message, limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000,
                                                max_cost_usd=1), 20, 400))
    judge = InteractionJudge(mutation)
    owner = InteractionSubjectOwner(principles=principles, source_current=source_current,
                                    window_current=window_current)
    reader = SavedCheckReader(store=store, log=log, model=judge, session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03, current_tools_version=lambda: registry.version,
        current_principles_version=lambda: principles.load().version,
        subject_packages=owner.packages, max_tokens=2048)
    return store, brain, outcome, judge, InteractionReviewService(reader=reader, owner=owner)


@pytest.mark.parametrize("kind", ["propose_conversation", "ask_advocate"])
def test_actual_saved_interactions_reach_a_distinct_judge_without_fake_legal_sources(
        tmp_path, kind):
    text = "Which document records that date?" if kind == "ask_advocate" else "Understood."
    store, _, outcome, judge, service = _case(tmp_path, kind=kind, text=text)
    reviewed = service.review(outcome)
    assert reviewed.checked and reviewed.candidate_text == text
    assert not reviewed.client_ready and not reviewed.released
    assert reviewed.model_steps == 1 and len(judge.prompts) == 1
    assert reviewed.budget.spend.cost_usd == pytest.approx(outcome.budget.spend.cost_usd + 0.02)
    assert reviewed.budget.spend.children == outcome.budget.spend.children + 1
    assert not store.load("mat_loop").turn_receipts
    assert not store.transcripts_for("mat_loop")
    saved = store.load("mat_loop").loop_records[-1]
    assert saved.terminal and saved.events[-1].payload["released"] is False
    assert saved.events[0].payload["schema"] == COMMUNICATION_REVIEW_SCHEMA
    packet = json.loads(judge.prompts[0].user)["subject"]
    assert packet["law_windows"] == packet["documents"] == []
    assert packet["original_instruction"] == "Thank you."
    assert packet["proposed_text"] == text
    assert "kind" not in packet  # Author-selected label is not a judge classification hint.
    assert all(row["assessed"] is True for row in saved.events[-1].payload["data"].values()
               if isinstance(row, dict))


@pytest.mark.parametrize("criterion", CRITERIA)
@pytest.mark.parametrize("value", [False, None])
def test_each_independent_communication_dimension_must_be_positively_assessed(
        tmp_path, criterion, value):
    def mutate(raw):
        raw[criterion]["assessed"] = value
        return raw
    _, _, outcome, _, service = _case(tmp_path, mutation=mutate)
    reviewed = service.review(outcome)
    assert not reviewed.checked and not reviewed.candidate_text
    assert next(row.assessed for row in reviewed.judgments if row.name == criterion) is value


@pytest.mark.parametrize("clause_kind", ["legal_or_applied_claim", "action_or_permission_claim",
                                       "unknown"])
def test_a_nonmerits_true_label_cannot_override_the_actual_classified_words(tmp_path, clause_kind):
    def mutate(raw):
        raw["clauses"][0]["kind"] = clause_kind
        return raw
    store, _, outcome, _, service = _case(tmp_path,
        text="Your opponent admitted liability; file tomorrow.", mutation=mutate)
    result = service.review(outcome)
    assert not result.checked and not result.candidate_text
    assert result.judgments[0].assessed is False
    assert not store.load("mat_loop").turn_receipts


@pytest.mark.parametrize("what", ["empty_clauses", "missing_end", "false_identity", "fake_words",
                                 "empty_positive", "no_instruction", "wrong_clause_words"])
def test_empty_incomplete_or_unattributable_reviews_cannot_certify_a_private_preview(
        tmp_path, what):
    def mutate(raw):
        if what == "empty_clauses":
            raw["clauses"] = []
        elif what == "missing_end":
            raw["clauses"][0]["end"] -= 1
        elif what == "false_identity":
            raw["subject_identity"] = "other subject"
        elif what == "fake_words":
            raw["faithfulness"]["supporting_words"] = [{
                "source_id": "fact:invented", "quote": "new"}]
        elif what == "empty_positive":
            raw["faithfulness"]["supporting_words"] = []
        elif what == "no_instruction":
            raw["relevance"]["supporting_words"] = raw["relevance"]["supporting_words"][:1]
        else:
            raw["clauses"][0]["supporting_words"] = [{
                "source_id": "original_instruction", "quote": "Thank you."}]
        return raw
    store, _, outcome, _, service = _case(tmp_path, mutation=mutate)
    with pytest.raises(ReviewRefused) as caught:
        service.review(outcome)
    # The rejected completed read still has its actual saved usage; it is not refunded.
    saved = store.load("mat_loop").loop_records[-1]
    assert saved.terminal and saved.events[-1].payload["spend"]["cost_usd"] == 0.02
    assert saved.events[-1].payload["released"] is False
    assert caught.value.budget.spend.cost_usd == pytest.approx(
        outcome.budget.spend.cost_usd + 0.02)


def test_an_exact_review_retry_has_no_new_dispatch_words_or_spend(tmp_path):
    _, _, outcome, judge, service = _case(tmp_path)
    first = service.review(outcome)
    judge.structured = lambda *_args, **_kwargs: pytest.fail("Retry must not spend again")
    assert service.review(outcome) == first
    assert service.recorded(outcome) == first


@pytest.mark.parametrize("what", ["session", "source_generation", "principles", "file", "proposal",
                                 "budget"])
def test_currentness_and_exact_parent_checks_survive_recorded_review_reuse(tmp_path, what):
    store, _, outcome, judge, service = _case(tmp_path)
    service.review(outcome)
    if what == "session":
        service.reader.session_current = lambda: False
    elif what == "source_generation":
        service.reader.current_tools_version = lambda: "changed"
    elif what == "principles":
        service.reader.current_principles_version = lambda: "changed"
    elif what == "file":
        current = store.load("mat_loop")
        store.commit(replace(current, facts=(premise(),), version=current.version + 1),
                     expected_version=current.version)
    elif what == "proposal":
        outcome = replace(outcome, proposal={**outcome.proposal, "text": "Replacement words"})
    else:
        outcome = replace(outcome, budget=replace(outcome.budget, max_cost_usd=100))
    with pytest.raises((ReviewRefused, ValueError)):
        service.recorded(outcome)
    assert len(judge.prompts) == 1


def test_late_logout_keeps_the_provider_receipt_but_cannot_finish_a_checked_interaction(tmp_path):
    store, _, outcome, judge, service = _case(tmp_path)
    live = [True]
    service.reader.session_current = lambda: live[0]
    original = judge.structured

    def logout(*args, **kwargs):
        result = original(*args, **kwargs)
        live[0] = False
        return result
    judge.structured = logout
    with pytest.raises(ReviewRefused) as caught:
        service.review(outcome)
    saved = store.load("mat_loop").loop_records[-1]
    assert not saved.terminal
    assert saved.events[-1].kind is StepKind.MODEL_RETURNED
    assert saved.events[-1].payload["result"]["usage"]["cost_usd"] == 0.02
    assert caught.value.budget.spend.cost_usd == pytest.approx(
        outcome.budget.spend.cost_usd + 0.02)
    live[0] = True
    with pytest.raises(ReviewRefused, match="unknown outcome"):
        service.review(outcome)
    assert len(judge.prompts) == 1


def test_failed_unknown_provider_call_retains_the_reservation_and_unassessed_dimensions(tmp_path):
    _, _, outcome, judge, service = _case(tmp_path)
    judge.structured = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        ProviderUnavailable("No usage receipt"))
    result = service.review(outcome)
    assert not result.checked and all(row.assessed is None for row in result.judgments)
    assert result.budget.spend.cost_usd == pytest.approx(outcome.budget.spend.cost_usd + 0.03)
    judge.structured = lambda *_args, **_kwargs: pytest.fail("Unknown failed outcome retried")
    assert service.review(outcome) == result


def test_no_dispatch_allowance_does_not_self_certify_or_spend(tmp_path):
    _, _, outcome, judge, service = _case(tmp_path)
    result = service.review(outcome, max_model_calls=0)
    assert not result.checked and result.model_steps == 0 and result.budget == outcome.budget
    assert not judge.prompts


@pytest.mark.parametrize("mutate", [lambda budget: replace(budget, max_cost_usd=100),
                                  lambda budget: replace(budget, spend=budget.spend.__class__())])
def test_an_authored_budget_cannot_buy_a_communication_review(tmp_path, mutate):
    _, _, outcome, judge, service = _case(tmp_path)
    with pytest.raises(ReviewRefused, match="budget"):
        service.review(outcome, budget=mutate(outcome.budget))
    assert not judge.prompts


def test_the_author_cannot_supply_its_own_independent_wording_verdict(tmp_path):
    _, _, outcome, judge, service = _case(tmp_path)
    judge.resolved_model = lambda _tier: "recorded-v1"
    with pytest.raises(ReviewRefused, match="model that wrote"):
        service.review(outcome)
    assert not judge.prompts


def test_actual_scoped_facts_prior_delivered_questions_and_law_windows_reach_the_judge(tmp_path):
    thread = replace(Thread.create("Dispute"), chronology=("fact_1",))
    asked = AskedQuestion("facts", "Which date was the notice sent?", "2026-09-26", thread.id)
    store, _, outcome, judge, service = _case(tmp_path, kind="ask_advocate",
        text="Which date was the notice sent?", message="The same question was already answered.",
        facts=(premise(),), threads=(thread,), asked=(asked,), read_source=True)
    reviewed = service.review(outcome)
    packet = json.loads(judge.prompts[0].user)["subject"]
    assert packet["selected_issue_ids"] == [thread.id]
    assert packet["delivered_questions"][0]["text"] == asked.text
    assert packet["law_windows"][0]["finding"]["span"] == finding().span
    fact = packet["checked_file"]["facts"][0]
    assert fact["statement"] == premise().statement and fact["certainty"] == "asserted"
    assert {row["dimension"] for row in packet["checked_file"]["independent_uncertainties"]}
    assert reviewed.checked  # Scripted positive proof of dispatch, not semantic certification.
    assert not store.load("mat_loop").turn_receipts


def test_captured_law_without_current_owned_source_read_cannot_reach_the_wording_judge(tmp_path):
    _, _, outcome, judge, service = _case(tmp_path, read_source=True)
    service.owner.source_current = lambda *_: False
    with pytest.raises(ReviewRefused, match="currently readable"):
        service.review(outcome)
    assert not judge.prompts


def test_private_prior_question_candidates_are_not_claimed_as_delivered_questions(tmp_path):
    store, brain, first, _, service = _case(tmp_path, kind="ask_advocate", text="Which date?")
    service.review(first)
    brain.model.tool_call.side_effect = [_response(ToolCall(
        "new", "propose_conversation", {"text": "Understood."}))]
    second = brain.run(matter_id="mat_loop", turn_id="second-interaction", message="Thank you.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 20, 400))
    subject = service.owner.build(second, store.load("mat_loop"))
    assert subject.payload["delivered_questions"] == []
    assert "Which date?" not in subject.payload_json


@pytest.mark.parametrize("current", [None, lambda *_: False])
def test_raw_navigation_windows_are_not_dropped_or_promoted_without_current_read_owner(
        tmp_path, current):
    _, _, outcome, judge, service = _case(tmp_path, read_raw=True, window_current=current)
    with pytest.raises(ReviewRefused, match="raw legal window"):
        service.review(outcome)
    assert not judge.prompts


def test_raw_navigation_words_remain_unassessed_legal_metadata_in_the_judge_subject(tmp_path):
    seen = []

    def current(window, generation):
        seen.append((window, generation))
        return (window["source_version"] == "exact-raw-snapshot"
                and generation == "actual-test-gen")
    _, _, outcome, judge, service = _case(tmp_path, read_raw=True, window_current=current)
    result = service.review(outcome)
    assert result.checked and seen
    subject = json.loads(judge.prompts[0].user)["subject"]
    assert subject["law_windows"] == []
    window = subject["unassessed_legal_windows"][0]["window"]
    assert window["legal_metadata"] == "not_assessed" and window["missing"]
    assert "Exact raw court words" in subject["quote_sources"][-1]["text"]


@pytest.mark.parametrize("boundary", ["source", "file", "principles"])
def test_late_source_file_and_principles_changes_cannot_finish_a_wording_check(tmp_path, boundary):
    store, _, outcome, judge, service = _case(tmp_path, read_source=True)
    original = judge.structured

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        if boundary == "source":
            service.owner.source_current = lambda *_: False
        elif boundary == "principles":
            service.reader.current_principles_version = lambda: "changed"
        else:
            current = store.load("mat_loop")
            store.commit(replace(current, facts=(premise(),), version=current.version + 1),
                         expected_version=current.version)
        return result
    judge.structured = change
    with pytest.raises((ReviewRefused, ValueError, StaleWrite)) as caught:
        service.review(outcome)
    saved = store.load("mat_loop").loop_records[-1]
    assert not saved.terminal
    if boundary == "file":
        # The CAS must not overwrite a concurrent correction to seal a receipt.
        # Unknown outcome retains its paid-call reservation and cannot be retried.
        assert saved.events[-1].kind is StepKind.MODEL_STARTED
        assert saved.events[-1].payload["reserved"]["cost_usd"] == 0.03
    else:
        assert saved.events[-1].kind is StepKind.MODEL_RETURNED
        assert saved.events[-1].payload["result"]["usage"]["cost_usd"] == 0.02
    assert caught.value.budget.spend.cost_usd == pytest.approx(
        outcome.budget.spend.cost_usd + 0.02)
    assert not store.load("mat_loop").turn_receipts


@pytest.mark.parametrize("bad_identity", ["model", "provider", "tier", "completion"])
def test_changed_incomplete_or_downgraded_checker_identity_remains_unassessed(
        tmp_path, bad_identity):
    _, _, outcome, judge, service = _case(tmp_path)
    original = judge.structured

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        updates = {"model": "another model"} if bad_identity == "model" else (
            {"provider": "another provider"} if bad_identity == "provider" else (
                {"tier": Tier.ROUTINE} if bad_identity == "tier" else {
                    "completion": Completion.LENGTH_LIMITED}))
        return replace(result, **updates)
    judge.structured = change
    result = service.review(outcome)
    assert not result.checked and all(row.assessed is None for row in result.judgments)
    assert result.budget.spend.cost_usd == pytest.approx(outcome.budget.spend.cost_usd + 0.02)


def test_actual_admitted_document_words_are_checked_without_law_or_fact_promotion(tmp_path):
    from nm.legal_brain.reason.matter_support import REFERENCE_KEYS, captured_documents
    from tests.test_document_words_reach_review_without_becoming_facts_or_law import (
        _case as document_case,
    )

    store, brain, first, _, documents, original_id, current = document_case(tmp_path)
    captured = captured_documents(first.record)[0]
    brain.model.tool_call.side_effect = [replace(_response(call), model="scripted:document-author")
        for call in (ToolCall("quote", "quote_matter", {
            key: captured.source[key] for key in REFERENCE_KEYS}),
            ToolCall("ask", "ask_advocate", {"question": "Is the recorded date disputed?"}))]
    outcome = brain.run(matter_id="mat_one", turn_id="document-question", message=
        "The extracted date may be wrong; ask what would resolve this uncertainty.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 20, 500))
    judge = InteractionJudge()
    owner = InteractionSubjectOwner(principles=brain.principles)
    reader = SavedCheckReader(store=store, log=brain.log, model=judge,
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: brain.principles.load().version,
        subject_packages=owner.packages, document_current=current, max_tokens=2048)
    service = InteractionReviewService(reader=reader, owner=owner)
    result = service.review(outcome)
    packet = json.loads(judge.prompts[0].user)["subject"]
    assert result.checked and not packet["law_windows"]
    assert packet["documents"][0]["source"]["facts_established"] is False
    assert packet["documents"][0]["source"]["representation"] == "local_extracted_text"
    assert store.load("mat_one").facts == () and not store.load("mat_one").turn_receipts
    documents.revoke("mat_one", "adv_one", store.load("mat_one").version, original_id)
    with pytest.raises(ReviewRefused):
        service.recorded(outcome)
    assert len(judge.prompts) == 1


def test_a_check_over_its_cost_reservation_is_charged_but_cannot_certify_words(tmp_path):
    _, _, outcome, judge, service = _case(tmp_path)
    original = judge.structured

    def costly(*args, **kwargs):
        return replace(original(*args, **kwargs), usage=Usage(80, 80, 1.2))
    judge.structured = costly
    result = service.review(outcome)
    assert not result.checked and not result.candidate_text
    assert result.budget.spend.cost_usd == pytest.approx(outcome.budget.spend.cost_usd + 1.2)
    assert result.budget.spent_out
