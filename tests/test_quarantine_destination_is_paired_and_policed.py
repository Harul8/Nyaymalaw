"""The configured checker is a recipient, not an unpoliced helper.

Controlled policy fixtures demonstrate the boundary, not a production scanner
approval. No third-party scanner runs and no actual original is released here.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nm.open_matter.document_permission import build_quarantine
from nm.open_matter.document_text_port import DocumentFormat
from nm.open_matter.matter_documents_port import QuarantinePort, QuarantineRead
from nm.open_matter.media_contracts import Quarantine
from nm.shared.egress_contracts import DataClass, EgressRefused, Gatekeeper, Policy, Processor, Sink
from nm.shared.egress_policy import egress_policy
from nm.shared.policed_port_adapter import PolicedPort
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
    from nm.app.composition import Application
    from nm.shared.model_config import ModelConfig, TierConfig
    from nm.shared.model_port import Tier
    from nm.shared.model_scripted import ScriptedModelAdapter

    config = ModelConfig(tiers={Tier.ROUTINE: TierConfig(Tier.ROUTINE, "scripted", "scripted-1", None, None)})
    return Application(
        model=ScriptedModelAdapter(config, responses={"__default__": "Synthetic."}), legal_search=None,
        environment={"NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path),
                     "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1",
                     "NM_EMBED_MODEL": "text-embedding-3-large",
                     "NM_PUBLIC_REGISTRATION": "local-test"},
        audit_root=tmp_path / "audit", **kwargs)


def test_the_application_reads_documents_only_after_a_check_on_this_machine(tmp_path):
    """Owner decisions, 15 Oct 2026 (item 6): ClamAV on this installation checks every
    document before anything reads it; the injectable outside scanner these tests once
    guarded is retired. Without the installation's scanner nothing is cleared, and the
    application has no way to take a scanner from outside."""
    import inspect

    from nm.app.composition import Application
    from nm.open_matter.clamav_check import ClamAVCheck

    composed = application(tmp_path)
    checker = composed.documents.checker
    assert isinstance(checker, ClamAVCheck)
    assert checker.check(BYTES) == ("unavailable", "no malware checker is set up on this installation")
    assert not {"document_quarantine", "document_quarantine_processor"} & set(
        inspect.signature(Application).parameters)
    assert egress_policy(ROOT).find(SCANNER) is None
