"""The generic saved-read seam accepts no authored terminal or release authority."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.verify.brain_assessment import AssessmentRefused, AssessmentService
from nm.Archives.legal_brain.verify.brain_finalization import FinalizationService, SavedCheckReader
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, captured_findings, prepare_claims
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind, StopReason
from nm.Archives.legal_brain.verify.verifier import EvidencePackage
from nm.shared.budget_contracts import Spend
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import Prompt, Tier, ToolCall
from nm.shared.model_scripted import ScriptedModelAdapter
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a

SCHEMA = {
    "x-nm-read": "private_interaction_check", "type": "object",
    "properties": {"faithful": {"type": "boolean"}},
    "required": ["faithful"], "additionalProperties": False,
}
PROMPT = Prompt(system="Check this private interaction subject without supplying law.",
                user="The exact proposed interaction is: Thank you; I have noted your instruction.")


def _model():
    result = ScriptedModelAdapter(ModelConfig({tier: TierConfig(
        tier, "scripted", "private-check-reader", None, None)
        for tier in (Tier.HARD, Tier.ROUTINE)}),
        structured_responses={"private_interaction_check": {"faithful": True}})
    result.structured = Mock(wraps=result.structured)
    return result


def _reader(store, brain, outcome, *, subject_packages=None, model=None, **overrides):
    values = {"store": store, "log": brain.log, "model": model or _model(),
        "session_current": lambda: True, "cost_ceiling": lambda *_: 0.03,
        "current_tools_version": lambda: outcome.record.identity.tools_version,
        "current_principles_version": lambda: outcome.record.identity.principles_version,
        "subject_packages": subject_packages}
    return SavedCheckReader(**{**values, **overrides})


def _conversation(tmp_path):
    store, brain, seeded, _, _ = _case(tmp_path)
    text = "Thank you; I have noted your instruction."
    brain.model.tool_call.side_effect = [replace(_response(ToolCall(
        "conversational", "propose_conversation", {"text": text})),
        provider="scripted", model="scripted:author")]
    outcome = brain.run(matter_id=seeded.record.identity.matter_id, turn_id="private-conversation",
        message="Thank you. No further legal assessment is requested.",
        limits=LoopLimits(seeded.budget, 10, 500))
    assert outcome.reason is StopReason.CONVERSATION and not captured_findings(outcome)

    def subject(parent, matter):
        if parent.reason is not StopReason.CONVERSATION:
            raise ReviewRefused("This owner is limited to a saved conversational proposal")
        proposal = parent.proposal
        if (set(proposal) != {"text", "assessment_state", "client_ready", "released"}
                or proposal["client_ready"] is not False or proposal["released"] is not False
                or proposal["assessment_state"] != "not_assessed"):
            raise ReviewRefused("The exact conversational subject is private and unassessed")
        # Nothing here invents a legal source or turns the account into truth.
        return (EvidencePackage("interaction", proposal["text"], (), ()),)

    return store, brain, outcome, subject


def test_actual_source_free_interaction_uses_saved_transport_without_a_release(tmp_path):
    store, brain, outcome, subject = _conversation(tmp_path)
    model = _model()
    reader = _reader(store, brain, outcome, subject_packages=subject, model=model)
    packages = subject(outcome, store.load("mat_loop"))
    assert not packages[0].spans and not packages[0].premises and not packages[0].documents
    assert reader.current(outcome).id == outcome.record.identity.matter_id
    checked = reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, outcome.budget)
    assert checked.data == {"faithful": True} and checked.model_steps == 1
    assert checked.spend.children == 1 and model.structured.call_count == 1
    actual = store.load("mat_loop")
    saved = next(row for row in actual.loop_records
                 if row.identity.turn_id == "private-conversation:check:interaction")
    assert saved.terminal and saved.events[-1].payload["released"] is False
    assert [event.kind for event in saved.events] == [StepKind.START, StepKind.MODEL_STARTED,
                                                    StepKind.MODEL_RETURNED, StepKind.STOP]
    assert not actual.turn_receipts and not store.transcripts_for("mat_loop")
    repeated = reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, outcome.budget)
    assert repeated == checked and model.structured.call_count == 1


@pytest.mark.parametrize("change", ["proposal", "reason", "cost_limit", "spend"])
def test_authored_terminal_or_budget_never_reaches_even_a_custom_subject_owner(tmp_path, change):
    store, brain, outcome, subject = _conversation(tmp_path)
    owner, model = Mock(side_effect=subject), _model()
    reader = _reader(store, brain, outcome, subject_packages=owner, model=model)
    altered = (replace(outcome, proposal={**outcome.proposal, "text": "Different words."})
        if change == "proposal" else replace(outcome, reason=StopReason.QUESTION)
        if change == "reason" else replace(outcome, budget=replace(
            outcome.budget, max_cost_usd=100)) if change == "cost_limit" else
        replace(outcome, budget=replace(outcome.budget, spend=replace(
            outcome.budget.spend, tokens=outcome.budget.spend.tokens + 1))))
    before = store.load("mat_loop")
    with pytest.raises(ReviewRefused, match="terminal|budget"):
        reader.read(altered, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, altered.budget)
    assert not owner.called and not model.structured.called
    assert store.load("mat_loop") == before


@pytest.mark.parametrize("change", ["max_ms", "max_tokens", "max_cost_usd", "max_retries",
                                  "max_children", "spend"])
def test_separate_read_budget_cannot_enlarge_or_restore_saved_task_limits(tmp_path, change):
    store, brain, outcome, subject = _conversation(tmp_path)
    model = _model()
    reader = _reader(store, brain, outcome, subject_packages=subject, model=model)
    value = Spend() if change == "spend" else getattr(outcome.budget, change) + 1
    altered = replace(outcome.budget, **{change: value})
    with pytest.raises(ReviewRefused, match="budget|limit"):
        reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, altered)
    assert not model.structured.called


def test_later_cancellation_stops_a_private_check_without_provider_dispatch(tmp_path):
    store, brain, outcome, subject = _conversation(tmp_path)
    model = _model()
    reader = _reader(store, brain, outcome, subject_packages=subject, model=model)
    stopped = replace(outcome.budget, cancelled_at="2026-09-27T15:00:00+00:00")
    result = reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, stopped)
    assert result.data is None and result.model_steps == 0 and not model.structured.called
    assert result.spend.tokens == 0 and result.spend.cost_usd == 0
    actual = store.load("mat_loop").loop_records[-1]
    assert actual.events[-1].payload["released"] is False
    assert not any(event.kind is StepKind.MODEL_STARTED for event in actual.events)


def test_a_saved_cancellation_cannot_be_cleared_to_buy_a_new_check(tmp_path):
    store, brain, original, _, _ = _case(tmp_path)
    cancelled = replace(original.budget, cancelled_at="2026-09-27T15:00:00+00:00")
    outcome = brain.run(matter_id="mat_loop", turn_id="cancelled-parent",
        message="Stop this work.", limits=LoopLimits(cancelled, 10, 500))
    assert outcome.budget.cancelled_at and outcome.reason is StopReason.BUDGET
    model = _model()
    reader = _reader(store, brain, outcome, subject_packages=lambda *_: (), model=model)
    with pytest.raises(ReviewRefused, match="budget"):
        reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE,
                    replace(outcome.budget, cancelled_at=""))
    assert not model.structured.called


@pytest.mark.parametrize("bad", [False, "author says PASS", {}, ()])
def test_subject_owner_must_be_installation_owned_callable(tmp_path, bad):
    store, brain, outcome, _, _ = _case(tmp_path)
    with pytest.raises(ValueError, match="callable subject owner"):
        _reader(store, brain, outcome, subject_packages=bad)


@pytest.mark.parametrize("bad", [None, [], ({"claim": "Authored PASS"},), ("PASS",)])
def test_custom_subject_owner_cannot_return_authored_or_untyped_packages(tmp_path, bad):
    store, brain, outcome, _ = _conversation(tmp_path)
    model = _model()
    reader = _reader(store, brain, outcome, subject_packages=lambda *_: bad, model=model)
    before = store.load("mat_loop")
    with pytest.raises(ReviewRefused, match="typed document packages"):
        reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, outcome.budget)
    assert not model.structured.called and store.load("mat_loop") == before


@pytest.mark.parametrize("change", ["session", "tools", "principles", "file", "actor", "journal"])
def test_custom_owner_still_requires_live_scope_file_and_actual_saved_journal(tmp_path, change):
    store, brain, outcome, subject = _conversation(tmp_path)
    owner, model = Mock(side_effect=subject), _model()
    reader = _reader(store, brain, outcome, subject_packages=owner, model=model)
    if change == "session":
        reader.session_current = lambda: False
    elif change == "tools":
        reader.current_tools_version = lambda: "changed-source-and-tool-generation"
    elif change == "principles":
        reader.current_principles_version = lambda: "changed-principles"
    elif change in ("file", "actor"):
        current = store.load("mat_loop")
        updates = {"facts": (replace(current.facts[0], statement="Changed account.",
                                      exact_words=None),)} if change == "file" else {
            "advocate_id": "foreign-actor"}
        store.commit(replace(current, **updates, version=current.version + 1),
                     expected_version=current.version)
    else:
        reader.log = Mock(read=Mock(return_value=None))
    with pytest.raises(ReviewRefused):
        reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, outcome.budget)
    assert not owner.called and not model.structured.called
    assert not store.load("mat_loop").turn_receipts


def test_default_legal_owner_and_merits_preflight_remain_mandatory(tmp_path):
    store, brain, outcome, subject = _conversation(tmp_path)
    default = _reader(store, brain, outcome)
    with pytest.raises(ReviewRefused, match="answer proposal"):
        default.current(outcome)
    with pytest.raises(ReviewRefused, match="answer proposal"):
        brain.review(outcome)
    legal = FinalizationService(reader=_reader(store, brain, outcome, subject_packages=subject),
                               today=lambda: date(2026, 9, 27), jurisdiction="not assessed")
    with pytest.raises(ReviewRefused, match="answer proposal"):
        legal._requests(store.load("mat_loop"), outcome, None)
    with pytest.raises((AssessmentRefused, ReviewRefused)):
        AssessmentService(store=store, log=brain.log, session_current=lambda: True).assess(
            outcome, None)
    assert not store.load("mat_loop").turn_receipts


def test_default_owner_still_refuses_a_saved_legal_package_with_an_unretrieved_quote(tmp_path):
    _, _, _, _, original = _case(tmp_path / "seed")
    bad = {**original, "sources": [{"locator": "held:rule:1",
                                     "quote": "Words never retrieved from the corpus."}]}
    store, brain, outcome, _, _ = _case(tmp_path / "bad", claims=[bad])
    model = _model()
    reader = _reader(store, brain, outcome, model=model)
    with pytest.raises(ReviewRefused, match="exact captured source"):
        reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, outcome.budget)
    assert not model.structured.called


@pytest.mark.parametrize("owner", [None, lambda *_: False])
def test_custom_subjects_cannot_skip_current_document_permission(tmp_path, owner):
    from tests.test_document_words_reach_review_without_becoming_facts_or_law import (
        _case as doc_case,
    )

    store, brain, outcome, _, _, _, _ = doc_case(tmp_path)
    packages = prepare_claims(outcome, store.load("mat_one"))
    assert packages[0].documents and not packages[0].spans
    model = _model()
    reader = _reader(store, brain, outcome, model=model,
                     subject_packages=lambda *_: packages, document_current=owner)
    with pytest.raises(ReviewRefused, match="document"):
        reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, outcome.budget)
    assert not model.structured.called and not store.load("mat_one").turn_receipts


def test_subject_owner_programming_errors_are_not_success_or_provider_unavailability(tmp_path):
    store, brain, outcome, _ = _conversation(tmp_path)
    model = _model()

    def broken(*_):
        raise RuntimeError("Broken trusted subject decoder")

    reader = _reader(store, brain, outcome, subject_packages=broken, model=model)
    with pytest.raises(RuntimeError, match="trusted subject decoder"):
        reader.read(outcome, "interaction", PROMPT, SCHEMA, Tier.ROUTINE, outcome.budget)
    assert not model.structured.called
