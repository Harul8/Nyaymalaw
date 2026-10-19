"""RE-ENTRY AND HANDOVER PRESERVE RESPONSIBILITY. BK-39, BK-58-AC3, BK-59. P32.

WHAT THESE DEFEND
-------------------
Three sentences that are false in the same way -- each describes a thing that
happened to a MESSAGE or a RECORD as though it happened to the responsibility:

    "I handed it over."          (it was offered; nobody accepted)
    "There are no authorities."  (nobody searched for any)
    "The matter is closed."      (a deadline is still live inside it)

Each leaves an obligation with nobody watching it, and each is invisible
afterwards: a handover that was merely sent looks exactly like one that was
taken, right up until the hearing.

ARCHIVE, CLOSE AND DELETE ARE THREE THINGS. BK-59-AC3 says so, and P33 already
made the same separation for material. A matter archived is still held.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.class_a


# ============================ 1. the records are Appendix E's ================


# ================== 2. "none" and "nobody looked" are different ==============


# ======================= 3. offered is not accepted ==========================


# ============================ 4. closure refuses the live ====================


# ===================== 5. archive, close and delete are three ================


# ============================= 6. the served path ============================

BRIEF = ("We act for Ledger Traders in a recovery suit against Kiran Steels. "
         "Goods were supplied on 14 March 2023 and were never paid for.")


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


def test_re_entry_restores_the_matter_and_names_what_was_never_assessed(client):
    """BK-33-AC2, and the honesty half: a section nobody looked at says so
    rather than rendering as empty."""
    matter_id, _ = _matter(client)
    r = client.get(f"/api/matters/{matter_id}/re-entry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matter_id"] == matter_id
    assert body["lifecycle"] == "open"
    assert "sections" in body and body["sections"]
    for name in body["unassessed_sections"]:
        assert "not assessed" in body["sections"][name]


def test_re_entry_on_another_advocates_matter_is_not_found(client):
    """The leak this refuses renders another client's material under this
    client's name."""
    _matter(client)
    r = client.get("/api/matters/mat_someone_else/re-entry")
    assert r.status_code == 404, r.text


def test_the_wire_offers_a_handover_and_it_is_not_accepted(client):
    matter_id, version = _matter(client)
    r = client.post("/api/handovers", json={
        "matter_id": matter_id, "to_actor": "adv_b",
        "next_responsibility": "file the written statement by 1 October",
        "outstanding": ["file the written statement by 1 October"],
        "expected_matter_version": version})
    assert r.status_code == 201, r.text
    h = r.json()["handover"]
    assert h["state"] == "offered"
    assert h["responsibility_moved"] is False
    assert h["owner_of_outstanding"] != "adv_b"


def test_the_wire_refuses_acceptance_by_anyone_but_the_recipient(client):
    """The signed-in advocate is the offeror here, so accepting must refuse --
    the guard is on the identity, not on which route was called."""
    matter_id, version = _matter(client)
    made = client.post("/api/handovers", json={
        "matter_id": matter_id, "to_actor": "adv_b",
        "next_responsibility": "file the WS",
        "expected_matter_version": version}).json()
    hid = made["handover"]["handover_id"]
    r = client.post(f"/api/handovers/{hid}/acceptance", json={
        "matter_id": matter_id,
        "expected_matter_version": made["version"]})
    assert r.status_code == 409, r.text
    assert "not the recipient" in str(r.json()["detail"]["why"])


def test_closing_with_work_still_owed_is_refused_and_names_it(client):
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/closure", json={
        "matter_id": matter_id, "retention": "rr_1",
        "work_product": {"exported_at": "2026-09-13"},
        "continuing_obligations": [{"what": "file the WS", "until": "2026-10-01"}],
        "expected_matter_version": version})
    assert r.status_code == 409, r.text
    assert any("still owed" in b for b in r.json()["detail"]["blockers"])


def test_closing_without_a_retention_decision_is_refused_on_the_wire(client):
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/closure", json={
        "matter_id": matter_id, "work_product": {"exported_at": "x"},
        "expected_matter_version": version})
    assert r.status_code == 409, r.text
    assert any("retention" in b for b in r.json()["detail"]["blockers"])


def test_a_clean_matter_closes_and_reopening_lists_what_to_recheck(client):
    """THE POSITIVE CONTROL for closure, and BK-59-AC3's reopen list."""
    matter_id, version = _matter(client)
    closed = client.post(f"/api/matters/{matter_id}/closure", json={
        "matter_id": matter_id, "retention": "rr_1",
        "work_product": {"exported_at": "2026-09-13"},
        "continuing_obligations": [{"what": "file the WS", "resolved": True}],
        "expected_matter_version": version})
    assert closed.status_code == 201, closed.text
    assert closed.json()["state"] == "closed"

    again = client.post(f"/api/matters/{matter_id}/reopening", json={
        "matter_id": matter_id,
        "expected_matter_version": closed.json()["version"]})
    assert again.status_code == 201, again.text
    checks = again.json()["recheck_before_working"]
    assert any("permitted to act" in c for c in checks)
    assert any("rr_1" in c for c in checks)


def test_archiving_is_a_distinct_state_on_the_wire(client):
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/closure", json={
        "matter_id": matter_id, "retention": "rr_1",
        "work_product": {"exported_at": "x"}, "archive": True,
        "expected_matter_version": version})
    assert r.status_code == 201, r.text
    assert r.json()["state"] == "archived"


def test_reopening_a_matter_that_is_not_closed_is_refused(client):
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/reopening", json={
        "matter_id": matter_id, "expected_matter_version": version})
    assert r.status_code == 409, r.text


def test_a_recorded_event_reopens_only_what_rested_on_it(client):
    """BK-59-AC1, through P18's ledger: the past is not rewritten and nothing
    outside the closure is touched."""
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/events", json={
        "matter_id": matter_id, "kind": "order", "event_id": "order_1",
        "what": "the court directed the written statement by 1 October",
        "expected_matter_version": version})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["by"], "the event is not attributed to anyone"
    assert body["kind"] == "order"
    assert "reopened" in body and "untouched" in body["note"]


def test_the_wire_refuses_an_event_kind_it_does_not_recognise(client):
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/events", json={
        "matter_id": matter_id, "kind": "vibes", "event_id": "e1",
        "what": "x", "expected_matter_version": version})
    assert r.status_code == 422, r.text
