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

import json

import pytest

from nm.shared.store_file_store import FileMatterStore

pytestmark = pytest.mark.class_a

KEY = "test-key-for-transcript-attribution"


def _store(tmp_path) -> FileMatterStore:
    return FileMatterStore(tmp_path, key=KEY)


def _turn(matter: str, turn: str) -> dict:
    return {"matter_id": matter, "turn_id": turn, "at": "2026-09-04T10:00:00",
            "message": "what happened", "answer": "what was said back"}


def test_a_legacy_transcript_is_still_found_by_decrypting_it(tmp_path):
    """SIXTEEN OF THESE EXIST. A fix that orphans the record it was written to
    protect has not fixed anything."""
    store = _store(tmp_path)
    legacy = tmp_path / "transcripts"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "turn_old.nm").write_bytes(store._cipher.encrypt(
        json.dumps(_turn("mat_ddd", "turn_old")).encode("utf8")))

    found = store.transcripts_for("mat_ddd")
    assert [t["turn_id"] for t in found] == ["turn_old"]


