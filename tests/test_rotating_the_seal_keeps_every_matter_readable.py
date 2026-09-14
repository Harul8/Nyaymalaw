"""ROTATING THE SEAL MUST NOT LOSE A MATTER. BK-21-AC1, BK-21-AC2. P07.

THE FAILURE THIS EXISTS FOR IS RECORDED AND WAS PAID FOR
----------------------------------------------------------
`NM_MATTER_KEY` and the OpenAI credential once held the same value, and
rotating the credential -- which happens as a matter of routine -- would have
made every stored matter permanently unreadable. That is BK-21.

P07 changes what rotation MEANS. The seal is no longer the key the records are
encrypted with; it is the key that WRAPS each matter's own data key. So a
rotation rewrites the small key records and touches no ciphertext, and a tool
that did not know this would rotate the seal, leave every wrapped key under a
key nobody holds any more, and produce exactly the catastrophe the tool was
written to prevent.

WHICH IS NOT HYPOTHETICAL. Envelope and key records are both JSON, and the
tool's classifier filed readable text under "deliberately open, leave alone".
For the sealed records that is right. For the key records it was fatal, and it
was silent -- the run would have reported success.

WHAT IS ASSERTED
------------------
    every matter still opens after the seal is rotated
    the sealed records are BYTE-IDENTICAL: rotation rewraps, it re-encrypts nothing
    the old seal stops working, or the rotation was cosmetic
    a key record that will not unwrap stops the rotation before anything is written
"""
from __future__ import annotations

import json
import pathlib

import pytest
from nm.adapters.store.envelope import (
    LocalKeyRing,
    WrappedKey,
    WrappedKeyUnreadable,
)
from nm.adapters.store.file_store import FileMatterStore
from nm.domain.matter import Matter

from backend.operations.rekey_matter_store import (
    ENVELOPE,
    KEY_RECORD,
    OPEN,
    SEALED,
    _Cipher,
    classify,
    rewrap_key_records,
)

pytestmark = pytest.mark.class_a

OLD_SEAL = "the-old-installation-seal-" + "a" * 20
NEW_SEAL = "the-new-installation-seal-" + "b" * 20


def _populated(root: pathlib.Path, seal: str = OLD_SEAL) -> list[Matter]:
    store = FileMatterStore(root, key=seal)
    saved = []
    for n in range(3):
        matter = Matter(id=f"mat_{n:08x}", advocate_id="adv@example.test",
                        title=f"matter {n}")
        saved.append(store.commit(matter, expected_version=0))
    return saved


# ======================== the classifier tells them apart ===================

def test_a_key_record_is_not_filed_as_an_ordinary_open_file(tmp_path):
    """THE DEFECT, caught at its source. Both are JSON; only one must be
    rewritten by a rotation, and the other must never be."""
    _populated(tmp_path)
    old = _Cipher(OLD_SEAL)

    key_record = next((tmp_path / "keys").glob("*.key")).read_bytes()
    sealed = next((tmp_path / "matters").glob("*.nm")).read_bytes()

    assert classify(key_record, old) == KEY_RECORD
    assert classify(sealed, old) == ENVELOPE
    assert classify(b"tab\tseparated\taudit\tline", old) == OPEN


def test_a_legacy_sealed_record_is_still_classified_for_re_encryption(tmp_path):
    """The old path must keep working: a record written before envelopes is
    re-encrypted, because its key IS the seal."""
    old = _Cipher(OLD_SEAL)
    assert classify(old.encrypt(b"a legacy matter"), old) == SEALED


# ============================ rotation preserves ============================

def test_every_matter_opens_after_the_seal_is_rotated(tmp_path):
    """THE POINT OF THE FILE."""
    saved = _populated(tmp_path)
    records = sorted((tmp_path / "keys").glob("*.key"))

    for path, body in rewrap_key_records(records, OLD_SEAL, NEW_SEAL):
        path.write_bytes(body)

    rotated = FileMatterStore(tmp_path, key=NEW_SEAL)
    for matter in saved:
        reopened = rotated.load(matter.id)
        assert reopened is not None, f"{matter.id} was lost by the rotation"
        assert reopened.title == matter.title


def test_rotation_does_not_touch_one_byte_of_ciphertext(tmp_path):
    """The whole argument for the indirection. Re-encrypting the records
    would make a rotation a migration, and a migration is the thing nobody
    runs."""
    _populated(tmp_path)
    before = {p.name: p.read_bytes()
              for p in sorted((tmp_path / "matters").glob("*.nm"))}

    for path, body in rewrap_key_records(
            sorted((tmp_path / "keys").glob("*.key")), OLD_SEAL, NEW_SEAL):
        path.write_bytes(body)

    after = {p.name: p.read_bytes()
             for p in sorted((tmp_path / "matters").glob("*.nm"))}
    assert after == before


def test_the_old_seal_stops_opening_the_store(tmp_path):
    """A rotation that leaves the old key working is cosmetic, and an operator
    rotating because a key leaked would still be exposed."""
    saved = _populated(tmp_path)
    for path, body in rewrap_key_records(
            sorted((tmp_path / "keys").glob("*.key")), OLD_SEAL, NEW_SEAL):
        path.write_bytes(body)

    stale = FileMatterStore(tmp_path, key=OLD_SEAL)
    # NAMED, for the same reason as below: the old seal derives a different
    # wrapping key, so the AEAD tag fails and the record -- which still names
    # the right matter -- is unreadable rather than cross-matter.
    with pytest.raises(WrappedKeyUnreadable):
        stale.load(saved[0].id)


# ============================== all or nothing ==============================

def test_a_key_that_will_not_unwrap_stops_the_rotation_before_any_write(
        tmp_path):
    """A half-rotated store is worse than either end of the operation: the
    records nobody rewrapped open only with a key the operator is about to
    discard, and the failure surfaces later as an unreadable matter rather
    than now as a failed rotation."""
    _populated(tmp_path)
    records = sorted((tmp_path / "keys").glob("*.key"))
    before = {p: p.read_bytes() for p in records}

    # One record wrapped under a DIFFERENT installation's key ring.
    stranger = LocalKeyRing("a-third-installation-" + "c" * 20,
                            kek_id="matter-store")
    victim = records[1]
    theirs = WrappedKey.from_dict(json.loads(victim.read_bytes()))
    victim.write_bytes(json.dumps(
        stranger.wrap(theirs.matter_id, b"x" * 32).as_dict()).encode("utf8"))

    # THE EXCEPTION IS NAMED. `pytest.raises(Exception)` would also pass on a
    # typo in the call, which is the test asserting that the test is broken.
    with pytest.raises(WrappedKeyUnreadable):
        rewrap_key_records(records, OLD_SEAL, NEW_SEAL)

    for path, body in before.items():
        if path != victim:
            assert path.read_bytes() == body, (
                f"{path.name} was rewritten before the rotation failed")
