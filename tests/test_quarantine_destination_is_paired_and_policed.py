"""The configured checker is a recipient, not an unpoliced helper.

Controlled policy fixtures demonstrate the boundary, not a production scanner
approval. No third-party scanner runs and no actual original is released here.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nm.open_matter.document_text_port import DocumentFormat
from nm.open_matter.matter_documents_port import QuarantineRead
from nm.open_matter.media_contracts import Quarantine
from nm.shared.egress_contracts import DataClass, Processor, Sink
from nm.shared.egress_policy import egress_policy
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


def _composed(tmp_path, **kwargs):
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

    composed = _composed(tmp_path)
    checker = composed.documents.checker
    assert isinstance(checker, ClamAVCheck)
    assert checker.check(BYTES) == ("unavailable", "no malware checker is set up on this installation")
    assert not {"document_quarantine", "document_quarantine_processor"} & set(
        inspect.signature(Application).parameters)
    assert egress_policy(ROOT).find(SCANNER) is None
