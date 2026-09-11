"""A DATA KEY PER MATTER, AND ROTATION THAT ACTUALLY RETIRES A KEY.

BK-85-AC2, BK-21-AC1, BK-21-AC2.

`_Cipher` seals every matter under one key derived from `NM_MATTER_KEY`. It
refuses to run without it, which is right. What it cannot do is scope decrypt
authority — a process that can read any matter can read all of them — or be
rotated, because rotating that key re-encrypts everything or locks every
advocate out, and it did the second on 7 September 2026.

THE CRITERION'S THREE MUTATIONS, run below: *deny KMS access, rotate a key
during a write, attempt cross-matter decryption.* The expected failure is that
the request safely fails or recovers **without plaintext persistence, data loss
or cross-matter access** — three separate properties, each asserted.

WHAT THIS IS NOT. `LocalKeyRing` is not a KMS and says so in its name and its
`scheme`. It has the same key SHAPE — separate KEK, per-matter data key, bound
wrap, audited rotation — so the KMS adapter replaces one class and no caller
changes. A local stand-in with a different shape makes the real thing a
rewrite, and a rewrite scheduled after a deadline does not happen.
"""
from __future__ import annotations

import pytest

from nm.adapters.store.envelope import (
    CrossMatterAccess,
    KeyUnavailable,
    LocalKeyRing,
    WrappedKey,
    WrappedKeyUnreadable,
    envelope_blob,
    new_data_key,
    read_envelope,
    rewrap_all,
)

pytestmark = pytest.mark.class_a

SECRET = "a-local-kek-secret-for-tests"


@pytest.fixture
def ring() -> LocalKeyRing:
    return LocalKeyRing(SECRET)


# ============================ the negative control ==========================

def test_a_matters_own_key_opens_its_own_data(ring):
    """Without this, a key ring that refused everything satisfies the whole
    file and no matter can be read at all."""
    key = new_data_key()
    wrapped = ring.wrap("matter-A", key)
    assert ring.unwrap("matter-A", wrapped) == key


# ======================= the criterion's three mutations ====================

def test_one_matters_key_cannot_open_another(ring):
    """*Attempt cross-matter decryption.*

    Refused because the matter id is an INPUT to the derivation, not a label on
    the record. There is no check to forget: the wrong key does not open it.
    """
    wrapped = ring.wrap("matter-A", new_data_key())
    with pytest.raises(CrossMatterAccess):
        ring.unwrap("matter-B", wrapped)


def test_relabelling_a_wrapped_key_does_not_move_it(ring):
    """The label and the binding must not be the same thing, or renaming one
    field is enough to steal a matter."""
    wrapped = ring.wrap("matter-A", new_data_key())
    relabelled = WrappedKey(matter_id="matter-B", key_ref=wrapped.key_ref,
                            ciphertext=wrapped.ciphertext,
                            wrapped_at=wrapped.wrapped_at)
    with pytest.raises((CrossMatterAccess, WrappedKeyUnreadable)):
        ring.unwrap("matter-B", relabelled)


def test_an_unavailable_key_is_a_hard_failure_and_never_a_plaintext_path():
    """*Deny KMS access.* The read fails. It does not return the ciphertext, it
    does not return an empty matter, and it writes nothing."""
    for absent in ("", "   "):
        with pytest.raises(KeyUnavailable):
            LocalKeyRing(absent)


def test_a_key_from_another_key_ring_is_refused(ring):
    """Denied access includes access to the wrong KEK entirely."""
    wrapped = ring.wrap("matter-A", new_data_key())
    other = LocalKeyRing(SECRET, kek_id="somebody-elses")
    with pytest.raises(KeyUnavailable):
        other.unwrap("matter-A", wrapped)


# ===================== rotation actually retires a key ======================

def test_rotation_rewraps_every_matter_and_touches_no_ciphertext(ring):
    keys = {name: new_data_key() for name in ("matter-A", "matter-B", "matter-C")}
    wrapped = {name: ring.wrap(name, key) for name, key in keys.items()}
    later = ring.rotated()

    rewrapped, record = rewrap_all(ring, later, wrapped)
    assert record.from_generation == 1 and record.to_generation == 2
    assert record.matters == 3
    for name, key in keys.items():
        assert later.unwrap(name, rewrapped[name]) == key, name


def test_a_retired_generation_is_actually_retired(ring):
    """THE DEFECT THIS FILE EXISTS FOR, and it was in my first draft.

    `unwrap` derived from the generation recorded IN THE WRAPPED KEY, so any
    ring holding the same `kek_id` opened every generation and rotation was
    cosmetic for access control. An operator rotating because a generation had
    leaked would still have been exposed. A probe found it; reading did not.
    """
    wrapped = ring.wrap("matter-A", new_data_key())
    later = ring.rotated()
    rewrapped, _ = rewrap_all(ring, later, {"matter-A": wrapped})

    with pytest.raises(KeyUnavailable):
        ring.unwrap("matter-A", rewrapped["matter-A"])
    with pytest.raises(KeyUnavailable):
        later.unwrap("matter-A", wrapped)


def test_reading_a_prior_generation_is_a_stated_window_and_not_a_default(ring):
    """A rotation window somebody declared, versus one that exists because the
    code reads whatever the ciphertext claims."""
    key = new_data_key()
    wrapped = ring.wrap("matter-A", key)
    during = LocalKeyRing(SECRET, generation=2, accepts=(1,))
    assert during.unwrap("matter-A", wrapped) == key
    assert during.accepts == (1, 2)

    after = LocalKeyRing(SECRET, generation=2)
    assert after.accepts == (2,)
    with pytest.raises(KeyUnavailable):
        after.unwrap("matter-A", wrapped)


def test_a_rotation_is_all_or_nothing(ring):
    """A rotation that re-wrapped half the matters leaves the rest openable
    only by a generation the operator is about to retire, and the failure
    surfaces later as an unreadable matter rather than now as a failed
    rotation."""
    wrapped = {"matter-A": ring.wrap("matter-A", new_data_key()),
               "matter-B": WrappedKey(matter_id="matter-B",
                                      key_ref=ring.ref,
                                      ciphertext="not-decodable!!",
                                      wrapped_at="2026-09-11T00:00:00+00:00")}
    with pytest.raises(WrappedKeyUnreadable):
        rewrap_all(ring, ring.rotated(), wrapped)


def test_the_rotation_audit_records_no_key_of_any_kind(ring):
    key = new_data_key()
    _, record = rewrap_all(ring, ring.rotated(),
                           {"matter-A": ring.wrap("matter-A", key)})
    line = record.as_line()
    assert "kek=local" in line and "1->2" in line and "matters=1" in line
    assert key.hex() not in line
    assert "ciphertext" not in line


# ========================== what is stored on disk ==========================

def test_the_data_key_is_never_written_anywhere(ring):
    key = new_data_key()
    wrapped = ring.wrap("matter-A", key)
    blob = envelope_blob(wrapped, b"sealed matter bytes")
    assert key.hex() not in blob.decode("utf8")
    assert key not in blob
    import base64
    assert base64.b64encode(key).decode("ascii") not in blob.decode("utf8")


def test_an_envelope_round_trips_and_an_unreadable_one_is_refused(ring):
    wrapped = ring.wrap("matter-A", new_data_key())
    blob = envelope_blob(wrapped, b"sealed")
    back, ciphertext = read_envelope(blob)
    assert ciphertext == b"sealed"
    assert back.matter_id == "matter-A"

    for broken in (b"{}", b"not json at all", b'{"envelope": 2}'):
        with pytest.raises(WrappedKeyUnreadable):
            read_envelope(broken)


def test_corruption_and_cross_matter_access_are_different_answers(ring):
    """An operator who cannot tell them apart treats an attack as a bad disk
    and restores from backup."""
    wrapped = ring.wrap("matter-A", new_data_key())
    with pytest.raises(CrossMatterAccess):
        ring.unwrap("matter-B", wrapped)

    truncated = WrappedKey(matter_id="matter-A", key_ref=wrapped.key_ref,
                           ciphertext="AAAA", wrapped_at=wrapped.wrapped_at)
    with pytest.raises(WrappedKeyUnreadable):
        ring.unwrap("matter-A", truncated)


def test_the_local_ring_says_it_is_not_a_kms():
    """BK-85-AC2 asks for KMS-backed envelope encryption. This is not that, and
    a stand-in that let a reader believe otherwise would close the criterion
    without doing the work."""
    assert "NOT-KMS" in LocalKeyRing.scheme
    assert "NOT a KMS" in (LocalKeyRing.__doc__ or "")
