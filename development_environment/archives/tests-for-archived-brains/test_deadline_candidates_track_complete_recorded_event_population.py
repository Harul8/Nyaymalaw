"""Recorded event populations invalidate private clocks, not establish legal dates."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from nm.work_the_file import dependency
from nm.work_the_file.deadline_proposals import (
    CALENDAR,
    DEADLINE,
    VERSION,
    deadline_proposal_currency,
)
from nm.work_the_file.deadlines import DeadlineStatus, from_stored
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.file_mutation_contracts import neutral
from nm.work_the_file.matter_contracts import Thread
from tests.test_deadline_calendar_proposals_remain_source_owned_and_conditional import (
    authenticated_case,
    case_of,
    receipt,
)

pytestmark = pytest.mark.class_a


@pytest.fixture(scope="module")
def proposal_case(tmp_path_factory):
    return case_of(tmp_path_factory.mktemp("event-population"))


@pytest.fixture(scope="module")
def produced(proposal_case):
    case, _, outcome, _ = proposal_case
    return case[0].load("mat_loop"), outcome


def changed_population(saved, control):
    thread = saved.threads[0]
    rows = tuple(EventObservation.restore(raw) for raw in thread.event_observations)
    first = rows[0]
    if control == "reference":
        changed = replace(first, reference=first.reference - timedelta(days=1))
    elif control == "resolved_date":
        changed = replace(first, on=first.on + timedelta(days=1))
    elif control == "expression":
        changed = replace(first, date_expression="", on=None)
    elif control == "quote":
        changed = replace(first, event_quote=first.account)
    elif control == "account":
        changed = replace(first, account=first.account + " A corrected attributed reading.")
    elif control == "source_version":
        changed = replace(first, source_version=first.source_version + 1)
    elif control == "source_id":
        changed = replace(first, source_fact=rows[1].source_fact)
    else:
        changed = first
    readings = (changed, *rows[1:])
    chronology = thread.chronology
    if control == "remove":
        readings = rows[1:]
    elif control == "remove_all":
        readings = ()
    elif control == "add":
        readings = (*rows, replace(first, event_quote=first.account, date_expression="", on=None))
    elif control == "reorder_readings":
        readings = tuple(reversed(rows))
    elif control == "scope_remove":
        chronology = thread.chronology[1:]
    elif control == "scope_add":
        chronology = (*thread.chronology, "additional_recorded_membership")
    elif control == "scope_reorder":
        chronology = tuple(reversed(thread.chronology))
    return saved.with_thread(replace(thread, event_observations=readings, chronology=chronology))


def assert_exact_invalidation(saved, outcome, changed):
    before = dependency.Ledger.from_stored(saved.dependencies)
    independent = dependency.Node(
        "independent",
        "An independent conditional value",
        (dependency.Rest(dependency.InputKind.UNKNOWN, "independent_owner_gap"),),
    )
    before = dependency.record(before, independent)
    ledger, affected, moved = dependency.sync_inputs(
        before,
        changed,
        reason="The complete recorded event population changed.",
        by=saved.advocate_id,
    )
    names = {receipt(outcome, operation)["data"]["node_name"] for operation in (DEADLINE, CALENDAR)}
    assert names <= set(affected)
    assert "independent" not in affected and ledger.node("independent") == independent
    assert any(rest.kind is dependency.InputKind.EVENT_POPULATION for rest in moved)
    assert ledger.history[: len(before.history)] == before.history
    for name in names:
        assert ledger.node(name).value == before.node(name).value
        revision = ledger.revisions_of(name)[-1]
        assert (
            revision.was == before.node(name).value
            and revision.was_on == before.node(name).rests_on
        )
        assert "recorded event" in revision.reason and revision.now == ""
    row = from_stored(saved.threads[0].deadlines[-1], thread=saved.threads[0].id)
    assert deadline_proposal_currency(ledger, row)[0] == "stale"
    assert (
        row.on is None
        and row.status(EventObservation.restore(saved.threads[0].event_observations[0]).reference)
        is DeadlineStatus.NOT_COMPUTED
    )
    stable, later_affected, later_moved = dependency.sync_inputs(ledger, changed)
    assert stable == ledger and later_affected == later_moved == ()
    return ledger


def test_same_fact_date_reference_change_invalidates_both_exact_candidates(produced):
    saved, outcome = produced
    thread = saved.threads[0]
    original = EventObservation.restore(thread.event_observations[0])
    changed = saved.with_thread(
        replace(
            thread,
            event_observations=(
                replace(original, reference=original.reference - timedelta(days=1)),
                *thread.event_observations[1:],
            ),
        )
    )
    assert changed.facts == saved.facts
    assert_exact_invalidation(saved, outcome, changed)


@pytest.mark.parametrize(
    "control",
    [
        "resolved_date",
        "expression",
        "quote",
        "account",
        "source_version",
        "source_id",
        "remove",
        "remove_all",
        "add",
        "reorder_readings",
        "scope_remove",
        "scope_add",
        "scope_reorder",
    ],
)
def test_every_material_recorded_event_or_membership_change_reaches_the_exact_closure(
    produced, control
):
    saved, outcome = produced
    changed = changed_population(saved, control)
    assert changed.facts == saved.facts
    assert_exact_invalidation(saved, outcome, changed)


@pytest.mark.parametrize(
    "control",
    [
        "missing_field",
        "extra_field",
        "wrong_date_type",
        "duplicate_observation",
        "non_population",
        "duplicate_membership",
    ],
)
def test_unreadable_population_is_wholly_unavailable_not_a_partial_clean_subset(produced, control):
    saved, outcome = produced
    thread = saved.threads[0]
    readings = neutral([asdict(EventObservation.restore(row)) for row in thread.event_observations])
    chronology = thread.chronology
    if control == "missing_field":
        readings[0].pop("reference")
    elif control == "extra_field":
        readings[0]["confirmed"] = True
    elif control == "wrong_date_type":
        readings[0]["on"] = True
    elif control == "duplicate_observation":
        readings.append(deepcopy(readings[0]))
    elif control == "non_population":
        readings = {"looks_complete": True}
    else:
        chronology = (*chronology, chronology[0])
    changed = saved.with_thread(replace(thread, event_observations=readings, chronology=chronology))
    ledger = assert_exact_invalidation(saved, outcome, changed)
    tracked = ledger.input_of(
        dependency.InputKind.EVENT_POPULATION, dependency.event_population_id(thread.id)
    )
    assert tracked.withdrawn
    assert (
        tracked.digest
        != dependency.Ledger.from_stored(saved.dependencies)
        .input_of(tracked.kind, tracked.id)
        .digest
    )


def test_empty_population_is_recorded_and_later_addition_is_a_move_not_first_observation(produced):
    saved, _ = produced
    empty = saved.with_thread(replace(saved.threads[0], event_observations=(), chronology=()))
    ledger, _, _ = dependency.sync_inputs(dependency.Ledger(), empty)
    ident = dependency.event_population_id(empty.threads[0].id)
    tracked = ledger.input_of(dependency.InputKind.EVENT_POPULATION, ident)
    assert tracked is not None and not tracked.withdrawn
    node = dependency.Node(
        "empty_inventory", "No recorded observations", (dependency.Rest(tracked.kind, ident),)
    )
    assert node.currency is dependency.Currency.NOT_ESTABLISHED
    ledger = dependency.record(ledger, node)
    assert ledger.node(node.name).currency is dependency.Currency.NOT_ESTABLISHED
    changed, affected, moved = dependency.sync_inputs(ledger, saved)
    assert affected == (node.name,) and moved and changed.input_of(tracked.kind, ident).version == 2


def test_event_population_decoder_cannot_accept_a_serialized_current_grant(produced):
    saved, _ = produced
    ledger = dependency.Ledger.from_stored(saved.dependencies)
    ident = dependency.event_population_id(saved.threads[0].id)
    node = dependency.Node(
        "recorded_events_only",
        "A conditional computation",
        (dependency.Rest(dependency.InputKind.EVENT_POPULATION, ident, 1),),
    )
    raw = replace(ledger, nodes=(node,)).as_dict()
    raw["nodes"][0]["currency"] = "current"
    raw["nodes"][0]["usable"] = True
    restored = dependency.Ledger.from_stored(raw)
    assert restored.node(node.name).currency is dependency.Currency.NOT_ESTABLISHED
    assert not dependency.presentable(restored, node.name)[0]


def test_duplicate_dispute_identity_is_unavailable_not_last_member_wins(produced):
    saved, outcome = produced
    changed = replace(
        saved, threads=(*saved.threads, replace(saved.threads[0], event_observations=()))
    )
    ledger = assert_exact_invalidation(saved, outcome, changed)
    assert ledger.input_of(
        dependency.InputKind.EVENT_POPULATION, dependency.event_population_id(saved.threads[0].id)
    ).withdrawn


def test_removed_dispute_withdraws_exact_population_and_preserves_candidate_history(produced):
    saved, outcome = produced
    ledger = assert_exact_invalidation(saved, outcome, replace(saved, threads=()))
    tracked = ledger.input_of(
        dependency.InputKind.EVENT_POPULATION, dependency.event_population_id(saved.threads[0].id)
    )
    assert tracked.withdrawn


@pytest.mark.parametrize("control", ["other_dispute", "label", "title", "fact_outside_scope"])
def test_unrelated_changes_do_not_rewrite_this_population_or_its_candidates(produced, control):
    saved, outcome = produced
    changed = saved
    if control == "other_dispute":
        changed = replace(
            saved, threads=(*saved.threads, Thread("separate", "Independent dispute"))
        )
    elif control == "label":
        changed = saved.with_thread(replace(saved.threads[0], label="Reworded presentation label"))
    elif control == "title":
        changed = replace(saved, title="Reworded matter title")
    else:
        changed = replace(
            saved,
            facts=(
                *saved.facts,
                replace(
                    saved.facts[0],
                    id="outside",
                    statement="Unrelated attributed account.",
                    exact_words=None,
                ),
            ),
        )
    before = dependency.Ledger.from_stored(saved.dependencies)
    ledger, affected, moved = dependency.sync_inputs(before, changed)
    names = {receipt(outcome, operation)["data"]["node_name"] for operation in (DEADLINE, CALENDAR)}
    assert not names.intersection(affected) and not moved
    assert ledger.history == before.history
    assert all(ledger.node(name) == before.node(name) for name in names)


@pytest.mark.parametrize("control", ["missing_edge", "missing_tracked", "old_version"])
def test_legacy_or_missing_exact_proof_cannot_borrow_a_current_label(produced, control):
    saved, outcome = produced
    ledger = dependency.Ledger.from_stored(saved.dependencies)
    name = receipt(outcome, DEADLINE)["data"]["node_name"]
    node = ledger.node(name)
    if control == "missing_edge":
        node = replace(
            node,
            rests_on=tuple(
                edge
                for edge in node.rests_on
                if edge.kind is not dependency.InputKind.EVENT_POPULATION
            ),
        )
    elif control == "missing_tracked":
        ledger = replace(
            ledger,
            tracked=tuple(
                row
                for row in ledger.tracked
                if row.kind is not dependency.InputKind.EVENT_POPULATION
            ),
        )
    else:
        data = json.loads(node.value)
        data["version"] = VERSION.replace("v2", "v1")
        node = replace(node, value=json.dumps(data))
    ledger = replace(ledger, nodes=tuple(node if row.name == name else row for row in ledger.nodes))
    row = from_stored(saved.threads[0].deadlines[-1], thread=saved.threads[0].id)
    assert deadline_proposal_currency(ledger, row)[0] == "not_established"
    assert row.on is None


@pytest.mark.parametrize(
    "control", ["current", "changed_population", "missing_edge", "missing_tracked"]
)
def test_prior_calendar_receipt_requires_current_exact_native_population_proof(
    proposal_case, produced, control
):
    from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
    from nm.Archives.legal_brain.orchestrate.tools import ToolRefused
    from nm.Archives.legal_brain.reason.working_record import WorkingRecordOwner
    from nm.work_the_file.deadline_proposals import _prior_calendar

    case, _, _, state = proposal_case
    saved, outcome = produced
    changed = changed_population(saved, "reference") if control == "changed_population" else saved
    owner = WorkingRecordOwner(
        source_current=lambda source, generation: state["source"] and case[6](source, generation)
    )
    inventory = owner.build(outcome.record, saved)
    if control == "changed_population":
        with pytest.raises(ReviewRefused):
            owner.build(outcome.record, changed)
    calendar = next(
        row
        for row in inventory.references.values()
        if row["reference"]["kind"] == "work"
        and row["value"].get("call", {}).get("name") == CALENDAR
    )
    ledger, _, _ = dependency.sync_inputs(
        dependency.Ledger.from_stored(saved.dependencies), changed
    )
    name = receipt(outcome, CALENDAR)["data"]["node_name"]
    if control == "missing_edge":
        ledger = replace(
            ledger,
            nodes=tuple(
                replace(
                    node,
                    rests_on=tuple(
                        edge
                        for edge in node.rests_on
                        if edge.kind is not dependency.InputKind.EVENT_POPULATION
                    ),
                )
                if node.name == name
                else node
                for node in ledger.nodes
            ),
        )
    elif control == "missing_tracked":
        ledger = replace(
            ledger,
            tracked=tuple(
                row
                for row in ledger.tracked
                if row.kind is not dependency.InputKind.EVENT_POPULATION
            ),
        )

    def bind():
        return _prior_calendar(
            inventory,
            calendar["reference"],
            ledger,
            {},
            thread_id=saved.threads[0].id,
            source_generation=state["generation"],
        )

    if control == "current":
        result = bind()
        assert (
            result["adjustments_applied"] is False
            and result["candidate"]["calendar_complete"] is False
        )
    else:
        with pytest.raises(ToolRefused):
            bind()


def test_actual_authenticated_views_reopen_current_native_population_without_writing_or_model_calls(
    client,
):
    app, matter, model, _, _ = authenticated_case(client)
    served = client.post(
        f"/api/matters/{matter.id}/brain/preview",
        json={
            "version": matter.version,
            "turn_id": "proposal",
            "message": "Compare actual supplied events and source-backed conditional clocks.",
        },
    )
    assert served.status_code == 200, served.text
    saved = app.store.load(matter.id)
    changed = changed_population(saved, "reference")
    changed = app.store.commit(
        replace(changed, version=saved.version + 1), expected_version=saved.version
    )
    assert changed.dependencies == saved.dependencies
    before = neutral(asdict(changed))
    calls = model.tool_call.call_count
    board = client.get(f"/api/matters/{matter.id}")
    cover = client.get(f"/api/matters/{matter.id}/cover")
    listing = client.get("/api/matters")
    currentness = client.get(f"/api/matters/{matter.id}/dependencies")
    casefile = client.get(f"/api/matters/{matter.id}/casefile")
    assert all(
        result.status_code == 200 for result in (board, cover, listing, currentness, casefile)
    )
    listed = next(row for row in listing.json()["matters"] if row["matter_id"] == matter.id)
    for view in (board.json()["threads"][0], cover.json()["case_deadlines"], listed):
        assert view["next_deadline"] is None and view["stale_deadlines"] == 1
        assert view["next_deadline_status"] == "stale" and view["uncomputed_deadlines"] == []
    entry = cover.json()["case_deadlines"]["deadline_entries"][0]
    assert entry["currency"] == "stale" and entry["on"] is None
    assert entry["status"] == DeadlineStatus.NOT_COMPUTED.value and entry["conditional_on"]
    for view in (cover.json()["currency"], currentness.json()):
        assert view["state"] == "stale" and len(view["stale"]) == 2
        assert all(row["currency"] == "stale" for row in view["nodes"])
        assert any(
            edge["kind"] == dependency.InputKind.EVENT_POPULATION.value
            for edge in view["history"][-1]["moved"]
        )
    assert model.tool_call.call_count == calls
    assert neutral(asdict(app.store.load(matter.id))) == before


def test_actual_grounded_file_registry_writer_uses_same_native_population_closure(produced):
    from nm.Archives.legal_brain.reason.grounded_file_tools import grounded_file_tools
    from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopIdentity, LoopMode, digest
    from nm.Archives.legal_brain.orchestrate.tools import Boundary, PreparedToolResult, ToolContext, ToolRegistry
    from nm.shared.model_port import ToolCall

    saved, outcome = produced
    thread = saved.threads[0]
    original = EventObservation.restore(thread.event_observations[1])
    fact = saved.fact(original.source_fact)
    identity = LoopIdentity(
        saved.id,
        saved.advocate_id,
        "reading",
        digest(fact.statement),
        digest("principles"),
        digest("tools"),
        saved.version,
        LoopMode.SYNTHETIC,
    )
    context = ToolContext(identity, original_message=fact.statement, issue_ids=(thread.id,))

    class Store:
        def load(self, ident):
            assert ident == saved.id
            return saved

    boundary = Boundary(True, "Controlled actual owner admission")
    registry = ToolRegistry(
        grounded_file_tools(Store(), today=lambda: original.reference),
        before=lambda *_: boundary,
        after=lambda *_: boundary,
    )
    args = {
        "thread_id": thread.id,
        "fact_id": fact.id,
        "events": [{"event_quote": fact.statement, "date_expression": original.date_expression}],
        "posture": {
            "states_client": False,
            "role": "not_stated",
            "role_basis": "not_stated",
            "client_described_as": "",
            "opponent": "",
            "quoted": "",
            "role_quote": "",
            "opponent_correction_quote": "",
        },
        "parties": {"parties": [], "why": "No party direction is being established."},
    }
    result = registry.invoke(ToolCall("reading", "record_grounded_file_reading", args), context)
    assert isinstance(result, PreparedToolResult)
    after = result.mutation.after
    assert after.facts == saved.facts and after.version == saved.version
    assert len(after.threads[0].event_observations) == len(thread.event_observations) + 1
    names = {receipt(outcome, operation)["data"]["node_name"] for operation in (DEADLINE, CALENDAR)}
    assert names <= set(result.envelope.data["stale_nodes"])
    ledger = dependency.Ledger.from_stored(after.dependencies)
    assert all(ledger.node(name).currency is dependency.Currency.STALE for name in names)
    assert result.mutation.identity and all(
        from_stored(row, thread=thread.id).on is None for row in after.threads[0].deadlines
    )
