"""The real typed source/table ports survive capture without certifying current law."""
from copy import deepcopy
from datetime import date
from typing import get_type_hints
from unittest.mock import Mock

import pytest

from nm.legal_brain.evidence_port import Coverage, EvidenceResult, SourceKind
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.practice_playbooks_adapter import FilePracticePlaybooks
from nm.legal_brain.replay_capture_contracts import ReplayCaptureRefused
from nm.legal_brain.runtime_port_tape import (
    CONTRACTS,
    METHODS,
    NativePortRecorder,
    NativePortReplay,
    validate_exchange,
)
from nm.open_matter.matter_documents_port import DocumentRefused, MatterDocumentQuote
from tests.test_provision_revisions_need_owned_interval_proof import BEFORE, TITLE, adapter

pytestmark = pytest.mark.class_a
GENERATION = "controlled-observed-generation"


def _recorder():
    checks = []
    recorder = NativePortRecorder(generation=GENERATION,
                                  require_current=lambda: checks.append("current"))
    return recorder, checks


def test_real_dated_source_and_exact_document_read_restore_without_currentness_upgrade(tmp_path):
    actual = adapter(tmp_path)
    recorder, checks = _recorder()
    port = recorder.wrap("evidence", actual)
    revision = port.read_provision_at_date(TITLE, "7", BEFORE)
    assert revision.evidence.coverage is Coverage.NOT_ASSESSED
    assert revision.passages and not revision.evidence.findings
    raw = port.document(revision.passages[0].locator, SourceKind.PROVISION)
    replay = NativePortReplay(recorder.rows, generation=GENERATION)
    frozen = replay.port("evidence")
    assert frozen.read_provision_at_date(TITLE, "7", BEFORE) == revision
    assert frozen.document(revision.passages[0].locator, SourceKind.PROVISION) == raw
    assert replay.remaining() == 0 and len(checks) == 4
    assert recorder.rows[0]["outcome"]["value"]["selection"]["state"] == "not_assessed"


def test_missing_governing_date_stays_none_and_not_assessed(tmp_path):
    recorder, _ = _recorder()
    actual = adapter(tmp_path)
    value = recorder.wrap("evidence", actual).read_provision(TITLE, "7", None)
    assert value.coverage is Coverage.NOT_ASSESSED
    replay = NativePortReplay(recorder.rows, generation=GENERATION)
    assert replay.port("evidence").read_provision(TITLE, "7", None) == value
    assert replay.remaining() == 0


def test_actual_owner_playbook_remains_navigation_and_keeps_exact_version():
    recorder, _ = _recorder()
    value = recorder.wrap("playbooks", FilePracticePlaybooks()).load()
    replay = NativePortReplay(recorder.rows, generation=GENERATION)
    restored = replay.port("playbooks").load()
    assert restored == value and restored.version == value.version
    assert len(restored.catalogue) == 5
    assert replay.remaining() == 0


def test_admitted_document_quotation_keeps_private_source_identity_and_verbatim_words():
    recorder, _ = _recorder()
    source = {"original_id": "owned_original", "asset_version": 2,
              "source_sha256": "a" * 64, "derivative_sha256": "b" * 64}
    value = MatterDocumentQuote(
        "The original words are not a fact finding.", "owned-locator", source)
    actual = Mock(quote=Mock(return_value=value))
    arguments = {"original_id": "owned_original", "asset_version": 2,
                 "source_sha256": "a" * 64, "derivative_sha256": "b" * 64,
                 "number": 1, "location_kind": "page", "part": "text", "start": 0, "end": 47}
    assert recorder.wrap("documents", actual).quote("owned", "actor", 3, **arguments) == value
    replay = NativePortReplay(recorder.rows, generation=GENERATION)
    assert replay.port("documents").quote("owned", "actor", 3, **arguments) == value
    actual.quote.assert_called_once_with("owned", "actor", 3, **arguments)
    assert replay.remaining() == 0


def test_actual_document_refusal_is_replayed_as_refusal_never_empty_success():
    recorder, _ = _recorder()
    actual = Mock(search=Mock(side_effect=DocumentRefused("The original is withdrawn.")))
    with pytest.raises(DocumentRefused, match="withdrawn"):
        recorder.wrap("documents", actual).search("owned", "actor", 3, "exact words")
    replay = NativePortReplay(recorder.rows, generation=GENERATION)
    with pytest.raises(DocumentRefused, match="withdrawn"):
        replay.port("documents").search("owned", "actor", 3, "exact words")
    assert replay.remaining() == 0


@pytest.mark.parametrize("mutation", ["operation", "arguments", "generation", "unknown",
    "missing", "state", "untyped_boolean", "unbounded", "exception", "empty_refusal"])
def test_planted_native_capture_mutations_are_refused_without_erasing_the_population(mutation):
    recorder, _ = _recorder()
    result = EvidenceResult(Coverage.NOT_ASSESSED, missing="The source is unreadable.")
    recorder.wrap("evidence", Mock(read_provision=Mock(return_value=result))).read_provision(
        "Recorded rule", "1", date(2026, 1, 1))
    rows = deepcopy(recorder.rows)
    assert len(rows) == 1 and rows[0]["operation"] == "evidence.read_provision"
    row = rows[0]
    if mutation == "operation":
        row["operation"] = "provider.execute"
    elif mutation == "arguments":
        row["arguments"]["as_of"] = "tomorrow"
    elif mutation == "generation":
        row["generation"] = "https://foreign.invalid"
    elif mutation == "unknown":
        row["outcome"]["value"]["verified"] = True
    elif mutation == "missing":
        del row["outcome"]["value"]["coverage"]
    elif mutation == "state":
        row["outcome"]["state"] = "PASS"
    elif mutation == "untyped_boolean":
        row["schema"] = True
    elif mutation == "unbounded":
        row["outcome"]["value"]["search_note"] = "x" * 16_000_001
    elif mutation == "exception":
        row["outcome"] = {"state": "refused", "exception": "ImportError", "reason": "load"}
    else:
        row["outcome"] = {"state": "refused", "exception": "ValueError", "reason": ""}
    assert digest(rows) != digest(recorder.rows), "A mutation that did not land proves nothing"
    with pytest.raises((ReplayCaptureRefused, ValueError)):
        NativePortReplay(rows, generation=GENERATION)
    assert recorder.rows[0]["outcome"]["value"]["coverage"] == "not_assessed"


@pytest.mark.parametrize("change", ["instrument", "section", "day", "order", "generation"])
def test_actual_native_invocation_mismatch_does_not_consume_or_substitute_a_result(change):
    recorder, _ = _recorder()
    result = EvidenceResult(Coverage.NOT_HELD, missing="The exact rule was not held.")
    recorder.wrap("evidence", Mock(read_provision=Mock(return_value=result))).read_provision(
        "Recorded rule", "1", date(2026, 1, 1))
    replay = NativePortReplay(recorder.rows,
        generation="changed-generation" if change == "generation" else GENERATION)
    frozen = replay.port("evidence")
    with pytest.raises(ReplayCaptureRefused):
        if change == "order":
            frozen.document("locator", "provision")
        else:
            frozen.read_provision("Different rule" if change == "instrument" else "Recorded rule",
                "2" if change == "section" else "1",
                date(2026, 1, 2) if change == "day" else date(2026, 1, 1))
    assert replay.position == 0 and replay.remaining() == 1


@pytest.mark.parametrize("result", [Mock(), {"coverage": "answered"},
    EvidenceResult("answered", missing="A string is not a typed coverage state.")])
def test_untyped_actual_port_results_do_not_enter_the_tape(result):
    recorder, _ = _recorder()
    with pytest.raises(ReplayCaptureRefused):
        recorder.wrap("evidence", Mock(read_provision=Mock(return_value=result))).read_provision(
            "Recorded rule", "1", date(2026, 1, 1))
    assert recorder.rows == []


def test_native_population_is_closed_nonempty_and_all_operation_types_are_owned():
    assert len(METHODS) == 32 and len(CONTRACTS) == 11
    for operation, method in METHODS.items():
        hints = get_type_hints(method)
        assert "return" in hints and operation.count(".") == 1
    recorder, _ = _recorder()
    with pytest.raises(ReplayCaptureRefused):
        recorder.wrap("provider", Mock())
    with pytest.raises(AttributeError):
        recorder.wrap("evidence", Mock()).execute("arbitrary path")
    replay = NativePortReplay([], generation=GENERATION)
    with pytest.raises(ReplayCaptureRefused, match="exhausted"):
        replay.port("playbooks").load()
    assert replay.remaining() == 0


def test_constructor_validates_real_finite_exchange_population():
    with pytest.raises(ReplayCaptureRefused):
        validate_exchange({"operation": "evidence.document", "outcome": {"state": "returned"}})
