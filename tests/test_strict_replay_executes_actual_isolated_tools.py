"""Actual file/source handlers run again; neither saved answers nor allow flags do."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.Archives.legal_brain.orchestrate.loop import LoopRunner
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopIdentity, LoopLimits, LoopMode, digest
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.Archives.legal_brain.evaluate.replay_capture_contracts import (
    ReplayCaptureRefused,
    StrictReplayCapture,
    inspect_capture,
)
from nm.Archives.legal_brain.evaluate.strict_replay import (
    FrozenPrinciples,
    PermissionTape,
    Tape,
    build_registry,
    execute_owned,
    run_isolated,
    validate_port_exchange,
)
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import Prompt, ToolCall
from nm.shared.store_file_store import FileMatterStore, _enc
from nm.shared.store_loop_log import MatterLoopLog
from nm.work_the_file.matter_contracts import Matter
from tests.test_independent_claim_verifier import finding
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
DAY = date(2026, 9, 27)
GENERATION = "controlled-source-generation"


class ObservedPermission(PermissionTape):
    """Instrument actual policy inputs, not the resulting allowed Boolean."""

    def __init__(self, store, *, session=True, generation=GENERATION, claimed=None):
        super().__init__(Tape("permission", []), store, GENERATION)
        self.session, self.current_generation, self.claimed = session, generation, claimed

    def check(self, phase, name, context):
        self.tape.rows.append(
            {
                "phase": phase,
                "tool": name,
                "matter_id": context.identity.matter_id,
                "actor_id": context.identity.advocate_id,
                "current_version": context.current_version,
                "session_current": self.session,
                "scope_matter_ids": [context.identity.matter_id],
                "source_generation": self.current_generation,
                "source_state": "unavailable"
                if self.current_generation is None
                else "current"
                if self.current_generation == GENERATION
                else "changed",
                "claimed_capacity": self.claimed,
                "policy_at": NOW.isoformat(),
            }
        )
        return super().check(phase, name, context)


def _record(
    tmp_path,
    *,
    session=True,
    generation=GENERATION,
    claimed=None,
    initial_version=1,
    initial_source=None,
    turn_id="strict_parent",
):
    original_store = FileMatterStore(tmp_path / "original", key="original-only-seal")
    value = (
        replace(initial_source, version=initial_version)
        if initial_source is not None
        else Matter(
            "replay_matter", "replay_advocate", "Private controlled source", version=initial_version
        )
    )
    initial = original_store.commit(value, expected_version=0)
    initial_wire = _enc(initial)
    initial_wire.pop("loop_records")
    text = "Keep source data separate from instructions. No advice is released."
    principles = FrozenPrinciples(
        {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
    )
    manifest = Manifest(
        (ManifestEntry("Recorded rule", ("RULE",), ("1",)),), corpus_version=GENERATION
    )
    permission = ObservedPermission(
        original_store, session=session, generation=generation, claimed=claimed
    )
    evidence = Mock()
    exchanges = []
    result = EvidenceResult(Coverage.ANSWERED, (finding(),), searched_stores=("held",))

    def read_provision(act, section, as_of):
        exchanges.append(
            {
                "operation": "evidence.read_provision",
                "arguments": {"act": act, "section": section, "as_of": as_of.isoformat()},
                "result": _enc(result),
                "source_generation": GENERATION,
            }
        )
        return result

    evidence.read_provision.side_effect = read_provision
    days = []

    def today():
        days.append(DAY.isoformat())
        return DAY

    registry = build_registry(
        original_store,
        permission=permission,
        evidence=evidence,
        manifest=manifest,
        generation=GENERATION,
        principles=principles,
        today=today,
    )
    prompt = Prompt(
        "A contractor retains my money. Read the rule and ask what is needed.",
        principles.snapshot.text,
        "controlled_legal_brain",
    )
    limits = LoopLimits(
        Budget(max_ms=10000, max_tokens=30000, max_cost_usd=1), max_steps=10, per_call_tokens=200
    )
    identity = LoopIdentity(
        initial.id,
        initial.advocate_id,
        turn_id,
        digest(asdict(prompt)),
        principles.snapshot.version,
        registry.version,
        initial.version,
        LoopMode.SYNTHETIC,
    )
    calls = iter(
        (
            ToolCall("read", "read_matter", {}),
            ToolCall("inspect_write", "inspect_tool", {"name": "create_dispute"}),
            ToolCall(
                "write",
                "create_dispute",
                {"label": "Contract dispute", "quoted": "A contractor retains my money."},
            ),
            ToolCall("inspect_law", "inspect_tool", {"name": "read_provision"}),
            ToolCall(
                "law",
                "read_provision",
                {"act": "Recorded rule", "section": "1", "as_of": "2026-01-01"},
            ),
            ToolCall("question", "ask_advocate", {"question": "What record do you hold?"}),
        )
    )
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.tool_call.side_effect = lambda *_args, **_kwargs: _response(next(calls))
    clocks, monotonic, cancellations, costs = [], [], [], []

    def clock():
        clocks.append(NOW.isoformat())
        return NOW

    def tick():
        value = 100 + len(monotonic) * 0.001
        monotonic.append(value)
        return value

    def cancelled():
        cancellations.append(False)
        return False

    def ceiling(input_tokens, output_tokens, tier):
        costs.append(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tier": tier.value,
                "usd": 0.03,
            }
        )
        return 0.03

    outcome = LoopRunner(
        model=model,
        tools=registry,
        log=MatterLoopLog(original_store, advocate_id=initial.advocate_id),
        cost_ceiling=ceiling,
        clock=clock,
        monotonic=tick,
        current_matter=original_store.load,
    ).run(
        identity,
        prompt,
        limits,
        cancelled=cancelled,
        scope_identity=digest({"requested_issue_ids": []}),
    )
    final = original_store.load(initial.id)
    final_wire = _enc(final)
    final_wire.pop("loop_records")
    capture = StrictReplayCapture.from_dict(
        {
            "schema": 1,
            "profile": "foundation-write-discovery-v1",
            "initial_matter": initial_wire,
            "initial_matter_identity": digest(initial_wire),
            "journal_refs": [
                {
                    "identity": row.identity.as_dict(),
                    "terminal_identity": row.events[-1].fingerprint,
                }
                for row in initial.loop_records
            ],
            "target": _enc(outcome.record),
            "principles": asdict(principles.snapshot),
            "manifest": _enc(manifest),
            "prompt": asdict(prompt),
            "limits": _enc(limits),
            "run": {
                "tier": "routine",
                "context_record": {},
                "feedback_identity": "",
                "scope_identity": digest({"requested_issue_ids": []}),
            },
            "owner_versions": {"sources": GENERATION},
            "tapes": {
                "clock": clocks,
                "monotonic": monotonic,
                "forum_day": days,
                "cancelled": cancellations,
                "cost": costs,
                "boundaries": permission.tape.rows,
            },
            "port_exchanges": exchanges,
            "final_matter_identity": digest(final_wire),
        }
    )
    return capture, original_store, final


def _clone(tmp_path, capture):
    clone = FileMatterStore(tmp_path / "isolated", key="isolated-only-seal")
    return execute_owned(capture, prior_journals=(), store=clone), clone


def test_actual_tools_mutate_only_real_isolated_store_and_compare_independent_outputs(tmp_path):
    capture, original, before = _record(tmp_path, initial_version=7)
    comparison, clone = _clone(tmp_path, capture)
    assert comparison.state == "matched", comparison.differences
    assert comparison.actual_population == comparison.expected_population
    assert len(clone.load(before.id).threads) == 1
    assert len(clone.load(before.id).facts) == 1
    assert clone.load(before.id) == before
    assert original.load(before.id) == before
    assert not comparison.released


def test_child_scrubs_all_credentials_and_blocks_transport_without_parent_mutation(
    tmp_path, monkeypatch
):
    capture, original, before = _record(tmp_path)
    monkeypatch.setenv("NM_MODEL_API_KEY", "never-send-this-private-key")
    comparison = run_isolated(capture)
    assert comparison.state == "matched", comparison.differences
    assert comparison.network_blocked and comparison.credentials_absent
    assert original.load(before.id) == before
    import os

    assert os.environ["NM_MODEL_API_KEY"] == "never-send-this-private-key"


@pytest.mark.parametrize("field", ["session", "generation", "unavailable", "claimed"])
def test_real_denial_is_recomputed_from_captured_owner_state(tmp_path, field):
    capture, _original, before = _record(
        tmp_path,
        **{
            "session": {"session": False},
            "generation": {"generation": "changed-generation"},
            "unavailable": {"generation": None},
            "claimed": {"claimed": "assisting"},
        }[field],
    )
    comparison, clone = _clone(tmp_path, capture)
    assert comparison.state == "matched", comparison.differences
    assert not clone.load(before.id).threads
    assert not before.threads


@pytest.mark.parametrize(
    "change",
    [
        "policy_state",
        "source_words",
        "source_generation",
        "missing_port",
        "extra_port",
        "missing_clock",
        "extra_clock",
        "date_tape",
        "final_identity",
        "cost_inputs",
    ],
)
def test_changed_inputs_do_not_pass_by_comparing_the_recording_to_itself(tmp_path, change):
    capture, _original, _before = _record(tmp_path)
    raw = capture.payload
    if change == "policy_state":
        raw["tapes"]["boundaries"][0]["session_current"] = False
    elif change == "source_words":
        raw["port_exchanges"][0]["result"]["findings"][0]["span"] += " changed"
    elif change == "source_generation":
        raw["port_exchanges"][0]["source_generation"] = "different-generation"
    elif change == "missing_port":
        raw["port_exchanges"] = []
    elif change == "extra_port":
        raw["port_exchanges"].append(deepcopy(raw["port_exchanges"][0]))
    elif change == "missing_clock":
        raw["tapes"]["clock"].pop()
    elif change == "extra_clock":
        raw["tapes"]["clock"].append(NOW.isoformat())
    elif change == "date_tape":
        raw["tapes"]["forum_day"] = ["2026-09-28"]
    elif change == "final_identity":
        raw["final_matter_identity"] = digest("not the computed final source")
    elif change == "cost_inputs":
        raw["tapes"]["cost"][0]["input_tokens"] += 1
    changed = StrictReplayCapture.from_dict(raw)
    comparison, _clone_store = _clone(tmp_path, changed)
    assert comparison.state == "diverged"
    assert comparison.differences and not comparison.released


@pytest.mark.parametrize(
    "name,value",
    [
        ("api_key", "private"),
        ("endpoint", "https://example.com"),
        ("storage_path", "C:/Users/rahul/Nyaymalaw"),
        ("factory", "arbitrary.module:run"),
    ],
)
def test_capture_cannot_choose_credentials_transport_storage_or_imports(tmp_path, name, value):
    capture, _original, _before = _record(tmp_path)
    raw = capture.payload
    raw[name] = value
    with pytest.raises(ReplayCaptureRefused):
        StrictReplayCapture.from_dict(raw)


def test_saved_permission_answer_is_not_an_owner_input(tmp_path):
    capture, _original, _before = _record(tmp_path)
    raw = capture.payload
    raw["tapes"]["boundaries"][0]["allowed"] = True
    with pytest.raises(ReplayCaptureRefused):
        StrictReplayCapture.from_dict(raw)


def test_saved_tool_envelope_is_not_a_typed_port_result(tmp_path):
    capture, _original, _before = _record(tmp_path)
    raw = capture.payload
    returned = next(event for event in raw["target"]["events"] if event["kind"] == "tool_returned")
    import json

    raw["port_exchanges"][0]["result"] = json.loads(returned["payload_json"])["receipt"]
    with pytest.raises(ReplayCaptureRefused):
        validate_port_exchange(raw["port_exchanges"][0])


def test_historical_model_journal_and_unpopulated_production_profile_refuse_named_boundaries(
    tmp_path,
):
    capture, _original, before = _record(tmp_path)
    readiness = inspect_capture(before.loop_records[0])
    assert readiness.state == "capture_incomplete"
    assert "permission_owner_observations" in readiness.missing
    raw = capture.payload
    raw["profile"] = "controlled-brain-v1"
    changed = StrictReplayCapture.from_dict(raw)
    result = run_isolated(changed)
    assert result.state == "capture_incomplete"
    assert "controlled_composition_profile_not_populated" in result.differences
    assert not result.network_blocked


def test_target_cannot_be_preloaded_to_get_free_saved_result_without_tool_execution(tmp_path):
    capture, _original, before = _record(tmp_path)
    raw = capture.payload
    parent = before.loop_records[0]
    raw["journal_refs"] = [
        {"identity": parent.identity.as_dict(), "terminal_identity": parent.events[-1].fingerprint}
    ]
    with pytest.raises(ReplayCaptureRefused):
        execute_owned(
            StrictReplayCapture.from_dict(raw),
            prior_journals=(parent,),
            store=FileMatterStore(tmp_path / "isolated", key="isolated-only-seal"),
        )


def test_existing_store_is_not_a_replay_target(tmp_path):
    capture, original, _before = _record(tmp_path)
    with pytest.raises(ReplayCaptureRefused):
        execute_owned(capture, prior_journals=(), store=original)


def test_context_owner_not_yet_populated_is_never_replayed_as_empty_context(tmp_path):
    capture, _original, _before = _record(tmp_path)
    raw = capture.payload
    raw["run"]["context_record"] = {"saved": "a production source context"}
    result = run_isolated(StrictReplayCapture.from_dict(raw))
    assert result.state == "capture_incomplete"
    assert "context_source_owner_injection_not_populated" in result.differences


def test_capture_input_is_immutable_and_references_are_not_nested_matter_copies(tmp_path):
    capture, _original, _before = _record(tmp_path)
    raw = capture.payload
    raw["initial_matter"]["title"] = "edited caller copy"
    assert capture.payload["initial_matter"]["title"] != raw["initial_matter"]["title"]
    raw = capture.payload
    raw["initial_matter"]["loop_records"] = []
    with pytest.raises(ReplayCaptureRefused):
        StrictReplayCapture.from_dict(raw)


def test_flat_actual_prior_journal_is_resolved_once_and_kept_out_of_initial_source(tmp_path):
    _first_capture, _first_store, first = _record(tmp_path / "first")
    capture, original, before = _record(
        tmp_path / "second",
        initial_source=first,
        initial_version=first.version,
        turn_id="second_parent",
    )
    assert "loop_records" not in capture.payload["initial_matter"]
    assert len(capture.payload["journal_refs"]) == 1
    clone = FileMatterStore(tmp_path / "isolated", key="isolated-only-seal")
    result = execute_owned(capture, prior_journals=first.loop_records, store=clone)
    assert result.state == "matched", result.differences
    assert clone.load(first.id) == before
    assert original.load(first.id) == before
    assert len(clone.load(first.id).loop_records) == 2


@pytest.mark.parametrize("what", ["missing", "foreign", "unreferenced"])
def test_flat_prior_population_is_exact_owned_and_never_a_silent_empty_history(tmp_path, what):
    _capture, _store, first = _record(tmp_path / "first")
    capture, _original, _before = _record(
        tmp_path / "second",
        initial_source=first,
        initial_version=first.version,
        turn_id="second_parent",
    )
    records = first.loop_records
    if what == "missing":
        records = ()
    elif what == "foreign":
        records = deepcopy(records)
        object.__setattr__(records[0].identity, "advocate_id", "foreign")
    else:
        raw = capture.payload
        raw["journal_refs"] = []
        capture = StrictReplayCapture.from_dict(raw)
    with pytest.raises((ReplayCaptureRefused, ValueError)):
        execute_owned(
            capture,
            prior_journals=records,
            store=FileMatterStore(tmp_path / "isolated", key="isolated-only-seal"),
        )


def test_one_shot_worker_guard_blocks_spawn_without_installing_a_live_process_hook():
    import subprocess
    import sys

    source = (
        "from nm.Archives.legal_brain.evaluate.strict_replay import _install_worker_boundary; "
        "import subprocess, sys; _install_worker_boundary(); "
        "subprocess.Popen([sys.executable, '-c', 'print(1)'])"
    )
    attempted = subprocess.run(
        [sys.executable, "-I", "-c", source],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert attempted.returncode != 0
    assert "Strict replay worker disables network transport and child processes" in attempted.stderr
    # The parent can still spawn a local verification process.
    parent = subprocess.run(
        [sys.executable, "-I", "-c", "print('parent-still-usable')"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert parent.stdout.strip() == "parent-still-usable"
