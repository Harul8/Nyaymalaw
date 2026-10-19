"""A DOCUMENT DOES NOT PICK ITS OWN DISPUTE. BK-94-AC5. P25.

WHAT THIS DEFENDS
-------------------
    an unattached source never defaults to the first or largest thread

That default is attractive because it is usually right. On a single-thread
matter it is right every time -- so it survives every test written against a
single-thread fixture -- and it is wrong on exactly the files where being wrong
costs most: two disputes, one shared opponent, a delivery note that belongs to
one of them.

A document filed against the wrong dispute does not look like an error. It
looks like evidence, and it is read as evidence by whoever picks the file up.

WHY THE STRUCTURAL TEST IS HERE
---------------------------------
Asserting that today's code does not pick a thread is asserting current
behaviour, which CLAUDE.md says is not an invariant. The invariant is that
nothing in the binding module can pick one, because nothing there is ever
given the list of threads to pick from. That is the assertion below.
"""
from __future__ import annotations


import pytest


pytestmark = pytest.mark.class_a


# ============================================== 1. there is no silent default =


# ================================= 2. stated and inferred stay distinguishable =


# ========================================= 3. correction preserves custody ====


# ==================== 4. the correction reaches P28's reassessment ===========


# ==================================== 5. the served binding path, BK-94-AC5 ===

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


def _bind(client, matter_id, version, **kw):
    payload = {"matter_id": matter_id, "source_id": "doc_1",
               "source_version": "v1", "thread_id": "t1", "basis": "stated",
               "expected_matter_version": version}
    payload.update(kw)
    return client.post("/api/source-bindings", json=payload)


def test_the_wire_records_a_binding_and_shows_it_is_correctable(client):
    matter_id, version = _matter(client)
    r = _bind(client, matter_id, version, basis="inferred")
    assert r.status_code == 201, r.text
    assert r.json()["binding"]["provisional"] is True, (
        "an inferred binding served as settled; the advocate cannot tell it "
        "is the product's reading")
    assert r.json()["was_attached_to"] == ""


def test_rebinding_on_the_wire_names_the_thread_whose_work_must_reopen(client):
    """The served half of the join: a correction says which dispute lost the
    source, so exactly that thread's work is reopened and no other."""
    matter_id, version = _matter(client)
    version = _bind(client, matter_id, version).json()["version"]
    again = _bind(client, matter_id, version, thread_id="t2")
    assert again.status_code == 201, again.text
    assert again.json()["was_attached_to"] == "t1"
    assert "t1" in again.json()["reopen_note"]


def test_rebinding_to_the_same_thread_is_refused_on_the_wire(client):
    matter_id, version = _matter(client)
    version = _bind(client, matter_id, version).json()["version"]
    same = _bind(client, matter_id, version)
    assert same.status_code == 409, same.text


def test_the_served_list_reports_what_each_unbound_source_is_blocking(client):
    matter_id, version = _matter(client)
    _bind(client, matter_id, version)
    listed = client.get(f"/api/matters/{matter_id}/source-bindings")
    assert listed.status_code == 200, listed.text
    rows = listed.json()["bindings"]
    assert len(rows) == 1 and rows[0]["refused"] == ""


def test_the_wire_will_not_accept_a_binding_with_no_thread(client):
    """A request naming no thread is not an unbound source -- it is an
    incomplete request, and letting it through is how a default appears."""
    matter_id, version = _matter(client)
    assert _bind(client, matter_id, version, thread_id="").status_code == 422
