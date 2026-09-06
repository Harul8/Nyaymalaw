"""A1 — E-010, against what the clause actually says.

WHAT THIS REPLACES
-------------------
E-010's two tests were real and they held, and they measured something much
narrower than A1: `anonymous` in the code meant the EMPTY STRING while
`anonymous` in the spec meant unauthenticated. `advocate_id` was a query
parameter, so every non-blank string was an accepted identity — and the eval
passed, green, for the whole time the product had no authentication at all
(B-082).

The three clauses, each with a mechanism:

  1. never restore a matter list on a shared or borrowed device without
     re-authentication  -> the session is bound to the device that
     authenticated, and expires;
  2. never disclose, on a failed or expired credential, WHICH MATTERS EXIST
     -> one message, one status code, and the key derivation runs even for an
     advocate who does not exist, so the clock does not answer either;
  3. never allow an anonymous session to create a matter -> there is no field
     left to assert an identity with.
"""
from __future__ import annotations

import time
from datetime import timedelta

import pytest

from nm.domain.advocate import (
    AdvocateIdentity,
    Credential,
    Enrolment,
    dummy,
    enrol,
    open_session,
    token_fingerprint,
    utcnow,
)
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

#: Satisfies every clause `advocate.enrol` enforces: 8 or more, and an
#: upper-case letter, a lower-case letter, a numeral and a special
#: character. It read "a-password-long-enough-to-enrol" until 6 September
#: 2026, which was long enough and had no capital and no digit -- a
#: fixture that stops satisfying the rule turns every test using it into a
#: test of the refusal.
PASSWORD = "A-password-long-enough-2-enrol"


def _identity(advocate_id: str = "adv_1") -> AdvocateIdentity:
    return AdvocateIdentity(id=advocate_id, name="R Kumar",
                            enrolment="AP/1234/2010", practice="Hyderabad",
                            firm_id="firm_rk")


def _directory(tmp_path, advocate_id: str = "adv_1"):
    from nm.adapters.store.directory import FileDirectory
    d = FileDirectory(tmp_path, key="k" * 32)
    d.enrol(Enrolment(identity=_identity(advocate_id),
                      credential=enrol(PASSWORD)))
    return d


# ===================== the identity that did not exist =====================

@pytest.mark.eval_id("E-010")
def test_the_identity_carries_every_field_the_contract_names():
    """A1's PRODUCES had NO CLASS and no field of it anywhere in `nm/`, and the
    feature stood at `tested` (B-082)."""
    i = _identity()
    assert set(i.as_dict()) == {"id", "name", "enrolment", "practice",
                            "firm_id", "email"}


@pytest.mark.eval_id("E-010")
def test_the_identifying_fields_may_not_be_blank():
    """`id`, `name` and `email` are what an advocate IS to this product: no id
    is no file, and no email is no way to sign in.

    ENROLMENT, PRACTICE AND FIRM BECAME OPTIONAL on 6 September 2026, on the
    advocate's instruction, so registration asks for three things rather than
    seven. The test that pinned them non-blank said `firm_id` most of all,
    because B3's conflicts registry is SCOPED by the firm and a blank one is a
    screen run against a registry of one.

    THAT COST IS NOT GONE, IT IS DEFERRED, and the next test is where it now
    lives. `nm.core.screens` is declared UNWIRED, so nothing live is weakened
    today — and when the screen is built a blank firm must read NOT_ASSESSED
    and never CLEAR.
    """
    for field in ("id", "name"):
        with pytest.raises(ValueError):
            AdvocateIdentity(**{**_identity().as_dict(), field: "   "})

    # EMAIL IS REQUIRED AT THE REGISTRATION DOOR AND NOT ON THE TYPE, and the
    # difference is not an oversight. Every advocate enrolled by
    # `tools/enrol.py` before the field existed has none, and requiring it on
    # the type would make those records unreadable. The route that MINTS a new
    # advocate insists on it; the type that reads an old one cannot.
    AdvocateIdentity(**{**_identity().as_dict(), "email": ""})


def test_an_advocate_with_no_firm_is_a_conflicts_registry_of_one():
    """THE DEFERRED COST, WRITTEN DOWN WHERE IT WILL BE FOUND.

    This does not assert a control that exists. It asserts the SHAPE the
    control must have when it is built: an advocate with no firm cannot be
    screened, and "cannot be screened" is not "clear". A blank firm reaching a
    future screen as a clean result is the absent-input defect aimed at the
    one control that stops the product advising both sides of a dispute.
    """
    lone = AdvocateIdentity(id="r@x.com", name="R Kumar", email="r@x.com")
    assert lone.firm_id == "", (
        "a blank firm must stay blank rather than being defaulted to "
        "something -- a placeholder firm would put every unaffiliated "
        "advocate in ONE registry together, which is worse than none")


# ================ clause 2: a failure discloses nothing ====================

@refuses("A1", 1)
@pytest.mark.eval_id("E-010")
def test_an_unknown_advocate_and_a_wrong_password_are_indistinguishable(tmp_path):
    d = _directory(tmp_path)
    assert d.authenticate("adv_1", "wrong-password-entirely") is None
    assert d.authenticate("nobody-at-all", "wrong-password-entirely") is None
    assert d.authenticate("adv_1", PASSWORD) is not None


@refuses("A1", 1)
@pytest.mark.eval_id("E-010")
def test_the_clock_does_not_disclose_which_advocates_exist(tmp_path):
    """BYTE-IDENTICAL IS NOT ENOUGH.

    A login that returns in microseconds for a stranger and in tens of
    milliseconds for a wrong password discloses which accounts exist just as
    plainly as a different message would — in the one place A1 says nothing
    may. The unknown case verifies against `dummy()` and pays the same cost.

    Asserted as a RATIO with wide latitude rather than as a duration: a
    threshold in milliseconds is a test that fails on a slow machine, and a
    test that fails for the wrong reason gets deleted.
    """
    d = _directory(tmp_path)

    def elapsed(advocate_id: str) -> float:
        t0 = time.perf_counter()
        d.authenticate(advocate_id, "some-wrong-password")
        return time.perf_counter() - t0

    known = min(elapsed("adv_1") for _ in range(3))
    unknown = min(elapsed("no-such-advocate") for _ in range(3))

    assert unknown > known / 4, (
        f"an unknown advocate answered in {unknown * 1000:.1f}ms against "
        f"{known * 1000:.1f}ms for a wrong password. The gap is an oracle: it "
        f"tells anyone who can time a request which advocates are enrolled.")


@pytest.mark.eval_id("E-010")
def test_the_dummy_credential_matches_nothing():
    """The positive control for the timing defence. If `dummy()` ever verified
    something, an unknown advocate would AUTHENTICATE."""
    d = dummy()
    for attempt in ("", "password", "0" * 32, PASSWORD):
        assert not d.verify(attempt)


# =============== clause 1: a session does not travel or last ===============

@refuses("A1", 0)
@pytest.mark.eval_id("E-010")
def test_a_session_does_not_work_from_another_device(tmp_path):
    """A1's first NEVER, mechanically. A token that works from anywhere IS the
    restoration of a matter list on a borrowed machine, however short its
    life."""
    d = _directory(tmp_path)
    now = utcnow()
    token = d.open_session("adv_1", "device-in-chambers", now)

    assert d.session(token, "device-in-chambers", now) is not None
    assert d.session(token, "a-borrowed-laptop", now) is None


@refuses("A1", 0)
@pytest.mark.eval_id("E-010")
def test_a_session_expires(tmp_path):
    d = _directory(tmp_path)
    now = utcnow()
    token = d.open_session("adv_1", "dev", now)

    assert d.session(token, "dev", now + timedelta(hours=11)) is not None
    assert d.session(token, "dev", now + timedelta(hours=13)) is None


@pytest.mark.eval_id("E-010")
def test_signing_out_ends_the_session_on_the_server(tmp_path):
    """A cleared cookie is not a sign-out — it is a tidier screen over a live
    session."""
    d = _directory(tmp_path)
    now = utcnow()
    token = d.open_session("adv_1", "dev", now)
    d.close_session(token, "signed out")
    assert d.session(token, "dev", now) is None


@pytest.mark.eval_id("E-010")
def test_the_token_is_never_written_to_disk(tmp_path):
    """A store holding live tokens is a store whose theft is a login."""
    d = _directory(tmp_path)
    token = d.open_session("adv_1", "dev", utcnow())

    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert token.encode("utf8") not in path.read_bytes(), (
                f"the session token is on disk in {path.name}")


@pytest.mark.eval_id("E-010")
def test_the_password_is_never_written_to_disk(tmp_path):
    d = _directory(tmp_path)
    assert d.authenticate("adv_1", PASSWORD) is not None
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert PASSWORD.encode("utf8") not in path.read_bytes(), (
                f"the password is on disk in {path.name}")


# ============================ the credential ===============================

@pytest.mark.eval_id("E-010")
def test_a_credential_records_the_cost_it_was_made_with():
    """Raising the cost later must not lock out every existing advocate. The
    parameters travel WITH the hash rather than being read from the module at
    verification time."""
    c = enrol(PASSWORD)
    assert (c.n, c.r, c.p) == (2 ** 14, 8, 1)
    assert c.verify(PASSWORD)

    # A credential made at a DIFFERENT cost still verifies against its own.
    from nm.domain.advocate import _derive
    salt = c.salt
    old = Credential(algorithm="scrypt", salt=salt, n=2 ** 10,
                     hash=_derive(PASSWORD, salt, 2 ** 10, 8, 1))
    assert old.verify(PASSWORD), (
        "a credential made at an older cost stopped verifying, so raising the "
        "cost would lock out every advocate enrolled before the change")


@pytest.mark.eval_id("E-010")
def test_a_credential_with_no_hash_is_refused():
    """An empty hash compared against a derived one is a login that always
    fails — which reads to the advocate as a forgotten password rather than as
    a broken record."""
    with pytest.raises(ValueError, match="verifies nothing"):
        Credential(algorithm="scrypt", salt="00", hash="   ")


@pytest.mark.eval_id("E-010")
def test_an_unverifiable_algorithm_is_refused_at_construction():
    with pytest.raises(ValueError, match="unknown credential algorithm"):
        Credential(algorithm="md5", salt="00", hash="ab")


@pytest.mark.eval_id("E-010")
def test_a_short_password_is_refused_in_the_domain_not_at_the_door():
    """An enrolment tool, a migration and a fixture all reach `enrol`. A rule
    that lives at one door is a rule with a back one."""
    with pytest.raises(ValueError, match="8 characters"):
        enrol("short")


@pytest.mark.eval_id("E-010")
def test_two_sessions_never_share_a_token():
    seen = {open_session("adv_1", "dev", utcnow())[0] for _ in range(50)}
    assert len(seen) == 50


@pytest.mark.eval_id("E-010")
def test_what_is_stored_is_a_fingerprint_and_not_the_token():
    token, session = open_session("adv_1", "dev", utcnow())
    assert session.token_fingerprint != token
    assert session.token_fingerprint == token_fingerprint(token)


# ======================= clause 3: on the served wire ======================

@refuses("A1", 2)
@pytest.mark.eval_id("E-010")
def test_the_turn_request_has_no_field_to_assert_an_identity_with(client):
    """A1's third NEVER, structurally.

    The identity used to come from the request BODY, so the caller asserted
    who they were and the product wrote that assertion onto the file. There is
    no field now — the mechanism is the absence.
    """
    from nm.edge.api import TurnRequest

    assert "advocate_id" not in TurnRequest.model_fields, (
        "the turn request carries an advocate id again. Whoever posts it "
        "chooses whose file this turn lands on.")

    # AND THE WIRE REFUSES AN UNAUTHENTICATED TURN.
    client.cookies.clear()
    r = client.post("/api/turn", json={"message": "we act for the plaintiff"})
    assert r.status_code == 401, r.text


def _unguarded_matter_routes(app, caller) -> list[str]:
    """Every `/api/matters*` route that answers WITHOUT a session.

    Extracted from the sweep below so a positive control can drive it over an
    app that deliberately carries one. A sweep whose walk cannot be exercised
    is a sweep whose empty result nobody has ever seen.
    """
    found = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/matters"):
            continue
        probe = path.replace("{matter_id}", "mat_000000000000")
        if caller.get(probe).status_code != 401:
            found.append(path)
    return found


@refuses("A1", 2)
@pytest.mark.eval_id("E-010")
def test_every_matter_route_requires_a_session(client):
    """THE POPULATION IS THE ROUTE TABLE, not a list somebody maintained.

    A route added next month that forgot the dependency is exactly the one
    that would not be in a hand-written list — and it would serve matters to
    anyone who asked.
    """
    from nm.edge.api import app

    client.cookies.clear()
    unguarded = _unguarded_matter_routes(app, client)

    assert not unguarded, (
        f"these matter routes answered without a session: {unguarded}")


@pytest.mark.eval_id("E-010")
def test_the_route_sweep_can_see_an_unguarded_route():
    """THE POSITIVE CONTROL.

    A walk over a route table where every route happens to be guarded returns
    `[]` — and so does a walk that matched nothing at all, because the prefix
    changed or the router moved. The two are indistinguishable from the
    assertion, which is exactly the shape B-049 hid in for weeks.

    So an app is built with one deliberately unguarded matter route, and the
    sweep must report it.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    planted = FastAPI()

    @planted.get("/api/matters/{matter_id}")
    def anyone_may_read_this(matter_id: str) -> dict:  # noqa: ARG001
        return {"secret": "another advocate\'s file"}

    found = _unguarded_matter_routes(planted, TestClient(planted))
    assert found == ["/api/matters/{matter_id}"], (
        f"the sweep did not see a matter route that answers without a "
        f"session; it reported {found}")
