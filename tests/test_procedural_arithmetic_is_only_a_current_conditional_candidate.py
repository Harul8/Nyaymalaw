"""Actual saved-loop computation; no legal deadline or calendar curation claim."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from unittest.mock import Mock

import pytest

from nm.legal_brain.procedure import limitation
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, SourceDocument
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind, StopReason
from nm.legal_brain.procedure.procedural_calculation import (
    COMPUTE,
    READ,
    VERSION,
    procedural_calculation_tools,
)
from nm.legal_brain.reason.working_record import WorkingRecordOwner
from nm.shared.authority_contracts import Act
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from nm.shared.store_port import StaleWrite
from nm.work_the_file.event_observation_contracts import EventObservation
from nm.work_the_file.file_mutation_contracts import neutral
from tests.test_event_limitation_selections_need_sealed_review import GENERATION, _fixture
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def case_of(
    tmp_path,
    *,
    period="ninety days",
    on=date(2023, 2, 28),
    rule=None,
    change=lambda args, _data: args,
    state=None,
    selected=(),
    missing=False,
    generation=None,
    owner_mutation=None,
):
    case = _fixture(
        tmp_path,
        period=period,
        on=on,
        empty_premises=True,
        rule=rule or "The stated period is ninety days from the described event.",
    )
    store, brain, setup, _judge, thread, _candidate, current_source = case
    state = state if state is not None else {"source": True, "generation": GENERATION}
    state["store"] = store

    def source_current(finding, source_generation):
        return state["source"] and current_source(finding, source_generation)

    owner = WorkingRecordOwner(source_current=source_current)
    if owner_mutation:
        owner_mutation(store, thread)
    tools = procedural_calculation_tools(
        store,
        owner=owner,
        source_generation=GENERATION,
        current_source_generation=generation or (lambda: state["generation"]),
    )
    brain.registry = brain.registry.extend(tools)
    brain._runner._tools = brain.registry
    responses = ["source", "inputs", "compute", "done"] if not missing else ["inputs", "done"]
    calls = []

    def next_response(*_args, **_kwargs):
        operation = responses.pop(0)
        if operation == "source":
            call = ToolCall(
                "actual-source",
                "read_provision",
                {"act": "Recorded source", "section": "1", "as_of": on.isoformat()},
            )
        elif operation == "inputs":
            call = ToolCall("actual-inputs", READ, {"thread_id": thread.id})
        elif operation == "compute":
            matter = store.load("mat_loop")
            record = next(
                row for row in matter.loop_records if row.identity.turn_id == "procedural"
            )
            data = next(
                event.payload["receipt"]["data"]
                for event in reversed(record.events)
                if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == READ
            )
            source = data["sources"][0]
            args = {
                "thread_id": thread.id,
                "source_reference": source["reference"],
                "start": 0,
                "end": len(source["text"]),
                "trigger_observation_id": data["observations"][0]["identity"],
                "reason": "A private possible association, not an established legal trigger.",
            }
            args = change(args, data)
            call = ToolCall("actual-calculation", COMPUTE, args)
        else:
            call = ToolCall("stop", "ask_advocate", {"question": "Which association needs review?"})
        calls.append(call)
        return replace(_response(call), provider="scripted", model="scripted:author")

    brain.model.tool_call.side_effect = next_response
    before = store.load("mat_loop")
    outcome = brain.run(
        matter_id="mat_loop",
        turn_id="procedural",
        message="Compare the source-stated interval to the attributed events.",
        selected_issue_ids=selected,
        limits=LoopLimits(setup.budget, 12, 500),
    )
    return case, before, outcome, calls, tools, state


def result(outcome, name=COMPUTE):
    return next(
        event.payload["receipt"]
        for event in outcome.record.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == name
    )


@pytest.mark.parametrize(
    "period,on,expected",
    [
        ("ninety days", date(2023, 2, 28), "2023-05-29"),
        ("one month", date(2025, 1, 31), "2025-02-28"),
        ("one year", date(2024, 2, 29), "2025-02-28"),
    ],
)
def test_actual_loop_computes_only_conditional_arithmetic_without_losing_competing_events(
    tmp_path, period, on, expected
):
    case, before, outcome, calls, tools, _state = case_of(tmp_path, period=period, on=on)
    assert outcome.reason is StopReason.QUESTION
    actual = result(outcome)
    data = actual["data"]
    assert actual["version"] == VERSION and actual["assessment"] == "not_assessed"
    assert data["conditional_date"] == expected and data["arithmetic_verified"] is True
    assert len(data["observations"]) == 3 and data["observations"][-1]["on"] is None
    assert {row["value"]["id"] for row in data["chronology"]} == {row.id for row in before.facts}
    assert data["clause"]["quote"] == data["source"]["finding"]["span"]
    assert data["source_reference"]["id"].startswith("law:")
    for field in (
        "selection_independently_reviewed",
        "legal_deadline_established",
        "legal_applicability_established",
        "factual_truth_established",
        "holiday_adjusted",
        "deadline_registered",
        "released",
        "client_ready",
    ):
        assert data[field] is False
    assert all(tool.required_act is Act.READ and tool.parallel_safe for tool in tools)
    saved = case[0].load("mat_loop")
    for field in (
        "facts",
        "threads",
        "dependencies",
        "authority_bindings",
        "commission",
        "advice_decisions",
        "turn_receipts",
    ):
        assert neutral(asdict(saved)[field]) == neutral(asdict(before)[field])
    assert not any("mutation_identity" in event.payload for event in outcome.record.events)
    count = case[1].model.tool_call.call_count
    repeat = case[1].run(
        matter_id="mat_loop",
        turn_id="procedural",
        message="Compare the source-stated interval to the attributed events.",
        limits=LoopLimits(case[2].budget, 12, 500),
    )
    assert repeat.record == outcome.record and repeat.proposal == outcome.proposal
    assert repeat.budget.spend.tokens == outcome.budget.spend.tokens
    assert repeat.budget.spend.cost_usd == pytest.approx(outcome.budget.spend.cost_usd)
    assert case[1].model.tool_call.call_count == count


def test_later_attributed_event_is_not_replaced_by_an_earlier_global_date(tmp_path):
    _, _, outcome, *_rest = case_of(
        tmp_path,
        change=lambda args, data: dict(
            args, trigger_observation_id=data["observations"][1]["identity"]
        ),
    )
    assert result(outcome)["data"]["conditional_date"] == "2024-05-29"
    assert len(result(outcome)["data"]["observations"]) == 3


@pytest.mark.parametrize(
    "rule",
    [
        "The stated condition fixes no period.",
        "The first clock is thirty days; another is sixty days.",
        "The period is zero days.",
        "The period is one year and one month.",
    ],
)
def test_absent_zero_or_competing_periods_are_not_a_clean_computed_deadline(tmp_path, rule):
    _, _, outcome, *_rest = case_of(tmp_path, rule=rule)
    data = result(outcome)["data"]
    assert data["conditional_date"] is None and data["arithmetic_verified"] is False
    assert (
        data["deadline_registered"] is False and "No date was computed" in result(outcome)["reason"]
    )


def test_undated_trigger_remains_undated_instead_of_borrowing_another_event_date(tmp_path):
    _, _, outcome, *_rest = case_of(
        tmp_path,
        change=lambda args, data: dict(
            args, trigger_observation_id=data["observations"][-1]["identity"]
        ),
    )
    assert result(outcome)["data"]["conditional_date"] is None
    assert result(outcome)["data"]["selected_observation"]["on"] is None


def test_complete_reader_without_captured_law_is_explicitly_partial_not_a_clock(tmp_path):
    case, before, outcome, *_rest = case_of(tmp_path, missing=True)
    receipt = result(outcome, READ)
    assert receipt["availability"] == "partial"
    assert receipt["assessment"] == "not_assessed"
    assert receipt["data"]["sources"] == []
    assert len(receipt["data"]["observations"]) == 3
    assert not receipt["data"]["legal_deadline_established"]
    assert not receipt["data"]["deadline_registered"]
    assert case[0].load("mat_loop").threads == before.threads


@pytest.mark.parametrize(
    "key",
    [
        "amount",
        "unit",
        "on",
        "approved",
        "reviewed",
        "actor",
        "status",
        "holiday_adjusted",
        "track",
        "deadline_registered",
    ],
)
def test_arithmetic_cannot_invent_inputs_or_register_a_legal_deadline(tmp_path, key):
    _, _, outcome, *_rest = case_of(tmp_path, change=lambda args, _data: dict(args, **{key: True}))
    assert outcome.reason is StopReason.REFUSED
    failures = [event.payload for event in outcome.record.events if event.kind is StepKind.FAILURE]
    assert failures[-1]["kind"] == "unoffered_or_invalid_tool"
    assert not any(
        event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
        for event in outcome.record.events
    )


@pytest.mark.parametrize(
    "change",
    [
        "foreign_source",
        "changed_source",
        "raw_window",
        "foreign_event",
        "bool_offset",
        "outside_offset",
        "blank_reason",
        "long_reason",
    ],
)
def test_unknown_changed_untyped_or_unbounded_selectors_are_refused(tmp_path, change):
    def tamper(args, data):
        if change == "foreign_source":
            args["source_reference"] = dict(args["source_reference"], id="law:" + "f" * 64)
        elif change == "changed_source":
            args["source_reference"] = dict(args["source_reference"], identity="f" * 64)
        elif change == "raw_window":
            args["source_reference"] = dict(args["source_reference"], id="window:" + "f" * 64)
        elif change == "foreign_event":
            args["trigger_observation_id"] = "e" * 64
        elif change == "bool_offset":
            args["start"] = False
        elif change == "outside_offset":
            args["end"] = len(data["sources"][0]["text"]) + 1
        else:
            args["reason"] = " " if change == "blank_reason" else "x" * 16001
        return args

    case, before, outcome, *_rest = case_of(tmp_path, change=tamper)
    assert outcome.reason is StopReason.REFUSED
    assert neutral(asdict(case[0].load("mat_loop"))["threads"]) == neutral(
        asdict(before)["threads"]
    )


@pytest.mark.parametrize(
    "damage",
    [
        "source_version",
        "account",
        "date",
        "duplicate",
        "foreign_fact",
        "conflict",
        "superseded",
        "denied",
    ],
)
def test_one_damaged_observation_refuses_the_full_population_instead_of_disappearing(
    tmp_path, damage
):
    def alter(store, thread):
        matter = store.load("mat_loop")
        old = matter.thread(thread.id)
        rows = list(old.event_observations)
        row = EventObservation.restore(rows[0])
        facts = matter.facts
        if damage == "source_version":
            rows[0] = replace(row, source_version=row.source_version + 1)
        elif damage == "account":
            rows[0] = replace(row, account="Another supplied account: " + row.account)
        elif damage == "date":
            rows[0] = replace(row, on=date(2000, 1, 1))
        elif damage == "duplicate":
            rows.append(row)
        elif damage == "foreign_fact":
            rows[0] = replace(row, source_fact="foreign")
        else:
            facts = tuple(
                replace(
                    fact,
                    **{"conflicts_with": (matter.facts[1].id,)}
                    if damage == "conflict"
                    else {"superseded_by": matter.facts[1].id}
                    if damage == "superseded"
                    else {"confirmed": False},
                )
                if fact.id == row.source_fact
                else fact
                for fact in facts
            )
        changed = replace(old, event_observations=tuple(rows))
        store.commit(
            replace(matter, facts=facts, threads=(changed,), version=matter.version + 1),
            expected_version=matter.version,
        )

    _, _, outcome, *_rest = case_of(tmp_path, owner_mutation=alter)
    assert outcome.reason is StopReason.REFUSED


@pytest.mark.parametrize("late", ["source", "generation", "file"])
def test_source_generation_or_file_revocation_during_arithmetic_cannot_escape(
    tmp_path, monkeypatch, late
):
    state = {"source": True, "generation": GENERATION}
    actual = limitation.run_period

    def revoke(*args):
        answer = actual(*args)
        if late == "source":
            state["source"] = False
        elif late == "generation":
            state["generation"] = "changed"
        else:
            store = state["store"]
            matter = store.load("mat_loop")
            store.commit(
                replace(
                    matter,
                    version=matter.version + 1,
                    facts=(
                        replace(
                            matter.facts[0], statement=matter.facts[0].statement + " Correction."
                        ),
                        *matter.facts[1:],
                    ),
                ),
                expected_version=matter.version,
            )
        return answer

    monkeypatch.setattr(limitation, "run_period", revoke)
    if late == "file":
        with pytest.raises(StaleWrite):
            case_of(tmp_path, state=state)
        matter = state["store"].load("mat_loop")
        record = next(row for row in matter.loop_records if row.identity.turn_id == "procedural")
        assert record.events[-1].kind is StepKind.TOOL_STARTED
        assert record.events[-1].payload["call"]["name"] == COMPUTE
        assert any(event.kind is StepKind.MODEL_RETURNED for event in record.events)
        assert not any(
            event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
            for event in record.events
        )
        assert matter.facts[0].statement.endswith(" Correction.")
        return
    _, _, outcome, *_rest = case_of(tmp_path, state=state)
    assert outcome.reason is StopReason.REFUSED
    assert not any(
        event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
        for event in outcome.record.events
    )


@pytest.mark.parametrize("span", ["one month", "ninety days", "one year"])
def test_unique_period_reader_reuses_the_only_regex_and_preserves_legacy_reader(span):
    assert limitation.unique_period_in(span) == limitation.period_in(span)
    assert limitation.unique_period_in(span + " and two days") is None
    first = limitation.period_in(span)
    competing = limitation.period_in(span + " and two days")
    assert (competing.years, competing.months, competing.days) == (
        first.years,
        first.months,
        first.days,
    )
    assert competing.read_from == span + " and two days"


def test_unique_reader_never_coerces_a_nontext_input():
    with pytest.raises(ValueError):
        limitation.unique_period_in(True)


def authenticated_procedural_case(client):
    from tests.test_private_file_proposals_use_actual_sources_and_atomic_history import (
        authenticated_case,
    )

    app, matter, model, generation, held = authenticated_case(client)
    held = replace(held, span="The stated interval is two months from the described event.")
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
    fact = replace(
        matter.facts[0],
        statement="The advocate reports the described event on 2024-01-31.",
        confirmed=None,
    )
    observation = EventObservation(
        fact.id,
        fact.version,
        fact.statement,
        "the described event on 2024-01-31",
        "2024-01-31",
        date.today(),
        date(2024, 1, 31),
    )
    thread = replace(matter.threads[0], event_observations=(observation,))
    matter = app.store.commit(
        replace(matter, facts=(fact,), threads=(thread,), version=matter.version + 1),
        expected_version=matter.version,
    )
    grant = app.controlled_evaluations[0]
    app.controlled_evaluations = (
        replace(
            grant,
            limits=LoopLimits(
                Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1.0, max_children=4), 30, 500
            ),
        ),
    )
    operations = [
        "inspect:read_provision",
        "read_provision",
        "inspect:" + READ,
        READ,
        "inspect:" + COMPUTE,
        COMPUTE,
        "ask_advocate",
    ]

    def answer(*_args, **_kwargs):
        operation = operations.pop(0)
        if operation.startswith("inspect:"):
            call = ToolCall(
                "discovered-" + operation.split(":", 1)[1],
                "inspect_tool",
                {"name": operation.split(":", 1)[1]},
            )
        elif operation == "read_provision":
            call = ToolCall(
                "primary",
                operation,
                {"act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"},
            )
        elif operation == READ:
            call = ToolCall("inputs", READ, {"thread_id": thread.id})
        elif operation == COMPUTE:
            current = app.store.load(matter.id)
            parent = current.loop_records[0]
            data = next(
                event.payload["receipt"]["data"]
                for event in parent.events
                if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == READ
            )
            source = data["sources"][0]
            call = ToolCall(
                "conditional",
                COMPUTE,
                {
                    "thread_id": thread.id,
                    "source_reference": source["reference"],
                    "start": 0,
                    "end": len(source["text"]),
                    "trigger_observation_id": data["observations"][0]["identity"],
                    "reason": "PRIVATE CANDIDATE ASSOCIATION: not a legally reviewed trigger.",
                },
            )
        else:
            call = ToolCall("stop", "ask_advocate", {"question": "PRIVATE PROCEDURAL QUESTION"})
        return _response(call)

    model.tool_call.side_effect = answer
    return app, app.store.load(matter.id), model, generation


def test_actual_authenticated_composition_discovers_conditional_tools_and_never_releases_date(
    client,
):
    app, matter, model, generation = authenticated_procedural_case(client)
    body = {
        "version": matter.version,
        "turn_id": "served_procedural",
        "message": "Compare the stated source period and attributed event.",
    }
    served = client.post(f"/api/matters/{matter.id}/brain/preview", json=body)
    assert served.status_code == 200, served.text
    assert served.json()["client_ready"] is False
    assert served.json()["result_state"] == "not_released"
    assert "2024-03-31" not in served.text and "PRIVATE" not in served.text
    assert served.headers["cache-control"] == "no-store"
    saved = app.store.load(matter.id)
    parent = saved.loop_records[0]
    receipt = next(
        event.payload["receipt"]
        for event in parent.events
        if event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
    )
    assert receipt["data"]["conditional_date"] == "2024-03-31"
    assert receipt["receipt"]["source_generation"] == generation
    assert not receipt["data"]["legal_deadline_established"]
    assert saved.facts == matter.facts and saved.threads == matter.threads
    assert not saved.turn_receipts
    calls = model.tool_call.call_count
    repeated = client.post(
        f"/api/matters/{matter.id}/brain/preview", json={**body, "version": saved.version}
    )
    assert repeated.status_code == 200, repeated.text
    assert model.tool_call.call_count == calls


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
def test_actual_authenticated_procedural_entry_cannot_be_body_authorised(client, control, status):
    app, matter, model, _generation = authenticated_procedural_case(client)
    body = {
        "version": matter.version,
        "turn_id": "procedural_transport_control",
        "message": "Compare the source period without establishing a deadline.",
    }
    headers = {}
    target = client
    if control == "foreign":
        target = client.sign_in("procedural_other_account", fresh=True)
    elif control == "stale":
        body["version"] += 10
    elif control == "csrf":
        headers["x-nm-csrf"] = "not-the-session-token"
    elif control == "device":
        headers["user-agent"] = "different-device"
    elif control == "logout":
        assert client.post("/api/logout").status_code == 200
    else:
        body["advocate_id"] = "foreign_account"
    served = target.post(f"/api/matters/{matter.id}/brain/preview", json=body, headers=headers)
    assert served.status_code == status, served.text
    assert not model.tool_call.called and app.store.load(matter.id) == matter


def test_actual_file_change_during_arithmetic_returns_owned_409_without_compute_receipt(
    client, monkeypatch
):
    app, matter, _model, _generation = authenticated_procedural_case(client)
    actual = limitation.run_period

    def external_correction(*args):
        answer = actual(*args)
        current = app.store.load(matter.id)
        app.store.commit(
            replace(
                current,
                version=current.version + 1,
                facts=(
                    replace(
                        current.facts[0], statement=current.facts[0].statement + " Correction."
                    ),
                ),
            ),
            expected_version=current.version,
        )
        return answer

    monkeypatch.setattr(limitation, "run_period", external_correction)
    served = client.post(
        f"/api/matters/{matter.id}/brain/preview",
        json={
            "version": matter.version,
            "turn_id": "procedural_file_changed",
            "message": "Compute conditional addition only.",
        },
    )
    assert served.status_code == 409, served.text
    assert "PRIVATE" not in served.text and "2024-03-31" not in served.text
    saved = app.store.load(matter.id)
    parent = saved.loop_records[0]
    assert parent.events[-1].kind is StepKind.TOOL_STARTED
    assert parent.events[-1].payload["call"]["name"] == COMPUTE
    assert not any(
        event.kind is StepKind.TOOL_RETURNED and event.payload["receipt"]["tool"] == COMPUTE
        for event in parent.events
    )
    assert any(event.kind is StepKind.MODEL_RETURNED for event in parent.events)
    assert saved.threads == matter.threads and not saved.turn_receipts
    assert saved.facts[0].statement.endswith(" Correction.")
