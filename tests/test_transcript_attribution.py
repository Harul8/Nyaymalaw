"""B-083 — a transcript is attributed WITHOUT being decrypted.

THE DEFECT
-----------
`record_turn` keyed the file by turn id alone, so the only way to learn which
matter a transcript belonged to was to decrypt it. `transcripts_for` therefore
appended EVERY undecryptable file to whichever matter was asking — because it
could not tell whose it was — and the consequences ran in both directions:

  * one corrupt turn marked every matter's record `incomplete`, telling six
    advocates their conversation was missing turns that were never theirs; and
  * it disclosed another matter's turn id to each of them.

THE RULE, STATED GENERALLY
---------------------------
Attribution must not depend on being able to read the payload. Anything that
routes a record — which matter, which advocate, which thread — has to be
readable from outside the thing being routed, or the failure case has nowhere
to go but everywhere.
"""
from __future__ import annotations

import pytest

from nm.adapters.store.file_store import FileMatterStore

pytestmark = pytest.mark.class_a

KEY = "test-key-for-transcript-attribution"


def _store(tmp_path) -> FileMatterStore:
    return FileMatterStore(tmp_path, key=KEY)


def _turn(matter: str, turn: str) -> dict:
    return {"matter_id": matter, "turn_id": turn, "at": "2026-09-04T10:00:00",
            "message": "what happened", "answer": "what was said back"}


def test_a_transcript_is_read_back_for_its_own_matter(tmp_path):
    store = _store(tmp_path)
    store.record_turn(_turn("mat_aaa", "turn_1"))
    store.record_turn(_turn("mat_bbb", "turn_2"))

    assert [t["turn_id"] for t in store.transcripts_for("mat_aaa")] == ["turn_1"]
    assert [t["turn_id"] for t in store.transcripts_for("mat_bbb")] == ["turn_2"]


def test_an_unreadable_transcript_belongs_to_one_matter_only(tmp_path):
    """THE INVARIANT. Corrupt one matter's transcript; the OTHER matter's
    record must be untouched and must still read `ok`."""
    store = _store(tmp_path)
    store.record_turn(_turn("mat_aaa", "turn_1"))
    store.record_turn(_turn("mat_bbb", "turn_2"))

    corrupt = tmp_path / "transcripts" / "mat_aaa__turn_1.nm"
    corrupt.write_bytes(b"not a ciphertext this store can open")

    mine = store.transcripts_for("mat_aaa")
    assert len(mine) == 1 and mine[0]["unreadable"] is True, (
        "the matter that OWNS the corrupt turn must be told it is missing")
    assert mine[0]["turn_id"] == "turn_1", (
        "the turn id must survive a payload that does not — it is in the name")

    theirs = store.transcripts_for("mat_bbb")
    assert [t.get("unreadable") for t in theirs] == [None], (
        "another matter's corrupt transcript appeared in this matter's record. "
        "It marks a complete conversation incomplete and discloses a turn id "
        "from a file this advocate may not read.")


def test_the_matter_is_readable_from_the_filename_without_the_key(tmp_path):
    """The mechanism, asserted directly rather than through its effect.

    A test that only checks the behaviour above would pass again if someone
    restored the old scheme and added a lookup table beside it — and the table
    would go stale. The property that matters is that the NAME carries it.
    """
    store = _store(tmp_path)
    store.record_turn(_turn("mat_ccc", "turn_9"))
    names = [p.name for p in (tmp_path / "transcripts").glob("*.nm")]
    assert names == ["mat_ccc__turn_9.nm"], names


def test_a_transcript_with_no_matter_is_named_unattributed_not_dropped(tmp_path):
    """An absent matter id must not silently become another matter's turn, and
    must not vanish either. It gets a name that says what it is."""
    store = _store(tmp_path)
    store.record_turn({"turn_id": "orphan", "at": "2026-09-04T10:00:00"})
    names = [p.name for p in (tmp_path / "transcripts").glob("*.nm")]
    assert names == ["unattributed__orphan.nm"], names
    assert store.transcripts_for("mat_aaa") == (), (
        "an unattributed transcript was served as a matter's own")


def test_a_legacy_transcript_is_still_found_by_decrypting_it(tmp_path):
    """SIXTEEN OF THESE EXIST. A fix that orphans the record it was written to
    protect has not fixed anything."""
    store = _store(tmp_path)
    legacy = tmp_path / "transcripts"
    legacy.mkdir(parents=True, exist_ok=True)
    import json
    (legacy / "turn_old.nm").write_bytes(store._cipher.encrypt(
        json.dumps(_turn("mat_ddd", "turn_old")).encode("utf8")))

    found = store.transcripts_for("mat_ddd")
    assert [t["turn_id"] for t in found] == ["turn_old"]


def test_an_unreadable_legacy_transcript_is_counted_and_never_attributed(tmp_path):
    """THE THIRD STATE, and it is a fact about the STORE.

    A legacy file that will not decrypt has its matter inside the ciphertext,
    so it belongs to no KNOWN matter. Dropping it silently is the absent-input
    shape; adding it to every matter was the defect. It is neither: it is
    counted, once, where it is true.
    """
    store = _store(tmp_path)
    store.record_turn(_turn("mat_eee", "turn_1"))
    legacy = tmp_path / "transcripts" / "turn_lost.nm"
    legacy.write_bytes(b"unopenable")

    assert store.unattributable() == ("turn_lost",)
    assert [t.get("unreadable") for t in store.transcripts_for("mat_eee")] == [None], (
        "an unattributable legacy transcript was charged to a matter")
