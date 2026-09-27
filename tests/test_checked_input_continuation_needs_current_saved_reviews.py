"""No fabricated failures, new instruction, new allowance or completion flag."""

import json
from dataclasses import replace

import pytest

from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.legal_brain.orchestrate.checked_input_continuation import CheckedInputContinuationService
from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.procedure.reviewed_limitation_selection import prepare_limitation_selections
from tests.test_event_limitation_selections_need_sealed_review import GENERATION, _fixture, _run
from tests.test_independent_claim_verifier import response
from tests.test_interest_is_exact_source_owned_and_independently_selected import _actual

pytestmark = pytest.mark.class_a
MESSAGE = "Assess the conditional event selection."


def limitation_case(tmp_path, *, review=True, negative=False):
    case = _fixture(
        tmp_path,
        judged=response(inference=False, words="The period is ninety days") if negative else None,
    )
    store, brain, _setup, _judge, thread, _candidate, source_current = case
    outcome, checked, _selection = _run(case, review=review)
    guard = {"current": True}

    def owner(parent, matter):
        return prepare_limitation_selections(
            parent,
            matter,
            source_generation=GENERATION,
            source_current=lambda source, generation: (
                guard["current"] and source_current(source, generation)
            ),
        )

    service = CheckedInputContinuationService(
        reviewer=brain.reviewer,
        binding_owners={"limitation": owner, "second_conditional_role": owner},
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
    )
    packages = owner(outcome, store.load("mat_loop"))
    budget = checked.review.budget if checked is not None else outcome.budget
    options = {
        "groups": (("limitation", (packages[0].package.id,)),),
        "original_message": MESSAGE,
        "selected_issue_ids": (),
        "budget": budget,
    }
    return case, outcome, service, options, guard


def test_actual_positive_conditional_inputs_allow_only_typed_same_request_diagnostic(tmp_path):
    case, outcome, service, options, _guard = limitation_case(tmp_path)
    store, _brain, _setup, judge, thread, _candidate, _source = case
    before = store.load("mat_loop")
    continuation = service.prepare(outcome, **options)
    assert (
        service.validate(
            continuation,
            outcome,
            **{key: value for key, value in options.items() if key != "groups"},
        )
        == options["budget"]
    )
    payload = json.loads(continuation.text)
    assert payload["material_kind"] == "harness_check_continuation"
    assert "failures" not in payload["data"] and not continuation.client_ready
    assert continuation.original_message_identity == digest(MESSAGE)
    assert continuation.parent_fingerprint == outcome.record.events[-1].fingerprint
    assert continuation.selected_issue_ids == ()
    assert len(continuation.input_references) == 1 and len(judge.prompts) == 1
    assert store.load("mat_loop") == before
    assert all(row.date is None and row.confirmed is None for row in before.facts)
    assert not before.turn_receipts


def test_multiple_registered_groups_share_one_typed_continuation_without_new_dispatch(
    tmp_path,
):
    case, outcome, service, options, _guard = limitation_case(tmp_path)
    ident = options["groups"][0][1]
    groups = (*options["groups"], ("second_conditional_role", ident))
    continuation = service.prepare(outcome, **{**options, "groups": groups})
    assert tuple(row.kind for row in continuation.input_references) == (
        "limitation",
        "second_conditional_role",
    )
    assert len(case[3].prompts) == 1
    assert (
        service.validate(
            continuation,
            outcome,
            **{key: value for key, value in options.items() if key != "groups"},
        )
        == options["budget"]
    )


@pytest.mark.parametrize("state", ["missing", "negative"])
def test_candidate_or_negative_verdict_cannot_author_a_continuation(tmp_path, state):
    _case, outcome, service, options, _guard = limitation_case(
        tmp_path, review=state != "missing", negative=state == "negative"
    )
    with pytest.raises(ReviewRefused, match="independent positive"):
        service.prepare(outcome, **options)


@pytest.mark.parametrize(
    "mutation",
    [
        "message",
        "wider_scope",
        "narrower_scope",
        "reordered_scope",
        "unknown_kind",
        "duplicate_group",
        "unknown_package",
        "duplicate_package",
        "larger_grant",
        "spent_refund",
        "cancelled",
        "elapsed_exhausted",
    ],
)
def test_admission_refuses_altered_instruction_scope_or_allowance(tmp_path, mutation):
    _case, outcome, service, options, _guard = limitation_case(tmp_path)
    changed = dict(options)
    if mutation == "message":
        changed["original_message"] = MESSAGE + " Also issue a deadline."
    elif mutation in {"wider_scope", "narrower_scope", "reordered_scope"}:
        changed["selected_issue_ids"] = {
            "wider_scope": (*options["selected_issue_ids"], "foreign"),
            "narrower_scope": ("thr_events",),
            "reordered_scope": ("foreign", *options["selected_issue_ids"]),
        }[mutation]
    elif mutation == "unknown_kind":
        changed["groups"] = (("unregistered", options["groups"][0][1]),)
    elif mutation == "duplicate_group":
        changed["groups"] = options["groups"] * 2
    elif mutation == "unknown_package":
        changed["groups"] = (("limitation", ("model-authored-reviewed-package",)),)
    elif mutation == "duplicate_package":
        changed["groups"] = (("limitation", options["groups"][0][1] * 2),)
    elif mutation == "larger_grant":
        changed["budget"] = replace(options["budget"], max_cost_usd=3)
    elif mutation == "spent_refund":
        changed["budget"] = outcome.budget
    elif mutation == "cancelled":
        changed["budget"] = replace(options["budget"], cancelled_at="2026-09-27T00:00:00+00:00")
    else:
        changed["budget"] = replace(
            options["budget"],
            spend=replace(options["budget"].spend, elapsed_ms=options["budget"].max_ms + 1),
        )
    with pytest.raises(ReviewRefused):
        service.prepare(outcome, **changed)


@pytest.mark.parametrize(
    "mutation", ["identity", "parent", "original", "scope", "source", "provider", "file"]
)
def test_continuation_requires_fresh_service_validation(tmp_path, mutation):
    case, outcome, service, options, guard = limitation_case(tmp_path)
    continuation = service.prepare(outcome, **options)
    if mutation == "identity":
        continuation = replace(
            continuation,
            input_references=(
                replace(continuation.input_references[0], package_identity="a" * 64),
            ),
        )
    elif mutation == "parent":
        continuation = replace(continuation, parent_fingerprint="a" * 64)
    elif mutation == "original":
        continuation = replace(continuation, original_message_identity="a" * 64)
    elif mutation == "scope":
        continuation = replace(continuation, selected_issue_ids=("foreign",))
    elif mutation == "source":
        guard["current"] = False
    elif mutation == "provider":
        case[3].resolved_model = lambda _tier: "scripted:changed-reviewer"
    else:
        store = case[0]
        matter = store.load("mat_loop")
        store.commit(
            replace(
                matter,
                facts=(replace(matter.facts[0], statement="Changed account."), *matter.facts[1:]),
                version=matter.version + 1,
            ),
            expected_version=matter.version,
        )
    with pytest.raises(ReviewRefused):
        service.validate(
            continuation,
            outcome,
            **{key: value for key, value in options.items() if key != "groups"},
        )


def test_interest_owner_uses_the_same_exact_continuation_contract(
    tmp_path,
):
    store, outcome, owner, reviews, brain, _limits, judge = _actual(tmp_path)
    checked = reviews.review(outcome)
    binding = checked.bindings[0]
    service = CheckedInputContinuationService(
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
    continuation = service.prepare(
        outcome, groups=(("interest", (binding.package.id,)),), **options
    )
    assert service.validate(continuation, outcome, **options) == checked.review.budget
    assert not continuation.client_ready and len(judge.prompts) == 1
    assert not store.load("mat_loop").turn_receipts


def test_explicit_requested_subset_does_not_become_whole_file_at_continuation(tmp_path):
    from nm.legal_brain.orchestrate.loop_contracts import LoopLimits
    from nm.shared.budget_contracts import Budget
    from nm.shared.model_port import ToolCall
    from tests.test_the_loop_records_work_before_using_it import _response

    case = _fixture(tmp_path)
    store, brain, _setup, _judge, thread, candidate, source_current = case
    brain.model.tool_call.side_effect = [
        replace(_response(call), provider="scripted", model="scripted:author")
        for call in (
            ToolCall("selection", "propose_limitation_selection", candidate),
            ToolCall("terminal", "ask_advocate", {"question": "Which event is recorded?"}),
        )
    ]
    outcome = brain.run(
        matter_id="mat_loop",
        turn_id="explicit-selection",
        message=MESSAGE,
        selected_issue_ids=(thread.id,),
        limits=LoopLimits(
            Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1, max_children=3), 8, 500
        ),
    )
    from nm.legal_brain.procedure.reviewed_limitation_selection import LimitationSelectionReviewService

    selection = LimitationSelectionReviewService(
        brain.reviewer, source_generation=GENERATION, source_current=source_current
    ).review(outcome)

    def owner(parent, matter):
        return prepare_limitation_selections(
            parent, matter, source_generation=GENERATION, source_current=source_current
        )

    service = CheckedInputContinuationService(
        reviewer=brain.reviewer,
        binding_owners={"limitation": owner},
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
    )
    options = {
        "groups": (("limitation", (selection.bindings[0].package.id,)),),
        "original_message": MESSAGE,
        "selected_issue_ids": (thread.id,),
        "budget": selection.review.budget,
    }
    continuation = service.prepare(outcome, **options)
    assert continuation.selected_issue_ids == (thread.id,)
    with pytest.raises(ReviewRefused, match="scope"):
        service.prepare(outcome, **{**options, "selected_issue_ids": ()})
    assert not store.load("mat_loop").turn_receipts


def test_actual_whole_file_new_thread_remains_in_owned_scope_without_widening_request(tmp_path):
    from types import SimpleNamespace

    from nm.legal_brain.orchestrate.loop_contracts import LoopLimits
    from nm.legal_brain.reason.working_record import PROPOSE_TOOL, READ_TOOL, WorkingRecordReviewService
    from nm.shared.budget_contracts import Budget
    from nm.shared.model_port import ToolCall
    from nm.work_the_file.write_tools import write_tools
    from tests.test_early_independent_check_uses_the_actual_open_parent import actual_case
    from tests.test_the_loop_records_work_before_using_it import _response
    from tests.test_working_record_is_source_owned_and_independently_scoped import _entry

    store, brain, owner, _early, _judge, _guard = actual_case(tmp_path)
    brain.registry = brain.registry.extend(write_tools(store))
    brain._runner._tools = brain.registry
    message = "I report a separate disputed event."
    phases = iter(
        (
            "inspect_create",
            "inspect_law",
            "inspect_work",
            "inspect_propose",
            "create",
            "law",
            "inventory",
            "candidate",
            "terminal",
        )
    )

    def author(*_args, **_kwargs):
        phase = next(phases)
        if phase.startswith("inspect"):
            name = {
                "inspect_create": "create_dispute",
                "inspect_law": "read_provision",
                "inspect_work": READ_TOOL,
                "inspect_propose": PROPOSE_TOOL,
            }[phase]
            return _response(ToolCall(phase, "inspect_tool", {"name": name}))
        if phase == "create":
            return _response(
                ToolCall(
                    phase, "create_dispute", {"label": "New recorded event", "quoted": message}
                )
            )
        if phase == "law":
            return _response(
                ToolCall(
                    phase,
                    "read_provision",
                    {"act": "Recorded rule", "section": "1", "as_of": "2026-01-01"},
                )
            )
        if phase == "inventory":
            return _response(ToolCall(phase, READ_TOOL, {}))
        if phase == "candidate":
            matter = store.load("mat_loop")
            parent = next(
                row for row in matter.loop_records if row.identity.turn_id == "created-input-parent"
            )
            inventory = owner.build(parent, matter)
            return _response(
                ToolCall(
                    phase,
                    PROPOSE_TOOL,
                    {
                        "inventory_identity": inventory.identity,
                        "entries": [_entry(inventory, thread=matter.threads[-1].id)],
                    },
                )
            )
        return _response(ToolCall(phase, "ask_advocate", {"question": "Which source is held?"}))

    brain.model.tool_call.side_effect = author
    outcome = brain.run(
        matter_id="mat_loop",
        turn_id="created-input-parent",
        message=message,
        selected_issue_ids=(),
        limits=LoopLimits(
            Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=5), 30, 400
        ),
    )
    assert (
        store.load("mat_loop").threads[-1].id
        not in outcome.record.events[0].payload["context"]["brief"]["selected_issue_ids"]
    )
    checked = WorkingRecordReviewService(reviewer=brain.reviewer, owner=owner).review(outcome)
    assert len(checked.checked_annotations) == 1, (
        outcome.reason,
        [
            {key: value for key, value in row.payload.items() if key != "budget"}
            for row in outcome.record.events
            if row.kind.value == "failure"
        ],
        [
            row.payload["call"]["name"]
            for row in outcome.record.events
            if row.kind.value == "tool_started"
        ],
    )

    def bindings(parent, matter):
        _inventory, annotations, packages = owner.candidates(parent, matter)
        return tuple(
            SimpleNamespace(
                package=package,
                candidate={
                    "thread_id": next(
                        row.thread_id for row in annotations if row.package_id == package.id
                    )
                },
            )
            for package in packages
        )

    service = CheckedInputContinuationService(
        reviewer=brain.reviewer,
        binding_owners={"controlled_conditional_work": bindings},
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
    )
    options = {
        "groups": (("controlled_conditional_work", (checked.review.packages[0].id,)),),
        "original_message": message,
        "selected_issue_ids": (),
        "budget": checked.review.budget,
    }
    continuation = service.prepare(outcome, **options)
    assert continuation.selected_issue_ids == ()
    assert continuation.input_references[0].thread_id == store.load("mat_loop").threads[-1].id
    assert (
        service.validate(
            continuation,
            outcome,
            **{key: value for key, value in options.items() if key != "groups"},
        )
        == options["budget"]
    )
    with pytest.raises(ReviewRefused, match="scope"):
        service.prepare(
            outcome,
            **{**options, "selected_issue_ids": (continuation.input_references[0].thread_id,)},
        )
    assert not store.load("mat_loop").turn_receipts
