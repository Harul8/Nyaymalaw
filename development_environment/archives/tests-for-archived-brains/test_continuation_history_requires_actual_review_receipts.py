"""Typed same-request history reuses real independently dispatched verdicts."""

import json
from dataclasses import replace

import pytest

from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.Archives.legal_brain.orchestrate.checked_input_continuation import (
    CheckedInputContinuation,
    CheckedInputContinuationService,
    CheckedInputReference,
)
from nm.Archives.legal_brain.evaluate.evaluation_history import (
    _feedback_parent,
    record_repaired_evaluation,
    resolve_preview_parent,
)
from nm.Archives.legal_brain.orchestrate.loop_contracts import StepKind
from tests.test_checked_inputs_continue_in_the_actual_evaluation import _actual, _evaluate
from tests.test_reviewed_private_preview_checks_saved_words import changed_payload, replace_record

pytestmark = pytest.mark.class_a


def actual_history(tmp_path):
    store, brain, _first, judge, _thread, requests = _actual(tmp_path)
    result = _evaluate(brain)
    assert len(result.attempts) == 2
    return store, brain, result, judge, requests


def _wire(record):
    return next(
        json.loads(row["text"])
        for row in record.events[0].payload["context"]["messages"]
        if "harness_check_continuation" in row["text"]
    )


def _typed(data):
    return CheckedInputContinuation(
        data["matter_id"],
        data["parent_turn_id"],
        data["parent_fingerprint"],
        data["original_message_identity"],
        tuple(data["selected_issue_ids"]),
        tuple(CheckedInputReference(**row) for row in data["input_references"]),
    )


def test_actual_continuation_history_reopens_only_its_previous_reviewed_input(tmp_path):
    store, brain, result, judge, requests = actual_history(tmp_path)
    record_repaired_evaluation(brain, result, "event-selection")
    before = store.load("mat_loop")
    for log in (brain.log, None):
        parent, complete = resolve_preview_parent(before, "event-selection", log)
        assert parent == result.attempts[-1].record and not complete
    assert len(judge.prompts) == 1 and len(requests) == 2
    assert store.load("mat_loop") == before and not before.turn_receipts


@pytest.mark.parametrize(
    "change",
    [
        "parent",
        "original",
        "scope",
        "reference_identity",
        "reference_parent",
        "wrong_kind_fee",
        "wrong_kind_interest",
        "unknown_kind",
        "extra_reference_key",
        "both_diagnostics",
        "unknown_field",
        "grant_reset",
        "spend_refund",
    ],
)
def test_history_cannot_relabel_or_reset_an_actual_continuation(tmp_path, change):
    store, brain, result, _judge, _requests = actual_history(tmp_path)
    prior, original = (row.record for row in result.attempts)

    def alter(record):
        start = record.events[0].payload
        wire = _wire(record)
        data = wire["data"]
        if change == "parent":
            data["parent_fingerprint"] = "a" * 64
        elif change == "original":
            data["original_message_identity"] = "a" * 64
        elif change == "scope":
            data["selected_issue_ids"] = ["thr_events"]
        elif change == "reference_identity":
            data["input_references"][0]["package_identity"] = "a" * 64
        elif change == "reference_parent":
            data["input_references"][0]["parent_turn_id"] = "other-parent"
        elif change in {"wrong_kind_fee", "wrong_kind_interest", "unknown_kind"}:
            data["input_references"][0]["kind"] = {
                "wrong_kind_fee": "fee",
                "wrong_kind_interest": "interest",
                "unknown_kind": "model-authored-role",
            }[change]
        elif change == "extra_reference_key":
            data["input_references"][0]["approved"] = True
        elif change == "both_diagnostics":
            start["context"]["messages"].append(
                {
                    "role": "system",
                    "text": json.dumps(
                        {"material_kind": "harness_check_feedback", "data": {"failures": []}}
                    ),
                }
            )
        elif change == "unknown_field":
            data["completed"] = True
        elif change == "grant_reset":
            start["budget"]["max_cost_usd"] += 1
        else:
            start["budget"]["spend"]["children"] = prior.events[-1].payload["budget"]["spend"][
                "children"
            ]
        # Do not rely solely on the diagnostic hash: forged-but-closed metadata
        # must also fail association with the actual independent source/result.
        if change not in {"extra_reference_key", "unknown_field", "both_diagnostics"}:
            start["feedback_identity"] = _typed(data).identity
        for message in start["context"]["messages"]:
            if "harness_check_continuation" in message["text"]:
                message["text"] = json.dumps(wire)
        return changed_payload(record, 0, **start)

    replace_record(store, original.identity.turn_id, alter)
    matter = store.load("mat_loop")
    changed = next(row for row in matter.loop_records if row.identity == original.identity)
    if change == "spend_refund":
        assert (
            changed.events[0].payload["budget"]["spend"]["children"]
            < original.events[0].payload["budget"]["spend"]["children"]
        )
    with pytest.raises((ReviewRefused, TypeError, ValueError)):
        _feedback_parent(changed, prior, matter, brain.log)


@pytest.mark.parametrize("change", ["saved_pass", "negative", "prompt", "judge", "missing"])
def test_history_requires_real_positive_judge_response_not_a_saved_pass(tmp_path, change):
    store, brain, result, _judge, _requests = actual_history(tmp_path)
    prior, child = (row.record for row in result.attempts)
    reference = _wire(child)["data"]["input_references"][0]
    turn = f"{prior.identity.turn_id}:verify:{reference['package_id']}"

    def alter(record):
        if change in {"saved_pass", "negative"}:
            stop = record.events[-1]
            payload = stop.payload
            if change == "saved_pass":
                payload["verification"]["reason"] = "Caller-authored independent PASS"
            else:
                payload["verification"]["textual_support"]["assessed"] = False
            return changed_payload(record, stop.sequence - 1, **payload)
        kind = StepKind.MODEL_STARTED if change == "prompt" else StepKind.MODEL_RETURNED
        event = next(row for row in record.events if row.kind is kind)
        row = event.payload
        if change == "prompt":
            payload = json.loads(row["prompt"]["user"])
            payload["claim"] = "Foreign candidate"
            row["prompt"]["user"] = json.dumps(payload)
        else:
            row["result"]["value"]["model"] = "scripted:author"
        return changed_payload(record, event.sequence - 1, **row)

    if change == "missing":
        matter = store.load("mat_loop")
        store.commit(
            replace(
                matter,
                loop_records=tuple(
                    row for row in matter.loop_records if row.identity.turn_id != turn
                ),
                version=matter.version + 1,
            ),
            expected_version=matter.version,
        )
    else:
        replace_record(store, turn, alter)
    with pytest.raises((ReviewRefused, ValueError)):
        _feedback_parent(child, prior, store.load("mat_loop"), brain.log)


def test_actual_interest_history_uses_its_canonical_source_selection_owner(tmp_path):
    from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits
    from nm.shared.model_port import ToolCall
    from tests.test_interest_is_exact_source_owned_and_independently_selected import (
        _actual as interest,
    )
    from tests.test_the_loop_records_work_before_using_it import _response

    store, outcome, owner, reviews, brain, limits, _judge = interest(tmp_path)
    checked = reviews.review(outcome)
    brain.input_continuations = CheckedInputContinuationService(
        reviewer=reviews.reviewer,
        binding_owners={"interest": owner.candidates},
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
    )
    options = {
        "original_message": "Compute the exact recorded monetary period conditionally.",
        "selected_issue_ids": (),
        "budget": checked.review.budget,
    }
    diagnostic = brain.input_continuations.prepare(
        outcome, groups=(("interest", (checked.bindings[0].package.id,)),), **options
    )
    brain.model.tool_call.side_effect = [
        _response(ToolCall("terminal", "ask_advocate", {"question": "Which account is supported?"}))
    ]
    child = brain.run(
        matter_id="mat_loop",
        turn_id="interest-parent:repair:1",
        message=options["original_message"],
        selected_issue_ids=(),
        continuation=diagnostic,
        limits=LoopLimits(checked.review.budget, limits.max_steps, limits.per_call_tokens),
    )
    _feedback_parent(child.record, outcome.record, store.load("mat_loop"), brain.log)
    assert not store.load("mat_loop").turn_receipts


def test_actual_checked_working_package_cannot_masquerade_as_fee_input_in_history(tmp_path):
    from types import SimpleNamespace

    from nm.Archives.legal_brain.reason.working_record import WorkingRecordReviewService
    from nm.shared.model_port import ToolCall
    from tests.test_early_independent_check_uses_the_actual_open_parent import (
        LIMITS,
        MESSAGE,
        actual_case,
        run,
    )
    from tests.test_the_loop_records_work_before_using_it import _response

    store, brain, owner, _early, _judge, _guard = actual_case(tmp_path)
    limits = replace(LIMITS, budget=replace(LIMITS.budget, max_children=5))
    outcome = run(brain, limits)
    checked = WorkingRecordReviewService(reviewer=brain.reviewer, owner=owner).review(outcome)
    assert len(checked.checked_annotations) == 1

    def planted_wrong_owner(parent, matter):
        _inventory, annotations, packages = owner.candidates(parent, matter)
        return tuple(
            SimpleNamespace(package=package, candidate={"thread_id": annotation.thread_id})
            for annotation, package in zip(annotations, packages, strict=True)
        )

    # A deliberately misconfigured host mapping still cannot relabel a real
    # working review as the canonical fee producer in sealed history.
    brain.input_continuations = CheckedInputContinuationService(
        reviewer=brain.reviewer,
        binding_owners={"fee": planted_wrong_owner},
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
    )
    diagnostic = brain.input_continuations.prepare(
        outcome,
        groups=(("fee", (checked.review.packages[0].id,)),),
        original_message=MESSAGE,
        selected_issue_ids=("thread_one",),
        budget=checked.review.budget,
    )
    brain.model.tool_call.side_effect = [
        _response(ToolCall("terminal", "ask_advocate", {"question": "What supplies the fee rule?"}))
    ]
    child = brain.run(
        matter_id="mat_loop",
        turn_id="early-parent:repair:1",
        message=MESSAGE,
        selected_issue_ids=("thread_one",),
        continuation=diagnostic,
        limits=replace(limits, budget=checked.review.budget),
    )
    with pytest.raises(ReviewRefused, match="selection producer"):
        _feedback_parent(child.record, outcome.record, store.load("mat_loop"), brain.log)
