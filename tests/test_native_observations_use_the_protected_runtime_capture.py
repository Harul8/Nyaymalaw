"""Full-port building blocks are sealed, attributable and explicitly incomplete."""
from dataclasses import replace

import pytest

from nm.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord, digest
from nm.legal_brain.retrieve.practice_playbooks_adapter import FilePracticePlaybooks
from nm.legal_brain.evaluate.replay_capture_contracts import ReplayCaptureRefused, ReplayProfile
from tests.test_runtime_capture_uses_the_actual_protected_journal import NOW, admitted_runtime

pytestmark = pytest.mark.class_a


def test_actual_native_observation_survives_sealed_owner_read_without_new_release(tmp_path):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(
        tmp_path, profile=ReplayProfile.CONTROLLED)
    port = capture.native_port("playbooks", FilePracticePlaybooks())
    actual = port.load()
    saved = capture.finish(outcome)
    assert saved.journal.events[0].payload["schema"] == 2
    assert saved.metadata["native_port_exchanges"][0]["operation"] == "playbooks.load"
    assert saved.metadata["native_port_exchanges"][0]["outcome"]["value"]["payload_json"] \
        == actual.payload_json
    assert owner.read(outcome.record.identity) == saved
    assert saved.readiness.state == "capture_incomplete"
    assert not owner.store.load("owned_matter").turn_receipts
    encrypted = owner.store._path("owned_matter").read_bytes()
    assert actual.payload_json.encode() not in encrypted
    with pytest.raises(ReplayCaptureRefused, match="closure"):
        port.load()


def test_foundation_profile_cannot_hide_unreplayed_full_port_observations(tmp_path):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(tmp_path)
    with pytest.raises(ReplayCaptureRefused, match="foundation profile"):
        capture.native_port("playbooks", FilePracticePlaybooks())
    assert capture.native_ports.rows == []
    assert capture.finish(outcome).readiness.ready
    assert owner.read(outcome.record.identity).metadata["native_port_exchanges"] == []


def test_changed_native_capture_metadata_cannot_borrow_its_sealed_admission(tmp_path):
    owner, capture, outcome, _session, _knowledge, _evidence = admitted_runtime(
        tmp_path, profile=ReplayProfile.CONTROLLED)
    capture.native_port("playbooks", FilePracticePlaybooks()).load()
    saved = capture.finish(outcome)
    matter = owner.store.load("owned_matter")
    stop = saved.journal.events[-1].payload
    original_digest = digest(stop["metadata"])
    stop["metadata"]["native_port_exchanges"][0]["generation"] = "changed-generation"
    assert digest(stop["metadata"]) != original_digest
    last = LoopEvent.create(2, saved.journal.events[-1].kind, NOW.isoformat(), stop,
                            saved.journal.events[0].fingerprint)
    changed = LoopRecord(saved.journal.identity, (saved.journal.events[0], last))
    owner.store.commit(replace(matter,
        loop_records=tuple(changed if row.identity == changed.identity else row
                           for row in matter.loop_records), version=matter.version + 1),
        expected_version=matter.version)
    with pytest.raises(ReplayCaptureRefused):
        owner.read(outcome.record.identity)
