"""Quote contracts distinguish actual source words from metadata, without a waiver."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.legal_brain.brain_finalization import CheckRead
from nm.legal_brain.brain_release import ReviewRefused
from nm.legal_brain.interaction_review import (
    COMMUNICATION_QUOTE_REVIEW_SCHEMA,
    CRITERIA,
    InteractionReviewService,
    MalformedInteractionReview,
    build_quote_prompt,
    communication_subject,
    interpret_quote_review,
)
from nm.shared.budget_contracts import Completion, Spend
from nm.shared.model_port import ModelResult, Tier, Usage
from tests.test_communication_evidence_roles_are_owned import EvidenceJudge, _evidence_judgment
from tests.test_communication_reviews_see_actual_work import _work_case

pytestmark = pytest.mark.class_a


class QuoteJudge(EvidenceJudge):
    def structured(self, prompt, schema, tier, **_kwargs):
        assert schema == COMMUNICATION_QUOTE_REVIEW_SCHEMA and tier is Tier.JUDGE
        self.prompts.append(prompt)
        packet = json.loads(prompt.user)
        assert packet["protocol_version"] == 5
        data = self.mutation(deepcopy(_evidence_judgment(packet)))
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(80, 80, 0.02), 1, completion=Completion.COMPLETE)


def _quote_case(tmp_path, mutation=lambda raw: raw):
    store, brain, outcome, _, old = _work_case(tmp_path)
    judge = QuoteJudge(mutation)
    old.reader.model = judge
    service = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=5)
    return store, brain, outcome, judge, service


def test_selectors_and_returned_quotation_values_have_distinct_contracts(tmp_path):
    store, _, outcome, judge, service = _quote_case(tmp_path)
    reviewed = service.review(outcome)
    packet = json.loads(judge.prompts[0].user)
    for name in CRITERIA:
        roles = packet["judgment_evidence_roles"][name]
        assert roles["response_quote"] == {
            "source_field": "proposed_text", "value_kind": "actual_verbatim_substring",
            "source_selector_is_not_a_quote": True}
        props = COMMUNICATION_QUOTE_REVIEW_SCHEMA["properties"][name]["properties"]
        assert "not its field name or source ID" in props["response_quote"]["description"]
        if name in {"relevance", "instruction_safety"}:
            assert roles["instruction_quote"]["source_field"] == "original_instruction"
    assert reviewed.checked and reviewed.check_turn_id.endswith(":check:communication_quotes")
    assert service.recorded(outcome) == reviewed and service.review(outcome) == reviewed
    assert len(judge.prompts) == 1 and not store.load("mat_loop").turn_receipts


@pytest.mark.parametrize("role", ["response_quote", "instruction_quote"])
@pytest.mark.parametrize("bad", ["source_selector", "abbreviation", "missing", "blank"])
def test_metadata_and_abbreviated_words_cannot_become_quotation_evidence(tmp_path, role, bad):
    def mutate(raw):
        value = raw["instruction_safety"]
        if bad == "source_selector":
            value[role] = "proposed_text" if role == "response_quote" else "original_instruction"
        elif bad == "abbreviation":
            value[role] = value[role][:3] + "..." + value[role][-3:]
        elif bad == "missing":
            del value[role]
        else:
            value[role] = " "
        return raw
    store, _, outcome, _, service = _quote_case(tmp_path, mutate)
    subject = communication_subject(service.owner, outcome, store.load("mat_loop"), 5)
    packet = json.loads(build_quote_prompt(subject, service.owner.principles.load().text).user)
    raw = mutate(_evidence_judgment(packet))
    with pytest.raises(MalformedInteractionReview):
        interpret_quote_review(subject, CheckRead(raw, "Completed", Spend(), 1),
                               outcome.budget, "exact-quote-check")
    if bad == "missing":
        # SavedCheckReader preserves a provider schema violation as unknown,
        # not a completed judgment or an invitation to author-repair it.
        reviewed = service.review(outcome)
        assert not reviewed.checked and not reviewed.clauses_complete
        assert all(row.assessed is None for row in reviewed.judgments)
    else:
        with pytest.raises(MalformedInteractionReview):
            service.review(outcome)


@pytest.mark.parametrize("verdict", [False, None])
def test_verbatim_quote_structure_does_not_rewrite_negative_or_unknown_verdicts(tmp_path, verdict):
    def mutate(raw):
        raw["faithfulness"]["assessed"] = verdict
        return raw
    _, _, outcome, _, service = _quote_case(tmp_path, mutate)
    reviewed = service.review(outcome)
    assert not reviewed.checked
    assert next(row.assessed for row in reviewed.judgments if row.name == "faithfulness") is verdict


def test_user_objective_not_the_selected_tool_defines_the_review_task(tmp_path):
    store, _, outcome, _, service = _quote_case(tmp_path)
    subject = communication_subject(service.owner, outcome, store.load("mat_loop"), 5)
    prompt = build_quote_prompt(subject, service.owner.principles.load().text)
    assert "cannot redefine it as a conversational opening" in prompt.system
    assert "does not establish that it was performed" in prompt.system
    assert "silently substitute their details" in prompt.system
    assert json.loads(prompt.user)["subject"]["work_receipts"]["count"] > 0


def test_historical_protocol_four_is_not_upgraded_or_redispatched_as_five(tmp_path):
    store, _, outcome, judge, old = _work_case(tmp_path)
    reviewed = old.review(outcome)
    newer = InteractionReviewService(reader=old.reader, owner=old.owner, protocol_version=5)
    assert newer.recorded(outcome) == reviewed and len(judge.prompts) == 1
    with pytest.raises(ReviewRefused, match="cannot be upgraded"):
        newer.review(outcome)
    subject = communication_subject(old.owner, outcome, store.load("mat_loop"), 4)
    assert subject == communication_subject(newer.owner, outcome, store.load("mat_loop"), 4)
