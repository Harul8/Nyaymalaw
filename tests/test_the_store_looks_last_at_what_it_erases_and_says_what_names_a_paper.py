"""The store gives a last look at each conversation it erases, and says which of an advocate's conversations still name a paper
(plan AN.53, D244's fourth piece).

D244: a conversation's papers go after it, unless another conversation the advocate keeps still names them, and none on a guess.
Two things only the store can give for that. A LAST LOOK: the erasure and the sweep hand the caller each conversation's owner and
saved record inside its lock, before its key is destroyed - after that nothing can read what it named. The sweep's owner is the
one its deletion mark names, never what the record merely says: a conversation whose record names someone else is left, as one
whose owner record does already was. NAMING: which of some papers any conversation of the advocate's still names - in use, or
deleted and not yet erased - and how many that may be theirs could not be read. Nothing asks for either yet (Erase now and the
sweep are the next pieces).

Offline: a store in a temporary folder and a stand-in clock; no model call; the words are invented.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from nm.shared.store_file_store import PUT_BACK_DAYS, FileMatterStore, owner_mark
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a

KEY = "last-look-control-" + "k" * 32
OWNER, OTHER = "owner@example.test", "other@example.test"
A, B, C = ("doc_" + digit * 24 for digit in "abc")
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=PUT_BACK_DAYS, minutes=1)


def _store(root):
    return FileMatterStore(root, key=KEY)


def _saved(store, matter_id, papers=(), advocate=OWNER):
    rows = [{"documents": [{"document_ref": f"{paper}-{'0' * 64}", "name": "notice.txt"} for paper in papers]}]
    return store.commit(Matter(id=matter_id, advocate_id=advocate, title="Papers", version=1,
                               intake_answers={"rows": {"sent": rows}}), expected_version=0)


# --------------------------------------------------------------------------------------- the last look ---

def test_erase_gives_a_last_look_before_the_key_goes(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_one", [A, B])
    seen = []

    def look(owner, record):
        seen.append((owner, record, (tmp_path / "keys" / "m_one.key").exists()))
    receipt = store.erase("m_one", OWNER, look=look)
    assert receipt["key_destroyed"] is True
    [(owner, record, key_there)] = seen
    assert owner == OWNER and key_there, "looked at while its key was still there"
    assert A.encode() in record and B.encode() in record and json.loads(record)["id"] == "m_one", "the record as saved"


def test_a_conversation_that_cannot_be_opened_is_looked_at_as_nothing_and_erased(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_one", [A])
    (tmp_path / "matters" / "m_one.nm").write_bytes(b"damaged beyond reading")
    seen = []
    assert store.erase("m_one", OWNER, look=lambda owner, record: seen.append((owner, record)))["key_destroyed"] is True
    assert seen == [(OWNER, None)]


def test_no_look_at_what_is_not_theirs_or_not_there(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_one", [A])
    for matter_id, advocate in (("m_one", OTHER), ("m_absent", OWNER)):
        assert store.erase(matter_id, advocate, look=lambda *args: pytest.fail("not theirs to look at")) is None


def test_the_sweep_looks_last_at_each_conversation_it_erases_and_at_no_other(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_old", [A])
    _saved(store, "m_recent", [B])
    _saved(store, "m_theirs", [C], advocate=OTHER)
    store.mark_deleted("m_old", OWNER, NOW)
    store.mark_deleted("m_theirs", OTHER, NOW)
    store.mark_deleted("m_recent", OWNER, NOW + timedelta(days=20))
    seen = []
    assert store.sweep_deleted(LATER, look=lambda owner, record: seen.append((owner, A.encode() in record,
                                                                             C.encode() in record))) == ("m_old", "m_theirs")
    assert seen == [(OWNER, True, False), (OTHER, False, True)], "each with its own owner, as its deletion mark names"


def test_the_sweep_leaves_a_conversation_whose_record_names_someone_else_than_its_deletion_mark(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_one", [A])
    store.mark_deleted("m_one", OWNER, NOW)
    (tmp_path / "matter-owners" / "m_one.json").unlink()
    (tmp_path / "deleted" / "m_one.json").write_text(json.dumps({"format": 1, "owner": owner_mark(OTHER),
                                                                   "at": NOW.isoformat()}), encoding="utf8")
    store = _store(tmp_path)  # as after a restart: no owner record to say whose it is, only the record itself
    assert store.sweep_deleted(LATER, look=lambda *args: pytest.fail("no look at what is left")) == ()
    assert (tmp_path / "keys" / "m_one.key").exists() and (tmp_path / "matters" / "m_one.nm").exists()


def test_the_sweep_looks_at_one_that_cannot_be_opened_as_nothing_and_erases_it(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_one", [A])
    store.mark_deleted("m_one", OWNER, NOW)
    (tmp_path / "matters" / "m_one.nm").write_bytes(b"damaged beyond reading")
    seen = []
    assert store.sweep_deleted(LATER, look=lambda owner, record: seen.append((owner, record))) == ("m_one",)
    assert seen == [(None, None)]


def test_without_a_look_the_erasure_and_the_sweep_are_as_they_were(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_one", [A])
    _saved(store, "m_two", [B])
    store.mark_deleted("m_two", OWNER, NOW)
    assert store.erase("m_one", OWNER)["key_destroyed"] is True
    assert store.sweep_deleted(LATER) == ("m_two",)


# ---------------------------------------------------------------------------------------------- naming ---

def test_a_paper_is_named_by_a_conversation_in_use_or_deleted_and_not_by_one_erased_or_another_advocates(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_in_use", [A])
    _saved(store, "m_deleted", [B])
    _saved(store, "m_erased", [C])
    _saved(store, "m_theirs", [C], advocate=OTHER)
    store.mark_deleted("m_deleted", OWNER, NOW)
    store.erase("m_erased", OWNER)
    assert store.naming(OWNER, {A, B, C}) == (frozenset({A, B}), 0)
    assert store.naming(OTHER, {A, B, C}) == (frozenset({C}), 0)


def test_a_conversation_of_theirs_that_cannot_be_read_is_counted_and_another_advocates_is_not(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_mine", [A])
    _saved(store, "m_damaged", [B])
    _saved(store, "m_theirs", [B], advocate=OTHER)
    (tmp_path / "matters" / "m_damaged.nm").write_bytes(b"damaged beyond reading")
    (tmp_path / "matters" / "m_theirs.nm").write_bytes(b"damaged beyond reading")
    assert store.naming(OWNER, {A, B}) == (frozenset({A}), 1)
    assert store.naming(OTHER, {A, B}) == (frozenset(), 1), "theirs is counted for them"


def test_one_nobody_is_recorded_as_owning_that_cannot_be_read_may_be_theirs_and_is_counted(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_nobodys", [A], advocate=OTHER)
    (tmp_path / "matter-owners" / "m_nobodys.json").unlink()
    (tmp_path / "matters" / "m_nobodys.nm").write_bytes(b"damaged beyond reading")
    assert _store(tmp_path).naming(OWNER, {A}) == (frozenset(), 1), "as after a restart, with no owner record"
    (tmp_path / "matters" / "m_nobodys.nm").unlink()
    (tmp_path / "saved-versions" / "m_nobodys.json").unlink(missing_ok=True)
    _saved(_store(tmp_path), "m_nobodys", [A], advocate=OTHER)
    (tmp_path / "matter-owners" / "m_nobodys.json").unlink()
    assert _store(tmp_path).naming(OWNER, {A}) == (frozenset(), 0), "one that opens says whose it is"


def test_naming_asks_nothing_more_once_every_paper_is_named(tmp_path):
    store = _store(tmp_path)
    _saved(store, "m_one", [A])
    _saved(store, "m_two", [A])
    (tmp_path / "matters" / "m_two.nm").write_bytes(b"damaged beyond reading")
    named, _ = store.naming(OWNER, {A})
    assert named == {A}, "named, and so kept, whatever the rest say"


def test_the_port_declares_naming_and_the_policed_wrapper_passes_the_look(tmp_path):
    from nm.shared.egress_contracts import DataClass, Gatekeeper, Policy, Processor, Sink
    from nm.shared.policed_port_adapter import PolicedPort, port_methods
    from nm.shared.store_port import StorePort
    assert {"naming", "erase", "sweep_deleted"} <= port_methods(StorePort)
    approved = Policy(processors=(Processor(processor_id="local-disk", region="in", purposes=(Sink.STORAGE,),
                                            data_classes=(DataClass.CLIENT_MATTER,), approval_id="IN-PROCESS-NO-EGRESS"),))
    inner = _store(tmp_path)
    _saved(inner, "m_one", [A])
    store = PolicedPort(inner=inner, gate=Gatekeeper(policy=approved), port=StorePort, sink=Sink.STORAGE,
                        processor_id="local-disk")
    seen = []
    assert store.naming(OWNER, {A}) == (frozenset({A}), 0)
    store.erase("m_one", OWNER, look=lambda owner, record: seen.append(owner))
    assert seen == [OWNER]
