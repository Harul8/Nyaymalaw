"""The real upload→local reader→sealed derivative→tool path, with rejecting controls.

The trusted checker below is explicitly controlled test configuration, not a
production scanner or permission to release arbitrary live documents.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from nm.close import retention as rt
from nm.close.retention_contracts import (
    AssetRef,
    Copy,
    Hold,
    RequestedAction,
    RequestScope,
    RetentionRequest,
    RetentionState,
    Tombstone,
)
from nm.legal_brain.loop_contracts import LoopIdentity, LoopMode, digest
from nm.legal_brain.tool_catalogue import catalogue_tools
from nm.legal_brain.tools import Assessment, Availability, Boundary, ToolContext, ToolRegistry
from nm.open_matter.document_local import LocalDocumentText
from nm.open_matter.document_text_port import (
    DocumentFormat,
    ExtractionResult,
    LocatedText,
    TextState,
)
from nm.open_matter.documents_api import DocumentService
from nm.open_matter.matter_documents_port import (
    DocumentReadInstruction,
    DocumentRefused,
    QuarantineRead,
)
from nm.open_matter.media_contracts import Quarantine
from nm.open_matter.uploads_api import UploadService
from nm.shared.model_port import ToolCall
from nm.shared.store_documents import SealedDocumentStore
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_port import StaleWrite
from nm.shared.store_sealing import MatterSealer
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a
WORDS = "The recorded date is 4 March 2026. Amount ₹10000. Straße."


class ControlledChecker:
    def __init__(self, state=Quarantine.RELEASED):
        self.state, self.calls = state, []

    def inspect(self, original_id, sha256, data):
        self.calls.append((original_id, sha256, data))
        return QuarantineRead(
            original_id,
            hashlib.sha256(data).hexdigest(),
            len(data),
            self.state,
            DocumentFormat.TEXT,
            "controlled-checker",
            "fixture-v1",
            "Controlled test-only original check; no production clearance.",
        )


class ControlledReader:
    def __init__(self, state=TextState.EXTRACTED):
        self.state, self.calls = state, []

    def extract(self, document, *, bounds):
        self.calls.append(document)
        text = document.data.decode("utf8") if self.state is TextState.EXTRACTED else ""
        unit = LocatedText(
            1,
            "part",
            "text",
            self.state,
            text,
            "" if text else "The controlled reader has no text layer.",
        )
        return ExtractionResult(
            document.source_sha256,
            document.admission.media_id,
            document.format,
            len(document.data),
            1,
            (unit,),
            parser="controlled-local",
            parser_version="fixture-v1",
        )


def fixture(tmp_path, *, parser=None, checker=None, words=WORDS):
    seal = Fernet.generate_key().decode()
    store = FileMatterStore(tmp_path, key=seal)
    store.commit(
        Matter("mat_one", "adv_one", "Controlled private file", version=1), expected_version=0
    )
    uploads = UploadService(store, store.upload_storage())
    original = words.encode("utf8")
    offer = uploads.begin(
        "mat_one",
        "adv_one",
        {
            "request_key": "offer_one",
            "filename": "private.txt",
            "declared_size": len(original),
            "purpose": "Hold this original only",
            "authority": "User supplied holding authority",
            "retention": "matter_life",
        },
    )
    original_id = offer["asset_id"]
    uploads.append("mat_one", "adv_one", original_id, 0, original)
    uploads.complete("mat_one", "adv_one", original_id)
    derivatives = SealedDocumentStore(tmp_path, MatterSealer(seal, tmp_path / "keys"))
    reader = parser or ControlledReader()
    service = DocumentService(
        uploads,
        derivatives,
        reader,
        quarantine=checker if checker is not None else ControlledChecker(),
    )
    return service, store, uploads, derivatives, reader, original_id


def instruction(service, original_id, *, request_key="read_one"):
    matter = service.store.load("mat_one")
    row = matter.uploads[original_id]
    return DocumentReadInstruction(
        request_key,
        "adv_one",
        original_id,
        row["asset_version"],
        row["receipt"]["observed_hash"],
        "Read this document for this matter",
        "The owner explicitly instructs local reading",
        True,
    )


def analyse(service, original_id):
    request = instruction(service, original_id)
    return service.analyse("mat_one", "adv_one", service.store.load("mat_one").version, request)


def quote_args(reading):
    request = reading["instruction"]
    return {
        "original_id": request["original_id"],
        "asset_version": request["asset_version"],
        "source_sha256": request["source_sha256"],
        "derivative_sha256": reading["derivative"]["sha256"],
        "number": 1,
        "location_kind": "part",
        "part": "text",
        "start": 0,
        "end": 10,
    }


def registry(service):
    matter = service.store.load("mat_one")
    tools = catalogue_tools(
        service.store, Mock(), source_version="controlled-source", matter_documents=service
    )

    def gate(*_):
        return Boundary(True, "controlled authenticated reading scope")

    result = ToolRegistry(tools, before=gate, after=gate)
    context = ToolContext(
        LoopIdentity(
            matter.id,
            matter.advocate_id,
            "turn_one",
            digest("offer"),
            digest("principles"),
            result.version,
            matter.version,
            LoopMode.SYNTHETIC,
        )
    )
    return result, context


def test_actual_local_parser_and_catalogue_read_exact_encrypted_derivative(tmp_path):
    service, store, _uploads, derivatives, _reader, original_id = fixture(
        tmp_path, parser=LocalDocumentText()
    )
    reading = analyse(service, original_id)
    assert reading["extraction"]["complete"] is True
    assert store.load("mat_one").facts == ()
    path = derivatives._path("mat_one", reading["derivative"]["id"])
    assert WORDS.encode() not in path.read_bytes()
    assert "text" not in reading["extraction"]["units"][0]
    tools, context = registry(service)
    searched = tools.invoke(
        ToolCall("search", "search_matter", {"query": "4 March", "limit": 20}), context
    )
    assert searched.availability is Availability.AVAILABLE
    assert searched.assessment is Assessment.SUPPORTED
    assert searched.data["document_sources_searched"] == [original_id]
    found = searched.data["matches"][0]["source"]
    assert searched.data["matches"][0]["words"] == "4 March"
    quoted = tools.invoke(
        ToolCall("quote", "quote_matter", {key: found[key] for key in quote_args(reading)}), context
    )
    assert quoted.data["text"] == "4 March"
    assert quoted.data["source"]["facts_established"] is False


def test_holding_only_never_becomes_analysis_permission_or_empty_search_success(tmp_path):
    service, store, _uploads, _derived, reader, original_id = fixture(tmp_path)
    found = service.search("mat_one", "adv_one", store.load("mat_one").version, "March")
    assert found.partial and not found.matches and not found.searched
    assert found.not_searched[0]["original_id"] == original_id
    assert not reader.calls and not service.quarantine.calls
    with pytest.raises(ValueError, match="Holding permission|holding permission"):
        replace(instruction(service, original_id), analysis_allowed=False)


@pytest.mark.parametrize("state", [Quarantine.HELD, Quarantine.NOT_ASSESSED])
def test_trusted_checker_unreleased_states_never_call_the_parser(tmp_path, state):
    service, store, _uploads, _derived, reader, original_id = fixture(
        tmp_path, checker=ControlledChecker(state)
    )
    reading = analyse(service, original_id)
    assert reading["quarantine"]["state"] == state.value and reading["derivative"] is None
    assert not reader.calls
    search = service.search("mat_one", "adv_one", store.load("mat_one").version, "March")
    assert search.partial and not search.matches and not search.searched


def test_missing_checker_cannot_read_or_release_the_original(tmp_path):
    service, _store, _uploads, _derived, reader, original_id = fixture(tmp_path)
    service.quarantine = None
    with pytest.raises(DocumentRefused, match="not configured"):
        analyse(service, original_id)
    assert not reader.calls


def test_actual_local_reader_failure_is_recorded_not_a_complete_empty_read(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(
        tmp_path, parser=LocalDocumentText(), words="invalid\x00plain text"
    )
    reading = analyse(service, original_id)
    assert reading["extraction"]["failure"] == "malformed"
    assert not reading["extraction"]["complete"] and reading["derivative"] is None
    found = service.search("mat_one", "adv_one", store.load("mat_one").version, "plain")
    assert found.partial and not found.matches and not found.searched
    assert "malformed" in found.not_searched[0]["reason"]


@pytest.mark.parametrize("operation", ["analyse", "search", "quote"])
def test_every_operation_checks_authenticated_owner_before_material_access(tmp_path, operation):
    service, store, uploads, derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    uploads.objects.read = Mock(side_effect=AssertionError("cross-owner original access"))
    derived.read = Mock(side_effect=AssertionError("cross-owner derivative access"))
    version = store.load("mat_one").version
    with pytest.raises(DocumentRefused, match="not available"):
        if operation == "analyse":
            service.analyse("mat_one", "other_actor", version, instruction(service, original_id))
        elif operation == "search":
            service.search("mat_one", "other_actor", version, "March")
        else:
            service.quote("mat_one", "other_actor", version, **quote_args(reading))


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_id", "other_actor"),
        ("asset_version", 2),
        ("source_sha256", "0" * 64),
        ("original_id", "missing_original"),
    ],
)
def test_reading_instruction_cannot_select_another_actor_version_or_original(
    tmp_path, field, value
):
    service, store, _uploads, _derived, reader, original_id = fixture(tmp_path)
    request = replace(instruction(service, original_id), **{field: value})
    with pytest.raises((DocumentRefused, ValueError)):
        service.analyse("mat_one", "adv_one", store.load("mat_one").version, request)
    assert not reader.calls


def test_checker_receipt_must_identify_the_actual_examined_bytes(tmp_path):
    service, _store, _uploads, _derived, reader, original_id = fixture(tmp_path)
    genuine = service.quarantine.inspect
    service.quarantine.inspect = lambda *args: replace(genuine(*args), source_sha256="0" * 64)
    with pytest.raises(DocumentRefused, match="actual original"):
        analyse(service, original_id)
    assert not reader.calls


@pytest.mark.parametrize("which", ["original", "derivative"])
def test_corrupt_material_never_reaches_search_or_quotation(tmp_path, which):
    service, store, uploads, derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    if which == "original":
        chunk = store.load("mat_one").uploads[original_id]["chunks"][0]
        path = uploads.objects._path("mat_one", chunk["object_id"])
    else:
        path = derived._path("mat_one", reading["derivative"]["id"])
    path.write_bytes(b"corrupt ciphertext")
    version = store.load("mat_one").version
    found = service.search("mat_one", "adv_one", version, "March")
    assert found.partial and not found.matches and not found.searched
    with pytest.raises(DocumentRefused):
        service.quote("mat_one", "adv_one", version, **quote_args(reading))


@pytest.mark.parametrize(
    "field,value",
    [
        ("asset_version", 2),
        ("source_sha256", "0" * 64),
        ("derivative_sha256", "0" * 64),
        ("source_sha256", "malformed"),
        ("derivative_sha256", "MALFORMED"),
        ("number", 2),
        ("part", "missing"),
        ("start", -1),
        ("end", 99999),
        ("number", True),
    ],
)
def test_quotation_never_guesses_versions_pages_or_offsets(tmp_path, field, value):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    with pytest.raises(DocumentRefused):
        service.quote(
            "mat_one",
            "adv_one",
            store.load("mat_one").version,
            **{**quote_args(reading), field: value},
        )


def test_unread_unit_preserves_explicit_gap_not_a_complete_empty_document(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(
        tmp_path, parser=ControlledReader(TextState.NO_TEXT_LAYER)
    )
    reading = analyse(service, original_id)
    found = service.search("mat_one", "adv_one", store.load("mat_one").version, "March")
    assert found.partial and not found.matches
    assert found.not_searched[0]["unread_units"] == [1]
    with pytest.raises(DocumentRefused, match="no extracted text"):
        service.quote("mat_one", "adv_one", store.load("mat_one").version, **quote_args(reading))


def test_permission_withdrawal_blocks_existing_derivative_and_retry(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    request = instruction(service, original_id)
    service.revoke("mat_one", "adv_one", store.load("mat_one").version, original_id)
    found = service.search("mat_one", "adv_one", store.load("mat_one").version, "March")
    assert found.partial and not found.matches
    with pytest.raises(DocumentRefused):
        service.quote("mat_one", "adv_one", store.load("mat_one").version, **quote_args(reading))
    with pytest.raises(DocumentRefused, match="withdrawn"):
        service.analyse("mat_one", "adv_one", store.load("mat_one").version, request)


def test_restart_reconstructs_receipts_without_releasing_any_new_original(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    restarted = DocumentService(
        UploadService(store, store.upload_storage()),
        service.derivatives,
        LocalDocumentText(),
        quarantine=None,
    )
    quoted = restarted.quote(
        "mat_one", "adv_one", store.load("mat_one").version, **quote_args(reading)
    )
    assert quoted.text == WORDS[:10]
    with pytest.raises(DocumentRefused, match="not configured"):
        restarted.analyse(
            "mat_one",
            "adv_one",
            store.load("mat_one").version,
            instruction(restarted, original_id, request_key="new_read"),
        )


def test_unreadable_retention_state_cannot_be_defaulted_to_read_permission(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    retention(
        service,
        original_id,
        action=RequestedAction.RESTRICT_ACCESS,
        state=RetentionState.APPROVED,
        tombstone=False,
    )
    matter = store.load("mat_one")
    corrupted = {**matter.retention[0], "state": "unrecognised"}
    store.commit(
        replace(matter, retention=(corrupted,), version=matter.version + 1),
        expected_version=matter.version,
    )
    found = service.search("mat_one", "adv_one", store.load("mat_one").version, "March")
    assert found.partial and not found.matches and "retention" in found.not_searched[0]["reason"]
    with pytest.raises(DocumentRefused):
        service.quote("mat_one", "adv_one", store.load("mat_one").version, **quote_args(reading))


def test_stale_file_and_lost_cas_never_publish_a_derivative_receipt(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    request = instruction(service, original_id)
    with pytest.raises(DocumentRefused, match="file moved"):
        service.analyse("mat_one", "adv_one", store.load("mat_one").version - 1, request)
    store.commit = Mock(side_effect=StaleWrite("concurrent mutation"))
    with pytest.raises(StaleWrite):
        analyse(service, original_id)
    assert "document_reading" not in store.load("mat_one").uploads[original_id]


def test_duplicate_read_request_is_idempotent_but_changed_instruction_is_refused(tmp_path):
    service, store, _uploads, _derived, reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    version = store.load("mat_one").version
    assert (
        service.analyse("mat_one", "adv_one", version, instruction(service, original_id)) == reading
    )
    assert store.load("mat_one").version == version and len(reader.calls) == 1
    with pytest.raises(DocumentRefused, match="different instructions"):
        service.analyse(
            "mat_one",
            "adv_one",
            version,
            replace(instruction(service, original_id), purpose="Different purpose"),
        )


def retention(
    service,
    original_id,
    *,
    action=RequestedAction.ERASE,
    state=RetentionState.ERASED_FROM_ACTIVE_SYSTEMS,
    tombstone=True,
    hold=False,
):
    matter = service.store.load("mat_one")
    request = RetentionRequest(
        "rr_one",
        matter.id,
        matter.advocate_id,
        "2026-09-27",
        RequestScope.SELECTED_ASSETS,
        action,
        "Owner retention review",
        "adv_one",
        1,
        assets=(AssetRef(original_id, 1),),
        tombstones=(Tombstone(original_id, 1, "2026-09-27", "rr_one"),) if tombstone else (),
        holds=(Hold("hold_one", "Preserve evidence", "adv_one", "2026-09-27"),) if hold else (),
        state=state,
    )
    service.store.commit(
        replace(matter, retention=(rt.as_dict(request),), version=matter.version + 1),
        expected_version=matter.version,
    )


def test_restored_ciphertext_cannot_bypass_current_original_tombstone(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    retention(service, original_id)
    found = service.search("mat_one", "adv_one", store.load("mat_one").version, "March")
    assert found.partial and not found.matches
    with pytest.raises(DocumentRefused):
        service.quote("mat_one", "adv_one", store.load("mat_one").version, **quote_args(reading))


def test_restricted_access_blocks_text_but_legal_hold_alone_does_not_hide_it(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    analyse(service, original_id)
    retention(service, original_id, state=RetentionState.UNDER_HOLD, tombstone=False, hold=True)
    assert service.search("mat_one", "adv_one", store.load("mat_one").version, "March").matches
    retention(
        service,
        original_id,
        action=RequestedAction.RESTRICT_ACCESS,
        state=RetentionState.APPROVED,
        tombstone=False,
    )
    assert not service.search("mat_one", "adv_one", store.load("mat_one").version, "March").matches


def test_session_revoked_during_parsing_cannot_publish_or_disclose_text(tmp_path):
    service, store, _uploads, _derived, reader, original_id = fixture(tmp_path)
    live = [True]
    service.session_current = lambda: live[0]
    original = reader.extract

    def revoke_during_read(*args, **kwargs):
        result = original(*args, **kwargs)
        live[0] = False
        return result

    reader.extract = revoke_during_read
    with pytest.raises(DocumentRefused, match="session"):
        analyse(service, original_id)
    assert "document_reading" not in store.load("mat_one").uploads[original_id]


def test_exact_unicode_offsets_survive_casefold_expansion(tmp_path):
    service, store, _uploads, _derived, _reader, original_id = fixture(tmp_path)
    analyse(service, original_id)
    version = store.load("mat_one").version
    found = service.search("mat_one", "adv_one", version, "STRASSE")
    assert found.matched_count == 1 and found.matches[0]["words"] == "Straße"
    args = {
        key: found.matches[0]["source"][key]
        for key in quote_args(store.load("mat_one").uploads[original_id]["document_reading"])
    }
    assert service.quote("mat_one", "adv_one", version, **args).text == "Straße"


def test_derivative_store_is_immutable_contained_and_exactly_erasable(tmp_path):
    service, _store, _uploads, derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    ref = reading["derivative"]
    original = derived.read("mat_one", ref["id"], ref["sha256"])
    derived.put("mat_one", ref["id"], original)
    with pytest.raises(ValueError):
        derived.put("mat_one", ref["id"], b"replacement")
    with pytest.raises(ValueError, match="identifier"):
        derived.read("../outside", ref["id"], ref["sha256"])
    assert derived.forget("mat_one", ref["id"], ref["sha256"])
    assert not derived._path("mat_one", ref["id"]).exists()
    assert derived.forget("mat_one", ref["id"], ref["sha256"])


@pytest.mark.parametrize("held", [True, False])
def test_actual_derivative_erasure_obeys_holds_and_restore_tombstones(tmp_path, held):
    service, store, _uploads, derived, _reader, original_id = fixture(tmp_path)
    reading = analyse(service, original_id)
    ref = reading["derivative"]
    ciphertext = derived._path("mat_one", ref["id"]).read_bytes()
    matter = store.load("mat_one")
    request = RetentionRequest(
        "rr_erase",
        matter.id,
        matter.advocate_id,
        "2026-09-27",
        RequestScope.SELECTED_ASSETS,
        RequestedAction.ERASE,
        "Erase only this derivative",
        "adv_one",
        1,
        assets=(AssetRef(ref["id"], 1),),
        copies=(
            Copy(ref["id"] + "#active:document-text", "derivative"),
            Copy(ref["id"] + "#backup:generation-one", "backup"),
        ),
        holds=(Hold("hold_one", "Preserve evidence", "adv_one", "2026-09-27"),) if held else (),
        state=RetentionState.IN_PROGRESS,
    )
    store.commit(
        replace(matter, retention=(rt.as_dict(request),), version=matter.version + 1),
        expected_version=matter.version,
    )
    version = store.load("mat_one").version
    if held:
        with pytest.raises(DocumentRefused, match="hold"):
            service.erase_derivative("mat_one", "adv_one", version, original_id, "rr_erase")
        assert derived._path("mat_one", ref["id"]).exists()
    else:
        erased = service.erase_derivative("mat_one", "adv_one", version, original_id, "rr_erase")
        assert erased["original_erased"] is False and erased["completion_problems"]
        assert not derived._path("mat_one", ref["id"]).exists()
        # Restoring real old ciphertext cannot erase the current tombstone.
        derived._path("mat_one", ref["id"]).write_bytes(ciphertext)
        assert not service.search(
            "mat_one", "adv_one", store.load("mat_one").version, "March"
        ).matches
