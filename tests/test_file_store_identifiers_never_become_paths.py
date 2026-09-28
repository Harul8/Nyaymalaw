"""Every file-store identifier stays an opaque name at every read/write door."""
from __future__ import annotations

import json

import pytest

from nm.shared.store_file_store import FileMatterStore, _enc
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a


def _store(tmp_path):
    return FileMatterStore(tmp_path / "owned", key="opaque-id-control-" + "k" * 24)


@pytest.mark.parametrize("bad", ["../outside", "..\\outside", "/absolute", "C:outside",
                                   "other*", "other?", ".", "", "has space"])
def test_matter_identifier_cannot_traverse_or_pattern_match_storage(tmp_path, bad):
    store = _store(tmp_path)
    outside = tmp_path / "outside.nm"
    outside.write_bytes(b"not a matter")
    with pytest.raises(ValueError, match="opaque storage identifier"):
        store.load(bad)
    with pytest.raises(ValueError):
        store.commit(Matter(id=bad, advocate_id="adv", title="Unsafe"), expected_version=0)
    with pytest.raises(ValueError, match="opaque storage identifier"):
        store.transcripts_for(bad)
    assert outside.read_bytes() == b"not a matter"


def test_turn_identifiers_are_names_not_paths_or_globs(tmp_path):
    store = _store(tmp_path)
    matter = store.commit(Matter(id="matter-1", advocate_id="adv", title="Safe"),
                          expected_version=0)
    with pytest.raises(ValueError, match="opaque storage identifier"):
        store.record_turn({"matter_id": matter.id, "turn_id": "../foreign"})
    with pytest.raises(ValueError, match="opaque storage identifier"):
        store.record_metrics({"turn_id": "../foreign"})
    assert not list((tmp_path / "owned" / "transcripts").glob("*.nm"))


def test_legacy_ciphertext_must_name_the_matter_requested_by_the_reader(tmp_path):
    store = _store(tmp_path)
    saved = store.commit(Matter(id="matter-1", advocate_id="adv", title="Safe"),
                         expected_version=0)
    # Legacy ciphertext is deliberately not bound to its filename by the
    # envelope. The reader must therefore enforce the identity after opening.
    alias = tmp_path / "owned" / "matters" / "matter-2.nm"
    alias.write_bytes(store._cipher.encrypt(json.dumps(_enc(saved)).encode("utf8")))
    with pytest.raises(ValueError, match="identity conflicts"):
        store.load("matter-2")
    assert store.load(saved.id) == saved


def test_list_refuses_a_legacy_ciphertext_alias_with_another_saved_identity(tmp_path):
    store = _store(tmp_path)
    saved = store.commit(Matter(id="matter-1", advocate_id="adv", title="Safe"),
                         expected_version=0)
    alias = tmp_path / "owned" / "matters" / "matter-2.nm"
    alias.write_bytes(store._cipher.encrypt(json.dumps(_enc(saved)).encode("utf8")))
    listing = store.list_for("adv")
    assert [row.id for row in listing.matters] == ["matter-1"]
    assert listing.unreadable == ("matter-2",)


@pytest.mark.parametrize("matter,turn", [
    ("matter__two", "turn"),
    ("matter", "turn__two"),
    ("matter_", "turn"),
])
def test_new_transcript_name_is_unambiguous_when_identifiers_touch_the_delimiter(
    tmp_path, matter, turn
):
    store = _store(tmp_path)
    store.commit(Matter(id=matter, advocate_id="adv", title="Safe"), expected_version=0)
    transcript = {"matter_id": matter, "turn_id": turn, "at": "2026-09-28T10:00:00"}
    store.record_turn(transcript)
    assert store.transcripts_for(matter) == (transcript,)
    assert len(list((tmp_path / "owned" / "transcripts" / "v2").rglob("*.nm"))) == 1
    assert store.transcripts_for("matter") == (() if matter != "matter" else (transcript,))


def test_ambiguous_legacy_name_is_never_charged_to_two_matters(tmp_path):
    store = _store(tmp_path)
    root = tmp_path / "owned" / "transcripts"
    root.mkdir(parents=True, exist_ok=True)
    old = {"matter_id": "matter__two", "turn_id": "turn", "at": "2026-09-28T10:00:00"}
    path = root / "matter__two__turn.nm"
    path.write_bytes(store._cipher.encrypt(json.dumps(old).encode("utf8")))
    assert store.transcripts_for("matter__two") == (old,)
    assert store.transcripts_for("matter") == ()
    assert store.unattributable() == ()

    path.write_bytes(b"corrupt old transcript")
    assert store.transcripts_for("matter__two") == ()
    assert store.transcripts_for("matter") == ()
    assert store.unattributable() == ("matter__two__turn",)


def test_overlapping_legacy_separator_requires_payload_attribution(tmp_path):
    store = _store(tmp_path)
    root = tmp_path / "owned" / "transcripts"
    root.mkdir(parents=True, exist_ok=True)
    old = {"matter_id": "matter_", "turn_id": "turn", "at": "2026-09-28T10:00:00"}
    path = root / "matter___turn.nm"
    path.write_bytes(store._cipher.encrypt(json.dumps(old).encode("utf8")))
    assert store.transcripts_for("matter_") == (old,)
    assert store.transcripts_for("matter") == ()
    assert store.unattributable() == ()

    path.write_bytes(b"corrupt overlapping legacy transcript")
    assert store.transcripts_for("matter_") == ()
    assert store.transcripts_for("matter") == ()
    assert store.unattributable() == ("matter___turn",)
