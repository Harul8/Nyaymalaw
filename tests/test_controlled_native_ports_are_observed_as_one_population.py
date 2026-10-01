"""The controlled composition has one closed native capture projection."""

from __future__ import annotations

from dataclasses import fields
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.evaluate import runtime_capture
from nm.Archives.legal_brain.evaluate.replay_capture_contracts import ReplayCaptureRefused, ReplayProfile
from nm.Archives.legal_brain.evaluate.runtime_port_tape import CONTRACTS
from nm.Archives.legal_brain.orchestrate.controlled_registry_composition import ControlledRegistryPorts
from nm.Archives.legal_brain.orchestrate.tool_catalogue import PracticeTables
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.Archives.legal_brain.retrieve.practice_playbooks_adapter import FilePracticePlaybooks
from tests.test_runtime_capture_uses_the_actual_protected_journal import admitted_runtime

pytestmark = pytest.mark.class_a


def _ports(generation):
    playbooks = FilePracticePlaybooks()
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.NOT_HELD, missing="The exact provision is not held."
    )
    table_names = ("elements", "institution", "interim", "procedural", "filing", "governing")
    tables = PracticeTables("owned-table-version", **{name: Mock() for name in table_names})
    ports = ControlledRegistryPorts(
        evidence=evidence,
        manifest=Manifest((ManifestEntry("Held rule", ("RULE",), ("1",)),),
                          corpus_version=generation),
        search=Mock(),
        tables=tables,
        authority_weight=Mock(),
        matter_documents=Mock(),
        model=Mock(),
        principles=Mock(),
        playbooks=playbooks,
        playbook_snapshot=playbooks.load(),
    )
    return ports


def test_one_controlled_projection_observes_every_present_native_owner_and_seals_actual_calls(
    tmp_path,
):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(
        tmp_path, profile=ReplayProfile.CONTROLLED
    )
    ports = _ports(owner.guard.version)
    observed = capture.observe_registry_ports(ports)
    with pytest.raises(ReplayCaptureRefused, match="already projected"):
        capture.observe_registry_ports(ports)
    assert observed is not ports
    assert observed.manifest is ports.manifest
    assert observed.model is ports.model
    assert observed.principles is ports.principles
    assert observed.playbook_snapshot is ports.playbook_snapshot
    assert observed.tables.version == ports.tables.version
    for name in ("evidence", "search", "authority_weight", "matter_documents", "playbooks"):
        assert getattr(observed, name) is not getattr(ports, name)
    for name in ("elements", "institution", "interim", "procedural", "filing", "governing"):
        assert getattr(observed.tables, name) is not getattr(ports.tables, name)
    result = observed.evidence.read_provision("Held rule", "1", date(2026, 1, 1))
    assert result.coverage is Coverage.NOT_HELD
    assert observed.playbooks.load() == ports.playbook_snapshot
    saved = capture.finish(outcome)
    assert owner.read(outcome.record.identity) == saved
    assert [row["operation"] for row in saved.metadata["native_port_exchanges"]] == [
        "evidence.read_provision", "playbooks.load"
    ]
    assert not saved.readiness.ready
    assert not owner.store.load(outcome.record.identity.matter_id).turn_receipts


def test_absent_native_readers_stay_absent_and_are_not_fake_successes(tmp_path):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(
        tmp_path, profile=ReplayProfile.CONTROLLED
    )
    ports = _ports(owner.guard.version)
    ports = ControlledRegistryPorts(**{
        **vars(ports),
        "search": None,
        "authority_weight": None,
        "matter_documents": None,
        "tables": PracticeTables("owned-table-version"),
    })
    observed = capture.observe_registry_ports(ports)
    assert observed.search is observed.authority_weight is observed.matter_documents is None
    assert all(getattr(observed.tables, name) is None for name in (
        "elements", "institution", "interim", "procedural", "filing", "governing"
    ))
    assert capture.native_ports.rows == []
    saved = capture.finish(outcome)
    assert saved.metadata["native_port_exchanges"] == []
    assert not saved.readiness.ready


def test_unclassified_port_contract_or_revoked_source_refuses_before_any_capture(
    tmp_path, monkeypatch
):
    owner, capture, _outcome, session, _knowledge, _evidence = admitted_runtime(
        tmp_path, profile=ReplayProfile.CONTROLLED
    )
    ports = _ports(owner.guard.version)
    actual_fields = fields

    def gained_port(kind):
        found = actual_fields(kind)
        if kind is ControlledRegistryPorts:
            return (*found, SimpleNamespace(name="new_unclassified_source"))
        return found

    monkeypatch.setattr(runtime_capture, "fields", gained_port)
    with pytest.raises(ReplayCaptureRefused, match="unclassified capture port"):
        capture.observe_registry_ports(ports)
    assert capture.native_ports.rows == []
    monkeypatch.setattr(runtime_capture, "fields", actual_fields)
    monkeypatch.setitem(CONTRACTS, "future_owner", (object, ("read",)))
    with pytest.raises(ReplayCaptureRefused, match="unclassified owner"):
        capture.observe_registry_ports(ports)
    assert capture.native_ports.rows == []
    monkeypatch.delitem(CONTRACTS, "future_owner")
    session["current"] = False
    with pytest.raises(ReplayCaptureRefused, match="scope"):
        capture.observe_registry_ports(ports)
    assert capture.native_ports.rows == []
