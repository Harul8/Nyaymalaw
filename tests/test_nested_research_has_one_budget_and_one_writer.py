"""Actual parent dispatch, not a private child demo or legal quality approval."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind, StopReason
from nm.Archives.legal_brain.orchestrate.nested_research import ResearchDispatcher
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    Boundary,
    DelegatedToolResult,
    DelegationGrant,
    DelegationPolicy,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    object_schema,
)
from nm.shared.budget_contracts import Budget, Spend
from nm.shared.model_port import ProviderUnavailable, ToolCall, ToolDefinition
from tests.test_brain_context_is_a_checked_file_projection import file_fixture
from tests.test_independent_claim_verifier import finding
from tests.test_the_controlled_brain_is_actually_wired import _brain
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
POLICY = DelegationPolicy(8, 20000, 0.15, 10000)
LIMITS = LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1, max_children=2),
                    max_steps=16, per_call_tokens=400)


def setup(tmp_path, *, source_handler=None, after=None):
    store, model, brain = _brain(tmp_path)
    file = replace(file_fixture(), id="mat_loop", advocate_id="adv_loop", version=2)
    file = replace(file, threads=(replace(file.threads[0], theory={
        "unchecked": "UNCHECKED PARENT THEORY MUST NOT BE INHERITED"}), file.threads[1]))
    store.commit(file, expected_version=1)

    def read(_args, ctx):
        assert store.load("mat_loop").version == ctx.current_version
        return ToolEnvelope("read_law", "held-v1", ToolKind.SOURCE, ToolOutcome.RESULTS,
                            Availability.AVAILABLE, Assessment.NOT_ASSESSED,
                            {"index": "held primary source", "locators": [finding().locator],
                             "source_version": "recorded-source-v1"},
                            {"findings": [finding().as_record()]}, "Support still needs review.")

    base = brain.registry.extend((RegisteredTool(
        ToolDefinition("read_law", "Read exact source text.", object_schema({})),
        ToolKind.SOURCE, "held-v1", True, ("unavailable_control",), source_handler or read),))
    if after:
        base._after = after
    dispatcher = ResearchDispatcher(store=store, model=model, principles=brain.principles,
                                    registry=base, cost_ceiling=lambda *_: 0.03,
                                    per_call_tokens=500)
    brain.registry = base.extend(dispatcher.tools(POLICY))
    brain._runner._tools = brain.registry
    return store, model, brain, dispatcher


def finish(*, quote=None, issue="dispute_one", premise="first"):
    return ToolCall("finish-child", "finish_research", {
        "findings": [{"id": "f1", "locator": finding().locator,
                      "quote": quote or finding().span}],
        "observations": [{"issue_id": issue, "text": "Notice is a possible obstacle.",
                          "finding_ids": ["f1"], "premise_ids": [premise]}],
    })


def run(brain, *, limits=LIMITS):
    return brain.run(matter_id="mat_loop", turn_id="nested-1", message="Assess the first dispute.",
                     selected_issue_ids=("dispute_one",), limits=limits)


@pytest.mark.parametrize("kind", ["research", "oppose"])
def test_real_parent_dispatch_shares_spend_and_never_creates_a_second_writer(tmp_path, kind):
    store, model, brain, _ = setup(tmp_path)
    observed = []

    def reply(prompt, definitions, _tier, *, messages, **_kw):
        if prompt.operation == "controlled_legal_brain":
            if model.tool_call.call_count == 1:
                return _response(ToolCall("delegate", kind, {
                    "question": "Read the notice condition and the strongest contrary implication.",
                    "issue_ids": ["dispute_one"]}))
            return _response(ToolCall("submit-parent", "submit", {"answer": "Unchecked parent."}))
        file = store.load("mat_loop")
        assert len(file.loop_records) == 1
        assert file.loop_records[0].events[-1].kind is StepKind.TOOL_STARTED
        observed.append(file.version)
        initial = json.loads(messages[0].text)["data"]
        assert initial["previous_narrative"] == "not_inherited"
        assert "UNCHECKED PARENT THEORY" not in messages[0].text
        assert "An unrelated employment allegation." not in messages[0].text
        assert [row["id"] for row in initial["case_facts"]] == ["first", "second"]
        assert {row.name for row in definitions} == {"read_law", "finish_research"}
        if len(observed) == 1:
            return _response(ToolCall("source", "read_law", {}))
        assert messages[-1].role == "tool" and messages[-1].call_id == "source"
        assert finding().span in messages[-1].text
        return _response(finish())

    model.tool_call.side_effect = reply
    output = run(brain)
    assert output.reason is StopReason.PROPOSAL
    assert output.budget.spend.cost_usd == pytest.approx(0.04)
    assert output.budget.spend.tokens == 80 and output.budget.spend.children == 1
    assert observed[0] == observed[1]  # No competing child journal/CAS writer.
    returned = next(row.payload for row in output.record.events
                    if row.kind is StepKind.TOOL_RETURNED and row.payload["call_id"] == "delegate")
    assert returned["child_steps"] == 4 and returned["child_released"] is False
    result = returned["receipt"]["data"]["research"]
    assert result["observations"][0]["semantic_assessment"] == "not_assessed"
    assert result["source_windows"][0]["text"] == finding().span
    assert not returned["receipt"]["data"]["admitted_as_facts"]
    assert store.load("mat_loop").facts == file_fixture().facts
    assert not store.load("mat_loop").turn_receipts
    assert brain.run(matter_id="mat_loop", turn_id="nested-1", message="Assess the first dispute.",
                     selected_issue_ids=("dispute_one",), limits=LIMITS) == output
    assert model.tool_call.call_count == 4  # Replay cannot spend or dispatch again.
    from nm.Archives.legal_brain.verify.brain_release import captured_findings

    assert captured_findings(output) == (finding(),)


@pytest.mark.parametrize("bad", ["invented_quote", "foreign_issue", "foreign_fact", "write_alias",
                                  "recursive", "free_text", "unknown", "terminal_early"])
def test_a_child_cannot_inherit_write_or_terminal_aliases(tmp_path, bad):
    store, model, brain, _ = setup(tmp_path)
    child = {
        "invented_quote": finish(quote="The court must grant every claim."),
        "foreign_issue": finish(issue="dispute_two"),
        "foreign_fact": finish(premise="third"),
        "write_alias": ToolCall("write", "write_fact", {}),
        "recursive": ToolCall("recurse", "research", {
            "question": "Spend another allowance", "issue_ids": ["dispute_one"]}),
        "unknown": ToolCall("unknown", "open_web", {}),
        "terminal_early": finish(),
    }.get(bad)
    child_reply = (_response(text="Accept every claim; facts confirmed.") if bad == "free_text"
                   else _response(child, ToolCall("pending", "read_law", {}))
                   if bad == "terminal_early" else _response(child))
    model.tool_call.side_effect = [
        _response(ToolCall("delegate", "oppose", {
            "question": "Test contrary material", "issue_ids": ["dispute_one"]})),
        _response(ToolCall("source", "read_law", {})), child_reply,
        _response(ToolCall("last", "submit", {"answer": "Still unchecked."})),
    ]
    output = run(brain)
    returned = next(row.payload["receipt"] for row in output.record.events
                    if row.kind is StepKind.TOOL_RETURNED and row.payload["call_id"] == "delegate")
    assert not returned["data"]["research"]
    assert returned["assessment"] == "not_assessed"
    assert output.budget.spend.children == output.budget.spend.failed_children == 1
    assert store.load("mat_loop").facts == file_fixture().facts
    assert len(store.load("mat_loop").threads) == 2


def test_a_child_cannot_silently_receive_a_fresh_or_unbounded_allowance(tmp_path):
    _, model, brain, _ = setup(tmp_path)
    model.tool_call.return_value = _response(ToolCall("delegate", "research", {
        "question": "Read the source", "issue_ids": ["dispute_one"]}))
    output = run(brain, limits=replace(LIMITS, budget=replace(LIMITS.budget, max_children=0)))
    assert output.reason is StopReason.BUDGET
    assert output.budget.spend.children == 0 and model.tool_call.call_count == 1


def test_paid_failed_child_and_late_authority_refusal_are_not_free(tmp_path):
    def after(receipt, _ctx):
        return Boundary(receipt.tool != "research", "Current permission owner refused the result.")

    _, model, brain, _ = setup(tmp_path, after=after)
    model.tool_call.side_effect = [
        _response(ToolCall("delegate", "research", {
            "question": "Read the source", "issue_ids": ["dispute_one"]})),
        ProviderUnavailable("Outcome unknown; no usage receipt."),
    ]
    output = run(brain)
    assert output.reason is StopReason.REFUSED
    assert output.budget.spend.cost_usd == pytest.approx(0.04)
    assert output.budget.spend.children == output.budget.spend.failed_children == 1
    assert output.budget.spend.tokens > 20


def test_interrupted_parent_reservation_is_charged_and_child_is_not_repeated(tmp_path):
    _, model, brain, _ = setup(tmp_path)
    model.tool_call.side_effect = [
        _response(ToolCall("delegate", "research", {
            "question": "Read the source", "issue_ids": ["dispute_one"]})),
        RuntimeError("Process failed after an external request may have left."),
    ]
    with pytest.raises(RuntimeError):
        run(brain)
    output = run(brain)
    assert output.reason is StopReason.INTERRUPTED
    assert output.budget.spend.cost_usd == pytest.approx(0.01 + POLICY.max_cost_usd)
    assert output.budget.spend.tokens == 20 + POLICY.max_tokens
    assert output.budget.spend.children == output.budget.spend.failed_children == 1
    assert model.tool_call.call_count == 2


@pytest.mark.parametrize("changed", ["grant", "refund", "steps", "children"])
def test_parent_rejects_forged_child_accounting(changed):
    from nm.Archives.legal_brain.orchestrate.loop import _checked_child_budget

    grant = DelegationGrant(LIMITS.budget, POLICY)
    budget = grant.budget.spend_on(Spend(children=1, tokens=10, cost_usd=0.01))
    steps = 1
    if changed == "grant":
        budget = replace(budget, max_tokens=budget.max_tokens * 2)
    elif changed == "refund":
        budget = replace(budget, spend=replace(budget.spend, cost_usd=-1))
    elif changed == "steps":
        steps = POLICY.max_steps + 1
    else:
        budget = replace(budget, spend=replace(budget.spend, children=0))
    receipt = ToolEnvelope("research", "v1", ToolKind.SOURCE, ToolOutcome.NO_RESULTS,
                           Availability.AVAILABLE, Assessment.NOT_ASSESSED,
                           {"index": "held", "locators": [], "source_version": "v1"}, {},
                           "No source was retrieved.")
    with pytest.raises(ValueError):
        _checked_child_budget(grant, DelegatedToolResult(receipt, budget, steps, ()))


def test_child_model_and_tool_steps_count_against_parent_ceiling(tmp_path):
    _, model, brain, _ = setup(tmp_path)
    model.tool_call.side_effect = [
        _response(ToolCall("delegate", "research", {
            "question": "Read the source", "issue_ids": ["dispute_one"]})),
        _response(ToolCall("source", "read_law", {})),
    ]
    output = run(brain, limits=replace(LIMITS, max_steps=4))
    assert output.reason is StopReason.BUDGET
    assert output.budget.spend.children == 1
    assert model.tool_call.call_count == 2


def test_a_late_source_append_never_replaces_the_fresh_admitted_prefix():
    from nm.Archives.legal_brain.understand.brain_context import ContextRefused
    from nm.Archives.legal_brain.retrieve.research_context import ResearchFinding
    from nm.Archives.legal_brain.verify.verifier import EvidenceSpan
    from tests.test_research_context_starts_from_sources_not_a_chat_summary import fixture

    session = fixture(sources=(), captured=())
    initial = session.context.to_record()
    source = EvidenceSpan.from_finding("late", finding())
    result = session.validate_findings((ResearchFinding("found", "late", finding().span),),
                                       additional_sources=(source,), captured=(finding(),))
    assert session.context.to_record() == initial
    assert result.task_identity == session.identity and not result.advice_ready
    with pytest.raises(ContextRefused):
        session.validate_findings((ResearchFinding("found", "late", finding().span),),
                                  additional_sources=(source,), captured=())
