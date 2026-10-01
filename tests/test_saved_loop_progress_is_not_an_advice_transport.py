"""P52: served, owned, committed stages cannot become an advice/trace channel."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from fastapi import HTTPException

from nm.advise.turn_receipt_contracts import fingerprint
from nm.Archives.legal_brain.communicate.loop_progress import (
    AUTHORITY_STAGE,
    OPPOSITION_STAGE,
    PROVISION_STAGE,
    REQUIREMENTS_STAGE,
    InvalidProgressCursor,
    cursor_at,
    progress,
    project_event,
    recorded_scope,
    resume_position,
    sse_frame,
)
from nm.Archives.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopMode,
    LoopRecord,
    StepKind,
    StopReason,
    digest,
)
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
)
from nm.shared.model_port import Prompt
from nm.work_the_file.file_mutation import assertion_identity, dispute_identity
from nm.work_the_file.matter_contracts import Matter
from nm.work_the_file.original_instruction import capture_original_instruction
from nm.work_the_file.write_tools import VERSION as WRITE_VERSION

pytestmark = pytest.mark.class_a
SECRET = "PRIVATE MODEL DELIBERATION AND UNRELEASED LEGAL CONCLUSION"
AT = "2026-09-27T10:00:00+00:00"


def work(*, actor="adv_demo", matter_id="progress_matter", turn_id="progress_turn", stop=True):
    identity = LoopIdentity(
        matter_id, actor, turn_id, "a" * 64, "b" * 64, "c" * 64, 1, LoopMode.SYNTHETIC
    )
    record = LoopRecord(identity)
    kinds = [StepKind.START, StepKind.MODEL_STARTED, StepKind.MODEL_RETURNED]
    if stop:
        kinds.append(StepKind.STOP)
    for kind in kinds:
        payload = {"model_text": SECRET, "private_context": {"thoughts": SECRET}}
        if kind is StepKind.STOP:
            payload.update(reason=StopReason.PROPOSAL.value, proposal={"answer": SECRET})
        record = add(record, kind, payload)
    return record


def add(record, kind, payload):
    previous = record.events[-1].fingerprint if record.events else record.identity.fingerprint
    event = LoopEvent.create(len(record.events) + 1, kind, AT, payload, previous)
    return replace(record, events=record.events + (event,))


def reseal(record, changed_index, payload):
    """Rebuild a coherent event chain so each control tests the projection."""
    rebuilt = LoopRecord(record.identity)
    for index, event in enumerate(record.events):
        rebuilt = add(rebuilt, event.kind, payload if index == changed_index else event.payload)
    return rebuilt


def scoped_work(*, stop=True):
    """Two actual saved receipt shapes; proposal words remain private."""
    identity = work(stop=False).identity
    source = {
        "id": identity.matter_id,
        "advocate_id": identity.advocate_id,
        "threads": [
            {"id": "first", "label": "First dispute"},
            {"id": "second", "label": "Second dispute"},
        ],
    }
    brief = {
        "matter_id": identity.matter_id,
        "advocate_id": identity.advocate_id,
        "source_record_json": json.dumps(source),
        "selected_issue_ids": ["first", "second"],
        "snapshot_id": fingerprint(source),
    }
    record = add(LoopRecord(identity), StepKind.START,
                 {"context": {"schema": 1, "brief": brief}, "private": SECRET})
    for index, thread_id in enumerate(("first", "second"), 1):
        call_id = f"requirements-{index}"
        record = add(record, StepKind.TOOL_STARTED, {
            "call": {"call_id": call_id, "name": "record_requirements",
                     "arguments": {"thread_id": thread_id}},
            "private": SECRET,
        })
        envelope = ToolEnvelope(
            "record_requirements", "captured-source-requirements-v1",
            ToolKind.MATTER, ToolOutcome.RESULTS, Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {"matter_id": identity.matter_id, "matter_version": 1,
             "snapshot": "d" * 64, "source_version": "generation-1"},
            {"thread_id": thread_id, "requirements": [{
                "need": SECRET, "why": SECRET, "span": "Exact source words",
                "source": "source", "locator": f"source:{index}", "force": "required",
                "source_identity": "e" * 64, "context_identity": "f" * 64,
            }], "states_derived": True, "facts_established": False,
             "legal_interpretation": "not_assessed"},
            "A captured source proposal, not an independently reviewed need.",
        )
        record = add(record, StepKind.TOOL_RETURNED, {
            "call_id": call_id, "receipt": json.loads(envelope.wire()),
            "mutation_identity": "d" * 64, "private": SECRET,
        })
    if stop:
        record = add(record, StepKind.STOP, {"reason": StopReason.BUDGET.value})
    return record


def opening_work(*, actor="adv_demo", matter_id="progress_matter", stop=True):
    """An empty file gains two disputes and two needs in one saved turn."""
    message = (
        "The family disputes my ownership share. Separately, they blocked my shop access."
    )
    system = "Recorded principles for a controlled test."
    prompt = Prompt(message, system, "controlled_legal_brain")
    identity = LoopIdentity(
        matter_id, actor, "progress_turn", digest({
            "user": message, "system": system, "operation": prompt.operation,
        }), "b" * 64, "c" * 64, 1, LoopMode.SYNTHETIC,
    )
    source = {"id": identity.matter_id, "advocate_id": identity.advocate_id, "threads": []}
    brief = {
        "matter_id": identity.matter_id,
        "advocate_id": identity.advocate_id,
        "source_record_json": json.dumps(source),
        "selected_issue_ids": [],
        "snapshot_id": fingerprint(source),
    }
    record = add(LoopRecord(identity), StepKind.START, {
        "context": {"schema": 1, "system": system, "brief": brief},
        "original_instruction": capture_original_instruction(prompt),
        "scope_identity": digest({"requested_issue_ids": []}),
        "private": SECRET,
    })
    created = []
    for index, (label, quote) in enumerate((
        ("Ownership share", "family disputes my ownership share"),
        ("Shop access", "they blocked my shop access"),
    ), 1):
        thread_id = dispute_identity(identity.matter_id, identity.turn_id, quote, label)
        created.append(thread_id)
        call_id = f"create-{index}"
        record = add(record, StepKind.TOOL_STARTED, {
            "call": {"call_id": call_id, "name": "create_dispute",
                     "arguments": {"label": label, "quoted": quote}},
            "private": SECRET,
        })
        mutation = f"{index + 1:064x}"
        envelope = ToolEnvelope(
            "create_dispute", WRITE_VERSION, ToolKind.MATTER, ToolOutcome.RESULTS,
            Availability.AVAILABLE, Assessment.NOT_ASSESSED,
            {"matter_id": identity.matter_id,
             "matter_version": identity.matter_version + len(record.events),
             "snapshot": mutation},
            {"operation": "create_dispute", "changed_fields": (
                ["threads", "facts"] if index == 1 else ["threads"]
            ),
             "thread_id": thread_id,
             "fact_id": assertion_identity(identity.matter_id, identity.turn_id, message),
             "unassessed": True, "merged_existing": False,
             "selected_span": quote, "asserted_only": True},
            "A source-bound file change; the assertions are not established facts.",
        )
        record = add(record, StepKind.TOOL_RETURNED, {
            "call_id": call_id, "receipt": json.loads(envelope.wire()),
            "mutation_identity": mutation, "checked_snapshot": "f" * 64,
            "private": SECRET,
        })
    for index, thread_id in enumerate(created, 1):
        call_id = f"requirements-{index}"
        record = add(record, StepKind.TOOL_STARTED, {
            "call": {"call_id": call_id, "name": "record_requirements",
                     "arguments": {"thread_id": thread_id}}, "private": SECRET,
        })
        envelope = ToolEnvelope(
            "record_requirements", "captured-source-requirements-v1",
            ToolKind.MATTER, ToolOutcome.RESULTS, Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {"matter_id": identity.matter_id, "matter_version": len(record.events),
             "snapshot": "d" * 64, "source_version": "generation-1"},
            {"thread_id": thread_id, "requirements": [{
                "need": SECRET, "why": SECRET, "span": "Exact source words",
                "source": "source", "locator": f"source:{index}", "force": "required",
                "source_identity": "e" * 64, "context_identity": "f" * 64,
            }], "states_derived": True, "facts_established": False,
             "legal_interpretation": "not_assessed"},
            "A captured source proposal, not an independently reviewed need.",
        )
        record = add(record, StepKind.TOOL_RETURNED, {
            "call_id": call_id, "receipt": json.loads(envelope.wire()),
            "mutation_identity": "d" * 64, "private": SECRET,
        })
    if stop:
        record = add(record, StepKind.STOP, {"reason": StopReason.BUDGET.value})
    return record, tuple(created)


def save(client, record):
    from nm.app.api import application

    matter = Matter(
        id=record.identity.matter_id,
        advocate_id=record.identity.advocate_id,
        title="Recorded-work presentation test",
        version=1,
        loop_records=(record,),
    )
    application().store.commit(matter, expected_version=0)
    return matter


def base(record):
    return f"/api/matters/{record.identity.matter_id}/loops/{record.identity.turn_id}"


def frames(response):
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_every_stage_and_stop_projects_plain_words_without_private_payload():
    record = work(stop=False)
    projected = set()
    for kind in StepKind:
        if kind in (StepKind.START, StepKind.STOP):
            continue
        variant = add(record, kind, {"text": SECRET})
        row = project_event(variant, len(variant.events))
        assert row["state"] == "working"
        assert SECRET not in json.dumps(row)
        projected.add(kind)
    assert projected == set(StepKind) - {StepKind.START, StepKind.STOP}
    stops = set()
    for reason in StopReason:
        variant = add(record, StepKind.STOP, {"reason": reason.value, "answer": SECRET})
        row = project_event(variant, len(variant.events))
        assert row["working_not_advice"] is True
        assert SECRET not in json.dumps(row)
        assert row["state"] in {"requires_checks", "stopped"}
        assert row["label"] and row["label"].endswith(".")
        stops.add(reason)
    assert stops == set(StopReason)


def test_source_linked_dispute_receipts_have_neutral_saved_and_streamed_stages(client):
    record = scoped_work()
    saved = progress(record)
    assert [saved["events"][index]["dispute_index"] for index in (2, 4)] == [1, 2]
    assert all(saved["events"][index]["label"] == REQUIREMENTS_STAGE
               for index in (2, 4))
    assert SECRET not in json.dumps(saved)
    save(client, record)
    served = client.get(base(record))
    stream = client.get(base(record) + "/progress?follow=false")
    assert served.status_code == stream.status_code == 200
    assert served.json()["events"] == frames(stream) == saved["events"]
    assert SECRET not in served.text + stream.text
    resumed = client.get(base(record) + "/progress?follow=false",
                         headers={"Last-Event-ID": cursor_at(record, 3)})
    assert [row["sequence"] for row in frames(resumed)] == [4, 5, 6]
    assert frames(resumed)[1]["dispute_index"] == 2


def test_two_new_disputes_in_the_opening_turn_keep_their_saved_streamed_scope(client):
    record, created = opening_work()
    saved = progress(record)
    assert [row["issue_id"] for row in saved["scope"]["disputes"]] == list(created)
    assert [row["label"] for row in saved["scope"]["disputes"]] == [
        "Ownership share", "Shop access",
    ]
    assert [saved["events"][index]["dispute_index"] for index in (6, 8)] == [1, 2]
    assert SECRET not in json.dumps(saved)
    save(client, record)
    served = client.get(base(record))
    stream = client.get(base(record) + "/progress?follow=false")
    assert served.status_code == stream.status_code == 200
    assert served.json()["events"] == frames(stream) == saved["events"]
    resumed = client.get(base(record) + "/progress?follow=false",
                         headers={"Last-Event-ID": cursor_at(record, 7)})
    assert [row["sequence"] for row in frames(resumed)] == [8, 9, 10]
    assert frames(resumed)[1]["dispute_index"] == 2


def test_actual_opposition_receipt_marks_one_dispute_but_not_private_words(tmp_path):
    from tests.test_opposition_work_is_three_distinct_private_source_tasks import (
        child_script,
        fixture,
        run,
    )

    _store, model, brain, _dispatcher = fixture(tmp_path)
    model.tool_call.side_effect = child_script(("oppose_early", "oppose_full"))
    output = run(brain)
    rows = progress(output.record)["events"]
    opposed = [row for row in rows if row["label"] == OPPOSITION_STAGE]
    assert len(opposed) == 2
    assert [row["dispute_index"] for row in opposed] == [1, 1]
    assert all(row["working_not_advice"] is True for row in opposed)
    assert "The notice condition" not in json.dumps(rows)
    assert "Critically test" not in json.dumps(rows)
    assert all(sse_frame(row) for row in opposed)


def test_typed_source_read_stays_shared_and_candidate_set_aside_is_not_progress():
    from nm.Archives.legal_brain.retrieve.tool_sources import SourceCapture, source_envelope
    from tests.test_independent_claim_verifier import finding

    record = scoped_work(stop=False)
    law = finding()
    envelope = source_envelope(
        "read_provision", "foundation-dated-v3", "dated provision owner",
        "source-generation", (), {"coverage": "answered"},
        capture=SourceCapture(findings=(law,)), reason="Applicability not assessed.",
    )
    record = add(record, StepKind.TOOL_STARTED, {"call": {
        "call_id": "section", "name": "read_provision",
        "arguments": {"act": "Act", "section": "1", "as_of": "2026-09-28"},
    }})
    record = add(record, StepKind.TOOL_RETURNED, {
        "call_id": "section", "receipt": json.loads(envelope.wire()),
    })
    source = project_event(record, len(record.events))
    assert source["label"] == PROVISION_STAGE
    assert "dispute_index" not in source
    assert sse_frame(source)
    bad = json.loads(envelope.wire())
    bad["tool"] = "read_paragraph"
    forged = add(replace(record, events=record.events[:-1]), StepKind.TOOL_RETURNED, {
        "call_id": "section", "receipt": bad,
    })
    assert project_event(forged, len(forged.events))["label"] != AUTHORITY_STAGE
    paragraph = source_envelope(
        "read_paragraph", "owner-wrappers-v1", "exact paragraph reader",
        "source-generation", (), {},
        capture=SourceCapture(windows=({
            "locator": "case:p1", "text": "The court's exact words.",
            "source_kind": "authority", "source_version": "source-generation",
            "legal_metadata": "not_assessed", "missing": ["binding", "treatment"],
        },)), reason="The passage has not been assessed.",
    )
    record = add(record, StepKind.TOOL_STARTED, {"call": {
        "call_id": "paragraph", "name": "read_paragraph",
        "arguments": {"locator": "case:p1"},
    }})
    record = add(record, StepKind.TOOL_RETURNED, {
        "call_id": "paragraph", "receipt": json.loads(paragraph.wire()),
    })
    authority = project_event(record, len(record.events))
    assert authority["label"] == AUTHORITY_STAGE
    assert "dispute_index" not in authority
    assert sse_frame(authority)
    # The model's private candidate can propose a set-aside, but no checked
    # disposition event exists in this journal to project as completed work.
    candidate = add(record, StepKind.TOOL_STARTED, {"call": {
        "call_id": "candidate", "name": "propose_working_record", "arguments": {},
    }})
    candidate = add(candidate, StepKind.TOOL_RETURNED, {
        "call_id": "candidate", "receipt": json.loads(ToolEnvelope(
            "propose_working_record", "source-owned-working-record-v1",
            ToolKind.CONTROL, ToolOutcome.RESULTS, Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {"operation": "propose_working_record", "turn_id": record.identity.turn_id},
            {"candidate": {"entries": [{"disposition": "set_aside", "analysis": SECRET}]}},
            "Private candidate; not independently reviewed.",
        ).wire()),
    })
    proposed = project_event(candidate, len(candidate.events))
    assert proposed["label"] == "A material check was recorded."
    assert SECRET not in json.dumps(progress(candidate))


def test_whole_progress_checks_one_historic_scope_even_with_many_dispute_events(monkeypatch):
    from nm.Archives.legal_brain.communicate import loop_progress

    record, _created = opening_work()
    actual = loop_progress.recorded_scope
    calls = []

    def counted(saved):
        calls.append(saved.identity.fingerprint)
        return actual(saved)

    monkeypatch.setattr(loop_progress, "recorded_scope", counted)
    rows = progress(record)["events"]
    assert len(calls) == 1
    assert [rows[index]["dispute_index"] for index in (6, 8)] == [1, 2]
    assert project_event(record, 7)["dispute_index"] == 1
    assert len(calls) == 2, "A standalone projector still checks the sealed record itself"


def test_actual_controlled_first_turn_binds_new_disputes_to_the_saved_progress(tmp_path):
    from nm.shared.model_port import ToolCall
    from nm.work_the_file.write_tools import write_tools
    from tests.test_the_controlled_brain_is_actually_wired import _brain
    from tests.test_the_loop_records_work_before_using_it import _limits, _response

    store, model, brain = _brain(tmp_path)
    brain.registry = brain.registry.extend(write_tools(store))
    brain._runner._tools = brain.registry
    message = "My share is disputed. The shop was separately blocked."
    proposals = (
        ("Ownership share", "My share is disputed"),
        ("Shop access", "The shop was separately blocked"),
    )

    def respond(*_args, **_kwargs):
        index = model.tool_call.call_count - 1
        if index < len(proposals):
            label, quoted = proposals[index]
            return _response(ToolCall(f"create-{index}", "create_dispute",
                                      {"label": label, "quoted": quoted}))
        return _response(ToolCall("done", "submit", {"answer": "Unchecked proposal."}))

    model.tool_call.side_effect = respond
    outcome = brain.run(matter_id="mat_loop", turn_id="opening_disputes",
                        message=message, limits=_limits())
    matter = store.load("mat_loop")
    assert len(matter.threads) == 2
    assert matter.loop_records == (outcome.record,)
    scope = recorded_scope(outcome.record)
    assert [row["issue_id"] for row in scope["disputes"]] == [
        thread.id for thread in matter.threads
    ]
    assert [row["label"] for row in scope["disputes"]] == [
        "Ownership share", "Shop access",
    ]
    assert all(not thread.assessed for thread in matter.threads)


@pytest.mark.parametrize("tamper", [
    "uncommitted", "wrong_call", "wrong_mutation", "wrong_thread", "wrong_quote",
    "wrong_version", "wrong_fields", "missing_original", "narrowed_scope", "unquoted_source",
])
def test_opening_scope_cannot_borrow_model_only_or_forged_dispute(tamper):
    record, created = opening_work(stop=False)
    if tamper == "uncommitted":
        record = replace(record, events=record.events[:2])
    elif tamper == "unquoted_source":
        proposed = "Unspoken additional allegation"
        raw_call = json.loads(json.dumps(record.events[1].payload))
        raw_call["call"]["arguments"]["quoted"] = proposed
        record = reseal(record, 1, raw_call)
        raw_receipt = json.loads(json.dumps(record.events[2].payload))
        raw_receipt["receipt"]["data"]["thread_id"] = dispute_identity(
            record.identity.matter_id, record.identity.turn_id,
            proposed, raw_call["call"]["arguments"]["label"],
        )
        raw_receipt["receipt"]["data"]["selected_span"] = proposed
        record = reseal(record, 2, raw_receipt)
    elif tamper in {"wrong_call", "wrong_mutation", "wrong_thread", "wrong_version",
                    "wrong_fields"}:
        raw = dict(record.events[2].payload)
        if tamper == "wrong_call":
            raw["call_id"] = "another-call"
        elif tamper == "wrong_mutation":
            raw["mutation_identity"] = "0" * 64
        else:
            receipt = json.loads(json.dumps(raw["receipt"]))
            if tamper == "wrong_thread":
                receipt["data"]["thread_id"] = "another-thread"
            elif tamper == "wrong_fields":
                receipt["data"]["changed_fields"] = ["threads", "permissions"]
            else:
                receipt["receipt"]["matter_version"] += 1
            raw["receipt"] = receipt
        record = reseal(record, 2, raw)
    else:
        raw = dict(record.events[0].payload)
        if tamper == "wrong_quote":
            original = dict(raw["original_instruction"])
            original["text"] = "Words without the alleged ownership dispute."
            raw["original_instruction"] = original
        elif tamper == "missing_original":
            raw.pop("original_instruction")
        else:
            raw["scope_identity"] = "0" * 64
        record = reseal(record, 0, raw)
    scoped = recorded_scope(record)["disputes"]
    assert created[0] not in {row["issue_id"] for row in scoped}
    if tamper == "unquoted_source":
        assert scoped == [{"issue_id": created[1], "label": "Shop access"}]


def test_uncommitted_or_unbound_requirements_cannot_claim_dispute_progress():
    record = scoped_work(stop=False)
    only_started = LoopRecord(record.identity, record.events[:2])
    assert all("dispute_index" not in row for row in progress(only_started)["events"])
    bad = add(only_started, StepKind.TOOL_RETURNED, {
        **record.events[2].payload, "mutation_identity": "wrong",
    })
    assert project_event(bad, 3)["label"] != REQUIREMENTS_STAGE
    assert "dispute_index" not in project_event(bad, 3)
    wrong_version = json.loads(json.dumps(record.events[2].payload))
    wrong_version["receipt"]["version"] = "unreviewed-other-tool-version"
    mismatched = add(only_started, StepKind.TOOL_RETURNED, wrong_version)
    assert "dispute_index" not in project_event(mismatched, 3)
    forged = project_event(record, 3)
    forged["label"] = SECRET
    with pytest.raises(ValueError):
        sse_frame(forged)


def test_unknown_terminal_outcome_cannot_be_presented_as_success():
    row = project_event(add(work(stop=False), StepKind.STOP, {"reason": SECRET}), 4)
    assert row["state"] == "stopped"
    assert "not been established" in row["label"]
    assert SECRET not in json.dumps(row)


@pytest.mark.parametrize("sequence", [0, -1, True, 99, "1"])
def test_no_stage_is_returned_for_an_invalid_sequence(sequence):
    with pytest.raises(InvalidProgressCursor):
        project_event(work(), sequence)


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "1",
        "01." + "a" * 64,
        "-1." + "a" * 64,
        "999." + "a" * 64,
        "1." + "a" * 64 + "\nevent: advice",
        "1." + "a" * 64,
    ],
)
def test_resume_refuses_malformed_foreign_and_injected_cursors(cursor):
    with pytest.raises(InvalidProgressCursor):
        resume_position(work(), cursor)


def test_resume_is_bound_to_the_actual_saved_event_and_work_identity():
    record = work()
    assert resume_position(record, None) == 0
    for number in range(len(record.events) + 1):
        assert resume_position(record, cursor_at(record, number)) == number
    foreign = work(turn_id="different")
    with pytest.raises(InvalidProgressCursor):
        resume_position(foreign, cursor_at(record, 2))


@pytest.mark.parametrize("mutation", ["label", "extra", "state", "working", "time", "sequence"])
def test_sse_transport_refuses_a_second_channel_for_unverified_model_output(mutation):
    row = project_event(work(), 1)
    if mutation == "extra":
        row["answer"] = SECRET
    else:
        key, value = {
            "label": ("label", SECRET),
            "state": ("state", "approved"),
            "working": ("working_not_advice", False),
            "time": ("at", "2026-09-27T10:00:00"),
            "sequence": ("sequence", 0),
        }[mutation]
        row[key] = value
    with pytest.raises(ValueError):
        sse_frame(row)


def test_a_safe_label_cannot_be_relabelled_as_another_stage_state_or_sequence():
    row = project_event(work(), 4)
    row["state"] = "working"
    with pytest.raises(ValueError):
        sse_frame(row)
    row = project_event(work(), 1)
    row["cursor"] = cursor_at(work(), 2)
    with pytest.raises(InvalidProgressCursor):
        sse_frame(row)


def test_saved_stages_are_actually_served_with_authentication_and_owned_scope(client):
    record = work()
    save(client, record)
    listing = client.get(base(record).rsplit("/", 1)[0])
    assert listing.status_code == 200
    assert listing.json()["loops"][0]["result_state"] == "not_released"
    served = client.get(base(record))
    assert served.status_code == 200
    assert served.json() == progress(record)
    assert SECRET not in served.text
    outsider = client.sign_in("other", fresh=True)
    foreign = outsider.get(base(record))
    missing = outsider.get(base(record).replace("progress_matter", "missing_matter"))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert client.get(base(record).replace("progress_turn", "missing_turn")).status_code == 404
    assert client.post("/api/logout").status_code == 200
    assert client.get(base(record)).status_code == 401
    assert client.get(base(record) + "/progress?follow=false").status_code == 401


def test_served_sse_is_only_saved_plain_progress_not_raw_or_unreleased_work(client):
    record = work()
    save(client, record)
    response = client.get(base(record) + "/progress?follow=false")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert frames(response) == progress(record)["events"]
    assert SECRET not in response.text
    assert "event: advice" not in response.text
    assert "proposal" not in response.text and "model_text" not in response.text
    # Constructing an event is not committing it. A memory-only event must not
    # appear on the real sealed-store route.
    uncommitted = add(work(stop=False), StepKind.TOOL_STARTED, {"text": SECRET})
    assert uncommitted.events[-1].fingerprint not in response.text


def test_actual_sse_resume_uses_correlated_cursor_without_replaying_prior_stages(client):
    record = work()
    save(client, record)
    resumed = client.get(
        base(record) + "/progress?follow=false", headers={"Last-Event-ID": cursor_at(record, 2)}
    )
    assert resumed.status_code == 200
    assert [row["sequence"] for row in frames(resumed)] == [3, 4]
    # Browser EventSource retains its initial query while the reconnect header
    # advances. The header wins; an old query is not a false conflict.
    resumed = client.get(
        base(record) + "/progress",
        params={"follow": "false", "after": cursor_at(record, 1)},
        headers={"Last-Event-ID": cursor_at(record, 3)},
    )
    assert resumed.status_code == 200
    assert [row["sequence"] for row in frames(resumed)] == [4]
    backwards = client.get(
        base(record) + "/progress",
        params={"follow": "false", "after": cursor_at(record, 3)},
        headers={"Last-Event-ID": cursor_at(record, 1)},
    )
    assert backwards.status_code == 409
    forged = client.get(
        base(record) + "/progress?follow=false", headers={"Last-Event-ID": "2." + "e" * 64}
    )
    assert forged.status_code == 409 and not frames(forged)


def test_route_refuses_a_record_transplanted_between_matters(client):
    from nm.app.api import application

    record = work(matter_id="different_matter")
    foreign = Matter(
        id="progress_matter",
        advocate_id="adv_demo",
        title="Foreign journal",
        version=1,
        loop_records=(record,),
    )
    application().store.commit(foreign, expected_version=0)
    for suffix in ("", "/progress?follow=false"):
        assert (
            client.get("/api/matters/progress_matter/loops/progress_turn" + suffix).status_code
            == 503
        )
    assert client.get("/api/matters/progress_matter/loops").status_code == 503


def collect_stream(*, disconnect_after=None, revoke_after=None, owner_lost_after=None):
    """Drive the actual route generator so buffering cannot hide its checks."""
    from nm.Archives.legal_brain.communicate.loop_progress_api import router

    record = work()
    count = [0]

    def owned(matter_id, actor):
        if owner_lost_after is not None and count[0] >= owner_lost_after:
            raise HTTPException(404, "no such matter")
        assert matter_id == record.identity.matter_id and actor == record.identity.advocate_id
        return Matter(id=matter_id, advocate_id=actor, title="Owned", loop_records=(record,))

    def current(_request, _actor):
        return revoke_after is None or count[0] < revoke_after

    class Request:
        async def is_disconnected(self):
            return disconnect_after is not None and count[0] >= disconnect_after

    routes = router(owned=owned, signed_in=lambda: "adv_demo", session_current=current)
    endpoint = next(route.endpoint for route in routes.routes if route.path.endswith("/progress"))

    async def run():
        response = await endpoint(
            Request(),
            "progress_matter",
            "progress_turn",
            "adv_demo",
            follow=False,
            last_event_id=None,
            after=None,
        )
        collected = []
        async for item in response.body_iterator:
            collected.append(item)
            count[0] += 1
        return collected

    return asyncio.run(run())


@pytest.mark.parametrize("reason", ["disconnected", "revoked", "owner_lost"])
def test_every_frame_rechecks_liveness_and_scope_after_the_previous_frame(reason):
    kwargs = {
        "disconnected": "disconnect_after",
        "revoked": "revoke_after",
        "owner_lost": "owner_lost_after",
    }
    chunks = collect_stream(**{kwargs[reason]: 1})
    assert len(chunks) == 1
    assert SECRET.encode() not in b"".join(chunks)
    assert b'"sequence":1' in chunks[0]


def test_disconnected_or_logged_out_stream_has_no_first_frame():
    assert collect_stream(disconnect_after=0) == []
    assert collect_stream(revoke_after=0) == []
