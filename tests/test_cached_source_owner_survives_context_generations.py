"""A saved relevance proof is rechecked by the current runtime source owner."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.understand.brain_context import ContextRefused, ContextSession, assemble_brief
from nm.legal_brain.orchestrate.loop_contracts import StepKind, StopReason
from nm.shared.model_port import Prompt, Tier, ToolCall
from tests.test_checklist_classification_is_independently_reviewed import (
    current_fixture_source,
    run_conversation,
)
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


def fixture(tmp_path, *, observer=None):
    source_owner = observer or Mock(wraps=current_fixture_source)
    store, brain, _, _ = run_conversation(tmp_path, read=False, source_current=source_owner)
    matter = store.load("mat_loop")
    context = ContextSession(brain.principles.load(), brain.registry.definitions,
        assemble_brief(matter, advocate_id=matter.advocate_id, source_current=source_owner),
        provider=brain.model.provider, model=brain.model.resolved_model(Tier.ROUTINE),
        source_current=source_owner)
    return brain, matter, context, source_owner


def state(context):
    return json.loads(context.brief.text)["data"]["threads"][0]["checklist_context"]["items"][0]


def test_a_current_cached_classification_survives_checked_compaction_and_recovery(tmp_path):
    _, matter, context, observer = fixture(tmp_path)
    assert state(context)["state"] == "held"
    context.compact(matter, reason="The checked file is needed for the next context generation.")
    assert state(context)["state"] == "held"
    saved = context.to_record()
    assert "source_current" not in saved and "_source_current" not in saved
    recovered = ContextSession.from_record(saved, matter, advocate_id=matter.advocate_id,
                                            source_current=observer)
    assert recovered.to_record() == saved
    recovered.compact(matter, reason="A subsequent checked context generation.")
    assert state(recovered)["state"] == "held" and observer.call_count >= 4
    assert recovered.tool_offer.to_record() == context.tool_offer.to_record()


def test_capacity_compaction_keeps_the_runtime_reader_not_a_serialized_assertion(tmp_path):
    _, matter, context, observer = fixture(tmp_path)
    original_generation = context.generation
    prompt = Prompt("Continue from the held information.", context.system, "controlled_legal_brain")
    assert context.compact_for_request(matter, prompt, context.offered_definitions)
    assert context.generation == original_generation + 1
    assert state(context)["state"] == "held"
    assert observer.call_count > 1 and context._source_current is observer


def test_changed_source_owner_reopens_the_item_and_saved_proof_cannot_override_it(tmp_path):
    current = True

    def source_owner(source, generation):
        return current and current_fixture_source(source, generation)

    _, matter, context, _ = fixture(tmp_path, observer=source_owner)
    before = context.to_record()
    assert state(context)["state"] == "held"
    current = False
    context.compact(matter, reason="Re-check against the current actual source reader.")
    assert state(context)["state"] == "outstanding"
    with pytest.raises(ContextRefused):
        ContextSession.from_record(before, matter, advocate_id=matter.advocate_id,
                                   source_current=source_owner)
    assert before["brief"]["text"] != context.brief.text


@pytest.mark.parametrize("owner", [None, False, "journal_claimed_clear"])
def test_recovery_cannot_adopt_cached_legal_currency_without_a_trusted_callable(tmp_path, owner):
    _, matter, context, _ = fixture(tmp_path)
    with pytest.raises(ContextRefused):
        ContextSession.from_record(context.to_record(), matter,
            advocate_id=matter.advocate_id, source_current=owner)


@pytest.mark.parametrize("key", ["source_current", "_source_current"])
def test_source_permissions_or_callable_names_authored_in_a_record_are_refused(tmp_path, key):
    _, matter, context, observer = fixture(tmp_path)
    saved = copy.deepcopy(context.to_record())
    saved[key] = "current_fixture_source"
    with pytest.raises(ContextRefused):
        ContextSession.from_record(saved, matter, advocate_id=matter.advocate_id,
                                   source_current=observer)


def test_controlled_brain_admission_uses_the_same_current_reader_for_its_context(tmp_path):
    brain, matter, _, observer = fixture(tmp_path)
    brain.model.tool_call.side_effect = [
        # Use the actual resolved provider/model identity of this fixture.
        replace(_response(ToolCall("ask-new", "ask_advocate", {
            "question": "Which remaining information can you supply?"})),
            provider=brain.model.provider, model=brain.model.resolved_model(Tier.ROUTINE))]
    result = brain.run(matter_id=matter.id, turn_id="fresh-cached-context",
        message="Continue without asking again for the notice I supplied.", limits=_limits())
    assert result.reason is StopReason.QUESTION
    record = next(event.payload["context"] for event in result.record.events
                  if event.kind is StepKind.MODEL_STARTED)
    assert json.loads(record["brief"]["text"])["data"]["threads"][0][
        "checklist_context"]["items"][0]["state"] == "held"
    recovered = ContextSession.from_record(record, brain.store.load(matter.id),
        advocate_id=matter.advocate_id, source_current=observer)
    assert state(recovered)["state"] == "held"
