"""A new whole-file dispute needs actual source/writer receipts, never a flag."""

from dataclasses import replace

import pytest

from nm.legal_brain.brain_release import ReviewRefused
from nm.legal_brain.loop_contracts import LoopLimits, StepKind, StopReason, digest
from nm.legal_brain.tools import ToolRegistry
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from nm.work_the_file.file_mutation import assertion_identity, dispute_identity
from nm.work_the_file.matter_contracts import Thread
from nm.work_the_file.write_tools import write_tools
from tests.test_early_independent_check_uses_the_actual_open_parent import actual_case
from tests.test_reviewed_private_preview_checks_saved_words import changed_payload, replace_record
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
MESSAGE = "I report a separate disputed event. Another event also remains disputed."
TURN = "current-working-scope"
LABEL = "A new independent dispute"
QUOTE = "I report a separate disputed event."


def created_case(tmp_path, *, selected=(), bad_quote=False, uncommitted=False, second=False):
    store, brain, owner, _early, _judge, _guard = actual_case(tmp_path)
    cancelled = {"value": False}
    tools = write_tools(store)
    if uncommitted:
        wrapped = []
        for tool in tools:
            if tool.definition.name == "create_dispute":
                handler = tool.handler

                def prepare_then_cancel(args, context, actual=handler):
                    result = actual(args, context)
                    cancelled["value"] = True
                    return result

                tool = replace(tool, handler=prepare_then_cancel)
            wrapped.append(tool)
        tools = tuple(wrapped)
    brain.registry = brain.registry.extend(tools)
    assert isinstance(brain.registry, ToolRegistry)
    brain._runner._tools = brain.registry
    calls = [
        ToolCall("inspect", "inspect_tool", {"name": "create_dispute"}),
        ToolCall(
            "new",
            "create_dispute",
            {"label": LABEL, "quoted": "Never supplied." if bad_quote else QUOTE},
        ),
    ]
    if second:
        calls.append(
            ToolCall(
                "second_new",
                "create_dispute",
                {
                    "label": "Second independent dispute",
                    "quoted": "Another event also remains disputed.",
                },
            )
        )
    calls.append(ToolCall("finish", "ask_advocate", {"question": "Which record is available?"}))
    brain.model.tool_call.side_effect = [_response(call) for call in calls]
    outcome = brain.run(
        matter_id="mat_loop",
        turn_id=TURN,
        message=MESSAGE,
        selected_issue_ids=selected,
        cancelled=lambda: cancelled["value"],
        limits=LoopLimits(
            Budget(max_ms=60000, max_tokens=1000000, max_cost_usd=2, max_children=5), 20, 400
        ),
    )
    return store, owner, outcome


def parent(store):
    return next(row for row in store.load("mat_loop").loop_records if row.identity.turn_id == TURN)


def candidate(inventory, thread):
    facts = [
        row
        for row in inventory.references.values()
        if row["reference"]["kind"] == "fact" and thread in row["thread_ids"]
    ]
    return {
        "inventory_identity": inventory.identity,
        "entries": [
            {
                "id": "source_owned_candidate",
                "thread_id": thread,
                "area": "evidence_to_collect",
                "disposition": "unassessed",
                "analysis": "The supplied account remains unconfirmed.",
                "reason": "The file records an assertion, not its truth.",
                "references": [
                    inventory.references["original_instruction"]["reference"],
                    *(row["reference"] for row in facts),
                ],
                "sources": [],
                "fact_ids": [row["value"]["id"] for row in facts],
                "need_ids": [],
                "depends_on": [],
            }
        ],
    }


def test_whole_file_new_disputes_facts_work_and_needed_areas_reach_actual_inventory(tmp_path):
    store, owner, outcome = created_case(tmp_path, second=True)
    assert outcome.reason is StopReason.QUESTION
    matter = store.load("mat_loop")
    inventory = owner.build(outcome.record, matter)
    first = dispute_identity(matter.id, TURN, QUOTE, LABEL)
    second = dispute_identity(
        matter.id, TURN, "Another event also remains disputed.", "Second independent dispute"
    )
    assert {row["id"] for row in inventory.payload["threads"]} == {"thread_one", first, second}
    assert first not in outcome.record.events[0].payload["context"]["brief"]["selected_issue_ids"]
    fact_id = assertion_identity(matter.id, TURN, MESSAGE)
    value = inventory.references["fact:" + fact_id]
    assert value["text"] == MESSAGE and value["value"]["confirmed"] is None
    assert value["thread_ids"] == sorted((first, second))
    assert value["value"]["provenance"]["turn"] == TURN
    assert {row["thread_id"] for row in inventory.payload["areas"]} >= {first, second}
    assert "need:fact:" + fact_id in {row["id"] for row in inventory.payload["needs"]}
    creations = [
        row
        for row in inventory.references.values()
        if row["reference"]["kind"] == "work" and row["value"]["call"]["name"] == "create_dispute"
    ]
    assert {tuple(row["thread_ids"]) for row in creations} == {(first,), (second,)}
    _inventory, annotations, _packages = owner.bind(
        outcome.record, matter, candidate(inventory, first)
    )
    assert len(annotations) == 1 and annotations[0].thread_id == first
    assert not matter.turn_receipts


@pytest.mark.parametrize("mode", ["failed", "uncommitted", "explicit"])
def test_failed_prepared_uncommitted_and_explicit_narrow_writes_do_not_widen_working_scope(
    tmp_path,
    mode,
):
    store, owner, outcome = created_case(
        tmp_path,
        bad_quote=mode == "failed",
        uncommitted=mode == "uncommitted",
        selected=("thread_one",) if mode == "explicit" else (),
    )
    matter = store.load("mat_loop")
    assert len(matter.threads) == 1
    assert outcome.reason in {StopReason.CANCELLED, StopReason.REFUSED}
    inventory = owner.build(outcome.record, matter)
    assert inventory.payload["threads"] == [{"id": "thread_one", "label": matter.threads[0].label}]
    assert "fact:" + assertion_identity(matter.id, TURN, MESSAGE) not in inventory.references
    assert not any(
        row.kind is StepKind.TOOL_RETURNED and "mutation_identity" in row.payload
        for row in outcome.record.events
    )
    if mode == "uncommitted":
        assert any(
            row.payload.get("kind") == "write_not_committed" for row in outcome.record.events
        )


@pytest.mark.parametrize("scope", [None, "unrecognized", "explicit"])
def test_missing_or_nonwhole_sealed_scope_hash_never_authorizes_new_thread_annotation(
    tmp_path, scope
):
    store, owner, _outcome = created_case(tmp_path)
    value = digest({"requested_issue_ids": ["thread_one"]}) if scope == "explicit" else scope
    replace_record(store, TURN, lambda record: changed_payload(record, 0, scope_identity=value))
    record, matter = parent(store), store.load("mat_loop")
    inventory = owner.build(record, matter)
    assert {row["id"] for row in inventory.payload["threads"]} == {"thread_one"}
    with pytest.raises(ReviewRefused):
        owner.bind(record, matter, candidate(inventory, matter.threads[-1].id))


@pytest.mark.parametrize("field", ["fact_id", "snapshot", "mutation_identity", "selected_span"])
def test_current_thread_or_author_flags_cannot_replace_a_committed_exact_source_receipt(
    tmp_path, field
):
    store, owner, _outcome = created_case(tmp_path)

    def changed(record):
        index = next(
            number
            for number, event in enumerate(record.events)
            if event.kind is StepKind.TOOL_RETURNED
            and event.payload["receipt"]["tool"] == "create_dispute"
        )
        event = record.events[index]
        receipt = event.payload["receipt"]
        if field == "snapshot":
            receipt["receipt"][field] = "f" * 64
        elif field == "mutation_identity":
            return changed_payload(record, index, mutation_identity="f" * 64)
        else:
            receipt["data"][field] = "invented-source-identity-or-words"
        # Flags still say unassessed/asserted_only; those never prove scope.
        assert receipt["data"]["unassessed"] is True
        return changed_payload(record, index, receipt=receipt)

    replace_record(store, TURN, changed)
    with pytest.raises(ReviewRefused):
        owner.build(parent(store), store.load("mat_loop"))


def test_foreign_new_thread_and_unowned_parent_prefix_are_refused(tmp_path):
    store, owner, outcome = created_case(tmp_path)
    matter = store.load("mat_loop")
    store.commit(
        replace(
            matter,
            threads=(*matter.threads, Thread.create("Unrelated change")),
            version=matter.version + 1,
        ),
        expected_version=matter.version,
    )
    with pytest.raises(ReviewRefused):
        owner.build(outcome.record, store.load("mat_loop"))
    changed = changed_payload(
        outcome.record,
        0,
        scope_identity=digest({"requested_issue_ids": []}),
        not_an_owned_admission=True,
    )
    with pytest.raises(ReviewRefused):
        owner.build(changed, store.load("mat_loop"))
