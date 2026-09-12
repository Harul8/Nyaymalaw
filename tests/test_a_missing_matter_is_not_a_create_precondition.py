"""A conditional update cannot resurrect a matter that disappeared after read."""
from __future__ import annotations

from dataclasses import replace

import pytest

from nm.adapters.store.file_store import FileMatterStore
from nm.domain.matter import Matter
from nm.edge.api import application
from nm.ports.store import StaleWrite
from tests.test_a_turn_receipt_is_not_an_archival_trace import _opened
from tests.test_store_roundtrip import KEY

pytestmark = pytest.mark.class_a


def test_initial_creation_and_a_current_version_update_still_survive_restart(tmp_path):
    store = FileMatterStore(tmp_path, key=KEY)
    initial = replace(Matter.create(advocate_id="adv", title="Original"), version=1)
    assert store.commit(initial, expected_version=0) == initial
    restarted = FileMatterStore(tmp_path, key=KEY)
    loaded = restarted.load(initial.id)
    assert loaded == initial
    updated = replace(loaded, version=2, title="Updated instruction")
    assert restarted.commit(updated, expected_version=loaded.version) == updated
    assert FileMatterStore(tmp_path, key=KEY).load(initial.id) == updated


@pytest.mark.parametrize("version", [1, 7])
def test_a_loaded_matter_transferred_away_cannot_be_recreated_by_its_old_writer(tmp_path, version):
    store = FileMatterStore(tmp_path, key=KEY)
    initial = replace(Matter.create(advocate_id="adv", title="Retained original"), version=version)
    store.commit(initial, expected_version=0)
    restarted = FileMatterStore(tmp_path, key=KEY)
    loaded = restarted.load(initial.id)
    assert loaded == initial
    path = store._path(initial.id)
    original_bytes = path.read_bytes()
    transferred = path.with_suffix(".retained")
    path.replace(transferred)
    assert not path.exists()

    with pytest.raises(StaleWrite, match="absent"):
        restarted.commit(replace(loaded, version=version + 1, title="Stale write"),
                         expected_version=loaded.version)

    assert restarted.load(initial.id) is None
    assert not path.exists()
    assert transferred.read_bytes() == original_bytes
    assert not list(path.parent.glob("*.tmp"))
    assert not list(path.parent.glob("*.lock"))


@pytest.mark.parametrize("expected", [None, False, True, -1, 0.0, "0"])
def test_an_invalid_expected_version_cannot_authorise_initial_creation(tmp_path, expected):
    store = FileMatterStore(tmp_path, key=KEY)
    matter = replace(Matter.create(advocate_id="adv", title="Not admitted"), version=1)
    with pytest.raises(ValueError, match="nonnegative integer"):
        store.commit(matter, expected_version=expected)
    assert store.load(matter.id) is None
    assert not list((tmp_path / "matters").glob("*.nm"))


def test_a_served_turn_does_not_recreate_a_matter_transferred_after_admission(client, monkeypatch):
    opened = _opened(client)
    assert opened["matter_version"] > 0
    store = application().store
    engine = application().engine
    read_route = engine._read_route
    path = store._path(opened["matter_id"])
    original_bytes = path.read_bytes()
    transferred = path.with_suffix(".retained")
    moved = []

    def transfer_after_admission(*args, **kwargs):
        result = read_route(*args, **kwargs)
        snapshot = store.load(opened["matter_id"])
        assert snapshot.version == opened["matter_version"]
        path.replace(transferred)
        moved.append(snapshot)
        return result

    monkeypatch.setattr(engine, "_read_route", transfer_after_admission)
    turn_id = "missing-after-admission"
    response = client.post("/api/turn", json={
        "matter_id": opened["matter_id"], "expected_version": opened["matter_version"],
        "turn_id": turn_id, "message": "Keep the invoice date on this file.",
    })

    assert len(moved) == 1, "the actual admitted snapshot must have lost its persisted target"
    assert response.status_code == 409, response.text
    assert "absent" in response.text
    assert store.load(opened["matter_id"]) is None
    assert not path.exists()
    assert transferred.read_bytes() == original_bytes
    assert not moved[0].has_applied(turn_id)
    assert not any(receipt.turn_id == turn_id for receipt in moved[0].turn_receipts)
