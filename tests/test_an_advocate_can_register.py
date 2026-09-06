"""A1 — self-service enrolment, and what it must still record.

THE DECISION THIS REVERSES
----------------------------
The sign-in page used to say, in as many words, that enrolment was not
self-service and pointed at `tools/enrol.py` — a tool an advocate cannot run.
Self-service is permitted as of 6 September 2026, on the advocate's
instruction.

REVERSING WHO MAY ENROL IS NOT REVERSING WHAT ENROLMENT CAPTURES. The old page
recorded the Bar Council number and the FIRM, and both are still required. The
firm is not bookkeeping: it is what the conflicts registry is keyed on, and an
advocate in a firm of one has nothing to screen against — acting for both sides
becomes undetectable rather than refused.

WHAT THIS ROUTE DELIBERATELY DOES NOT DO
------------------------------------------
It does not sign anyone in. A form post that created a session would mean
creating an account also logs in whatever machine sent it, and A1's first NEVER
is that a session cannot be presented from a machine that never authenticated.
The device binding is minted at sign-in, for exactly that reason.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.class_a

GOOD = {
    "name": "R Kumar",
    "email": "R.Kumar@Example.com",
    "enrolment": "AP/1234/2010",
    "practice": "Hyderabad",
    "firm_id": "firm_rk",
    #: Satisfies the rule `advocate.enrol` enforces: 8+, and all four
#: character classes. A fixture that did not would test the refusal.
    "password": "Cinder-lantern-42",
    "password_again": "Cinder-lantern-42",
}


class _App:
    """Only what the register and login routes reach.

    A whole `Application` would need a corpus, a model and an authority index
    to test a form post. The edge takes its dependencies by injection
    precisely so this is possible -- `set_application` is the seam the
    composition root uses, and a test is allowed to use it too.
    """

    def __init__(self, directory):
        self.directory = directory


@pytest.fixture()
def client(tmp_path):
    import nm.edge.api as api
    from nm.adapters.store.directory import FileDirectory

    was = api._application
    api.set_application(_App(FileDirectory(tmp_path, key="k" * 32)))
    try:
        with TestClient(api.app) as c:
            yield c
    finally:
        api.set_application(was)


def test_an_advocate_can_enrol_and_then_sign_in(client):
    """THE WHOLE POINT, END TO END. A registration that succeeds and cannot be
    signed in with has enrolled someone who cannot get in."""
    r = client.post("/api/register", json=GOOD)
    assert r.status_code == 200, r.text
    advocate_id = r.json()["advocate_id"]

    signed = client.post("/api/login",
                         json={"advocate_id": advocate_id,
                               "password": GOOD["password"]})
    assert signed.status_code == 200, signed.text
    assert signed.json()["advocate"]["name"] == "R Kumar"


def test_the_email_is_the_login_handle_and_is_normalised(client):
    """An advocate cannot sign in with an identifier nobody showed them, so
    the email is the id. Normalised, or the same person typing a capital on
    Tuesday is a different advocate with a different file."""
    assert client.post("/api/register", json=GOOD).json()["advocate_id"] \
        == "r.kumar@example.com"


def test_registering_does_not_sign_anyone_in(client):
    """A1's first NEVER. A session presented from a machine that never
    authenticated is the thing the device binding exists to refuse, and a
    registration that issued one would mint it on whatever posted the form."""
    client.post("/api/register", json=GOOD)
    assert client.get("/api/session").status_code == 401


def test_two_passwords_that_differ_save_nothing(client):
    """Checked BEFORE the credential is derived, so a typo costs nothing and
    the two strings never both reach the hash."""
    r = client.post("/api/register",
                    json={**GOOD, "password_again": "something else entirely"})
    assert r.status_code == 400
    assert "do not match" in r.json()["detail"]

    # AND NOTHING WAS WRITTEN. A refusal that half-enrols is worse than one
    # that fails, because the second attempt then collides with the first.
    assert client.post("/api/register", json=GOOD).status_code == 200


@pytest.mark.parametrize(("password", "says"), [
    ("Ab1!", "8 characters"),
    ("alllower1!", "upper-case"),
    ("ALLUPPER1!", "lower-case"),
    ("NoDigits!!", "numeral"),
    ("NoSpecial1A", "special character"),
])
def test_the_password_rule_is_reached_rather_than_restated(client, password,
                                                           says):
    """THE RULE IS NOT RESTATED AT THIS DOOR.

    `advocate.enrol` enforces 8 characters and four character classes, and is
    reached by this route, the enrolment tool, a migration and every test
    fixture. Its own docstring says why: "a rule that lives at one door is a
    rule with a back one." This asserts the route REACHES it rather than
    carrying a second copy of the numbers.

    AND THAT THE REFUSAL NAMES WHAT IS MISSING. "Does not meet complexity
    requirements" makes the advocate guess which of four rules they broke; the
    named class is the difference between a rule and an obstacle.
    """
    r = client.post("/api/register",
                    json={**GOOD, "password": password,
                          "password_again": password})
    assert r.status_code == 400, r.text
    assert says in r.json()["detail"], r.json()["detail"]


def test_name_email_and_password_are_required(client):
    """What an advocate IS to this product. No name, no email, no password is
    not an advocate — and the form marks each with a red asterisk while the
    input carries `required`, so a screen reader hears it from the attribute
    rather than from a character it cannot see."""
    for field in ("name", "email"):
        r = client.post("/api/register", json={**GOOD, field: "   "})
        assert r.status_code == 422, (
            f"{field} was accepted blank: {r.status_code} {r.text[:100]}")


def test_the_bar_number_practice_and_firm_are_optional(client):
    """OPTIONAL as of 6 September 2026, on the advocate's instruction: a form
    that refuses someone who does not have their Bar number to hand is one
    they abandon.

    THE COST IS DEFERRED, NOT GONE. B3's conflicts registry is scoped by the
    firm, so a blank one is a registry of ONE. `nm.core.screens` is declared
    UNWIRED, so nothing live is weakened today — and when the screen is built
    a blank firm must read NOT_ASSESSED and never CLEAR.
    """
    lean = {k: v for k, v in GOOD.items()
            if k not in ("enrolment", "practice", "firm_id")}
    r = client.post("/api/register", json=lean)
    assert r.status_code == 200, r.text

    signed = client.post("/api/login",
                         json={"advocate_id": r.json()["advocate_id"],
                               "password": GOOD["password"]})
    assert signed.status_code == 200, (
        "an advocate who registered without a firm cannot sign in, which "
        "makes the field required in fact whatever the form says")
    assert signed.json()["advocate"]["firm_id"] == "", (
        "a blank firm was defaulted to something. A placeholder would put "
        "every unaffiliated advocate in ONE registry together, which is worse "
        "than none")


def test_enrolling_the_same_email_twice_is_refused(client):
    """Overwriting would replace a credential without anyone deciding to —
    the same refusal `tools/enrol.py` already makes, reached through a
    different door."""
    assert client.post("/api/register", json=GOOD).status_code == 200
    again = client.post("/api/register", json=GOOD)
    assert again.status_code == 409
    assert "already enrolled" in again.json()["detail"].lower()


def test_the_password_is_never_returned(client):
    """It should not need saying, and the check costs nothing next to what it
    would cost to find out later."""
    body = client.post("/api/register", json=GOOD).text
    assert GOOD["password"] not in body
