"""The configured checker is a recipient, not an unpoliced helper.

Controlled policy fixtures demonstrate the boundary, not a production scanner
approval. No third-party scanner runs and no actual original is released here.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from nm.adapters.policed_port import PolicedPort
from nm.bootstrap.document_permission import build_quarantine
from nm.bootstrap.egress_policy import egress_policy
from nm.domain.egress import DataClass, EgressRefused, Gatekeeper, Policy, Processor, Sink
from nm.domain.media import Quarantine
from nm.ports.document_text import DocumentFormat
from nm.ports.matter_documents import QuarantinePort, QuarantineRead

from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
SCANNER = "controlled-local-quarantine-test-only"
CLASSES = (DataClass.CLIENT_MATTER, DataClass.RESTRICTED)
BYTES = b"Controlled matter original - no client information"


class ControlledChecker:
    """No network, malware assertion or production clearance."""

    def __init__(self):
        self.calls = []

    def inspect(self, original_id, source_sha256, data):
        self.calls.append((original_id, source_sha256, data))
        return QuarantineRead(
            original_id, hashlib.sha256(data).hexdigest(), len(data),
            Quarantine.NOT_ASSESSED, DocumentFormat.TEXT,
            "a descriptive result label cannot approve a receiver", "fixture-v1",
            "Controlled recipient test; no quarantine release was established.",
        )


def controlled_processor(**changes):
    return replace(Processor(SCANNER, "in", (Sink.MEDIA,), CLASSES,
                             "CONTROLLED-TEST-ONLY"), **changes)


def test_default_has_no_scanner_and_configuration_cannot_name_only_half_the_pair():
    gate = Gatekeeper(Policy())
    assert build_quarantine(None, "", gate) is None
    with pytest.raises(ValueError, match="no configured checker"):
        build_quarantine(None, SCANNER, gate)
    checker = ControlledChecker()
    for identity in ("", " ", " " + SCANNER, SCANNER + " ", None, False):
        with pytest.raises(ValueError, match="identity"):
            build_quarantine(checker, identity, gate)
    assert not checker.calls


def test_checker_must_supply_its_declared_port_before_it_can_be_retained():
    with pytest.raises(ValueError, match="inspect port"):
        build_quarantine(object(), SCANNER, Gatekeeper(Policy()))


@pytest.mark.parametrize("processor", [
    None,
    controlled_processor(approval_id=""),
    controlled_processor(region="global"),
    controlled_processor(purposes=(Sink.MODEL,)),
    controlled_processor(data_classes=(DataClass.CLIENT_MATTER,)),
])
def test_unreviewed_or_wrong_scope_checker_is_refused_at_construction_before_bytes(processor):
    checker = ControlledChecker()
    logs = []
    policy = Policy(processors=() if processor is None else (processor,))
    gate = Gatekeeper(policy, audit=logs.append)
    with pytest.raises(EgressRefused):
        build_quarantine(checker, SCANNER, gate)
    assert not checker.calls and gate.refused
    assert logs and all("bytes=0" in row for row in logs)
    assert all(BYTES.decode() not in row for row in logs)


def test_every_inspect_call_is_policed_with_actual_bytes_and_both_data_classes():
    checker = ControlledChecker()
    logs = []
    gate = Gatekeeper(Policy(processors=(controlled_processor(),)), audit=logs.append)
    wrapped = build_quarantine(checker, SCANNER, gate)
    assert isinstance(wrapped, PolicedPort) and wrapped.admitted
    assert wrapped.port is QuarantinePort and wrapped.sink is Sink.MEDIA
    assert wrapped.processor_id == SCANNER and wrapped.data_classes == CLASSES
    sha = hashlib.sha256(BYTES).hexdigest()
    assert wrapped.inspect("original_one", sha, BYTES).state is Quarantine.NOT_ASSESSED
    assert wrapped.inspect(original_id="original_two", source_sha256=sha, data=BYTES).state \
        is Quarantine.NOT_ASSESSED
    assert len(checker.calls) == 2 and len(logs) == 3
    for row in logs[1:]:
        assert f"bytes={len(BYTES)}" in row
        assert "client_matter" in row and "restricted" in row
        assert f"processor={SCANNER}" in row and "sink=media" in row
        assert BYTES.decode() not in row
    # A previous admission is not continuing permission after policy changes.
    gate.policy = Policy()
    with pytest.raises(EgressRefused):
        wrapped.inspect("original_three", sha, BYTES)
    assert len(checker.calls) == 2 and gate.refused


def application(tmp_path, **kwargs):
    from nm.bootstrap.composition import Application

    return Application(
        environment={
            "NM_MATTER_KEY": KEY,
            "NM_MATTER_STORE": str(tmp_path),
            "NM_MODEL_PROVIDER": "scripted",
            "NM_MODEL_ROUTINE": "scripted-1",
            "NM_EMBED_MODEL": "text-embedding-3-large",
            "NM_PUBLIC_REGISTRATION": "local-test",
        },
        audit_root=tmp_path / "audit", **kwargs,
    )


def test_actual_application_defaults_do_not_configure_or_approve_any_scanner(tmp_path):
    composed = application(tmp_path)
    assert composed.documents is not None and composed.documents.quarantine is None
    assert composed.documents_for(session_current=lambda: True).quarantine is None
    assert egress_policy(ROOT).find(SCANNER) is None


@pytest.mark.parametrize("identity", ["", "external-quarantine", "local-looking-unregistered"])
def test_actual_application_cannot_inject_a_raw_checker_under_missing_or_unreviewed_id(
    tmp_path, identity
):
    checker = ControlledChecker()
    expected = ValueError if not identity else EgressRefused
    with pytest.raises(expected):
        application(tmp_path, document_quarantine=checker,
                    document_quarantine_processor=identity)
    assert not checker.calls


def test_actual_application_retains_policed_checker_in_request_bound_service(tmp_path, monkeypatch):
    from nm.bootstrap import composition

    # A unit-test-only reviewed recipient, not an authored production approval.
    local = egress_policy(ROOT)
    controlled = replace(local, processors=(*local.processors, controlled_processor()))
    monkeypatch.setattr(composition, "egress_policy", lambda _root: controlled)
    checker = ControlledChecker()
    composed = application(tmp_path, document_quarantine=checker,
                           document_quarantine_processor=SCANNER)
    wrapped = composed.documents.quarantine
    assert isinstance(wrapped, PolicedPort) and wrapped.inner is checker
    assert composed.documents_for(session_current=lambda: True).quarantine is wrapped
    composed._gate.policy = local
    with pytest.raises(EgressRefused):
        wrapped.inspect("original_one", hashlib.sha256(BYTES).hexdigest(), BYTES)
    assert not checker.calls
