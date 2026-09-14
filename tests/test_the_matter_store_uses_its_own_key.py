"""ONE DATA KEY PER MATTER, ON THE REAL STORAGE PATH. BK-85-AC2, BK-21. P07.

`tests/test_one_data_key_per_matter.py` proves the envelope. This proves the
STORE USES IT -- which is a different question and the one CLAUDE.md section 8
says every external review found the product failing: *a guard that is right in
the core and wrong in the composition root is not a guard.* The envelope module
was complete and imported by nothing for two days, and during those two days
every matter still shared one key.

WHAT IS ASSERTED
------------------
    a matter written and read back survives a restart of the process
    each matter's file carries ITS OWN wrapped key, and no two are the same
    the data key is never on disk unwrapped, and never in the record
    a key ring for a different installation cannot open a matter
    a wrapped key moved between matters does not open the other one
    a corrupt record RAISES rather than being retried as another format
    a record written before envelopes existed still opens
    two writers opening one matter at once agree on one data key
    rotation rewraps the keys and does not touch the sealed records
"""
from __future__ import annotations

import base64
import json
import pathlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from nm.adapters.store.envelope import (
    CrossMatterAccess,
    KeyUnavailable,
    LocalKeyRing,
    WrappedKey,
    WrappedKeyUnreadable,
    rewrap_all,
)
from nm.adapters.store.file_store import (
    EncryptionNotConfigured,
    FileMatterStore,
)
from nm.domain.matter import Matter

pytestmark = pytest.mark.class_a

SEAL = "installation-seal-" + "k" * 24
OTHER_SEAL = "a-different-installation-" + "z" * 16
SECRET = "the client admitted the possession began in March 2011"


def _store(root: pathlib.Path, key: str = SEAL) -> FileMatterStore:
    return FileMatterStore(root, key=key)


_COUNTER = [0]


def _matter(store: FileMatterStore, advocate: str = "adv@example.test") -> Matter:
    _COUNTER[0] += 1
    matter = Matter(id=f"mat_{_COUNTER[0]:08x}", advocate_id=advocate,
                    title="Kukatpally possession")
    return store.commit(matter, expected_version=0)


# ============================ it actually works =============================

def test_a_matter_survives_a_write_a_read_and_a_restart(tmp_path):
    """The negative control for everything below. Without it, a store that
    refused every read would satisfy the file."""
    saved = _matter(_store(tmp_path))

    reopened = _store(tmp_path).load(saved.id)
    assert reopened is not None, "the matter did not come back"
    assert reopened.id == saved.id
    assert reopened.advocate_id == saved.advocate_id


def test_the_store_says_both_keys_seal_it(tmp_path):
    """`/api/health` must not report one key when two are doing the work."""
    scheme = _store(tmp_path).scheme
    assert "envelope" in scheme and "NOT-KMS" in scheme, scheme


# ======================= one key per matter, on disk ========================

def test_each_matter_gets_its_own_wrapped_key(tmp_path):
    """THE CRITERION. Two matters on one installation must not share a key,
    or a process that can read either can read both."""
    store = _store(tmp_path)
    first, second = _matter(store), _matter(store)

    keys = sorted((tmp_path / "keys").glob("*.key"))
    assert len(keys) == 2, [k.name for k in keys]
    wrapped = [WrappedKey.from_dict(json.loads(k.read_bytes())) for k in keys]
    assert {w.matter_id for w in wrapped} == {str(first.id), str(second.id)}
    assert wrapped[0].ciphertext != wrapped[1].ciphertext

    ring = LocalKeyRing(SEAL, kek_id="matter-store")
    opened = [ring.unwrap(w.matter_id, w) for w in wrapped]
    assert opened[0] != opened[1], "two matters were given the same data key"


def test_the_data_key_is_never_written_unwrapped(tmp_path):
    """The whole indirection is pointless if the key is beside the record."""
    store = _store(tmp_path)
    saved = _matter(store)
    ring = LocalKeyRing(SEAL, kek_id="matter-store")
    wrapped = WrappedKey.from_dict(
        json.loads((tmp_path / "keys" / f"{saved.id}.key").read_bytes()))
    data_key = ring.unwrap(str(saved.id), wrapped)

    for path in tmp_path.rglob("*"):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        assert data_key not in blob, f"the raw data key is in {path.name}"
        assert base64.b64encode(data_key) not in blob, path.name
        assert data_key.hex().encode() not in blob, path.name


def test_the_sealed_record_holds_no_client_words(tmp_path):
    """An encrypted-at-rest claim is a claim about the bytes."""
    store = _store(tmp_path)
    matter = _matter(store)
    store.record_turn({"turn_id": "t1", "matter_id": str(matter.id),
                       "advocate_said": SECRET, "at": "2026-09-11T00:00:00"})

    for path in tmp_path.rglob("*.nm"):
        body = path.read_bytes()
        assert SECRET.encode() not in body
        assert b"possession" not in body


# ========================= what cannot open a matter ========================

def test_another_installations_seal_cannot_open_a_matter(tmp_path):
    """Scope is the wrap, not a check somebody can forget."""
    saved = _matter(_store(tmp_path))
    stranger = _store(tmp_path, key=OTHER_SEAL)
    with pytest.raises(Exception) as refused:
        stranger.load(saved.id)
    assert not isinstance(refused.value, AssertionError)


def test_a_missing_seal_is_a_hard_failure_and_never_a_plaintext_path(tmp_path):
    """An unconfigured key must never become 'no encryption'.

    The exception is NAMED. `pytest.raises(Exception)` would pass on a typo in
    the constructor call, which is the test asserting that the test is broken.
    """
    with pytest.raises(EncryptionNotConfigured):
        FileMatterStore(tmp_path, key="   ")


def test_one_matters_wrapped_key_does_not_open_another(tmp_path):
    """A wrapped key that is merely LABELLED with its matter can be
    relabelled. The id is bound into the derivation and the AEAD's associated
    data, so presenting A's key as B's does not decrypt wrongly -- it does not
    decrypt at all."""
    store = _store(tmp_path)
    first, second = _matter(store), _matter(store)
    ring = LocalKeyRing(SEAL, kek_id="matter-store")
    theirs = WrappedKey.from_dict(
        json.loads((tmp_path / "keys" / f"{first.id}.key").read_bytes()))

    with pytest.raises(CrossMatterAccess):
        ring.unwrap(str(second.id), theirs)


def test_a_record_moved_under_another_matters_name_is_refused(tmp_path):
    """THE RELABELLING ATTACK. A sealed record names the matter it was sealed
    for, so moving it under another matter's name does not produce a wrong
    plaintext -- it produces a refusal, and the refusal says which matter the
    record actually belongs to."""
    store = _store(tmp_path)
    first, second = _matter(store), _matter(store)
    stolen = (tmp_path / "matters" / f"{first.id}.nm").read_bytes()
    (tmp_path / "matters" / f"{second.id}.nm").write_bytes(stolen)

    with pytest.raises(CrossMatterAccess) as refused:
        _store(tmp_path).load(second.id)
    assert str(first.id) in str(refused.value)


def test_swapping_the_key_records_refuses_rather_than_opening_the_wrong_one(
        tmp_path):
    """The key record is the ONLY place a wrapped key lives, so a shuffled key
    directory is a real fault -- and the answer to it must be a refusal that
    names the mismatch, never a wrong decryption."""
    store = _store(tmp_path)
    first, second = _matter(store), _matter(store)
    one = tmp_path / "keys" / f"{first.id}.key"
    two = tmp_path / "keys" / f"{second.id}.key"
    one_body, two_body = one.read_bytes(), two.read_bytes()
    one.write_bytes(two_body)
    two.write_bytes(one_body)

    reopened = _store(tmp_path)
    for matter_id in (first.id, second.id):
        with pytest.raises(CrossMatterAccess):
            reopened.load(matter_id)


def test_there_is_only_one_place_a_wrapped_key_lives(tmp_path):
    """CLAUDE.md section 4 -- what makes a second copy impossible.

    An earlier wiring put the wrapped key in every sealed record AND in the
    key record, so rotating the key-encrypting key had two populations to
    update and whichever was missed would be unreadable for good. The sealed
    record must therefore carry no key material at all.
    """
    store = _store(tmp_path)
    saved = _matter(store)
    record = json.loads((tmp_path / "matters" / f"{saved.id}.nm").read_bytes())
    assert set(record) == {"envelope", "matter_id", "ciphertext"}, record.keys()
    assert "wrapped_key" not in record
    assert "key_ref" not in json.dumps(record)


# ===================== corrupt is not the same as legacy ====================

def test_a_corrupt_envelope_raises_and_is_not_retried_as_a_legacy_record(
        tmp_path):
    """S3, one level down. A damaged record reported as a record of another
    kind sends whoever reads the error looking for the wrong problem -- and
    the legacy cipher would refuse it too, so the mistake would look like a
    confirmation."""
    store = _store(tmp_path)
    saved = _matter(store)
    path = tmp_path / "matters" / f"{saved.id}.nm"

    doc = json.loads(path.read_bytes())
    doc["ciphertext"] = doc["ciphertext"][:-8] + "AAAAAAAA"
    path.write_bytes(json.dumps(doc).encode("utf8"))
    with pytest.raises(Exception) as broke:
        _store(tmp_path).load(saved.id)
    assert not isinstance(broke.value, AssertionError)

    doc.pop("ciphertext")
    path.write_bytes(json.dumps(doc).encode("utf8"))
    with pytest.raises(WrappedKeyUnreadable):
        _store(tmp_path).load(saved.id)


def test_a_sealed_record_whose_key_is_gone_says_so(tmp_path):
    """A missing key is not an empty matter. Saying which it is is the whole
    difference between a restore and a shrug."""
    store = _store(tmp_path)
    saved = _matter(store)
    (tmp_path / "keys" / f"{saved.id}.key").unlink()

    with pytest.raises(KeyUnavailable) as gone:
        _store(tmp_path).load(saved.id)
    assert "no plaintext path" in str(gone.value)


def test_an_unreadable_matter_is_named_in_the_list_and_does_not_vanish(tmp_path):
    """One unreadable matter must not take the list down and must not
    disappear from it -- six matters and seven with one corrupt are different
    answers."""
    store = _store(tmp_path)
    good = _matter(store)
    broken = _matter(store)
    (tmp_path / "matters" / f"{broken.id}.nm").write_bytes(b"{not json at all")

    listed = _store(tmp_path).list_for("adv@example.test")
    assert [m.id for m in listed.matters] == [good.id]
    assert listed.unreadable == (str(broken.id),)
    assert not listed.complete


# ===================== records written before envelopes =====================

def test_a_record_sealed_before_envelopes_existed_still_opens(tmp_path):
    """PRESERVE ACCEPTED DATA. An installation that upgrades must not find
    its matters unreadable, and the format is decided by what the record says
    it is rather than by when it was written."""
    store = _store(tmp_path)
    saved = _matter(store)
    path = tmp_path / "matters" / f"{saved.id}.nm"

    # Rewrite it in the OLD shape: sealed under the installation cipher.
    plain = store._open(str(saved.id), path.read_bytes())
    path.write_bytes(store._cipher.encrypt(plain))
    (tmp_path / "keys" / f"{saved.id}.key").unlink()

    reopened = _store(tmp_path).load(saved.id)
    assert reopened is not None and reopened.id == saved.id


def test_a_legacy_record_and_an_envelope_record_coexist(tmp_path):
    """An upgrade is gradual: the store must read both on the same day."""
    store = _store(tmp_path)
    legacy, modern = _matter(store), _matter(store)
    path = tmp_path / "matters" / f"{legacy.id}.nm"
    path.write_bytes(store._cipher.encrypt(
        store._open(str(legacy.id), path.read_bytes())))

    listed = _store(tmp_path).list_for("adv@example.test")
    assert {m.id for m in listed.matters} == {legacy.id, modern.id}
    assert listed.unreadable == ()


# ============================== concurrency =================================

def test_two_writers_opening_one_matter_agree_on_one_data_key(tmp_path):
    """Two turns opening one matter at the same instant must not mint two
    keys: the second would replace the first and every record written under
    it would stop opening.

    Repeated, because one lucky pass is not evidence of exclusion.
    """
    for attempt in range(10):
        root = tmp_path / str(attempt)
        store = _store(root)
        matter_id = f"mat_{attempt:04x}beef"
        barrier = threading.Barrier(2)

        def mint(store=store, matter_id=matter_id, barrier=barrier):
            barrier.wait()
            return store._sealer.matter_key(matter_id)[1]

        with ThreadPoolExecutor(max_workers=2) as pool:
            keys = list(pool.map(lambda _: mint(), range(2)))

        assert keys[0] == keys[1], (
            f"attempt {attempt}: two writers minted different data keys, so "
            f"whichever record lost is now unreadable")
        assert len(list((root / "keys").glob("*.key"))) == 1


# =============================== rotation ===================================

def test_rotation_rewraps_the_keys_and_does_not_touch_the_records(tmp_path):
    """The whole point of the indirection: rotating the key-encrypting key
    rewraps a few small records and re-encrypts nothing."""
    store = _store(tmp_path)
    matters = [_matter(store) for _ in range(3)]
    sealed_before = {
        m.id: (tmp_path / "matters" / f"{m.id}.nm").read_bytes() for m in matters}

    old = LocalKeyRing(SEAL, kek_id="matter-store")
    new = old.rotated()
    wrapped = {
        str(m.id): WrappedKey.from_dict(
            json.loads((tmp_path / "keys" / f"{m.id}.key").read_bytes()))
        for m in matters}
    rewrapped, record = rewrap_all(old, new, wrapped)

    assert record.matters == 3
    for matter in matters:
        sealed_after = (tmp_path / "matters" / f"{matter.id}.nm").read_bytes()
        assert sealed_after == sealed_before[matter.id], (
            "rotation re-encrypted the record; it must only rewrap the key")
        assert new.unwrap(str(matter.id), rewrapped[str(matter.id)]) == \
            old.unwrap(str(matter.id), wrapped[str(matter.id)])


def test_a_retired_generation_cannot_open_what_it_wrapped(tmp_path):
    """Rotation that leaves the old generation readable is cosmetic."""
    store = _store(tmp_path)
    saved = _matter(store)
    old = LocalKeyRing(SEAL, kek_id="matter-store")
    new = old.rotated()
    wrapped = WrappedKey.from_dict(
        json.loads((tmp_path / "keys" / f"{saved.id}.key").read_bytes()))

    with pytest.raises(KeyUnavailable):
        new.unwrap(str(saved.id), wrapped)
