"""Capture real owner invocations, then execute real handlers in an isolated file."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest

from nm.legal_brain.understand.brain_context import ContextPolicy, ContextSession, assemble_brief
from nm.legal_brain.orchestrate.controlled_brain import EvaluationScope
from nm.legal_brain.orchestrate.controlled_generations import GenerationGuard
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.legal_brain.orchestrate.generations_port import GenerationUnavailable
from nm.legal_brain.orchestrate.loop import LoopRunner
from nm.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopLimits,
    LoopMode,
    LoopRecord,
    digest,
)
from nm.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.legal_brain.evaluate.replay_capture_contracts import ReplayCaptureRefused, ReplayProfile
from nm.legal_brain.evaluate.runtime_capture import (
    PURPOSE,
    SUFFIX,
    RuntimeCaptureOwner,
    is_capture_record,
)
from nm.legal_brain.evaluate.strict_replay import FrozenPrinciples, build_registry, run_isolated
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import Prompt, ToolCall
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter
from tests.test_independent_claim_verifier import finding
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
DAY = date(2026, 9, 27)


def admitted_runtime(tmp_path, *, prior=False, profile=ReplayProfile.FOUNDATION, context=False):
    store = FileMatterStore(tmp_path / "protected", key="controlled-capture-seal")
    initial = store.commit(
        Matter("owned_matter", "owned_actor", "Private account", version=1), expected_version=0
    )
    knowledge = tmp_path / "actual-knowledge"
    knowledge.mkdir()
    (knowledge / "owned.py").write_text('"""Actual controlled practice bytes."""', encoding="utf8")
    guard = GenerationGuard(knowledge_root=knowledge)
    scope = EvaluationScope(
        "explicit-controlled-approval",
        initial.advocate_id,
        frozenset({initial.id}),
        LoopMode.SYNTHETIC,
    )
    session_state = {"current": True}
    ticks = iter(100 + number * 0.001 for number in range(10000))
    owner = RuntimeCaptureOwner(
        store=store,
        scope=scope,
        guard=guard,
        session_current=lambda: session_state["current"],
        clock=lambda: NOW,
        monotonic=lambda: next(ticks),
        forum_day=lambda: DAY,
        cost_ceiling=lambda *_args: 0.03,
    )
    text = "Use only captured sources. No client advice is released."
    principles = FrozenPrinciples(
        {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
    )
    manifest = Manifest(
        (ManifestEntry("Held rule", ("RULE",), ("1",)),), corpus_version=guard.version
    )
    limits = LoopLimits(
        Budget(max_ms=10000, max_tokens=30000, max_cost_usd=1), max_steps=10, per_call_tokens=200
    )
    if prior:
        registry = build_registry(
            store,
            permission=Mock(),
            evidence=Mock(),
            manifest=manifest,
            generation=guard.version,
            principles=principles,
            today=lambda: DAY,
        )
        prompt = Prompt(
            "Earlier original account.", principles.snapshot.text, "controlled_legal_brain"
        )
        identity = LoopIdentity(
            initial.id,
            initial.advocate_id,
            "prior_actual_turn",
            digest(asdict(prompt)),
            principles.snapshot.version,
            registry.version,
            initial.version,
            scope.mode,
        )
        model = Mock(provider="scripted")
        model.resolved_model.return_value = "recorded-v1"
        model.tool_call.return_value = _response(
            ToolCall("prior_question", "ask_advocate", {"question": "What record is available?"})
        )
        # The actual neutral terminal is subject to real registry admission;
        # its permission owner observes the same native scope policy.
        preparation = owner.begin(initial.id, profile=profile)
        registry = build_registry(
            store,
            permission=preparation.permissions,
            evidence=preparation.evidence(Mock()),
            manifest=manifest,
            generation=guard.version,
            principles=principles,
            today=preparation.forum_day,
        )
        assert registry.version == identity.tools_version
        LoopRunner(
            model=model,
            tools=registry,
            log=owner.log,
            cost_ceiling=lambda *_args: 0.03,
            clock=lambda: NOW,
            monotonic=lambda: next(ticks),
            current_matter=store.load,
        ).run(identity, prompt, limits)
        initial = store.load(initial.id)
    capture = owner.begin(initial.id, profile=profile)
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.ANSWERED, (finding(),), searched_stores=("actual-held-owner",)
    )
    registry = build_registry(
        store,
        permission=capture.permissions,
        evidence=capture.evidence(evidence),
        manifest=manifest,
        generation=guard.version,
        principles=principles,
        today=capture.forum_day,
    )
    context_session = None
    if context:
        policy = ContextPolicy(max_tokens=30000, reserve_tokens=limits.per_call_tokens)
        brief = assemble_brief(
            initial, (), policy, advocate_id=initial.advocate_id, as_of=capture.forum_day()
        )
        context_session = ContextSession(
            principles.snapshot,
            registry.definitions,
            brief,
            provider="scripted",
            model="recorded-v1",
            policy=policy,
            tool_offer=registry.offer_state(),
        )
    prompt = Prompt(
        "A contractor retains my money. Read the held rule.",
        context_session.system if context_session is not None else principles.snapshot.text,
        "controlled_legal_brain",
    )
    identity = LoopIdentity(
        initial.id,
        initial.advocate_id,
        "actual_capture_target",
        digest(asdict(prompt)),
        principles.snapshot.version,
        registry.version,
        initial.version,
        scope.mode,
    )
    capture.bind(
        identity,
        prompt,
        limits,
        principles=principles.snapshot,
        manifest=manifest,
        context_session=context_session,
        scope_identity=digest({"requested_issue_ids": []}),
    )
    calls = iter(
        (
            ToolCall("file", "read_matter", {}),
            ToolCall("schema", "inspect_tool", {"name": "create_dispute"}),
            ToolCall(
                "write",
                "create_dispute",
                {"label": "Contract dispute", "quoted": "A contractor retains my money."},
            ),
            ToolCall("law_schema", "inspect_tool", {"name": "read_provision"}),
            ToolCall(
                "law", "read_provision", {"act": "Held rule", "section": "1", "as_of": "2026-01-01"}
            ),
            ToolCall("question", "ask_advocate", {"question": "Which documents do you hold?"}),
        )
    )
    model = Mock(provider="scripted")
    model.resolved_model.return_value = "recorded-v1"
    model.tool_call.side_effect = lambda *_args, **_kwargs: _response(next(calls))
    outcome = LoopRunner(
        model=model,
        tools=registry,
        log=owner.log,
        cost_ceiling=capture.cost_ceiling,
        clock=capture.clock,
        monotonic=capture.monotonic,
        current_matter=store.load,
    ).run(
        identity,
        prompt,
        limits,
        cancelled=lambda: capture.cancelled(lambda: False),
        session=context_session,
        scope_identity=digest({"requested_issue_ids": []}),
    )
    return owner, capture, outcome, session_state, knowledge, evidence


def test_runtime_producer_records_actual_owners_and_real_isolated_tools_match(tmp_path):
    owner, capture, outcome, _session, _knowledge, evidence = admitted_runtime(tmp_path)
    before = owner.store.load(outcome.record.identity.matter_id)
    saved = capture.finish(outcome)
    assert saved.readiness.ready
    assert owner.log.read(outcome.record.identity) == outcome.record
    assert owner.store.load(before.id).version == before.version + 2
    assert len(owner.store.load(before.id).threads) == 1
    assert saved.journal.identity.turn_id.endswith(SUFFIX)
    assert is_capture_record(saved.journal)
    assert not any(
        ":check:" in saved.journal.identity.turn_id or ":verify:" in saved.journal.identity.turn_id
        for _ in (0,)
    )
    assert saved.journal.events[0].payload["purpose"] == PURPOSE
    assert "spend" not in saved.journal.events[-1].payload
    assert "budget" not in saved.journal.events[0].payload
    assert evidence.read_provision.call_count == 1
    assert saved.capture.payload["port_exchanges"][0]["result"]["findings"]
    assert all("allowed" not in row for row in saved.capture.payload["tapes"]["boundaries"])
    comparison = run_isolated(saved.capture, prior_journals=saved.prior_journals)
    assert comparison.state == "matched", comparison.differences
    assert comparison.network_blocked and comparison.credentials_absent
    assert owner.store.load(before.id).version == before.version + 2
    assert not comparison.released


def test_capture_survives_new_owner_without_sidecars_or_nested_initial_journals(tmp_path):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(
        tmp_path, prior=True
    )
    saved = capture.finish(outcome)
    restarted = RuntimeCaptureOwner(
        store=FileMatterStore(owner.store._root, key="controlled-capture-seal"),
        scope=owner.scope,
        guard=owner.guard,
        session_current=lambda: True,
        clock=lambda: NOW,
        monotonic=lambda: 0,
        forum_day=lambda: DAY,
        cost_ceiling=lambda *_args: 0.03,
    )
    read = restarted.read(outcome.record.identity)
    assert read == saved
    assert len(read.prior_journals) == 1
    assert "loop_records" not in read.capture.payload["initial_matter"]
    assert set(read.capture.payload["journal_refs"][0]) == {"identity", "terminal_identity"}
    assert {path.name for path in owner.store._root.iterdir()} == {"matters", "metrics", "keys"}
    blob = owner.store._path(outcome.record.identity.matter_id).read_bytes()
    assert b"A contractor retains my money" not in blob
    assert b"captured-source-api-key" not in json.dumps(read.capture.payload).encode()
    comparison = run_isolated(read.capture, prior_journals=read.prior_journals)
    assert comparison.state == "matched", comparison.differences


def test_controlled_profile_is_stored_but_not_falsely_replay_ready(tmp_path):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(
        tmp_path, profile=ReplayProfile.CONTROLLED
    )
    saved = capture.finish(outcome)
    assert saved.readiness.state == "capture_incomplete"
    assert "controlled_composition_profile_not_populated" in saved.readiness.missing
    assert owner.read(outcome.record.identity) == saved
    comparison = run_isolated(saved.capture)
    assert comparison.state == "capture_incomplete"
    assert not comparison.released


@pytest.mark.parametrize("change", ["session", "source", "target", "later_work"])
def test_changed_owner_or_target_cannot_be_saved_as_trusted_capture(tmp_path, change):
    owner, capture, outcome, session, knowledge, _evidence = admitted_runtime(tmp_path)
    if change == "session":
        session["current"] = False
    elif change == "source":
        (knowledge / "owned.py").write_text('"""Changed owned bytes."""', encoding="utf8")
    elif change == "target":
        outcome = replace(
            outcome,
            record=LoopRecord(replace(outcome.record.identity, turn_id="foreign_target")),
        )
    else:
        matter = owner.store.load(outcome.record.identity.matter_id)
        owner.store.commit(
            replace(matter, title="Outside substantive mutation", version=matter.version + 1),
            expected_version=matter.version,
        )
    with pytest.raises((ReplayCaptureRefused, GenerationUnavailable)):
        capture.finish(outcome)
    assert not any(is_capture_record(row) for row in owner.store.load("owned_matter").loop_records)


def test_mid_capture_revocation_leaves_an_explicit_incomplete_native_start(tmp_path, monkeypatch):
    owner, capture, outcome, session, _knowledge, _evidence = admitted_runtime(tmp_path)
    append = owner.log.append

    def stop_after_start(identity, event):
        result = append(identity, event)
        session["current"] = False
        return result

    monkeypatch.setattr(owner.log, "append", stop_after_start)
    with pytest.raises(ReplayCaptureRefused):
        capture.finish(outcome)
    matter = owner.store.load("owned_matter")
    journal = next(row for row in matter.loop_records if is_capture_record(row))
    assert len(journal.events) == 1 and not journal.terminal
    assert owner.log.read(outcome.record.identity) == outcome.record
    session["current"] = True
    with pytest.raises(ReplayCaptureRefused, match="capture_incomplete"):
        owner.read(outcome.record.identity)


def test_read_revocation_and_key_erasure_never_remint_a_key(tmp_path):
    owner, capture, outcome, session, knowledge, _evidence = admitted_runtime(tmp_path)
    capture.finish(outcome)
    session["current"] = False
    with pytest.raises(ReplayCaptureRefused):
        owner.read(outcome.record.identity)
    session["current"] = True
    (knowledge / "owned.py").write_text('"""Withdrawn source generation."""', encoding="utf8")
    assert owner.read(outcome.record.identity).capture.payload["owner_versions"]["sources"] == (
        owner.guard.version
    )
    with pytest.raises(GenerationUnavailable):
        owner.begin("owned_matter")
    # Reset only this controlled source to its exact originally owned bytes.
    (knowledge / "owned.py").write_text('"""Actual controlled practice bytes."""', encoding="utf8")
    from nm.shared.store_envelope import KeyUnavailable

    key = owner.store._keys / "owned_matter.key"
    key.unlink()
    with pytest.raises(KeyUnavailable):
        owner.read(outcome.record.identity)
    assert not key.exists()


def test_runtime_capture_rejects_unprotected_storage_and_foreign_scope(tmp_path, monkeypatch):
    owner, _capture, outcome, _session, _knowledge, _evidence = admitted_runtime(tmp_path)
    insecure = FileMatterStore(tmp_path / "not-protected", key="legacy-test-seal")
    monkeypatch.setattr(insecure, "_sealer", None)
    with pytest.raises(ReplayCaptureRefused):
        RuntimeCaptureOwner(
            store=insecure,
            scope=owner.scope,
            guard=owner.guard,
            session_current=lambda: True,
            clock=lambda: NOW,
            monotonic=lambda: 0,
            forum_day=lambda: DAY,
            cost_ceiling=lambda *_args: 0.03,
        )
    with pytest.raises(ReplayCaptureRefused):
        owner.begin("foreign_matter")
    with pytest.raises(ReplayCaptureRefused):
        owner.read(replace(outcome.record.identity, advocate_id="foreign_actor"))
    with pytest.raises(ReplayCaptureRefused):
        owner.begin("owned_matter", profile="arbitrary.import.target")


def test_closed_capture_refuses_double_bind_finish_and_post_terminal_observations(tmp_path):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(tmp_path)
    with pytest.raises(ReplayCaptureRefused):
        capture.bind(
            outcome.record.identity,
            Prompt("Changed", "", ""),
            Mock(),
            principles=Mock(),
            manifest=Mock(),
        )
    capture.finish(outcome)
    for action in (
        lambda: capture.finish(outcome),
        capture.clock,
        capture.monotonic,
        capture.forum_day,
        lambda: capture.cancelled(lambda: False),
    ):
        with pytest.raises(ReplayCaptureRefused):
            action()
    assert owner.read(outcome.record.identity).readiness.ready


def test_historical_frozen_generation_replays_but_cannot_certify_current_advice(tmp_path):
    owner, capture, outcome, _session, knowledge, _evidence = admitted_runtime(tmp_path)
    saved = capture.finish(outcome)
    (knowledge / "owned.py").write_text('"""New current-world practice bytes."""', encoding="utf8")
    refreshed = RuntimeCaptureOwner(
        store=owner.store,
        scope=owner.scope,
        guard=GenerationGuard(knowledge_root=knowledge),
        session_current=lambda: True,
        clock=lambda: NOW,
        monotonic=lambda: 0,
        forum_day=lambda: DAY,
        cost_ceiling=lambda *_args: 0.03,
    )
    assert refreshed.guard.version != owner.guard.version
    historical = refreshed.read(outcome.record.identity)
    assert historical.capture == saved.capture
    assert historical.metadata["generation_binding"] == owner.guard.binding
    assert historical.metadata["generation_binding"] != refreshed.guard.binding
    comparison = run_isolated(historical.capture, prior_journals=historical.prior_journals)
    assert comparison.state == "matched", comparison.differences
    assert not comparison.released
    with pytest.raises(GenerationUnavailable):
        owner.begin("owned_matter")


@pytest.mark.parametrize("field", ["generation_binding", "context_policy", "scope"])
def test_capture_metadata_cannot_change_without_its_exact_admission_digest(tmp_path, field):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(tmp_path)
    saved = capture.finish(outcome)
    matter = owner.store.load("owned_matter")
    stop = saved.journal.events[-1].payload
    if field == "generation_binding":
        stop["metadata"][field]["coverage_manifest_sha256"] = "invented"
    elif field == "context_policy":
        stop["metadata"][field] = {"max_tokens": 12000, "reserve_tokens": 200}
    else:
        stop["metadata"][field]["approval_reference"] = "invented-other-approval"
    last = LoopEvent.create(
        2, saved.journal.events[-1].kind, NOW.isoformat(), stop, saved.journal.events[0].fingerprint
    )
    changed = LoopRecord(saved.journal.identity, (saved.journal.events[0], last))
    owner.store.commit(
        replace(
            matter,
            loop_records=tuple(
                changed if row.identity == changed.identity else row for row in matter.loop_records
            ),
            version=matter.version + 1,
        ),
        expected_version=matter.version,
    )
    with pytest.raises(ReplayCaptureRefused):
        owner.read(outcome.record.identity)


def test_actual_controlled_context_policy_and_full_initial_prefix_are_captured_not_replay_claimed(
    tmp_path,
):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(
        tmp_path, profile=ReplayProfile.CONTROLLED, context=True
    )
    saved = capture.finish(outcome)
    assert saved.metadata["context_policy"] == {"max_tokens": 30000, "reserve_tokens": 200}
    assert (
        saved.capture.payload["run"]["context_record"]
        == (outcome.record.events[0].payload["context"])
    )
    assert saved.capture.payload["run"]["context_record"]["system"]
    assert saved.capture.payload["tapes"]["forum_day"] == [DAY.isoformat()]
    assert "context_source_owner_injection_not_populated" in saved.readiness.missing
    assert owner.read(outcome.record.identity) == saved
    assert run_isolated(saved.capture).state == "capture_incomplete"
