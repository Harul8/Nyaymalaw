"""The rebuilt app reads existing encrypted value records without a retired engine."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nm.advise.answer_contracts import Answer, Element, ElementKind, Mode, Route
from nm.advise.turn_receipt_contracts import TurnReceipt, answer_payload
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.advocate_memory_codec import decode_memory
from nm.arrive.advocate_memory_contracts import Preferences
from nm.arrive.directory_port import MemoryUnavailable
from nm.arrive.store_directory import FileDirectory
from nm.shared.source_excerpt_contracts import SourceExcerpt
from nm.shared.store_file_store import FileMatterStore, _enc, _matter
from nm.shared.store_port import StaleWrite
from nm.work_the_file.loop_record_contracts import (
    LoopEvent,
    LoopIdentity,
    LoopMode,
    LoopRecord,
    StepKind,
    digest,
)
from nm.work_the_file.matter_contracts import Matter

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
KEY = "synthetic-contract-relocation-key"
ROOT = Path(__file__).resolve().parents[1]


def memory_record():
    return {"schema": 1, "account_id": "adv_contract", "version": 1,
            "settings": {"advice_form": "bullets", "court_ids": ["hc_telangana"]},
            "approved": True, "approved_by": "adv_contract", "approved_at": NOW.isoformat()}


def matter_record():
    source = SourceExcerpt.capture(label="Saved source", locator="paragraph 3",
        namespace="judgments", text="The historical source words remain unchanged.",
        kind="authority", valid_from="", valid_to="")
    answer = Answer(route=Route.MATTER, mode=Mode.EXPLANATION,
        mode_statement="Historical saved explanation", elements=(Element(
            kind=ElementKind.FINDING, text="Historical saved finding",
            refs=(source.locator,), source=source),))
    receipt = TurnReceipt(turn_id="turn_record", offer_fingerprint="a" * 64,
        recorded_at=NOW.isoformat(), message="Original supplied message",
        input_admitted=True, answer=answer_payload(answer))
    identity = LoopIdentity("mat_contract", "adv_contract", "turn_log", digest("offer"),
                            digest("principles"), digest("tools"), 1, LoopMode.RECORDED)
    start = LoopEvent.create(1, StepKind.START, NOW.isoformat(),
                             {"original": "Retained historical work input"}, identity.fingerprint)
    stop = LoopEvent.create(2, StepKind.STOP, NOW.isoformat(),
                            {"reason": "budget", "released": False}, start.fingerprint)
    return Matter(id="mat_contract", advocate_id="adv_contract", title="Saved matter",
                  turn_receipts=(receipt,), turns_applied=("turn_record",),
                  loop_records=(LoopRecord(identity, (start, stop)),), version=1)


def test_existing_memory_wire_shape_and_exact_codec_are_preserved():
    raw = json.dumps(memory_record()).encode()
    record = decode_memory(raw, "adv_contract")
    assert record.as_dict() == memory_record()
    assert record.preferences == Preferences.from_values(memory_record()["settings"])


@pytest.mark.parametrize("damage", ["version", "unknown", "unapproved", "foreign"])
def test_memory_relocation_retains_consequential_rejections(damage):
    value = memory_record()
    if damage == "version":
        value["schema"] = 2
    elif damage == "unknown":
        value["unchecked_field"] = True
    elif damage == "unapproved":
        value["approved"] = False
    else:
        value["account_id"] = value["approved_by"] = "adv_other"
    with pytest.raises(ValueError):
        decode_memory(json.dumps(value).encode(), "adv_contract")


def test_encrypted_account_keeps_saved_preferences_and_login(tmp_path):
    directory = FileDirectory(tmp_path, key=KEY)
    directory.enrol(Enrolment(AdvocateIdentity("adv_contract", "Contract Reader"),
                             enrol("Synthetic-store-password-42!"), NOW))
    # Inject the pre-existing closed wire record, rather than a new engine output.
    document = directory._read("adv_contract")
    raw = json.dumps(memory_record()).encode()
    document["advocate_memory"] = directory._cipher.encrypt(raw).decode("ascii")
    directory._replace_advocate(directory._advocate_path("adv_contract"), document)
    fresh = FileDirectory(tmp_path, key=KEY)
    held = fresh.advocate_memory("adv_contract")
    assert held.as_dict() == memory_record()
    opened = fresh.authenticate_and_open_session("adv_contract", "Synthetic-store-password-42!",
                                                 "synthetic-device", NOW)
    assert opened is not None and opened[0].id == "adv_contract"
    changed = replace(held, version=2,
                      preferences=Preferences.from_values({"advice_form": "prose"}))
    fresh.record_advocate_memory(changed, expected_version=1)
    assert FileDirectory(tmp_path, key=KEY).advocate_memory("adv_contract") == changed
    # Wrong schema is not silently interpreted as absent preferences.
    bad = {**memory_record(), "schema": 9}
    document = fresh._read("adv_contract")
    document["advocate_memory"] = fresh._cipher.encrypt(json.dumps(bad).encode()).decode("ascii")
    fresh._replace_advocate(fresh._advocate_path("adv_contract"), document)
    with pytest.raises(MemoryUnavailable):
        fresh.advocate_memory("adv_contract")


def test_saved_loop_receipt_and_source_shapes_survive_encrypted_roundtrip(tmp_path):
    before = matter_record()
    wire = json.loads(json.dumps(_enc(before)))
    rebuilt = _matter(wire)
    assert rebuilt == before
    assert json.loads(json.dumps(_enc(rebuilt))) == wire
    store = FileMatterStore(tmp_path, key=KEY)
    store.commit(before, expected_version=0)
    fresh = FileMatterStore(tmp_path, key=KEY)
    reopened = fresh.load(before.id)
    assert reopened == before
    assert reopened.turn_receipts[0].validated_answer().elements[0].source.text == (
        "The historical source words remain unchanged.")
    saved_bytes = next((tmp_path / "matters").glob("*.nm")).read_bytes()
    assert b"Original supplied message" not in saved_bytes
    with pytest.raises(StaleWrite):
        fresh.commit(replace(before, version=2), expected_version=0)
    assert fresh.load(before.id) == before


@pytest.mark.parametrize("damage", ["loop_event", "loop_field", "source_text", "reply_field"])
def test_persisted_integrity_still_rejects_changed_or_unknown_content(damage):
    wire = json.loads(json.dumps(_enc(matter_record())))
    if damage == "loop_event":
        wire["loop_records"][0]["events"][0]["payload_json"] = '{"changed":true}'
    elif damage == "loop_field":
        wire["loop_records"][0]["unknown"] = "must not disappear"
    elif damage == "source_text":
        wire["turn_receipts"][0]["answer"]["elements"][0]["source"]["text"] = "Altered passage"
    else:
        wire["turn_receipts"][0]["answer"]["unchecked_status"] = "approved"
    with pytest.raises(ValueError):
        _matter(wire)


def test_store_auth_and_old_receipt_readback_do_not_import_archived_code():
    script = r'''
import importlib.abc
import sys
import tempfile
from pathlib import Path
class RejectArchive(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "nm.Archives" or fullname.startswith("nm.Archives."):
            raise AssertionError("Archived dependency: " + fullname)
sys.meta_path.insert(0, RejectArchive())
from tests.test_active_saved_contracts import (
    test_existing_memory_wire_shape_and_exact_codec_are_preserved,
    test_encrypted_account_keeps_saved_preferences_and_login,
    test_saved_loop_receipt_and_source_shapes_survive_encrypted_roundtrip,
)
test_existing_memory_wire_shape_and_exact_codec_are_preserved()
with tempfile.TemporaryDirectory() as folder:
    test_encrypted_account_keeps_saved_preferences_and_login(Path(folder) / "accounts")
    test_saved_loop_receipt_and_source_shapes_survive_encrypted_roundtrip(Path(folder) / "matter")
assert not any(name == "nm.Archives" or name.startswith("nm.Archives.") for name in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, text=True,
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
