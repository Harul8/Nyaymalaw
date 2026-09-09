"""THE ROSTER IS CONTROLLED, SO THE DOOR IS TOO. BK-31.

TWO DATED DECISIONS CONTRADICTED EACH OTHER
-------------------------------------------
Self-service enrolment was permitted on 6 September 2026. A CONTROLLED PRIVATE
ROSTER was recorded on 8 September. The register link stayed live, so the code
implemented the earlier one.

WHAT SETTLED IT WAS NOT THE DATES. `nm/core/turn.py` relaxes scope and capacity
release to ONE PERSON, and says why in terms:

    "The deployment is a controlled roster of practising advocates and the
     advocate IS the firm, so requiring a second person would stop every
     matter at intake in a solo practice."

That relaxation is sound only while the roster claim is true. With open
self-service a stranger enrols and then releases their own professional
screens -- competence, engagement, capacity -- and the product has no second
person anywhere in the loop. A safety relaxation resting on an assumption the
front door contradicts is the defect, not the door.

WHAT IS TESTED HERE IS THE DOOR. That the relaxation downstream is justified by
it is BK-34's business; this file only proves the premise it depends on.
"""
from __future__ import annotations

import pytest

from nm.edge.api import _refuse_an_unauthorised_enrolment
from tests.conftest import ENROLMENT_CODE

pytestmark = pytest.mark.class_a

GOOD = {
    "name": "R Kumar",
    "email": "R.Kumar@Example.com",
    "password": "Cinder-lantern-42",
    "password_again": "Cinder-lantern-42",
}


def test_an_unconfigured_deployment_is_closed_and_not_open(monkeypatch):
    """FAIL CLOSED, and this is the whole design decision.

    An unconfigured control that admits everyone is the absent-input-reads-as-
    success shape (CLAUDE.md section 9) aimed at the front door -- and this
    door decides who the professional screens get relaxed for. The failure
    mode of getting it the other way round is silent: nobody notices an open
    door, and the first evidence would be a stranger's matter on the roster.
    """
    monkeypatch.delenv("NM_ENROLMENT_CODE", raising=False)
    with pytest.raises(Exception) as caught:
        _refuse_an_unauthorised_enrolment("anything-at-all")
    assert getattr(caught.value, "status_code", None) == 403
    assert "closed" in str(caught.value.detail).lower()


def test_a_blank_configured_code_does_not_open_the_door(monkeypatch):
    """An empty string is not a configuration; it is an unset value wearing
    one. Without this, `NM_ENROLMENT_CODE=` in a deploy script would open
    enrolment to everyone while looking deliberate in the file."""
    for blank in ("", "   ", "\t"):
        monkeypatch.setenv("NM_ENROLMENT_CODE", blank)
        with pytest.raises(Exception) as caught:
            _refuse_an_unauthorised_enrolment(blank)
        assert getattr(caught.value, "status_code", None) == 403


def test_the_wrong_authorisation_is_refused(monkeypatch):
    """THE POSITIVE CONTROL. A guard that only ever passes is not a guard."""
    monkeypatch.setenv("NM_ENROLMENT_CODE", "the-real-authorisation")
    for offered in ("", "guess", "the-real-authorisatio", "THE-REAL-AUTHORISATION"):
        with pytest.raises(Exception) as caught:
            _refuse_an_unauthorised_enrolment(offered)
        assert getattr(caught.value, "status_code", None) == 403, offered


def test_the_right_authorisation_is_admitted(monkeypatch):
    """THE NEGATIVE CONTROL. A door that never opens is not a door, and this
    one has to admit the advocates the practice actually invited."""
    monkeypatch.setenv("NM_ENROLMENT_CODE", "the-real-authorisation")
    _refuse_an_unauthorised_enrolment("the-real-authorisation")
    _refuse_an_unauthorised_enrolment("  the-real-authorisation  ")


def test_the_refusal_tells_the_advocate_what_to_do_instead(monkeypatch):
    """An advocate who cannot enrol and is told nothing simply leaves.

    The route that still works -- enrolment by the practice -- has to be in
    the message, or a controlled roster is indistinguishable from a broken
    product.
    """
    monkeypatch.delenv("NM_ENROLMENT_CODE", raising=False)
    with pytest.raises(Exception) as caught:
        _refuse_an_unauthorised_enrolment("x")
    said = str(caught.value.detail).lower()
    assert "enrolled by the practice" in said or "administers" in said, (
        "the refusal does not say how to get in, so it reads as an outage")


def test_it_is_refused_on_the_wire_and_not_only_in_the_function(client,
                                                               monkeypatch):
    """VERIFY ON THE BYTES. CLAUDE.md section 8.

    A guard that is right in the function and unreached by the route is the
    failure this repository has recorded most: forty offline tests passing
    while every served turn crashed. So this drives the real ASGI app.
    """
    # The fixture authorises by default; strip it to become a stranger.
    del client.headers["X-Enrolment-Code"]
    r = client.post("/api/register", json=GOOD)
    assert r.status_code == 403, r.text
    assert "not recognised" in r.text or "closed" in r.text

    client.headers["X-Enrolment-Code"] = ENROLMENT_CODE
    assert client.post("/api/register", json=GOOD).status_code == 200


def test_an_unauthorised_attempt_enrols_nobody(client):
    """A REFUSAL THAT HALF-ENROLS IS WORSE THAN ONE THAT FAILS, because the
    advocate's second attempt then collides with a record they never made."""
    del client.headers["X-Enrolment-Code"]
    assert client.post("/api/register", json=GOOD).status_code == 403

    client.headers["X-Enrolment-Code"] = ENROLMENT_CODE
    assert client.post("/api/register", json=GOOD).status_code == 200, (
        "the refused attempt left a record behind, so the authorised advocate "
        "now collides with an enrolment that was never allowed to happen")


def test_the_authorisation_is_compared_without_leaking_its_length(monkeypatch):
    """`hmac.compare_digest`, not `==`.

    A timing-variable comparison on a shared secret is the kind of defect that
    is invisible in every test and real in production. Asserted on the source
    because the behaviour it prevents cannot be observed from here.
    """
    import inspect

    from nm.edge import api
    body = inspect.getsource(api._refuse_an_unauthorised_enrolment)
    assert "compare_digest" in body, (
        "the authorisation is compared with a timing-variable operator")
