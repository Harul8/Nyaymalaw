"""A VIEW, NOT A MENU -- AND A DECISION THAT IS NOT AUTHORITY. BK-96-AC1,
BK-55-AC3. P27.

WHAT THESE DEFEND
-------------------
Two failures that look like professionalism:

* THE MENU. Four equally polished routes and no view. It reads as balance and
  it hands back the judgement the advocate asked to have exercised.
* THE FABRICATED FIGURE. A cost, a duration or a recovery invented so the
  comparison looks complete. A number in a table reads as measured whatever
  produced it, and it is the part a client repeats.

And one that looks like helpfulness: treating a recorded acceptance as
permission to file. A recommendation, silence and a decision are three states,
and none of them is the client's instruction.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.class_a


# ================================================ 1. a view, never a menu ====


# ======================================= 2. established, estimate, unknown ===


# ============================ 3. a decision is not authority to act ==========


# ================================================= 4. the served path ========

BRIEF = ("We act for Ledger Traders in a recovery suit against Kiran Steels. "
         "The agreement is dated 15 April 2024 and the goods were delivered.")


def _matter(client) -> tuple[str, int]:
    r = client.post("/api/turn", json={
        "message": BRIEF, "today": "2026-09-13",
        "parties": {"Ledger Traders": "client", "Kiran Steels": "adverse"},
        "release": {"scope": "recover the price of goods sold"},
        "capacity": {"state": "not_in_doubt",
                     "basis": "The advocate assessed that the client "
                              "instructs directly."}})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"], r.json()["matter_version"]


def _decide(client, matter_id, version, **kw):
    payload = {"matter_id": matter_id, "disposition": "accept",
               "advice_version": "v1", "scope": "the recovery thread",
               "owner": "adv", "review_trigger": "if the defence pleads limitation",
               "expected_matter_version": version}
    payload.update(kw)
    return client.post("/api/advice-decisions", json=payload)


def test_a_decision_is_recorded_and_read_back_with_its_authority_note(client):
    matter_id, version = _matter(client)
    r = _decide(client, matter_id, version)
    assert r.status_code == 201, r.text
    assert r.json()["decision"]["authorises_action"] is False

    listed = client.get(f"/api/matters/{matter_id}/advice-decisions")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["current"]) == 1
    assert listed.json()["current"][0]["advice_version"] == "v1"


def test_the_wire_refuses_a_caller_naming_its_own_decider(client):
    """The actor is server-derived. A caller that could name its own decider
    could record the client as having accepted advice they never saw."""
    matter_id, version = _matter(client)
    r = _decide(client, matter_id, version, decided_by="the client")
    assert r.status_code == 422, r.text


def test_the_wire_refuses_a_disposition_that_sounds_like_authority(client):
    """There is no "approve for filing". A value that sounded like authority
    would be read as authority."""
    matter_id, version = _matter(client)
    r = _decide(client, matter_id, version, disposition="approve_for_filing")
    assert r.status_code == 422, r.text


def test_the_wire_refuses_a_decision_that_records_no_review_trigger(client):
    matter_id, version = _matter(client)
    r = _decide(client, matter_id, version, review_trigger="")
    assert r.status_code == 422, r.text
