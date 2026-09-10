"""A1 — a capital does not make a second advocate.

THE DEFECT THIS CLOSES, WHICH WOULD ONLY HAVE APPEARED IN PRODUCTION
---------------------------------------------------------------------
`POST /api/register` lower-cased the email to make the id. Nothing else did.
`FileDirectory` names the record file after the id as given, so:

    register  R.Kumar@X.com  ->  stored at  r.kumar@x.com.nm
    sign in   R.Kumar@X.com  ->  looks for  R.Kumar@X.com.nm

On Windows and macOS that finds the file, because the filesystem folds case.
On Linux it does not. So the advocate registers, signs in on the developer's
machine, and cannot sign in on the server — and what they see there is
"advocate or password not recognised", which is indistinguishable from having
mistyped their password.

THE SHAPE IS S9, TWO OWNERS FOR ONE TRUTH, with four of them: the register
route knew the canonical form, and the sign-in door, the identity lookup and
the failed-attempt note each took the string as typed.

TWO MECHANISMS, ONE RULE, AND NEITHER IS SUFFICIENT ALONE
-----------------------------------------------------------
`AdvocateIdentity` REFUSES a non-canonical id, so a second spelling cannot be
enrolled. `FileDirectory` FOLDS what comes off the wire, so a capital an
advocate types is not a different advocate. The first without the second would
still fail the sign-in above; the second without the first would let two
spellings be stored and silently collapse them later.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nm.adapters.store.directory import FileDirectory
from nm.domain.advocate import (
    AdvocateIdentity,
    Enrolment,
    canonical_id,
    enrol,
    utcnow,
)

pytestmark = pytest.mark.class_a

PASSWORD = "Cinder-lantern-42"


# ============================== the canonical form ==========================

@pytest.mark.parametrize(("given", "want"), [
    ("R.Kumar@Example.com", "r.kumar@example.com"),
    ("  r.kumar@example.com  ", "r.kumar@example.com"),
    ("ADV_DEMO", "adv_demo"),
    ("adv_demo", "adv_demo"),
    ("", ""),
    (None, ""),
])
def test_the_canonical_form_is_stripped_and_lower_cased(given, want):
    assert canonical_id(given) == want


def test_the_type_refuses_an_id_that_is_not_canonical():
    """SO A SECOND SPELLING CANNOT BE ENROLLED. Folding on the way out without
    this would let two records exist and then collapse them into one file,
    which loses whichever was written first."""
    with pytest.raises(ValueError, match="canonical form"):
        AdvocateIdentity(id="R.Kumar@Example.com", name="R Kumar")


def test_the_canonical_id_is_accepted():
    """The bound. A rule that refused everything would pass the test above."""
    assert AdvocateIdentity(id="r.kumar@example.com", name="R Kumar").id \
        == "r.kumar@example.com"


@pytest.mark.parametrize("unsafe", [
    "../outside", r"..\outside", "folder/name", "name:stream", "con",
    "trailing.", "line\nbreak",
])
def test_an_advocate_id_cannot_name_a_path_or_reserved_device(unsafe):
    with pytest.raises(ValueError, match="cannot contain a path"):
        AdvocateIdentity(id=unsafe, name="Unsafe")


def test_the_ids_already_on_disk_are_canonical():
    """MEASURED, not assumed. `adv_demo`, `adv_gs15` and `adv_scenarios` are
    enrolled in the working store, and a rule that made existing records
    unreadable would be a worse defect than the one it closes."""
    for existing in ("adv_demo", "adv_gs15", "adv_scenarios"):
        assert canonical_id(existing) == existing


# ================================ the store =================================

def test_the_store_finds_an_advocate_whatever_case_is_typed(tmp_path):
    """THE DEFECT, AS A RULE. This is what fails on Linux today."""
    d = FileDirectory(tmp_path, key="k" * 32)
    d.enrol(Enrolment(
        identity=AdvocateIdentity(id="r.kumar@example.com", name="R Kumar"),
        credential=enrol(PASSWORD)))

    for typed in ("r.kumar@example.com", "R.Kumar@Example.com",
                  "  R.KUMAR@EXAMPLE.COM  "):
        assert d.authenticate(typed, PASSWORD) is not None, (
            f"{typed!r} did not reach the advocate enrolled under "
            f"{canonical_id(typed)!r}")
        assert d.identity(typed) is not None


def test_enrolling_the_other_case_is_refused_as_already_enrolled(tmp_path):
    """It is the SAME advocate, so the answer is the refusal that already
    exists — not a second file, and not a silent overwrite of the credential
    the first one is signing in with."""
    from nm.ports.directory import AlreadyEnrolled

    d = FileDirectory(tmp_path, key="k" * 32)
    d.enrol(Enrolment(
        identity=AdvocateIdentity(id="r.kumar@example.com", name="R Kumar"),
        credential=enrol(PASSWORD)))
    with pytest.raises(AlreadyEnrolled):
        d.enrol(Enrolment(
            identity=AdvocateIdentity(id="r.kumar@example.com", name="Someone"),
            credential=enrol("Different-password-9")))


def test_a_wrong_password_is_still_wrong(tmp_path):
    """THE BOUND, and it is the one that matters: a fold that reached the
    right record would be worthless if it also stopped checking."""
    d = FileDirectory(tmp_path, key="k" * 32)
    d.enrol(Enrolment(
        identity=AdvocateIdentity(id="r.kumar@example.com", name="R Kumar"),
        credential=enrol(PASSWORD)))
    assert d.authenticate("R.Kumar@Example.com", "not-the-password") is None


def test_an_untrusted_login_id_cannot_escape_the_advocate_directory(tmp_path):
    d = FileDirectory(tmp_path, key="k" * 32)
    d.enrol(Enrolment(
        identity=AdvocateIdentity(id="victim@example.com", name="Victim"),
        credential=enrol(PASSWORD)))
    enrolled = d._advocates / "victim@example.com.nm"
    outside = tmp_path / "outside.nm"
    enrolled.replace(outside)

    assert d.identity("../outside") is None
    assert d.authenticate("../outside", PASSWORD) is None
    assert d.authenticate_and_open_session(
        "../outside", PASSWORD, "device", utcnow()) is None
    assert outside.exists()
    assert not tuple(d._recovery_locks.iterdir())


# ============================== end to end ==================================

class _App:
    def __init__(self, directory):
        self.directory = directory


@pytest.fixture()
def client(tmp_path):
    import nm.edge.api as api

    was = api._application
    directory = FileDirectory(tmp_path, key="k" * 32)
    api.set_application(_App(directory))
    try:
        with TestClient(api.app) as c:
            def invite(body: dict) -> str:
                email = canonical_id(body["email"])
                return directory.issue_invitation(
                    AdvocateIdentity(
                        id=email, email=email, name=body["name"].strip(),
                        enrolment=body.get("enrolment", "").strip(),
                        practice=body.get("practice", "").strip(),
                        firm_id=body.get("firm_id", "").strip()),
                    "fixture-operator", utcnow())

            c.invite = invite
            yield c
    finally:
        api.set_application(was)


def test_invited_capitals_return_a_canonical_handle_and_both_sign_in(client):
    """The operator may preserve capitals; the returned handle is canonical."""
    typed = "R.Kumar@Example.com"
    body = {
        "name": "R Kumar", "email": typed,
        "password": PASSWORD, "password_again": PASSWORD}
    r = client.post(
        "/api/register", json={
            "password": PASSWORD,
            "password_again": PASSWORD,
        },
        headers={"X-Enrolment-Invitation": client.invite(body)})
    assert r.status_code == 200, r.text
    assert r.json()["advocate_id"] == "r.kumar@example.com", (
        "the route returned a handle that is not the stored id, so the form "
        "would fill in something the store cannot find")

    for handle in (typed, "r.kumar@example.com"):
        signed = client.post("/api/login",
                             json={"advocate_id": handle, "password": PASSWORD})
        assert signed.status_code == 200, f"{handle!r}: {signed.text}"
