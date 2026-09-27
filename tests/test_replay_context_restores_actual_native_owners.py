"""Recover actual captured context; execute native tools, never saved receipts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta

import pytest

from nm.legal_brain.understand.brain_context import ContextSession
from nm.legal_brain.retrieve.checklist_sources import bind_source_current
from nm.legal_brain.orchestrate.loop import LoopRunner
from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, digest
from nm.legal_brain.retrieve.manifest_sources import Manifest
from nm.legal_brain.evaluate.replay_capture_contracts import ReplayCaptureRefused, inspect_capture, instant
from nm.legal_brain.evaluate.replay_context import restore_runtime_context
from nm.legal_brain.evaluate.strict_replay import (
    FrozenEvidence,
    FrozenModel,
    FrozenPrinciples,
    PermissionTape,
    Tape,
    _decode,
    _prior_records,
    build_registry,
)
from nm.shared.budget_contracts import Budget, Spend
from nm.shared.model_port import Prompt, Tier
from nm.shared.store_file_store import FileMatterStore, _enc, _matter
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_runtime_capture_uses_the_actual_protected_journal import DAY, admitted_runtime

pytestmark = pytest.mark.class_a


def restored_case(tmp_path, *, prior=False):
    owner, capture, outcome, _session, _knowledge, actual_evidence = admitted_runtime(
        tmp_path, prior=prior, context=True
    )
    saved = capture.finish(outcome)
    data = saved.capture.payload
    clone = FileMatterStore(tmp_path / "actual-clone", key="this-isolated-context-only")
    initial = replace(_matter(data["initial_matter"]), loop_records=saved.prior_journals)
    clone.commit(initial, expected_version=0)
    tapes = {name: Tape(name, rows) for name, rows in data["tapes"].items()}
    permission = PermissionTape(tapes["boundaries"], clone, owner.guard.version)
    source = FrozenEvidence(
        Tape("actual source ports", data["port_exchanges"]), owner.guard.version
    )
    principles = FrozenPrinciples(data["principles"])

    def today():
        return date.fromisoformat(tapes["forum_day"].take())

    registry = build_registry(
        clone,
        permission=permission,
        evidence=source,
        manifest=_decode(Manifest, data["manifest"]),
        generation=owner.guard.version,
        principles=principles,
        today=today,
    )
    target, _prior = _prior_records(data, saved.prior_journals)
    model = FrozenModel(target, registry.definitions)
    source_current = bind_source_current(
        actual_evidence,
        owner.guard,
        owned_current=lambda: clone.load(initial.id).advocate_id == initial.advocate_id,
        session_current=lambda: True,
    )
    kwargs = {
        "store": clone,
        "registry": registry,
        "principles": principles,
        "model": model,
        "source_current": source_current,
        "today": today,
    }
    return owner, saved, clone, target, tapes, source, kwargs


@pytest.mark.parametrize("prior", [False, True])
def test_real_context_and_new_thread_replay_use_actual_initial_clone_and_each_captured_clock(
    tmp_path, prior
):
    owner, saved, clone, target, tapes, source, kwargs = restored_case(tmp_path, prior=prior)
    original = owner.store.load(target.identity.matter_id)
    session = restore_runtime_context(saved, **kwargs)
    assert isinstance(session, ContextSession)
    assert session.to_record() == saved.capture.payload["run"]["context_record"]
    assert session.policy.max_tokens == saved.metadata["context_policy"]["max_tokens"]
    assert tapes["forum_day"].position == 1
    raw = deepcopy(saved.capture.payload["limits"])
    raw["budget"]["spend"] = Spend(**raw["budget"]["spend"])
    limits = LoopLimits(
        Budget(**raw["budget"]), raw["max_steps"], raw["per_call_tokens"], raw["max_stagnant_steps"]
    )

    def cost(incoming, outgoing, tier):
        row = tapes["cost"].take()
        assert (incoming, outgoing, tier.value) == (
            row["input_tokens"],
            row["output_tokens"],
            row["tier"],
        )
        return row["usd"]

    runner = LoopRunner(
        model=kwargs["model"],
        tools=kwargs["registry"],
        log=MatterLoopLog(clone, advocate_id=target.identity.advocate_id),
        current_matter=clone.load,
        cost_ceiling=cost,
        monotonic=tapes["monotonic"].take,
        clock=lambda: instant(tapes["clock"].take()),
    )
    actual = runner.run(
        target.identity,
        Prompt(**saved.capture.payload["prompt"]),
        limits,
        session=session,
        cancelled=tapes["cancelled"].take,
        tier=Tier(saved.capture.payload["run"]["tier"]),
        scope_identity=saved.capture.payload["run"]["scope_identity"],
        feedback_identity=saved.capture.payload["run"]["feedback_identity"],
    )
    assert actual.record == target
    current = clone.load(target.identity.matter_id)
    assert current.threads and current.facts
    final = _enc(current)
    final.pop("loop_records")
    assert digest(final) == saved.capture.payload["final_matter_identity"]
    assert all(tape.remaining() == 0 for tape in tapes.values())
    assert source.tape.remaining() == 0
    assert owner.store.load(original.id) == original
    assert not current.turn_receipts
    # Native injection is now controlled, but the production composition/full
    # ports/children coordinator is not made ready by this helper control.
    assert not inspect_capture(saved.capture).ready


@pytest.mark.parametrize("invalid", ["foreign", "changed", "version", "missing_prior"])
def test_foreign_changed_or_incomplete_initial_clone_cannot_recover_a_saved_context(
    tmp_path, invalid
):
    _owner, saved, clone, target, _tapes, _source, kwargs = restored_case(tmp_path, prior=True)
    value = clone.load(target.identity.matter_id)
    altered = replace(
        value,
        version=value.version + 1,
        advocate_id="other_actor" if invalid == "foreign" else value.advocate_id,
        title="Changed actual instruction" if invalid == "changed" else value.title,
        loop_records=() if invalid == "missing_prior" else value.loop_records,
    )
    clone.commit(altered, expected_version=value.version)
    with pytest.raises(ReplayCaptureRefused, match="initial clone"):
        restore_runtime_context(saved, **kwargs)
    assert kwargs["model"].adapter.position == 0


@pytest.mark.parametrize("invalid", ["metadata", "clock", "source_flag", "changed_tools"])
def test_context_policy_prefix_population_and_clock_cannot_be_replaced_by_unowned_defaults(
    tmp_path, invalid
):
    _owner, saved, _clone, _target, _tapes, _source, kwargs = restored_case(tmp_path)
    if invalid == "metadata":
        metadata = deepcopy(saved.metadata)
        metadata["context_policy"]["max_tokens"] += 1
        saved = replace(saved, metadata=metadata)
    elif invalid == "clock":
        kwargs["today"] = lambda: DAY + timedelta(days=1)
    elif invalid == "source_flag":
        kwargs["source_current"] = True
    else:
        kwargs["registry"] = kwargs["registry"].extend((), versions={"changed_owner": "new"})
    with pytest.raises(ReplayCaptureRefused):
        restore_runtime_context(saved, **kwargs)
    assert kwargs["model"].adapter.position == 0


def test_recovered_context_compaction_keeps_the_same_native_date_and_source_owner(tmp_path):
    _owner, saved, clone, target, tapes, _source, kwargs = restored_case(tmp_path)
    observed = []

    def captured_day():
        observed.append(DAY)
        return DAY

    session = restore_runtime_context(saved, **{**kwargs, "today": captured_day})
    assert observed == [DAY]
    assert session._source_current is kwargs["source_current"]
    original = session.transcript
    generation = session.generation
    session.compact(
        clone.load(target.identity.matter_id), reason="actual controlled capacity boundary"
    )
    assert session.generation == generation + 1
    assert session.transcript[: len(original)] == original
    assert session._source_current is kwargs["source_current"]
    assert observed == [DAY, DAY]
    assert tapes["forum_day"].position == 0
