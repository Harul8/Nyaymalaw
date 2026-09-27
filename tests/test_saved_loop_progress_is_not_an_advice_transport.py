"""P52: served, owned, committed stages cannot become an advice/trace channel."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from fastapi import HTTPException

from nm.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopMode,
    LoopRecord,
    StepKind,
    StopReason,
)
from nm.legal_brain.communicate.loop_progress import (
    InvalidProgressCursor,
    cursor_at,
    progress,
    project_event,
    resume_position,
    sse_frame,
)
from nm.work_the_file.matter_contracts import Matter

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
    from nm.legal_brain.communicate.loop_progress_api import router

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
