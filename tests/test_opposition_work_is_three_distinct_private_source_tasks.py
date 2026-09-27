"""Actual lead/child callers and rejection, not proof of legal judgment quality."""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from nm.core.opposition_work import (
    OppositionRequest,
    case_basis,
    opposition_status_tool,
    reusable_work,
    status_for_work,
)
from nm.core.tools import ToolRefused
from nm.domain.budget import Budget
from nm.domain.loop import LoopEvent, LoopLimits, StepKind, StopReason, digest
from nm.ports.model import ToolCall

from tests.test_independent_claim_verifier import finding
from tests.test_nested_research_has_one_budget_and_one_writer import setup
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
LIMITS = LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=2, max_children=8),
                    max_steps=64, per_call_tokens=500)


def args(kind, *, issues=None, question="Critically test the source-supported position."):
    return {"question": question,
            "issue_ids": issues or (["dispute_one", "dispute_two"]
                                     if kind == "oppose_matter" else ["dispute_one"])}


def observation(kind, *, id=None, issues=None, **updates):
    cross = kind in ("cross_exposure", "no_exposure_identified")
    row = {"id": id or kind, "kind": kind, "issue_ids": issues or (
        ["dispute_one", "dispute_two"] if cross else ["dispute_one"]),
        "text": "The notice condition could limit the claimed benefit.",
        "finding_ids": ["f1"], "premise_ids": ["first", "third"] if cross else ["first"],
        "response_to": "strongest_case" if kind == "reply" else "",
        "no_supported_reply": False, "course": ""}
    row.update(updates)
    return row


def finish(kind, *, observations=None, quote=None):
    rows = ([observation("cross_exposure")] if kind == "oppose_matter" else
            [observation("strongest_case"), observation("reply"),
             observation("judicial_question")] if kind == "oppose_full" else
            [observation("strongest_case")])
    return ToolCall("finish-" + kind, "finish_opposition", {
        "findings": [{"id": "f1", "locator": finding().locator,
                      "quote": quote or finding().span}],
        "observations": rows if observations is None else observations})


def fixture(tmp_path):
    store, model, brain, dispatcher = setup(tmp_path)
    status = opposition_status_tool(store=store, provider=lambda: model.provider,
                                    model=lambda: model.resolved_model.return_value)
    brain.registry = brain.registry.extend((status,))
    brain._runner._tools = brain.registry
    return store, model, brain, dispatcher


def run(brain, *, turn="opposition-1", selected=("dispute_one", "dispute_two")):
    return brain.run(matter_id="mat_loop", turn_id=turn,
                     message="Test the recorded case critically.",
                     selected_issue_ids=selected, limits=LIMITS)


def work(output, kind):
    return next(event.payload["receipt"]["receipt"]["task_result"]["opposition_work"]
                for event in output.record.events if event.kind is StepKind.TOOL_RETURNED
                and event.payload["receipt"]["tool"] == kind)


def child_script(kinds):
    replies = []
    for index, kind in enumerate(kinds):
        replies += [_response(ToolCall("delegate-" + str(index), kind, args(kind))),
                    _response(ToolCall("law-" + str(index), "read_law", {})),
                    _response(finish(kind))]
    return [*replies, _response(ToolCall("status", "read_opposition_status", {})),
            _response(ToolCall("submit", "submit", {"answer": "Unchecked private proposal."}))]


def test_three_distinct_passes_are_saved_and_never_complete_merits(tmp_path):
    store, model, brain, _ = fixture(tmp_path)
    kinds = ("oppose_early", "oppose_full", "oppose_matter")
    model.tool_call.side_effect = child_script(kinds)
    output = run(brain)
    assert output.reason is StopReason.PROPOSAL
    assert output.budget.spend.children == 3 and output.budget.spend.failed_children == 0
    assert output.budget.spend.cost_usd == pytest.approx(0.11)
    assert len({work(output, kind)["work_identity"] for kind in kinds}) == 3
    assert [work(output, kind)["case"]["pass"] for kind in kinds] == ["early", "full", "matter"]
    status = next(event.payload["receipt"]["data"] for event in output.record.events
                  if event.kind is StepKind.TOOL_RETURNED
                  and event.payload["receipt"]["tool"] == "read_opposition_status")
    assert len(status["passes"]) == 5
    assert sum(row["state"] == "current_unreviewed" for row in status["passes"]) == 3
    assert status["full_readiness"] == "not_assessed" and status["complete"] is False
    assert all(row["assessment"] == "not_assessed" for row in status["passes"])
    assert sum(bool(row.get("private_work")) for row in status["passes"]) == 3
    assert not store.load("mat_loop").turn_receipts
    assert len(store.load("mat_loop").loop_records) == 1
    # Child work is a read-only proposal, not a canonical case write.
    assert store.load("mat_loop").facts[0].statement == "Delivery did not occur on 2024-01-02."


def test_same_basis_reuses_sealed_work_without_another_paid_child_call(tmp_path):
    store, model, brain, _ = fixture(tmp_path)
    kind = "oppose_early"
    model.tool_call.side_effect = child_script((kind,))
    first = run(brain)
    original = work(first, kind)
    model.tool_call.reset_mock()
    model.tool_call.side_effect = [
        _response(ToolCall("refresh", "read_law", {})),
        _response(ToolCall("reuse", kind, args(kind))),
        _response(ToolCall("status", "read_opposition_status", {})),
        _response(ToolCall("finish", "submit", {"answer": "Unchecked private proposal."})),
    ]
    second = run(brain, turn="opposition-2")
    assert second.reason is StopReason.PROPOSAL and model.tool_call.call_count == 4
    assert work(second, kind) == original
    returned = next(event.payload for event in second.record.events
                    if event.kind is StepKind.TOOL_RETURNED and event.payload["call_id"] == "reuse")
    assert returned["child_steps"] == 0 and returned["child_transcript"] == []
    assert returned["receipt"]["receipt"]["task_result"]["reused_from"]["turn_id"] == "opposition-1"
    assert second.budget.spend.cost_usd == pytest.approx(0.04)
    assert second.budget.spend.children == 1  # Conservative local admission, no fabricated refund.
    assert not store.load("mat_loop").turn_receipts


def test_changed_dispute_stales_only_its_work_and_the_cross_pass(tmp_path):
    store, model, brain, _ = fixture(tmp_path)
    model.tool_call.side_effect = child_script(("oppose_early", "oppose_matter"))
    output = run(brain)
    file = store.load("mat_loop")
    control = work(output, "oppose_early")["controls"]
    changed = replace(file, facts=tuple(replace(row, statement="Unrelated detail changed.")
                                       if row.id == "third" else row for row in file.facts))
    assert status_for_work(changed, work(output, "oppose_early"), (finding(),), control) == (
        "current_unreviewed")
    assert status_for_work(changed, work(output, "oppose_matter"), (finding(),), control) == "stale"
    changed_one = replace(file, facts=tuple(replace(row, statement="The instruction was corrected.")
                                           if row.id == "first" else row for row in file.facts))
    for kind in ("oppose_early", "oppose_matter"):
        assert status_for_work(changed_one, work(output, kind), (finding(),), control) == "stale"
    assert status_for_work(replace(file, version=file.version + 10), work(output, "oppose_early"),
                           (finding(),), control) == "current_unreviewed"


@pytest.mark.parametrize("change", ["source", "missing_source", "principles", "model", "task"])
def test_reuse_needs_the_exact_current_subject_and_sources(tmp_path, change):
    store, model, brain, _ = fixture(tmp_path)
    model.tool_call.side_effect = child_script(("oppose_early",))
    output = run(brain)
    file = store.load("mat_loop")
    raw = work(output, "oppose_early")
    request = OppositionRequest("oppose_early", args("oppose_early")["question"], ("dispute_one",))
    captured, control = (finding(),), dict(raw["controls"])
    if change == "source":
        captured = (finding(span="The amended rule no longer contains the cited words."),)
    elif change == "missing_source":
        captured = ()
    elif change in ("principles", "model"):
        control["principles_version" if change == "principles" else "model"] = "changed"
    else:
        request = replace(request, question="Different task")
    assert reusable_work(file, request, captured, control) is None


@pytest.mark.parametrize("bad", ["empty", "invented", "foreign_fact", "foreign_issue",
                                  "full_incomplete", "reply_no_course", "cross_one_issue"])
def test_an_empty_or_unbound_attack_cannot_establish_private_work(tmp_path, bad):
    store, model, brain, _ = fixture(tmp_path)
    kind = "oppose_full" if bad in ("full_incomplete", "reply_no_course") else (
        "oppose_matter" if bad == "cross_one_issue" else "oppose_early")
    proposed = finish(kind)
    changed = copy.deepcopy(dict(proposed.arguments))
    if bad == "empty":
        changed["observations"] = []
    elif bad == "invented":
        changed["findings"][0]["quote"] = "All claims must succeed."
    elif bad == "foreign_fact":
        changed["observations"][0]["premise_ids"] = ["third"]
    elif bad == "foreign_issue":
        changed["observations"][0]["issue_ids"] = ["outside"]
    elif bad == "full_incomplete":
        changed["observations"] = changed["observations"][:1]
    elif bad == "reply_no_course":
        changed["observations"][1]["no_supported_reply"] = True
    else:
        changed["observations"][0]["issue_ids"] = ["dispute_one"]
    model.tool_call.side_effect = [
        _response(ToolCall("delegate", kind, args(kind))),
        _response(ToolCall("source", "read_law", {})),
        _response(replace(proposed, arguments=changed)),
        _response(ToolCall("finish", "submit", {"answer": "Still private and unchecked."})),
    ]
    output = run(brain)
    returned = next(event.payload["receipt"] for event in output.record.events
                    if event.kind is StepKind.TOOL_RETURNED
                    and event.payload["receipt"]["tool"] == kind)
    assert "opposition_work" not in returned["receipt"]["task_result"]
    assert returned["assessment"] == "not_assessed"
    assert output.budget.spend.failed_children == 1
    assert not store.load("mat_loop").turn_receipts


def test_the_cross_pass_cannot_expand_a_narrow_parent_grant(tmp_path):
    store, model, brain, _ = fixture(tmp_path)
    model.tool_call.return_value = _response(ToolCall(
        "cross", "oppose_matter", args("oppose_matter")))
    output = run(brain, selected=("dispute_one",))
    assert output.reason is StopReason.REFUSED and model.tool_call.call_count == 1
    assert not store.load("mat_loop").turn_receipts


def test_status_is_derived_and_cannot_be_written_by_the_model(tmp_path):
    _, model, brain, _ = fixture(tmp_path)
    model.tool_call.return_value = _response(ToolCall(
        "forge", "read_opposition_status", {"complete": True, "full_readiness": "ready"}))
    output = run(brain)
    assert output.reason is StopReason.REFUSED and model.tool_call.call_count == 1


def test_a_pass_subject_keeps_adverse_facts_and_separate_unknowns(tmp_path):
    store, _, _, _ = fixture(tmp_path)
    request = OppositionRequest("oppose_early", args("oppose_early")["question"], ("dispute_one",))
    basis = case_basis(store.load("mat_loop"), request)
    assert {row["id"] for row in basis["facts"]} == {"first", "second"}
    assert basis["facts"][1]["confirmed"] is None
    assert basis["threads"][0]["posture"]["role"] == "unknown"


def test_a_new_dispute_stales_the_whole_matter_pass_not_an_unrelated_single_pass(tmp_path):
    store, model, brain, _ = fixture(tmp_path)
    model.tool_call.side_effect = child_script(("oppose_early", "oppose_matter"))
    output = run(brain)
    file = store.load("mat_loop")
    added = replace(file, threads=(*file.threads, replace(
        file.threads[1], id="new_dispute", chronology=())))
    control = work(output, "oppose_early")["controls"]
    assert status_for_work(added, work(output, "oppose_early"), (finding(),), control) == (
        "current_unreviewed")
    assert status_for_work(added, work(output, "oppose_matter"), (finding(),), control) == "stale"


@pytest.mark.parametrize("field", [
    "source", "empty", "release", "reference", "self_review", "quote"])
def test_even_a_resealed_private_record_cannot_supply_unauthored_work(tmp_path, field):
    store, model, brain, _ = fixture(tmp_path)
    model.tool_call.side_effect = child_script(("oppose_early",))
    output = run(brain)
    file = store.load("mat_loop")
    original = work(output, "oppose_early")
    events, previous = [], output.record.identity.fingerprint
    for event in output.record.events:
        payload = event.payload
        if (event.kind is StepKind.TOOL_RETURNED
                and payload["receipt"]["tool"] == "oppose_early"):
            raw = payload["receipt"]["receipt"]["task_result"]["opposition_work"]
            if field == "source":
                raw["sources"][0]["span"] = "An invented source not returned by any reader."
            elif field == "empty":
                raw["research"]["observations"] = []
            elif field == "release":
                raw["advice_released"] = True
            elif field == "self_review":
                raw["research"]["observations"][0]["semantic_assessment"] = "PASS"
            elif field == "quote":
                raw["research"]["findings"][0]["quote"] = "Law that the actual source never said."
            else:
                payload["receipt"]["receipt"]["task_result"]["reused_from"] = {
                    "turn_id": "invented", "event_fingerprint": "0" * 64, "sequence": 1}
            raw["work_identity"] = digest({key: value for key, value in raw.items()
                                            if key != "work_identity"})
        rebuilt = LoopEvent.create(event.sequence, event.kind, event.at, payload, previous)
        events.append(rebuilt)
        previous = rebuilt.fingerprint
    changed = replace(file, loop_records=(replace(output.record, events=tuple(events)),))
    request = OppositionRequest("oppose_early", args("oppose_early")["question"], ("dispute_one",))
    with pytest.raises(ToolRefused):
        reusable_work(changed, request, (finding(),), original["controls"])


def test_private_full_reply_may_have_no_supported_answer_but_must_carry_a_course(tmp_path):
    _, model, brain, _ = fixture(tmp_path)
    rows = [observation("strongest_case"), observation(
        "reply", no_supported_reply=True,
        course="Obtain the source record before relying on a reply."),
        observation("judicial_question")]
    model.tool_call.side_effect = [
        _response(ToolCall("delegate", "oppose_full", args("oppose_full"))),
        _response(ToolCall("source", "read_law", {})),
        _response(finish("oppose_full", observations=rows)),
        _response(ToolCall("finish", "submit", {"answer": "Still private."})),
    ]
    output = run(brain)
    candidate = work(output, "oppose_full")["research"]["observations"][1]
    assert candidate["no_supported_reply"] is True and candidate["course"]
    assert candidate["semantic_assessment"] == "not_assessed"


def test_a_source_binding_change_is_scoped_not_a_text_similarity_guess(tmp_path):
    store, _, _, _ = fixture(tmp_path)
    file = store.load("mat_loop")
    request = OppositionRequest("oppose_early", "Test the basis", ("dispute_one",))
    original = case_basis(file, request)
    unrelated = replace(file, source_bindings={"receipt@1": {
        "thread_id": "dispute_two", "source_id": "receipt",
        "because": "These words mention dispute_one but do not identify it."}})
    assert case_basis(unrelated, request) == original
    related = replace(unrelated, source_bindings={"receipt@1": {
        "thread_id": "dispute_one", "source_id": "receipt", "because": "Explicit binding"}})
    assert case_basis(related, request) != original


def test_a_cross_observation_must_carry_actual_premises_from_each_dispute(tmp_path):
    _, model, brain, _ = fixture(tmp_path)
    proposed = finish("oppose_matter", observations=[observation(
        "cross_exposure", premise_ids=["first"])])
    model.tool_call.side_effect = [
        _response(ToolCall("delegate", "oppose_matter", args("oppose_matter"))),
        _response(ToolCall("source", "read_law", {})), _response(proposed),
        _response(ToolCall("finish", "submit", {"answer": "Private."})),
    ]
    output = run(brain)
    assert output.budget.spend.failed_children == 1
    receipt = next(event.payload["receipt"] for event in output.record.events
                   if event.kind is StepKind.TOOL_RETURNED
                   and event.payload["receipt"]["tool"] == "oppose_matter")
    assert "opposition_work" not in receipt["receipt"]["task_result"]
