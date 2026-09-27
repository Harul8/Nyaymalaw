"""Real LoopRunner delegation and exact sealed independent response controls."""

from dataclasses import replace

import pytest

from nm.legal_brain.brain_release import ReviewRefused
from nm.legal_brain.early_independent_review import (
    TOOL,
    EarlyIndependentReviewService,
    EarlyReviewSubject,
)
from nm.legal_brain.loop_contracts import LoopLimits, StepKind, StopReason
from nm.legal_brain.matter_support import captured_documents
from nm.legal_brain.tool_discovery import discovery_tools
from nm.legal_brain.tool_sources import findings_from_record
from nm.legal_brain.tools import DelegationPolicy, ToolRegistry
from nm.legal_brain.verifier import IndependentVerifier
from nm.legal_brain.working_record import PROPOSE_TOOL, READ_TOOL
from nm.shared.budget_contracts import Budget, Completion
from nm.shared.model_port import ProviderUnavailable, ToolCall, Usage
from tests.test_independent_claim_verifier import Judge, response
from tests.test_reviewed_private_preview_checks_saved_words import changed_payload, replace_record
from tests.test_the_loop_records_work_before_using_it import _response
from tests.test_working_record_is_source_owned_and_independently_scoped import _case, _entry

pytestmark = pytest.mark.class_a
POLICY = DelegationPolicy(1, 15000, 0.05, 10000)
LIMITS = LoopLimits(
    Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=2), 25, 400
)
MESSAGE = "Which rule was read?"


def actual_case(tmp_path, *, judge=None, extra_work=False, candidate="note_one", policy=POLICY):
    store, _old, owner, _working, _scope, _scope_judge, _old_judge, brain = _case(
        tmp_path, return_brain=True
    )
    brain.reviewer = _working.reviewer
    guard = {"current": True}
    judge = judge or Judge(answer=response())

    def bind(record, matter, ident):
        _inventory, annotations, packages = owner.candidates_for_record(record, matter)
        matching = [row for row in annotations if row.id == ident]
        if len(matching) != 1:
            raise ReviewRefused("No unique exact previously captured candidate")
        package = next(row for row in packages if row.id == matching[0].package_id)
        return EarlyReviewSubject(package, findings_from_record(record), captured_documents(record))

    service = EarlyIndependentReviewService(
        store=store,
        log=brain.log,
        verifier=IndependentVerifier(judge),
        subject_owner=bind,
        source_current=lambda _subject: guard["current"],
        session_current=lambda: True,
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
        cost_ceiling=lambda *_: 0.03,
    )
    previous = brain.registry
    brain.registry = ToolRegistry(
        tuple(
            row
            for row in previous._tools.values()
            if row.definition.name not in {"inspect_tool", "discover_tools", "read_owner_guide"}
        ),
        before=previous._before,
        after=previous._after,
        version_context=previous._versions,
    )
    brain.registry = brain.registry.extend(service.tools(policy)).extend(
        discovery_tools(lambda: brain.registry, brain.principles)
    )
    brain._runner._tools = brain.registry
    initial = iter(
        [
            ToolCall("inspect_read", "inspect_tool", {"name": READ_TOOL}),
            ToolCall("inspect_propose", "inspect_tool", {"name": PROPOSE_TOOL}),
            ToolCall("inspect_law", "inspect_tool", {"name": "read_provision"}),
            ToolCall("inspect_early", "inspect_tool", {"name": TOOL}),
            ToolCall(
                "law",
                "read_provision",
                {"act": "Recorded rule", "section": "1", "as_of": "2026-01-01"},
            ),
            ToolCall("inventory", READ_TOOL, {}),
        ]
    )
    stage = []

    def author(*_args, **_kwargs):
        call = next(initial, None)
        if call is None:
            parent = next(
                row
                for row in store.load("mat_loop").loop_records
                if row.identity.turn_id == "early-parent"
            )
            if not stage:
                stage.append("proposed")
                inventory = owner.build(parent, store.load("mat_loop"))
                call = ToolCall(
                    "candidate",
                    PROPOSE_TOOL,
                    {"inventory_identity": inventory.identity, "entries": [_entry(inventory)]},
                )
            elif stage == ["proposed"]:
                stage.append("checked")
                call = ToolCall("independent", TOOL, {"candidate_id": candidate})
            elif extra_work and stage == ["proposed", "checked"]:
                stage.append("new work")
                call = ToolCall(
                    "newlaw",
                    "read_provision",
                    {"act": "Recorded rule", "section": "1", "as_of": "2026-01-01"},
                )
            else:
                call = ToolCall(
                    "terminal", "ask_advocate", {"question": "Which document records it?"}
                )
        return _response(call)

    brain.model.tool_call.side_effect = author
    return store, brain, owner, service, judge, guard


def run(brain, limits=LIMITS):
    return brain.run(
        matter_id="mat_loop",
        turn_id="early-parent",
        message=MESSAGE,
        selected_issue_ids=("thread_one",),
        limits=limits,
    )


def receipt(outcome):
    return next(
        row
        for row in outcome.record.events
        if row.kind is StepKind.TOOL_RETURNED and row.payload.get("call_id") == "independent"
    )


def test_actual_open_loop_dispatches_a_distinct_independent_verifier(tmp_path):
    store, brain, owner, service, judge, _guard = actual_case(tmp_path)
    actual = judge.structured
    observed = []

    def dispatch(*args, **kwargs):
        parent = brain.log.read(
            next(
                row.identity
                for row in store.load("mat_loop").loop_records
                if row.identity.turn_id == "early-parent"
            )
        )
        assert not parent.terminal and parent.events[-1].kind is StepKind.TOOL_STARTED
        assert len(store.load("mat_loop").loop_records) == 2  # one prior parent, one open parent
        observed.append(parent.events[-1].fingerprint)
        assert "checked_conditional_inputs" not in args[0].user
        return actual(*args, **kwargs)

    judge.structured = dispatch
    outcome = run(brain)
    assert outcome.reason is StopReason.QUESTION
    read = service.recorded(outcome.record, "independent")
    assert read.checked and not read.client_ready and len(observed) == len(judge.prompts) == 1
    event = receipt(outcome)
    assert event.payload["child_steps"] == 1 and event.payload["child_released"] is False
    assert event.payload["receipt"]["assessment"] == "not_assessed"
    assert event.payload["receipt"]["data"]["released"] is False
    assert outcome.budget.spend.children == 1
    assert outcome.budget.max_cost_usd == LIMITS.budget.max_cost_usd
    inventory, annotations, packages = owner.candidates(outcome, store.load("mat_loop"))
    assert len(annotations) == len(packages) == 1 and packages[0] == read.subject.package
    assert not store.load("mat_loop").turn_receipts and not store.transcripts_for("mat_loop")
    before = store.load("mat_loop")
    assert run(brain) == outcome and store.load("mat_loop") == before
    assert len(judge.prompts) == 1


@pytest.mark.parametrize(
    "state",
    [
        "false",
        "partial",
        "unknown_usage",
        "measured_failure",
        "same_model",
        "too_small",
        "missing_candidate",
    ],
)
def test_failure_unknown_and_refusal_remain_private_and_count_actual_child_work(tmp_path, state):
    judge = Judge(answer=response(inference=state != "false"))
    actual = judge.structured
    if state == "partial":
        judge.structured = lambda *args, **kwargs: replace(
            actual(*args, **kwargs), completion=Completion.LENGTH_LIMITED
        )
    elif state in {"unknown_usage", "measured_failure"}:

        def fail(*_args, **_kwargs):
            raise ProviderUnavailable(
                "Controlled actual provider failure",
                usage=Usage(13, 17, 0.01) if state == "measured_failure" else None,
            )

        judge.structured = fail
    store, brain, _owner, service, judge, _guard = actual_case(
        tmp_path,
        judge=judge,
        candidate="missing" if state == "missing_candidate" else "note_one",
        policy=DelegationPolicy(1, 1, 0.05, 10000) if state == "too_small" else POLICY,
    )
    if state == "same_model":
        judge.resolved_model = lambda _tier: brain.model.resolved_model(_tier)
    outcome = run(brain)
    read = service.recorded(outcome.record, "independent")
    assert not read.checked and not read.client_ready
    assert read.spend.children == read.spend.failed_children == 1
    assert outcome.budget.spend.children == outcome.budget.spend.failed_children == 1
    assert not store.load("mat_loop").turn_receipts
    if state == "unknown_usage":
        assert read.spend.cost_usd == 0.03 and read.spend.tokens > 0
    elif state == "measured_failure":
        assert read.spend.cost_usd == 0.01 and read.spend.tokens == 30
    elif state in {"same_model", "too_small", "missing_candidate"}:
        assert read.model_steps == read.spend.tokens == read.spend.cost_usd == 0


@pytest.mark.parametrize("when", ["before", "after"])
def test_actual_source_fence_refuses_stale_early_inputs_without_refunding_paid_work(tmp_path, when):
    store, brain, _owner, service, judge, guard = actual_case(tmp_path)
    actual = judge.structured
    if when == "before":
        guard["current"] = False
    else:

        def withdraw(*args, **kwargs):
            result = actual(*args, **kwargs)
            guard["current"] = False
            return result

        judge.structured = withdraw
    outcome = run(brain)
    assert (
        not receipt(outcome).payload["receipt"]["data"]["verification"]
        or not (
            receipt(outcome).payload["receipt"]["data"]["verification"]["inference"]["assessed"]
        )
    )
    assert outcome.budget.spend.children == 1
    if when == "after":
        with pytest.raises(ReviewRefused, match="stale"):
            service.recorded(outcome.record, "independent")
        assert len(judge.prompts) == 1
    else:
        assert service.recorded(outcome.record, "independent").verification is None
        assert not judge.prompts
    assert not store.load("mat_loop").turn_receipts


def test_real_new_source_work_invalidates_the_candidate_but_owned_check_itself_does_not(tmp_path):
    store, brain, owner, service, _judge, _guard = actual_case(tmp_path, extra_work=True)
    outcome = run(brain)
    with pytest.raises(ReviewRefused, match="earlier work population"):
        owner.candidates(outcome, store.load("mat_loop"))
    # The independent reader reconstructs the exact earlier prefix, not later
    # author reasoning; it is not a blanket waiver of final inventory revalidation.
    assert service.recorded(outcome.record, "independent").checked


@pytest.mark.parametrize(
    "change",
    [
        "verdict",
        "response",
        "prompt",
        "subject",
        "usage",
        "child_steps",
        "child_budget",
        "downgrade_zero",
        "reserved_boolean",
        "recursive",
        "authority",
    ],
)
def test_early_positive_requires_its_actual_exact_response(tmp_path, change):
    store, brain, _owner, service, _judge, _guard = actual_case(tmp_path)
    outcome = run(brain)
    assert service.recorded(outcome.record, "independent").checked

    def alter(saved):
        event = receipt(type("Outcome", (), {"record": saved})())
        raw = event.payload
        trace = raw["child_transcript"]
        if change == "verdict":
            trace[-1]["verification"]["reason"] = "Model-authored independent PASS"
            raw["receipt"]["data"]["verification"] = trace[-1]["verification"]
        elif change == "response":
            next(row for row in trace if row["kind"] == "model_returned")["result"]["data"][
                "inference"
            ]["assessed"] = False
        elif change == "prompt":
            next(row for row in trace if row["kind"] == "model_started")["prompt"]["user"] = "other"
        elif change == "subject":
            trace[0]["subject"]["package"]["claim"] = "Foreign unchecked claim"
        elif change == "usage":
            trace[-1]["spend"]["tokens"] += 1
        elif change == "child_steps":
            raw["child_steps"] = True
        elif change == "child_budget":
            raw["budget"]["max_cost_usd"] += 1
        elif change == "downgrade_zero":
            next(row for row in trace if row["kind"] == "model_returned")["result"][
                "downgraded_from"
            ] = 0
        elif change == "reserved_boolean":
            next(row for row in trace if row["kind"] == "model_started")["reserved_cost_usd"] = (
                False
            )
        elif change == "recursive":
            trace.insert(-1, {"kind": "tool_started", "call": "unchecked external action"})
        else:
            raw["receipt"]["effect"] = "execute"
        return changed_payload(saved, event.sequence - 1, **raw)

    replace_record(store, "early-parent", alter)
    current = next(
        row for row in store.load("mat_loop").loop_records if row.identity.turn_id == "early-parent"
    )
    with pytest.raises((ReviewRefused, ValueError)):
        service.recorded(current, "independent")


def test_paired_child_checkpoints_cannot_reset_the_actual_parent_grant(tmp_path):
    store, brain, _owner, service, _judge, _guard = actual_case(tmp_path)
    outcome = run(brain)

    def alter(saved):
        start = next(
            row
            for row in saved.events
            if row.kind is StepKind.TOOL_STARTED and row.payload["call"]["call_id"] == "independent"
        )
        first = start.payload
        first["budget"]["max_cost_usd"] += 1
        first["delegation"]["budget"]["max_cost_usd"] += 1
        end = receipt(type("Outcome", (), {"record": saved})())
        last = end.payload
        last["budget"]["max_cost_usd"] += 1
        saved = changed_payload(saved, start.sequence - 1, **first)
        return changed_payload(saved, end.sequence - 1, **last)

    replace_record(store, "early-parent", alter)
    current = next(
        row
        for row in store.load("mat_loop").loop_records
        if row.identity.turn_id == outcome.record.identity.turn_id
    )
    with pytest.raises(ReviewRefused, match="whole-task"):
        service.recorded(current, "independent")


def test_no_child_permission_or_no_remaining_grant_cannot_dispatch_a_hidden_checker(tmp_path):
    _store, brain, _owner, _service, judge, _guard = actual_case(tmp_path)
    outcome = run(brain, replace(LIMITS, budget=replace(LIMITS.budget, max_children=0)))
    assert outcome.reason is StopReason.BUDGET and not judge.prompts
    assert outcome.budget.spend.children == 0
