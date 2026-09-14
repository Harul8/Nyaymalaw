"""BK-22 — signing in depends on the email and the password. Nothing else.

THE ADVOCATE ASKED THE RIGHT QUESTION: *if the email and password match,
they should be able to log in, nothing else.* They could not, and the reason
was a layer below where anyone was looking.

The password is an scrypt hash with its salt and cost -- exactly what a
stored password should be, and scrypt exists so such a hash can sit in the
open. But the record HOLDING it was sealed with `NM_MATTER_KEY`, so
verifying a password meant first opening a file. Hand the server the wrong
key and the comparison is never reached.

That coupling bought almost nothing and cost the failure it caused: SIGNING
IN DEPENDED ON A KEY THAT IS MEANT TO ROTATE. Rotate it for any good reason
and nobody can get in.

CLIENT MATERIAL IS UNAFFECTED. Matters, transcripts and metrics keep the
matter key and always did. What is now in the open is an advocate's own name,
enrolment number and firm, beside a hash that is safe in the open.
"""
from __future__ import annotations

import inspect
import json

import pytest
from nm.adapters.store.directory import FileDirectory

pytestmark = pytest.mark.class_a


def _enrolled(tmp_path, key: str):
    from datetime import datetime, timezone

    from nm.domain.advocate import AdvocateIdentity, Enrolment
    from nm.domain.advocate import enrol as make_credential

    d = FileDirectory(tmp_path, key=key)
    d.enrol(Enrolment(
        identity=AdvocateIdentity(id="a@b.in", name="A", enrolment="",
                                  practice="", firm_id="", email="a@b.in"),
        credential=make_credential("Correct-Horse-9!"),
        created_at=datetime.now(timezone.utc)))
    return d


def test_a_password_verifies_under_a_completely_different_matter_key(tmp_path):
    """THE WHOLE POINT, and it is what failed on 7 September.

    The advocate's account was intact and correct; the server had a different
    `NM_MATTER_KEY`, so the file would not open and they were told their
    credentials were wrong.
    """
    _enrolled(tmp_path, "the-key-it-was-enrolled-under")

    # A DIFFERENT SERVER, A DIFFERENT KEY, THE SAME PASSWORD.
    other = FileDirectory(tmp_path, key="an-entirely-unrelated-key")
    assert other.authenticate("a@b.in", "Correct-Horse-9!") is not None, (
        "signing in still depends on the matter key")
    assert other.authenticate("a@b.in", "wrong") is None
    assert other.why_last_sign_in_failed() == other.WRONG_PASSWORD, (
        "a wrong password reports as something else")


def test_the_record_is_plain_json_and_holds_no_password(tmp_path):
    """A hash, its salt and its cost. Never a password -- which is what makes
    storing it in the open the ordinary thing rather than a concession."""
    _enrolled(tmp_path, "k")
    raw = (tmp_path / "advocates" / "a@b.in.nm").read_text(encoding="utf8")

    doc = json.loads(raw)          # plain, or this raises
    assert doc["credential"]["algorithm"] == "scrypt"
    assert doc["credential"]["salt"] and doc["credential"]["hash"]
    assert "Correct-Horse-9!" not in raw, (
        "the password itself is in the record")


def test_a_record_sealed_before_the_change_still_opens_and_migrates(tmp_path):
    """NO MIGRATION STEP AND NO WINDOW WITH SIGN-IN DOWN.

    `enrol` is the only other writer and it REFUSES to overwrite, so
    unsealing the writer alone would have left every existing record sealed
    forever -- measured on the one account that existed, which did not change
    until the READ was taught to migrate.
    """
    from datetime import datetime, timezone

    from nm.adapters.store.file_store import _Cipher
    from nm.domain.advocate import AdvocateIdentity, Enrolment
    from nm.domain.advocate import enrol as make_credential

    d = FileDirectory(tmp_path, key="the-old-key")
    d.enrol(Enrolment(
        identity=AdvocateIdentity(id="c@d.in", name="C", enrolment="",
                                  practice="", firm_id="", email="c@d.in"),
        credential=make_credential("Another-Good-1!"),
        created_at=datetime.now(timezone.utc)))

    # Put it back in the OLD sealed form, as an existing install holds it.
    path = tmp_path / "advocates" / "c@d.in.nm"
    path.write_bytes(
        _Cipher("the-old-key").encrypt(path.read_bytes()))
    assert not path.read_bytes().startswith(b"{")

    again = FileDirectory(tmp_path, key="the-old-key")
    assert again.authenticate("c@d.in", "Another-Good-1!") is not None, (
        "a record sealed before the change no longer opens")
    assert path.read_bytes().startswith(b"{"), (
        "the record was read and not migrated, so it stays sealed forever "
        "and sign-in keeps depending on the matter key")


def test_the_migration_never_converts_what_it_could_not_read(tmp_path):
    """It runs only where the decrypt SUCCEEDED. A record it cannot open is
    left exactly as it is -- overwriting one would destroy an account whose
    key is merely absent today."""
    src = inspect.getsource(FileDirectory._read)
    migrate = src.index('path.write_text')
    decrypt = src.index('self._cipher.decrypt')
    assert decrypt < migrate, (
        "the rewrite is not inside the successful-decrypt path")


def test_client_material_still_needs_the_key():
    """THE BOUND. Unsealing the DIRECTORY must not have unsealed anything
    holding client material."""
    from nm.adapters.store import file_store

    src = inspect.getsource(file_store.FileMatterStore)
    assert "self._cipher.encrypt" in src, (
        "the matter store stopped encrypting")
