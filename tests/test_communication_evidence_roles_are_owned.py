"""Owned evidence roles constrain citations, never independent semantic judgments."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.verify.brain_finalization import CheckRead
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.Archives.legal_brain.evaluate.evaluation_models import VerifierOnly
from nm.Archives.legal_brain.verify.interaction_review import (
    COMMUNICATION_EVIDENCE_REVIEW_SCHEMA,
    COMMUNICATION_PROTOCOL_VERSIONS,
    CRITERIA,
    InteractionReviewService,
    MalformedInteractionReview,
    build_evidence_prompt,
    communication_contract,
    interpret_evidence_review,
    whole_text_unit,
)
from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
from nm.shared.budget_contracts import Completion, Spend
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_port import ModelResult, Prompt, Tier, Usage, require_schema
from tests.test_interaction_review_units_are_server_owned import _unit_judgment, _v2_case
from tests.test_interaction_words_require_an_independent_exact_review import (
    InteractionJudge,
    _case,
)
from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    path,
    request,
)
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview

pytestmark = pytest.mark.class_a


def _evidence_judgment(packet):
    raw = _unit_judgment(packet)
    for name in CRITERIA:
        value = raw[name]
        value["response_quote"] = packet["subject"]["proposed_text"]
        if name in {"relevance", "instruction_safety"}:
            value["instruction_quote"] = packet["subject"]["original_instruction"]
        value["supporting_words"] = []
    return raw


class EvidenceJudge(InteractionJudge):
    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_EVIDENCE_REVIEW_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        data = self.mutation(deepcopy(_evidence_judgment(json.loads(prompt.user))))
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def _v3_case(tmp_path, *, mutation=lambda raw: raw, **kwargs):
    store, brain, outcome, _, old = _case(tmp_path, **kwargs)
    judge = EvidenceJudge(mutation)
    old.reader.model = judge
    service = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=3)
    return store, brain, outcome, judge, service


@pytest.mark.parametrize("text", ["Understood.", "Which entry records that date?",
                                  "तारीख विवादित है? 👩🏽‍⚖️ e\u0301"])
def test_actual_role_review_uses_one_exact_unit_and_saved_independent_result(tmp_path, text):
    store, _, outcome, judge, service = _v3_case(tmp_path, text=text)
    result = service.review(outcome)
    assert result.checked and result.candidate_text == text
    assert result.check_turn_id.endswith(":check:communication_evidence")
    assert not result.released and not result.client_ready
    assert not store.load("mat_loop").turn_receipts
    packet = json.loads(judge.prompts[0].user)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    assert packet["review_units"] == [whole_text_unit(subject)]
    assert packet["protocol_version"] == 3
    for row in result.judgments:
        assert ("proposed_text", text) in row.supporting_words
        if row.name in {"relevance", "instruction_safety"}:
            assert ("original_instruction", packet["subject"]["original_instruction"]) in (
                row.supporting_words)
    assert service.recorded(outcome) == result
    assert service.review(outcome) == result and len(judge.prompts) == 1
    saved = store.load("mat_loop").loop_records[-1]
    assert saved.events[0].payload["schema"] == COMMUNICATION_EVIDENCE_REVIEW_SCHEMA
    assert "response_quote" in saved.events[-1].payload["data"]["instruction_safety"]


def test_new_prompt_adds_owned_roles_and_proportionate_relevance_without_rewriting_old_protocols(
        tmp_path):
    store, _, outcome, _, service = _v3_case(tmp_path)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    principles = service.owner.principles.load().text
    old = communication_contract(2)[2](subject, principles)
    new = build_evidence_prompt(subject, principles)
    assert new.system.startswith(old.system)
    assert new.operation == "interaction_evidence_review_v3"
    old_data, new_data = json.loads(old.user), json.loads(new.user)
    assert old_data["subject"] == new_data["subject"]
    assert old_data["review_units"] == new_data["review_units"]
    assert "judgment_evidence_roles" not in old_data
    assert new_data["judgment_evidence_roles"]["instruction_safety"] == {
        "response_quote": "proposed_text", "instruction_quote": "original_instruction"}
    assert "ALL supplied attributed earlier inputs" in new.system
    assert "unavailable does not mean nonexistent" in new.system
    assert "needlessly postpones" in new.system and "conditional analysis" in new.system


@pytest.mark.parametrize("name", CRITERIA)
@pytest.mark.parametrize("verdict", [False, None])
def test_required_exact_quotes_never_upgrade_negative_or_unknown_semantic_judgments(
        tmp_path, name, verdict):
    def mutate(raw):
        raw[name]["assessed"] = verdict
        return raw
    _, _, outcome, _, service = _v3_case(tmp_path, mutation=mutate)
    result = service.review(outcome)
    assert result.clauses_complete and not result.checked and not result.candidate_text
    assert next(row.assessed for row in result.judgments if row.name == name) is verdict


@pytest.mark.parametrize("role", ["response_quote", "instruction_quote"])
@pytest.mark.parametrize("bad", ["missing", "blank", "invented", "wrong_role", "wrong_type"])
def test_every_owned_role_refuses_missing_wrong_or_fabricated_words(tmp_path, role, bad):
    store, _, outcome, _, service = _v3_case(tmp_path)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    packet = json.loads(build_evidence_prompt(subject, service.owner.principles.load().text).user)
    raw = _evidence_judgment(packet)
    value = raw["instruction_safety"]
    if bad == "missing":
        del value[role]
    elif bad == "blank":
        value[role] = " "
    elif bad == "invented":
        value[role] = "Words never supplied by either source."
    elif bad == "wrong_type":
        value[role] = {"source_id": "proposed_text", "quote": subject.text}
    else:
        value[role] = packet["subject"]["original_instruction" if role == "response_quote"
                                        else "proposed_text"]
    with pytest.raises(MalformedInteractionReview):
        interpret_evidence_review(subject, CheckRead(raw, "Completed", Spend(), 1),
                                  outcome.budget, "exact-role-check")


@pytest.mark.parametrize("kind", [
    "legal_or_applied_claim", "action_or_permission_claim", "unknown"])
def test_owned_quote_slots_do_not_create_a_nonmerits_exemption(tmp_path, kind):
    def mutate(raw):
        raw["units"][0]["kind"] = kind
        return raw
    _, _, outcome, _, service = _v3_case(tmp_path, mutation=mutate)
    result = service.review(outcome)
    assert result.judgments[0].assessed is False and not result.checked


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("missing_instruction", [False, True])
def test_saved_old_contract_is_never_reinterpreted_or_redispatched_as_version_three(
        tmp_path, version, missing_instruction):
    def mutate(raw):
        if missing_instruction:
            raw["instruction_safety"]["supporting_words"] = [
                row for row in raw["instruction_safety"]["supporting_words"]
                if row["source_id"] != "original_instruction"]
        return raw
    fixture = _case if version == 1 else _v2_case
    _, _, outcome, judge, old = fixture(tmp_path, mutation=mutate)
    if missing_instruction:
        with pytest.raises(MalformedInteractionReview):
            old.review(outcome)
    else:
        result = old.review(outcome)
    new = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=3)
    assert new.protocol_for_recorded_check(outcome) == version
    if missing_instruction:
        with pytest.raises(MalformedInteractionReview):
            new.recorded(outcome)
    else:
        assert new.recorded(outcome) == result
    with pytest.raises(ReviewRefused, match="upgraded"):
        new.review(outcome)
    assert len(judge.prompts) == 1


def test_protocol_registry_and_verifier_facade_admit_only_exact_bounded_owned_v3_schema():
    assert COMMUNICATION_PROTOCOL_VERSIONS == (1, 2, 3, 4, 5, 6, 7)
    assert communication_contract(3)[0] == "communication_evidence"
    schema = deepcopy(COMMUNICATION_EVIDENCE_REVIEW_SCHEMA)
    for name in CRITERIA:
        properties = schema["properties"][name]
        assert set(properties["properties"]) == set(properties["required"])
        assert properties["additionalProperties"] is False
    inner = Mock()
    wrapper = VerifierOnly(inner)
    wrapper.structured(Prompt("Exact review"), schema, Tier.JUDGE)
    assert inner.structured.call_args.kwargs == {"max_tokens": 2048}
    inner.reset_mock()
    schema["properties"]["instruction_safety"]["required"].remove("instruction_quote")
    with pytest.raises(ModelPermissionRefused):
        wrapper.structured(Prompt("Relaxed role"), schema, Tier.JUDGE)
    with pytest.raises(ModelPermissionRefused):
        wrapper.structured(Prompt("Wrong role"), COMMUNICATION_EVIDENCE_REVIEW_SCHEMA, Tier.ROUTINE)
    with pytest.raises(ModelPermissionRefused):
        wrapper.structured(Prompt("Unbounded output"), COMMUNICATION_EVIDENCE_REVIEW_SCHEMA,
                           Tier.JUDGE, max_tokens=2049)
    assert not inner.mock_calls


def test_actual_schema_accepts_the_extra_words_empty_population_but_no_missing_roles(tmp_path):
    store, _, outcome, _, service = _v3_case(tmp_path)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    raw = _evidence_judgment(json.loads(build_evidence_prompt(
        subject, service.owner.principles.load().text).user))
    require_schema(raw, COMMUNICATION_EVIDENCE_REVIEW_SCHEMA)
    assert all(not raw[name]["supporting_words"] for name in CRITERIA)
    raw["relevance"]["supporting_words"] = [{"source_id": "original_instruction",
                                            "quote": raw["relevance"]["instruction_quote"]}]
    with pytest.raises(MalformedInteractionReview, match="Repeated"):
        interpret_evidence_review(subject, CheckRead(raw, "Completed", Spend(), 1),
                                  outcome.budget, "same-role-twice")


def test_actual_application_can_dispatch_read_and_acknowledge_the_distinct_v3_review(client):
    from nm.Archives.legal_brain.communicate.preview_display import displayed_questions
    from nm.shared.store_loop_log import MatterLoopLog

    app, matter, author, _ = approved(client)
    judges = []
    def reviewer(application, scope, current):
        judge = EvidenceJudge()
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling)
    assert app.controlled_evaluations[0].interaction_protocol_version == 1
    app.controlled_evaluations = (replace(app.controlled_evaluations[0],
        reviewer_factory=reviewer, interaction_protocol_version=3),)
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200, posted.text
    assert PRIVATE not in posted.text
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    assert shown.json()["paragraphs"] == [{"text": PRIVATE, "references": []}]
    assert shown.json()["released"] is shown.json()["client_ready"] is False
    seen = client.post(f"{preview(matter)}/seen", json={})
    assert seen.status_code == 200, seen.text
    saved = app.store.load(matter.id)
    history = displayed_questions(saved, before_version=saved.version, selected_issue_ids=())
    assert len(history) == 1 and history[0]["text"] == PRIVATE
    assert history[0]["state"] == "historical_private_preview_display_not_current_legal_validity"
    assert client.get(preview(matter)).json()["paragraphs"] == shown.json()["paragraphs"]
    assert not saved.facts and not saved.turn_receipts and not saved.asked
    assert author.tool_call.call_count == 1 and sum(len(j.prompts) for j in judges) == 1
