"""Real private runner/store history; user input is neither model prose nor fact."""
from __future__ import annotations

import pytest

from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord, StepKind, StopReason
from nm.shared.model_port import Prompt, ProviderUnavailable, ToolCall
from nm.work_the_file.original_instruction import (
    InstructionRefused,
    OriginalInstruction,
    capture_original_instruction,
    read_original_instruction,
)
from tests.test_reviewed_private_preview_checks_saved_words import changed_payload
from tests.test_the_loop_records_work_before_using_it import PROMPT, _limits, _response, _setup

pytestmark = pytest.mark.class_a


def _run(tmp_path, *, cancelled=False, failure=False):
    store, identity, log, model, runner = _setup(tmp_path)
    model.tool_call.side_effect = ProviderUnavailable("Controlled TLS failure") if failure else [
        _response(ToolCall("done", "submit", {"answer": "UNCHECKED MODEL WORDS"}))]
    outcome = runner.run(identity, PROMPT, _limits(), cancelled=lambda: cancelled,
                         context_record={"system": PROMPT.system})
    return store, model, outcome, log


def _without_admission(record):
    events, previous = [], record.identity.fingerprint
    for event in record.events:
        raw = event.payload
        if event.sequence == 1:
            raw.pop("original_instruction", None)
        rebuilt = LoopEvent.create(event.sequence, event.kind, event.at, raw, previous)
        events.append(rebuilt)
        previous = rebuilt.fingerprint
    return LoopRecord(record.identity, tuple(events))


def test_actual_cancelled_turn_keeps_original_instruction_before_any_model_dispatch(tmp_path):
    store, model, outcome, log = _run(tmp_path, cancelled=True)
    assert outcome.reason is StopReason.CANCELLED and not model.tool_call.called
    assert outcome.record.events[0].payload["original_instruction"] == (
        capture_original_instruction(PROMPT))
    original = read_original_instruction(log.read(outcome.record.identity))
    assert original.text == PROMPT.user and original.provenance == "sealed_turn_admission"
    assert not store.load("mat_loop").facts and not store.load("mat_loop").turn_receipts
    assert PROMPT.system not in str(original.as_dict())


def test_failed_real_dispatch_preserves_user_instruction_not_model_or_system_words(tmp_path):
    _, _, outcome, log = _run(tmp_path, failure=True)
    assert outcome.reason is StopReason.PROVIDER
    data = read_original_instruction(log.read(outcome.record.identity)).as_dict()
    assert data["state"] == "recorded" and data["text"] == PROMPT.user
    assert data["trust"] == "user_instruction_not_established_fact_or_legal_authority"
    assert "Controlled TLS failure" not in str(data) and PROMPT.system not in str(data)


def test_actual_legacy_failed_record_can_recover_only_first_real_user_dispatch(tmp_path):
    _, _, outcome, _ = _run(tmp_path, failure=True)
    legacy = _without_admission(outcome.record)
    original = read_original_instruction(legacy)
    assert original.text == PROMPT.user and original.provenance == "sealed_first_dispatch"


def test_legacy_predispatch_record_reports_missing_input_without_mining_context_or_stop(tmp_path):
    _, _, outcome, _ = _run(tmp_path, cancelled=True)
    legacy = _without_admission(outcome.record)
    assert read_original_instruction(legacy).as_dict() == (
        OriginalInstruction("not_recorded").as_dict())


def test_exact_replay_keeps_the_original_saved_input_and_calls_no_model(tmp_path):
    store, identity, log, model, runner = _setup(tmp_path)
    model.tool_call.side_effect = [_response(ToolCall(
        "done", "submit", {"answer": "UNCHECKED MODEL WORDS"}))]
    outcome = runner.run(identity, PROMPT, _limits(), context_record={"system": PROMPT.system})
    before = store.load("mat_loop")
    model.tool_call.side_effect = lambda *_args, **_kwargs: pytest.fail("Replay is free")
    repeated = runner.run(identity, PROMPT, _limits(),
                          context_record={"system": PROMPT.system})
    assert repeated.record == outcome.record and log.read(identity) == outcome.record
    assert store.load("mat_loop") == before
    assert read_original_instruction(repeated.record).text == PROMPT.user


@pytest.mark.parametrize("what", ["text", "identity", "request", "extra", "operation"])
def test_authored_or_ambiguous_original_instruction_cannot_be_read_as_real_user_history(
        tmp_path, what):
    _, _, outcome, _ = _run(tmp_path)
    raw = dict(outcome.record.events[0].payload["original_instruction"])
    if what == "text":
        raw["text"] = "Different purported input"
    elif what == "identity":
        raw["text_identity"] = "0" * 64
    elif what == "request":
        raw["request_identity"] = "0" * 64
    elif what == "extra":
        raw["unchecked_response"] = "Unreviewed advice"
    else:
        raw["operation"] = "task_scoped_research"
    assert raw != outcome.record.events[0].payload["original_instruction"]
    changed = changed_payload(outcome.record, 0, original_instruction=raw)
    with pytest.raises(InstructionRefused):
        read_original_instruction(changed)


def test_a_changed_first_dispatch_is_not_used_to_reconstruct_historical_input(tmp_path):
    _, _, outcome, _ = _run(tmp_path)
    legacy = _without_admission(outcome.record)
    index = next(index for index, event in enumerate(legacy.events)
                 if event.kind is StepKind.MODEL_STARTED)
    prompt = {**legacy.events[index].payload["prompt"], "user": "Different purported input"}
    with pytest.raises(InstructionRefused):
        read_original_instruction(changed_payload(legacy, index, prompt=prompt))


@pytest.mark.parametrize("state,text,identity,provenance", [
    ("recorded", " ", "", "sealed_turn_admission"),
    ("not_recorded", "Invented input", "", "not_recorded"),
    ("recorded", "Exact input", "forged", "sealed_turn_admission"),
    ("recorded", "Exact input", "", "authored_pass"),
])
def test_original_input_type_never_turns_absence_or_asserted_provenance_into_recorded_words(
        state, text, identity, provenance):
    with pytest.raises(ValueError):
        OriginalInstruction(state, text, identity, provenance)


def test_capture_refuses_blank_or_nonprompt_inputs():
    with pytest.raises(ValueError):
        capture_original_instruction(Prompt(" ", "Prefix", "controlled_legal_brain"))
    with pytest.raises(ValueError):
        capture_original_instruction({"text": "Unchecked purported input"})
