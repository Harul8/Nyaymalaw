"""Application and cloned files consume the same finite native tool assembly."""

from __future__ import annotations

import ast
import inspect
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from textwrap import dedent
from unittest.mock import Mock

import pytest

from nm.app.composition import Application
from nm.Archives.legal_brain.orchestrate import controlled_registry_composition as controlled_registry
from nm.Archives.legal_brain.verify.brain_release import ReviewService
from nm.Archives.legal_brain.orchestrate.controlled_brain import ControlledBrain
from nm.Archives.legal_brain.orchestrate.controlled_registry_composition import (
    ControlledRegistryPorts,
    assemble_controlled_registry,
)
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult, SourceDocument
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopIdentity, StopReason
from nm.Archives.legal_brain.evaluate.strict_replay import PermissionTape, Tape
from nm.Archives.legal_brain.orchestrate.tools import Boundary, ToolContext, ToolRefused
from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
from nm.open_matter.commission_contracts import Commission
from nm.shared.authority_contracts import capacity_for, permits
from nm.shared.model_port import ToolCall
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_controlled_brain_composition_keeps_the_account_boundary import _scope
from tests.test_independent_claim_verifier import Judge, finding
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a
DAY = date(2026, 9, 27)
NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def captured_application(client, monkeypatch, *, reviewed=False):
    app, matter, scope = _scope(client)
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000
    held = finding()
    app.evidence.read_provision = Mock(
        return_value=EvidenceResult(Coverage.ANSWERED, (held,), searched_stores=("held",))
    )
    app.evidence.document = Mock(
        return_value=SourceDocument(
            "read",
            label=held.ref,
            store="held",
            segments=(("1", held.span),),
            target=0,
            locator=held.locator,
            kind=held.source_kind.value,
        )
    )
    calls = []
    actual = controlled_registry.assemble_controlled_registry

    def observe(**kwargs):
        result = actual(**kwargs)
        calls.append((kwargs, result))
        return result

    monkeypatch.setattr(controlled_registry, "assemble_controlled_registry", observe)
    reviewer = (
        ReviewService(
            store=app.store,
            log=MatterLoopLog(app.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(Judge()),
            session_current=lambda: True,
            cost_ceiling=lambda *_: 0.03,
        )
        if reviewed
        else None
    )
    brain = app.controlled_brain_for(
        scope,
        session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03,
        source_version=app.source_generation_guard().version,
        table_version="actual-parity-table-generation",
        reviewer=reviewer,
        controlled_model=model,
    )
    assert len(calls) == 1
    return app, matter, scope, model, brain, calls[0]


@pytest.mark.parametrize("reviewed", [False, True])
def test_complete_actual_application_population_and_version_come_from_one_owner(
    client, monkeypatch, reviewed
):
    _app, _matter, _scope_value, _model, brain, (kwargs, assembled) = captured_application(
        client, monkeypatch, reviewed=reviewed
    )
    # Derive the complete population from the actual Application, not a second
    # name list that could omit the next operational tool.
    actual_definitions = tuple(asdict(row) for row in brain.registry.definitions)
    assert actual_definitions
    assert assembled.registry is brain.registry
    rebuilt = assemble_controlled_registry(**kwargs)
    if reviewed:
        rebuilt.install_early(brain.early_review)
    assert tuple(asdict(row) for row in rebuilt.registry.definitions) == actual_definitions
    assert rebuilt.registry.version == brain.registry.version
    assert rebuilt.registry._versions == brain.registry._versions
    assert set(rebuilt.registry._tools) == set(brain.registry._tools)
    for name, tool in brain.registry._tools.items():
        other = rebuilt.registry._tools[name]
        assert (
            other.kind,
            other.version,
            other.required_act,
            other.offer_role,
            other.parallel_safe,
            other.delegation,
            other.tests,
        ) == (
            tool.kind,
            tool.version,
            tool.required_act,
            tool.offer_role,
            tool.parallel_safe,
            tool.delegation,
            tool.tests,
        )
    assert rebuilt.interest_owner.source_owner is rebuilt.working_owner
    assert rebuilt.fee_owner.source_owner is rebuilt.working_owner
    assert rebuilt.research.registry.reading_tools()
    assert all(row.delegation is None for row in rebuilt.research.registry.reading_tools())


def test_application_does_not_maintain_a_second_tool_assembly_or_late_population():
    body = ast.parse(dedent(inspect.getsource(Application.controlled_brain_for)))
    calls = [
        row.func.id
        for row in ast.walk(body)
        if isinstance(row, ast.Call) and isinstance(row.func, ast.Name)
    ]
    assert calls.count("assemble_controlled_registry") == 1
    assert "foundation_tools" not in calls
    assert "catalogue_tools" not in calls
    assert "write_tools" not in calls
    assert "discovery_tools" not in calls
    assert not any(
        isinstance(row, ast.Call)
        and isinstance(row.func, ast.Attribute)
        and isinstance(row.func.value, ast.Name)
        and row.func.value.id == "registry"
        and row.func.attr == "extend"
        for row in ast.walk(body)
    )


def native_clone_boundary(store, scope, generations, *, session=lambda: True):
    def check(context, act):
        generations.require_current()
        value = store.load(context.identity.matter_id)
        if (
            not session()
            or context.identity.matter_id not in scope.matter_ids
            or value is None
            or value.advocate_id != scope.advocate_id
            or context.identity.advocate_id != scope.advocate_id
            or context.current_version != value.version
        ):
            return Boundary(False, "The actual isolated file is not currently in scope.")
        commission = Commission.from_stored(value.commission)
        capacity = capacity_for(
            scope.advocate_id,
            value.authority_bindings,
            commission.version if commission else 0,
            NOW,
        )
        ruling = permits(scope.advocate_id, capacity, act)
        return Boundary(ruling.authorises(), ruling.why)

    return check


def test_same_native_handlers_write_only_the_real_sealed_clone_and_read_typed_sources(
    client, monkeypatch, tmp_path
):
    app, matter, scope, model, brain, (kwargs, _assembly) = captured_application(
        client, monkeypatch
    )
    clone = FileMatterStore(tmp_path / "isolated", key="only-this-encrypted-clone")
    initial = clone.commit(matter, expected_version=0)
    boundary = native_clone_boundary(clone, scope, kwargs["generations"])
    frozen_arguments = {
        **kwargs,
        "store": clone,
        "boundary": boundary,
        "ports": replace(kwargs["ports"], matter_documents=None),
        "today": lambda: DAY,
        "monotonic": lambda: 0,
    }
    assembly = assemble_controlled_registry(**frozen_arguments)
    # Deliberately missing document population is visible in the actual
    # contract identity; this controlled probe is not full-port replay parity.
    assert assembly.registry.version != brain.registry.version
    words = "A contractor retains my deposit. Check the source and ask what is needed."
    model.tool_call.side_effect = [
        _response(ToolCall("inspect-create", "inspect_tool", {"name": "create_dispute"})),
        _response(
            ToolCall(
                "create",
                "create_dispute",
                {"label": "Deposit", "quoted": "A contractor retains my deposit."},
            )
        ),
        _response(ToolCall("inspect-law", "inspect_tool", {"name": "read_provision"})),
        _response(
            ToolCall(
                "law",
                "read_provision",
                {"act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"},
            )
        ),
        _response(ToolCall("inspect-work", "inspect_tool", {"name": "read_working_inventory"})),
        _response(ToolCall("inventory", "read_working_inventory", {})),
        _response(ToolCall("question", "ask_advocate", {"question": "When was payment made?"})),
    ]
    isolated_brain = ControlledBrain(
        store=clone,
        model=model,
        principles=kwargs["ports"].principles,
        log=MatterLoopLog(clone, advocate_id=scope.advocate_id),
        registry=assembly.registry,
        scope=scope,
        cost_ceiling=kwargs["cost_ceiling"],
        session_current=lambda: True,
    )
    result = isolated_brain.run(
        matter_id=matter.id,
        turn_id="isolated_actual_registry",
        message=words,
        limits=replace(
            _limits(),
            max_steps=20,
            budget=replace(_limits().budget, max_ms=60000, max_tokens=100000),
        ),
    )
    assert result.reason is StopReason.QUESTION, (
        result.budget.as_dict(),
        [
            (row.kind.value, row.payload.get("max_steps"), row.payload.get("reserved_tokens"))
            for row in result.record.events
        ],
    )
    assert app.store.load(matter.id) == matter
    saved = clone.load(matter.id)
    assert saved.version > initial.version and len(saved.threads) == 1
    assert saved.facts[0].statement == words and saved.facts[0].confirmed is not True
    receipts = [
        row.payload["receipt"] for row in result.record.events if row.kind.value == "tool_returned"
    ]
    assert [row["tool"] for row in receipts] == [
        "inspect_tool",
        "create_dispute",
        "inspect_tool",
        "read_provision",
        "inspect_tool",
        "read_working_inventory",
        "ask_advocate",
    ]
    assert next(row for row in receipts if row["tool"] == "read_provision")["data"]
    assert not saved.turn_receipts
    inventory = assembly.working_owner.build(result.record, saved).payload
    assert inventory["threads"][0]["id"] == saved.threads[0].id


@pytest.mark.parametrize("reason", ["session", "foreign_actor", "foreign_file", "stale"])
def test_reused_native_handler_cannot_cross_current_clone_permission_or_version(
    client, monkeypatch, tmp_path, reason
):
    app, matter, scope, _model, brain, (kwargs, _assembly) = captured_application(
        client, monkeypatch
    )
    clone = FileMatterStore(tmp_path / "isolated", key="rejecting-encrypted-clone")
    clone.commit(matter, expected_version=0)
    assembly = assemble_controlled_registry(
        **{
            **kwargs,
            "store": clone,
            "boundary": native_clone_boundary(
                clone, scope, kwargs["generations"], session=lambda: reason != "session"
            ),
        }
    )
    identity = LoopIdentity(
        "foreign" if reason == "foreign_file" else matter.id,
        "foreign" if reason == "foreign_actor" else scope.advocate_id,
        "unadmitted_read",
        "f" * 64,
        brain.principles.load().version,
        assembly.registry.version,
        matter.version + 1 if reason == "stale" else matter.version,
        scope.mode,
    )
    before = clone.load(matter.id)
    with pytest.raises(ToolRefused, match="actual isolated file"):
        assembly.registry.invoke(ToolCall("read", "read_matter", {}), ToolContext(identity))
    assert clone.load(matter.id) == before
    assert app.store.load(matter.id) == matter


def test_factory_cannot_replace_real_source_and_clock_owners_with_completion_flags(
    client, monkeypatch
):
    _app, _matter, _scope_value, _model, _brain, (kwargs, _assembly) = captured_application(
        client, monkeypatch
    )
    with pytest.raises(ValueError, match="source, permission"):
        assemble_controlled_registry(**{**kwargs, "source_current": True})
    with pytest.raises(ValueError, match="source, permission"):
        assemble_controlled_registry(**{**kwargs, "today": DAY})
    with pytest.raises(ValueError, match="actual port"):
        ControlledRegistryPorts(**{**vars(kwargs["ports"]), "tables": {"complete": True}})


def permission_rows(context, scope, generation, name="read_matter"):
    return [
        {
            "phase": phase,
            "tool": name,
            "matter_id": context.identity.matter_id,
            "actor_id": context.identity.advocate_id,
            "current_version": context.current_version,
            "session_current": True,
            "scope_matter_ids": sorted(scope.matter_ids),
            "source_generation": generation,
            "source_state": "current",
            "claimed_capacity": None,
            "policy_at": NOW.isoformat(),
        }
        for phase in ("before", "after")
    ]


def test_actual_typed_permission_tape_observes_each_named_phase_once_not_allowed_flags(
    client, monkeypatch
):
    app, matter, scope, _model, brain, (kwargs, _assembly) = captured_application(
        client, monkeypatch
    )
    identity = LoopIdentity(
        matter.id,
        scope.advocate_id,
        "actual_permission_read",
        "f" * 64,
        brain.principles.load().version,
        brain.registry.version,
        matter.version,
        scope.mode,
    )
    context = ToolContext(identity)
    tape = Tape("actual native policy", permission_rows(context, scope, kwargs["source_version"]))
    permissions = PermissionTape(tape, app.store, kwargs["source_version"])
    assembly = assemble_controlled_registry(
        **{
            **kwargs,
            "permission_owner": permissions,
            "boundary": Mock(side_effect=AssertionError("a duplicate native policy invocation")),
        }
    )
    assert assembly.registry.version == brain.registry.version
    assert permissions.registry is assembly.registry
    result = assembly.registry.invoke(ToolCall("read", "read_matter", {}), context)
    assert result.receipt["matter_id"] == matter.id
    assert tape.position == 2 and len(permissions.attempts) == 2
    assert all("allowed" not in row for row in tape.rows)


def test_late_independent_population_refreshes_actual_permission_and_discovery_owner(
    client, monkeypatch
):
    app, matter, scope, _model, brain, (kwargs, _assembly) = captured_application(
        client, monkeypatch, reviewed=True
    )
    identity = LoopIdentity(
        matter.id,
        scope.advocate_id,
        "inspect_current_early",
        "f" * 64,
        brain.principles.load().version,
        brain.registry.version,
        matter.version,
        scope.mode,
    )
    context = ToolContext(identity)
    name = brain.early_review.tools(controlled_registry.EARLY_REVIEW_POLICY)[0].definition.name
    tape = Tape(
        "native current phases",
        permission_rows(context, scope, kwargs["source_version"], name="inspect_tool"),
    )
    permissions = PermissionTape(tape, app.store, kwargs["source_version"])
    assembly = assemble_controlled_registry(**{**kwargs, "permission_owner": permissions})
    old = assembly.registry
    assembly.install_early(brain.early_review)
    assert permissions.registry is assembly.registry and permissions.registry is not old
    assert assembly.registry.version == brain.registry.version
    result = assembly.registry.invoke(ToolCall("inspect", "inspect_tool", {"name": name}), context)
    assert result.data["definition"]["name"] == name
    assert tape.position == 2


@pytest.mark.parametrize("invalid", ["flag", "duck", "wrong_store", "wrong_source"])
def test_unknown_incomplete_or_foreign_permission_owner_cannot_replace_native_policy(
    client, monkeypatch, tmp_path, invalid
):
    app, _matter, _scope_value, _model, _brain, (kwargs, _assembly) = captured_application(
        client, monkeypatch
    )
    owner = (
        True
        if invalid == "flag"
        else Mock()
        if invalid == "duck"
        else PermissionTape(
            Tape("unused native phases", []),
            FileMatterStore(tmp_path / "foreign", key="unrelated-only")
            if invalid == "wrong_store"
            else app.store,
            "different-generation" if invalid == "wrong_source" else kwargs["source_version"],
        )
    )
    with pytest.raises(ValueError, match="actual typed clone"):
        assemble_controlled_registry(**{**kwargs, "permission_owner": owner})
