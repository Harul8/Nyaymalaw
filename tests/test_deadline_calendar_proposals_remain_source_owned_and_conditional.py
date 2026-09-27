"""Actual loop/CAS and authenticated application; no live calls or court claims."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind, StopReason
from nm.legal_brain.orchestrate.tools import PreparedToolResult, ToolRegistry
from nm.legal_brain.reason.working_record import READ_TOOL, WorkingRecordOwner
from nm.shared.model_port import Tier, ToolCall
from nm.work_the_file import dependency
from nm.work_the_file.deadline_proposals import (
    CALENDAR,
    DEADLINE,
    VERSION,
    deadline_proposal_currency,
    deadline_proposal_tools,
)
from nm.work_the_file.deadlines import Deadline, DeadlineKind, DeadlineStatus, from_stored
from nm.work_the_file.file_mutation_contracts import FileMutation
from tests.test_event_limitation_selections_need_sealed_review import GENERATION, _fixture
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
RULE = (
    "Court scope: Recorded forum. The stated period is one month from the described event. "
    "The requested action is deliver the stated response. "
    "The stated consequence needs legal review. The recorded notification lists "
    "2023-03-28 and 2023-04-02; its applicability remains unassessed."
)


def clauses(data):
    source = data["references"][
        next(ident for ident in data["references"] if ident.startswith("law:"))
    ]
    return {"reference": source["reference"], "start": 0, "end": len(source["text"])}


def authored(
    model,
    store,
    matter_id,
    thread_id,
    *,
    change=lambda args, _data: args,
    calendar=True,
    deadline=True,
    turn="proposal",
    discover=False,
):
    queue = ["read_provision", READ_TOOL]
    if calendar:
        queue += [CALENDAR, READ_TOOL]
    if deadline:
        queue.append(DEADLINE)
    queue.append("ask_advocate")
    if discover:
        queue = [
            step
            for operation in queue
            for step in (
                ["inspect:" + operation, operation] if operation != "ask_advocate" else [operation]
            )
        ]

    def answer(*_args, **_kwargs):
        operation = queue.pop(0)
        if operation.startswith("inspect:"):
            call = ToolCall(
                "inspect" + str(len(queue)), "inspect_tool", {"name": operation.split(":", 1)[1]}
            )
        elif operation == "read_provision":
            call = ToolCall(
                "primary",
                operation,
                {"act": "Recorded source", "section": "1", "as_of": "2026-01-01"},
            )
        elif operation == READ_TOOL:
            call = ToolCall("inputs" + str(len(queue)), READ_TOOL, {})
        elif operation == "ask_advocate":
            call = ToolCall("stop", operation, {"question": "PRIVATE UNCHECKED PROPOSAL WORDS"})
        else:
            matter = store.load(matter_id)
            record = next(row for row in matter.loop_records if row.identity.turn_id == turn)
            data = next(
                event.payload["receipt"]["data"]["inventory"]
                for event in reversed(record.events)
                if event.kind is StepKind.TOOL_RETURNED
                and event.payload["receipt"]["tool"] == READ_TOOL
            )
            data = {
                **data,
                "references": {row["reference"]["id"]: row for row in data["references"]},
            }
            clause = clauses(data)
            if operation == CALENDAR:
                args = {
                    "thread_id": thread_id,
                    "court_clause": clause,
                    "entries": [
                        {"clause": clause, "date_expression": value}
                        for value in ("2023-03-28", "2023-04-02")
                    ],
                    "reason": "A private possible source-calendar interpretation.",
                }
            else:
                calendar_rows = [
                    row
                    for row in data["references"].values()
                    if row["reference"]["kind"] == "work"
                    and row["value"].get("call", {}).get("name") == CALENDAR
                ]
                thread = matter.thread(thread_id)
                from nm.work_the_file.event_observation_contracts import EventObservation

                observation = EventObservation.restore(thread.event_observations[0])
                args = {
                    "thread_id": thread_id,
                    "kind": "procedural_period",
                    "period_clause": clause,
                    "action_clause": clause,
                    "consequence_clause": clause,
                    "trigger_observation_id": observation.identity,
                    "calendar_reference": calendar_rows[0]["reference"] if calendar_rows else None,
                    "reason": "A conditional association requiring independent legal review.",
                }
            call = ToolCall("proposal" + operation, operation, change(args, data))
        return replace(
            _response(call), provider=model.provider, model=model.resolved_model(Tier.ROUTINE)
        )

    model.tool_call.side_effect = answer


def case_of(
    tmp_path,
    *,
    change=lambda args, data: args,
    calendar=True,
    deadline=True,
    before=None,
    state=None,
    rule=RULE,
):
    case = _fixture(tmp_path, period="one month", rule=rule, empty_premises=True)
    store, brain, setup, _judge, thread, _candidate, actual = case
    state = state if state is not None else {"source": True, "generation": GENERATION}
    owner = WorkingRecordOwner(
        source_current=lambda finding, generation: state["source"] and actual(finding, generation)
    )
    if before:
        before(store, thread)
    brain.registry = brain.registry.extend(
        deadline_proposal_tools(
            store,
            owner=owner,
            source_generation=GENERATION,
            current_source_generation=lambda: state["generation"],
        )
    )
    from nm.legal_brain.reason.working_record import working_record_tools

    # _fixture's actual lower loop does not compose these independently optional tools.
    if READ_TOOL not in {tool.name for tool in brain.registry.definitions}:
        brain.registry = brain.registry.extend(working_record_tools(store, owner=owner))
    brain._runner._tools = brain.registry
    authored(
        brain.model,
        store,
        "mat_loop",
        thread.id,
        change=change,
        calendar=calendar,
        deadline=deadline,
    )
    initial = store.load("mat_loop")
    outcome = brain.run(
        matter_id="mat_loop",
        turn_id="proposal",
        message="Compare actual source-stated clocks, calendar entries and all supplied events.",
        limits=LoopLimits(setup.budget, 20, 500),
    )
    return case, initial, outcome, state


def receipt(outcome, name):
    return next(
        event.payload["receipt"]
        for event in outcome.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == name
    )


def test_actual_loop_appends_only_conditional_deadlines_and_calendar_candidates(tmp_path):
    case, before, outcome, _state = case_of(tmp_path)
    assert outcome.reason is StopReason.QUESTION
    saved = case[0].load("mat_loop")
    row = from_stored(saved.threads[0].deadlines[-1], thread=saved.threads[0].id)
    assert row.on is None and row.conditional_on == date(2023, 3, 28)
    assert (
        row.status(date(2020, 1, 1)) is row.status(date(2030, 1, 1)) is DeadlineStatus.NOT_COMPUTED
    )
    assert "deadlines" not in saved.threads[0].assessed
    assert saved.facts == before.facts and saved.threads[0].event_observations == (
        before.threads[0].event_observations
    )
    assert not saved.turn_receipts
    deadline = receipt(outcome, DEADLINE)
    calendar = receipt(outcome, CALENDAR)
    for candidate in (deadline, calendar):
        assert candidate["version"] == VERSION and candidate["availability"] == "partial"
        assert candidate["assessment"] == "not_assessed"
        assert len(candidate["data"]["observations"]) == 3
        assert all(
            candidate["data"][key] is False
            for key in (
                "calendar_complete",
                "calendar_adjustments_established",
                "counting_convention_established",
                "legal_selection_established",
                "legal_deadline_established",
                "factual_truth_established",
                "advocate_task_accepted",
                "authorises_action",
                "released",
                "client_ready",
            )
        )
    assert deadline["data"]["calendar_proposal"]["adjustments_applied"] is False
    assert calendar["data"]["entries"][0]["on"] == "2023-03-28"
    ledger = dependency.Ledger.from_stored(saved.dependencies)
    for candidate in (deadline, calendar):
        node = ledger.node(candidate["data"]["node_name"])
        assert node.currency is dependency.Currency.NOT_ESTABLISHED
        assert not dependency.presentable(ledger, node.name)[0]
    assert deadline_proposal_currency(ledger, row)[0] == "not_established"
    written = [event for event in outcome.record.events if "mutation_identity" in event.payload]
    assert [event.payload["receipt"]["tool"] for event in written] == [CALENDAR, DEADLINE]
    calls = case[1].model.tool_call.call_count
    repeat = case[1].run(
        matter_id="mat_loop",
        turn_id="proposal",
        message="Compare actual source-stated clocks, calendar entries and all supplied events.",
        limits=LoopLimits(case[2].budget, 20, 500),
    )
    assert repeat.record == outcome.record and case[1].model.tool_call.call_count == calls


def test_actual_append_preserves_legacy_real_deadline_and_all_prior_words(tmp_path):
    previous = Deadline(
        "thr_events",
        DeadlineKind.LISTED_HEARING,
        "Earlier exact listed event",
        "Previously recorded action",
        "Earlier owner",
        "Earlier stated consequence",
        date(2020, 1, 1),
    )

    def prior(store, thread):
        matter = store.load("mat_loop")
        changed = replace(
            matter.thread(thread.id),
            deadlines=(previous,),
            assessed=("deadlines", "independent_prior_work"),
        )
        store.commit(
            replace(matter, threads=(changed,), version=matter.version + 1),
            expected_version=matter.version,
        )

    case, initial, outcome, _state = case_of(tmp_path, before=prior)
    assert outcome.reason is StopReason.QUESTION
    saved = case[0].load("mat_loop")
    assert saved.threads[0].deadlines[0] == initial.threads[0].deadlines[0]
    assert len(saved.threads[0].deadlines) == 2
    assert saved.threads[0].assessed == ("independent_prior_work",)


@pytest.mark.parametrize(
    "field",
    [
        "on",
        "conditional_on",
        "status",
        "approved",
        "reviewed",
        "calendar_complete",
        "holiday_adjusted",
        "owner",
        "advocate_id",
        "counting_convention",
    ],
)
def test_author_cannot_write_legal_deadline_calendar_or_human_acceptance_flags(tmp_path, field):
    _, _, outcome, _ = case_of(
        tmp_path, calendar=False, change=lambda args, _: {**args, field: True}
    )
    assert outcome.reason is StopReason.REFUSED
    assert not any(
        event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == DEADLINE
        for event in outcome.record.events
    )


@pytest.mark.parametrize(
    "damage",
    [
        "source_identity",
        "span",
        "bool_span",
        "foreign_event",
        "foreign_thread",
        "blank_reason",
        "changed_calendar",
        "fake_work_reference",
    ],
)
def test_changed_foreign_or_unowned_sources_events_calendars_are_refused(tmp_path, damage):
    def change(args, data):
        if "period_clause" not in args:
            return args
        if damage == "source_identity":
            args["period_clause"]["reference"]["identity"] = "0" * 64
        elif damage == "span":
            args["period_clause"]["end"] = 999999
        elif damage == "bool_span":
            args["period_clause"]["start"] = False
        elif damage == "foreign_event":
            args["trigger_observation_id"] = "0" * 64
        elif damage == "foreign_thread":
            args["thread_id"] = "foreign_dispute"
        elif damage == "blank_reason":
            args["reason"] = " "
        elif damage == "changed_calendar":
            args["calendar_reference"]["identity"] = "0" * 64
        else:
            args["calendar_reference"] = args["period_clause"]["reference"]
        return args

    case, initial, outcome, _state = case_of(tmp_path, change=change)
    assert outcome.reason is StopReason.REFUSED
    assert case[0].load("mat_loop").threads == initial.threads


@pytest.mark.parametrize("expression", ["2023-03-29", "tomorrow", "2023-02-30", "23-03-28", True])
def test_calendar_never_invents_or_resolves_unstated_dates(tmp_path, expression):
    def change(args, _):
        args["entries"][0]["date_expression"] = expression
        return args

    case, before, outcome, _ = case_of(tmp_path, deadline=False, change=change)
    assert outcome.reason is StopReason.REFUSED
    assert case[0].load("mat_loop").dependencies == before.dependencies
    assert case[0].load("mat_loop").threads == before.threads


@pytest.mark.parametrize("late", ["source", "generation"])
def test_deadline_proposals_recheck_sources_at_atomic_commit(tmp_path, monkeypatch, late):
    state = {"source": True, "generation": GENERATION}
    actual = ToolRegistry.invoke

    def revoke(registry, call, context):
        result = actual(registry, call, context)
        if call.name == DEADLINE:
            assert isinstance(result, PreparedToolResult)
            state[late] = False if late == "source" else "changed"
        return result

    monkeypatch.setattr(ToolRegistry, "invoke", revoke)
    case, initial, outcome, _ = case_of(tmp_path, calendar=False, state=state)
    assert outcome.reason is StopReason.REFUSED
    assert case[0].load("mat_loop").threads == initial.threads
    assert not any("mutation_identity" in event.payload for event in outcome.record.events)
    assert outcome.budget.spend.cost_usd > 0
    assert outcome.record.events[-2].payload["kind"] == "write_boundary_refused"


def test_ordinary_mutation_cannot_smuggle_a_conditional_deadline(tmp_path):
    case = _fixture(tmp_path, rule=RULE, empty_premises=True)
    matter = case[0].load("mat_loop")
    row = Deadline(
        "thr_events",
        DeadlineKind.PROCEDURAL_PERIOD,
        "A source",
        "An action",
        matter.advocate_id,
        "A consequence",
        conditional_on=date(2023, 3, 28),
    )
    after = matter.with_thread(replace(matter.threads[0], deadlines=(row,)))
    with pytest.raises(ValueError):
        FileMutation(matter, after, matter.advocate_id)


def test_source_and_event_correction_reaches_exact_nodes_but_not_unrelated_work(tmp_path):
    case, _, outcome, _ = case_of(tmp_path)
    saved = case[0].load("mat_loop")
    row = from_stored(saved.threads[0].deadlines[-1], thread=saved.threads[0].id)
    ledger = dependency.Ledger.from_stored(saved.dependencies)
    independent = dependency.Node(
        "unrelated",
        "A separate source-free unknown",
        (dependency.Rest(dependency.InputKind.UNKNOWN, "independent_unknown"),),
    )
    ledger = dependency.record(ledger, independent)
    changed = replace(
        saved,
        facts=(
            replace(saved.facts[0], statement="A corrected supplied account."),
            *saved.facts[1:],
        ),
    )
    moved, names, _ = dependency.sync_inputs(ledger, changed, reason="Actual account correction")
    assert receipt(outcome, DEADLINE)["data"]["node_name"] in names
    assert receipt(outcome, CALENDAR)["data"]["node_name"] not in names
    assert "unrelated" not in names
    assert deadline_proposal_currency(moved, row)[0] == "stale"
    assert moved.revisions_of(receipt(outcome, DEADLINE)["data"]["node_name"])[0].was


def test_currency_hook_does_not_claim_legacy_or_other_rows(tmp_path):
    row = Deadline(
        "old",
        DeadlineKind.OTHER,
        "Old source",
        "Old action",
        "Old owner",
        "Old consequence",
        date(2000, 1, 1),
    )
    assert deadline_proposal_currency(dependency.Ledger(), row) is None
    assert deadline_proposal_currency(dependency.Ledger(), {}) is None


def authenticated_case(client):
    from unittest.mock import Mock

    from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, SourceDocument
    from tests.test_procedural_arithmetic_is_only_a_current_conditional_candidate import (
        authenticated_procedural_case,
    )

    app, matter, model, generation = authenticated_procedural_case(client)
    held = replace(app.evidence.read_provision.return_value.findings[0], span=RULE)
    app.evidence.read_provision = Mock(
        return_value=EvidenceResult(Coverage.ANSWERED, (held,), searched_stores=(held.store,))
    )
    app.evidence.document = Mock(
        return_value=SourceDocument(
            "read",
            label=held.ref,
            store=held.store,
            segments=(("1", held.span),),
            target=0,
            locator=held.locator,
            kind=held.source_kind.value,
        )
    )
    authored(model, app.store, matter.id, matter.threads[0].id, turn="proposal", discover=True)
    return app, matter, model, generation, held


def test_actual_authenticated_application_saves_only_private_conditional_proposals(client):
    app, matter, model, generation, _held = authenticated_case(client)
    body = {
        "version": matter.version,
        "turn_id": "proposal",
        "message": "Compare actual source-stated clocks, calendar entries and all supplied events.",
    }
    served = client.post(f"/api/matters/{matter.id}/brain/preview", json=body)
    assert served.status_code == 200, served.text
    assert served.json()["client_ready"] is False
    assert "PRIVATE" not in served.text and "2024-02-29" not in served.text
    assert served.headers["cache-control"] == "no-store"
    saved = app.store.load(matter.id)
    assert saved.threads[0].deadlines, [
        (event.kind.value, event.payload.get("kind"), event.payload.get("reason"))
        for event in saved.loop_records[0].events[-4:]
    ]
    row = from_stored(saved.threads[0].deadlines[0], thread=saved.threads[0].id)
    assert row.on is None and row.conditional_on == date(2024, 2, 29)
    assert row.status(date.today()) is DeadlineStatus.NOT_COMPUTED
    parent = saved.loop_records[0]
    written = [event for event in parent.events if "mutation_identity" in event.payload]
    assert [event.payload["receipt"]["tool"] for event in written] == [CALENDAR, DEADLINE]
    assert all(
        event.payload["receipt"]["receipt"]["source_generation"] == generation for event in written
    )
    assert saved.facts == matter.facts and not saved.turn_receipts
    projected = client.get(f"/api/matters/{matter.id}")
    assert projected.status_code == 200
    assert "not_established" in projected.text and "2024-02-29" in projected.text
    calls = model.tool_call.call_count
    repeated = client.post(
        f"/api/matters/{matter.id}/brain/preview", json={**body, "version": saved.version}
    )
    assert repeated.status_code == 200 and model.tool_call.call_count == calls


@pytest.mark.parametrize(
    "control,status",
    [
        ("foreign", 404),
        ("stale", 409),
        ("csrf", 403),
        ("device", 401),
        ("logout", 401),
        ("extra_actor", 422),
    ],
)
def test_actual_authenticated_source_proposal_entry_is_owned_and_not_body_approved(
    client, control, status
):
    app, matter, model, _generation, _held = authenticated_case(client)
    body = {
        "version": matter.version,
        "turn_id": "proposal",
        "message": "Conditional proposal only.",
    }
    headers = {}
    target = client
    if control == "foreign":
        target = client.sign_in("deadline_other_account", fresh=True)
    elif control == "stale":
        body["version"] += 10
    elif control == "csrf":
        headers["x-nm-csrf"] = "not-the-session-token"
    elif control == "device":
        headers["user-agent"] = "different-device"
    elif control == "logout":
        assert client.post("/api/logout").status_code == 200
    else:
        body["advocate_id"] = "foreign"
    served = target.post(f"/api/matters/{matter.id}/brain/preview", json=body, headers=headers)
    assert served.status_code == status, served.text
    assert not model.tool_call.called and app.store.load(matter.id) == matter


def test_actual_authenticated_late_source_revocation_preserves_calendar_history_not_deadline(
    client, monkeypatch
):
    from nm.legal_brain.retrieve.evidence_port import SourceDocument

    app, matter, _model, _generation, held = authenticated_case(client)
    original = ToolRegistry.invoke

    def revoke(registry, call, context):
        answer = original(registry, call, context)
        if call.name == DEADLINE:
            assert isinstance(answer, PreparedToolResult)
            app.evidence.document.return_value = SourceDocument(
                "read",
                label=held.ref,
                store=held.store,
                segments=(("1", "Changed actual current source words"),),
                target=0,
                locator=held.locator,
                kind=held.source_kind.value,
            )
        return answer

    monkeypatch.setattr(ToolRegistry, "invoke", revoke)
    served = client.post(
        f"/api/matters/{matter.id}/brain/preview",
        json={
            "version": matter.version,
            "turn_id": "proposal",
            "message": "Conditional proposal only.",
        },
    )
    assert served.status_code == 200, served.text
    saved = app.store.load(matter.id)
    parent = saved.loop_records[0]
    assert parent.events[-1].payload["reason"] == StopReason.REFUSED.value
    assert parent.events[-2].payload["kind"] == "write_boundary_refused"
    assert [
        event.payload["receipt"]["tool"]
        for event in parent.events
        if "mutation_identity" in event.payload
    ] == [CALENDAR]
    assert saved.threads == matter.threads and saved.facts == matter.facts
    assert not saved.turn_receipts and served.json()["spend"]["cost_usd"] > 0


def test_missing_calendar_is_not_a_claim_of_an_open_court_or_complete_calendar(tmp_path):
    _, _, outcome, _ = case_of(tmp_path, calendar=False)
    data = receipt(outcome, DEADLINE)["data"]
    assert data["calendar_proposal"] is None and data["calendar_complete"] is False
    assert data["deadline"]["on"] is None
    assert data["deadline"]["conditional_on"] == "2023-03-28"


def test_changed_primary_source_invalidates_calendar_and_deadline_not_unrelated_work(tmp_path):
    from nm.legal_brain.retrieve.evidence_port import Finding

    case, _, outcome, _ = case_of(tmp_path)
    matter = case[0].load("mat_loop")
    data = receipt(outcome, CALENDAR)["data"]
    finding = Finding.from_record(data["sources"][0]["value"]["finding"])
    changed = replace(finding, span=finding.span + " A source correction.")
    ledger, names, _ = dependency.sync_inputs(
        dependency.Ledger.from_stored(matter.dependencies),
        matter,
        (changed,),
        reason="Actual primary source changed",
    )
    assert data["node_name"] in names and receipt(outcome, DEADLINE)["data"]["node_name"] in names
    assert all(ledger.node(name).currency is dependency.Currency.STALE for name in names)
