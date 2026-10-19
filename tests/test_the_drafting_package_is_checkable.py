"""A DRAFT AN ADVOCATE CAN CHECK, AND CANNOT FILE. BK-56, BK-92-AC3. P29.

WHAT THESE DEFEND
-------------------
A finished-looking document is the most dangerous artefact this product can
produce. Every sentence in it reads the same whether it came from the client's
own words, from a document, or from something the product worked out -- and
the advocate signs it.

So three things, and the third is the one nobody expects to need:

* EVERY CLAIM SAYS WHERE IT CAME FROM, in seven kinds that do not collapse. An
  inference rendered the way an established fact is rendered is what an
  opponent takes apart first.
* EVERY QUOTATION IS CHECKED against the source it names, by P21's owner of
  that question -- and a source the product could not read leaves the claim
  UNVERIFIED rather than making the citation look wrong.
* DRAFTING READINESS IS NOT FILING READINESS. `Readiness` has no member
  meaning ready to file, because a member meaning that would be read as that.
  CHOICE-09 disables the connectors and its `approval` field reads `None`.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.class_a

SPAN = "the goods were delivered on 14 March 2023"


# ================================== 1. the record is Appendix E's ============


# ============================ 2. provenance does not collapse ================


# ================================= 3. quotations are checked =================


# ============================== 4. readiness is not filing ===================


# ============================ 5. stale advice and decisions ==================


# ================================= 6. the export =============================


# ================================ 7. persistence =============================


# ============================== 8. the served path, BK-56-AC1 ================

BRIEF = ("We act for Ledger Traders in a recovery suit against Kiran Steels. "
         "Goods were supplied against invoices on 14 March 2023.")


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


def _prepare(client, matter_id, version, **kw):
    payload = {
        "matter_id": matter_id, "document": "plaint",
        "audience": "the City Civil Court, Hyderabad",
        "purpose": "recover the price of goods sold", "posture": "plaintiff",
        "cause_title": {"court": "City Civil Court", "parties": ["A", "B"]},
        "theory_sentence": "the price is due and unpaid",
        "material_facts": [{"text": "delivery is admitted",
                            "provenance": "extracted_text",
                            "locator": "inv_1::p2", "source_version": "v1",
                            "quoted": SPAN}],
        "reliefs": ["a decree for the price"],
        "expected_matter_version": version}
    payload.update(kw)
    return client.post("/api/drafting-packages", json=payload)


def test_the_served_package_reports_its_problems_and_never_claims_filing(client):
    matter_id, version = _matter(client)
    r = _prepare(client, matter_id, version)
    assert r.status_code == 201, r.text
    package = r.json()["package"]
    assert package["dispatch_authority"] is False
    assert "NOT ready to file" in package["filing_note"]
    assert package["readiness"] in ("incomplete", "ready_to_review")


def test_the_wire_refuses_a_caller_marking_its_own_quotation_verified(client):
    """The one field the packet exists to earn. A caller that could post it
    would be a caller that checked nothing."""
    matter_id, version = _matter(client)
    r = _prepare(client, matter_id, version, material_facts=[
        {"text": "delivery is admitted", "provenance": "extracted_text",
         "locator": "inv_1::p2", "source_version": "v1", "quoted": SPAN,
         "verified": True}])
    assert r.status_code == 422, r.text


def test_the_wire_refuses_a_provenance_it_does_not_recognise(client):
    matter_id, version = _matter(client)
    r = _prepare(client, matter_id, version, material_facts=[
        {"text": "x", "provenance": "obviously_true"}])
    assert r.status_code == 422, r.text


def test_a_quotation_with_no_matching_source_stays_unverified_on_the_wire(client):
    """This matter holds no research reliance at that locator, so the source
    cannot be read and the claim is served unverified rather than as checked."""
    matter_id, version = _matter(client)
    package = _prepare(client, matter_id, version).json()["package"]
    claim = package["claims"][0]
    assert claim["verified"] is False
    assert claim["provenance"] == "extracted_text"


def test_the_export_route_is_a_read_and_carries_no_dispatch(client):
    matter_id, version = _matter(client)
    made = _prepare(client, matter_id, version).json()
    pid = made["package"]["package_id"]
    r = client.get(f"/api/matters/{matter_id}/drafting-packages/{pid}/export")
    assert r.status_code == 200, r.text
    out = r.json()["export"]
    assert out["dispatch_authority"] is False
    assert out["renditions"]["parity"] == "not_assessed"
    assert out["content_digest"]


def test_a_package_on_another_advocates_matter_is_not_found(client):
    matter_id, version = _matter(client)
    made = _prepare(client, matter_id, version).json()
    pid = made["package"]["package_id"]
    r = client.get(f"/api/matters/mat_someone_else/drafting-packages/{pid}")
    assert r.status_code == 404, r.text


def test_the_package_survives_a_reread(client):
    matter_id, version = _matter(client)
    made = _prepare(client, matter_id, version).json()
    pid = made["package"]["package_id"]
    again = client.get(f"/api/matters/{matter_id}/drafting-packages/{pid}")
    assert again.status_code == 200, again.text
    assert again.json()["package"]["package_id"] == pid
