"""Exact server populations remove counting work, not independent judgment."""
from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest
from nm.bootstrap.evaluation_models import VerifierOnly
from nm.core.brain_finalization import CheckRead
from nm.core.brain_release import ReviewRefused
from nm.core.conversation import PRINCIPLES
from nm.core.interaction_review import (
    COMMUNICATION_UNIT_REVIEW_SCHEMA,
    CRITERIA,
    InteractionReviewService,
    MalformedInteractionReview,
    build_unit_prompt,
    communication_contract,
    interpret,
    interpret_unit_review,
    whole_text_unit,
)
from nm.domain.budget import Completion, Spend
from nm.domain.external_ai import ModelPermissionRefused
from nm.domain.register import PEER
from nm.ports.model import ModelResult, Prompt, Tier, Usage

from tests.test_interaction_words_require_an_independent_exact_review import (
    InteractionJudge,
    _case,
    _judgment,
)

pytestmark = pytest.mark.class_a


def _unit_judgment(packet):
    raw = _judgment(packet)
    clause = raw.pop("clauses")[0]
    clause.pop("start")
    clause.pop("end")
    raw["units"] = [{"unit_id": packet["review_units"][0]["unit_id"], **clause}]
    return raw


class UnitJudge(InteractionJudge):
    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_UNIT_REVIEW_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        data = self.mutation(deepcopy(_unit_judgment(json.loads(prompt.user))))
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def _v2_case(tmp_path, *, mutation=lambda raw: raw, **kwargs):
    store, brain, outcome, _, old = _case(tmp_path, **kwargs)
    judge = UnitJudge(mutation)
    old.reader.model = judge
    service = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=2)
    return store, brain, outcome, judge, service


@pytest.mark.parametrize("text", [
    "Understood.", "Is that date disputed?\nWhich record contains it?",
    "कृपया तारीख स्पष्ट करें। 👩🏽‍⚖️ e\u0301\nThe recorded allegation remains disputed.",
])
def test_actual_unit_review_and_saved_replay_cover_every_exact_unicode_word(tmp_path, text):
    store, _, outcome, judge, service = _v2_case(tmp_path, text=text)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    reviewed = service.review(outcome)
    assert reviewed.checked and reviewed.candidate_text == text
    assert reviewed.check_turn_id.endswith(":check:communication_units")
    packet = json.loads(judge.prompts[0].user)
    assert packet["review_units"] == [whole_text_unit(subject)]
    assert packet["review_units"][0]["end"] == len(text)
    assert "review_units" not in packet["subject"] and "kind" not in packet["subject"]
    assert subject.payload["kind"] == outcome.reason.value
    saved = store.load("mat_loop").loop_records[-1]
    assert saved.events[0].payload["schema"] == COMMUNICATION_UNIT_REVIEW_SCHEMA
    actual = saved.events[-1].payload["data"]
    assert "clauses" not in actual and "start" not in actual["units"][0]
    assert service.recorded(outcome) == reviewed
    assert service.review(outcome) == reviewed and len(judge.prompts) == 1
    assert not reviewed.released and not reviewed.client_ready
    assert not store.load("mat_loop").turn_receipts


def test_v2_keeps_the_same_subject_and_professional_owner_without_counted_ranges(tmp_path):
    store, _, outcome, _, service = _v2_case(tmp_path)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    old_prompt = communication_contract(1)[2](subject, service.owner.principles.load().text)
    prompt = build_unit_prompt(subject, service.owner.principles.load().text)
    old, new = json.loads(old_prompt.user), json.loads(prompt.user)
    assert old["subject"] == new["subject"] and old["subject_identity"] == new["subject_identity"]
    assert "character ranges" not in prompt.system and "EVERY word" in prompt.system
    assert prompt.system.count(PRINCIPLES) == 1 and prompt.system.count(PEER) == 1
    assert "Neither factual details nor law come from remembered model knowledge" in prompt.system
    assert prompt.operation == "interaction_unit_review_v2"
    assert whole_text_unit(subject)["unit_id"] == whole_text_unit(subject)["unit_id"]


@pytest.mark.parametrize("what", ["missing", "empty", "duplicate", "forged", "subject",
                                 "blank", "quote", "extra_range"])
def test_invalid_returned_unit_populations_are_malformed_not_positive(tmp_path, what):
    store, _, outcome, _, service = _v2_case(tmp_path)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    packet = json.loads(build_unit_prompt(subject, service.owner.principles.load().text).user)
    raw = _unit_judgment(packet)
    if what == "missing":
        del raw["units"]
    elif what == "empty":
        raw["units"] = []
    elif what == "duplicate":
        raw["units"] *= 2
    elif what == "forged":
        raw["units"][0]["unit_id"] = "invented"
    elif what == "subject":
        raw["subject_identity"] = "different subject"
    elif what == "blank":
        raw["units"][0]["reason"] = " "
    elif what == "quote":
        raw["units"][0]["supporting_words"][0]["quote"] = "Never supplied"
    else:
        raw["units"][0]["end"] = len(subject.text)
    with pytest.raises(MalformedInteractionReview):
        interpret_unit_review(subject, CheckRead(raw, "Completed", Spend(), 1),
                              outcome.budget, "controlled-check")


@pytest.mark.parametrize("kind", ["legal_or_applied_claim", "action_or_permission_claim",
                                 "unknown"])
def test_mixed_merits_or_action_words_block_even_with_six_true_judgments(tmp_path, kind):
    def mutate(raw):
        raw["units"][0]["kind"] = kind
        return raw
    _, _, outcome, _, service = _v2_case(tmp_path, mutation=mutate,
        text="Which date? You are entitled to recover and I have filed it.")
    reviewed = service.review(outcome)
    assert reviewed.clauses_complete and not reviewed.checked and not reviewed.candidate_text
    assert reviewed.judgments[0].assessed is False


@pytest.mark.parametrize("criterion", CRITERIA)
@pytest.mark.parametrize("value", [False, None])
def test_a_unit_cannot_replace_any_of_the_six_independent_dimensions(tmp_path, criterion, value):
    def mutate(raw):
        raw[criterion]["assessed"] = value
        return raw
    _, _, outcome, _, service = _v2_case(tmp_path, mutation=mutate)
    assert not service.review(outcome).checked


def test_a_malformed_real_receipt_keeps_actual_spend_and_is_not_paid_again(tmp_path):
    def mutate(raw):
        raw["units"][0]["unit_id"] = "not the owned unit"
        return raw
    store, _, outcome, judge, service = _v2_case(tmp_path, mutation=mutate)
    with pytest.raises(MalformedInteractionReview) as caught:
        service.review(outcome)
    assert caught.value.budget.spend.cost_usd == pytest.approx(
        outcome.budget.spend.cost_usd + 0.02)
    assert store.load("mat_loop").loop_records[-1].events[-1].payload["spend"]["cost_usd"] == 0.02
    with pytest.raises(MalformedInteractionReview):
        service.recorded(outcome)
    assert len(judge.prompts) == 1


def test_historic_counting_failure_is_strictly_refused_after_default_upgrade(tmp_path):
    def omit(raw):
        raw["clauses"][0]["end"] = 164
        return raw
    store, _, outcome, judge, old = _case(tmp_path, text="x" * 173, mutation=omit)
    with pytest.raises(MalformedInteractionReview):
        old.review(outcome)
    upgraded = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=2)
    assert upgraded.protocol_for_recorded_check(outcome) == 1
    with pytest.raises(MalformedInteractionReview):
        upgraded.recorded(outcome)
    with pytest.raises(ReviewRefused, match="upgraded"):
        upgraded.review(outcome)
    assert len(judge.prompts) == 1 and len(store.load("mat_loop").loop_records) == 2


def test_a_valid_historic_proof_is_read_with_its_original_contract(tmp_path):
    _, _, outcome, judge, old = _case(tmp_path)
    reviewed = old.review(outcome)
    upgraded = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=2)
    assert upgraded.recorded(outcome) == reviewed and len(judge.prompts) == 1
    assert reviewed.check_turn_id.endswith(":check:communication")


@pytest.mark.parametrize("version", [True, False, "2", 0, 4, None])
def test_protocol_versions_are_closed_owned_integers(tmp_path, version):
    _, _, _, _, old = _case(tmp_path)
    with pytest.raises(ValueError):
        InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=version)


@pytest.mark.parametrize("boundary", ["session", "source", "principles"])
def test_currentness_failures_are_not_mislabeled_as_malformed_judgments(tmp_path, boundary):
    _, _, outcome, judge, service = _v2_case(tmp_path, read_source=True)
    service.review(outcome)
    if boundary == "session":
        service.reader.session_current = lambda: False
    elif boundary == "source":
        service.owner.source_current = lambda *_: False
    else:
        service.reader.current_principles_version = lambda: "changed"
    with pytest.raises(ReviewRefused) as caught:
        service.recorded(outcome)
    assert not isinstance(caught.value, MalformedInteractionReview)
    assert len(judge.prompts) == 1


def test_missing_dispatch_allowance_does_not_spend_or_fabricate_review_units(tmp_path):
    _, _, outcome, judge, service = _v2_case(tmp_path)
    result = service.review(outcome, max_model_calls=0)
    assert result.budget == outcome.budget and result.model_steps == 0
    assert not result.checked and not judge.prompts
    assert service.recorded(outcome) is None


def test_the_verifier_facade_allows_only_the_exact_bounded_v2_schema():
    inner = Mock()
    model = VerifierOnly(inner)
    schema = deepcopy(COMMUNICATION_UNIT_REVIEW_SCHEMA)
    model.structured(Prompt("Exact check"), schema, Tier.JUDGE)
    assert inner.structured.call_args.kwargs == {"max_tokens": 2048}
    inner.reset_mock()
    schema["properties"]["units"]["maxItems"] = 2
    with pytest.raises(ModelPermissionRefused):
        model.structured(Prompt("Altered population"), schema, Tier.JUDGE)
    with pytest.raises(ModelPermissionRefused):
        model.structured(Prompt("Wrong role"), COMMUNICATION_UNIT_REVIEW_SCHEMA, Tier.ROUTINE)
    with pytest.raises(ModelPermissionRefused):
        model.structured(Prompt("Too many tokens"), COMMUNICATION_UNIT_REVIEW_SCHEMA,
                         Tier.JUDGE, max_tokens=2049)
    assert not inner.mock_calls


def test_historic_numeric_interpreter_still_rejects_an_incomplete_exact_population(tmp_path):
    store, _, outcome, _, service = _case(tmp_path, text="x" * 173)
    subject = service.owner.build(outcome, store.load("mat_loop"))
    packet = json.loads(communication_contract(1)[2](subject,
        service.owner.principles.load().text).user)
    raw = _judgment(packet)
    raw["clauses"][0]["end"] = 164
    with pytest.raises(MalformedInteractionReview):
        interpret(subject, CheckRead(raw, "Completed", Spend(), 1), outcome.budget, "old")
