"""PREPARATION THAT DOES NOT INVENT TESTIMONY OR AUTHORITY. BK-57. P31.

WHAT THESE DEFEND
-------------------
Three failures, each of which produces a document that looks right:

    A WITNESS PLAN THAT SUPPLIES THE ANSWER. The recollection is contaminated
    the moment the words reach the witness, and no later step recovers it.

    A HEARING PACK THAT LOOKS FINISHED. Its adverse section is empty because
    nobody examined the countercase, and an empty section reads as "there is
    none" -- the most dangerous sentence in the pack.

    A CONCESSION ON AUTHORITY NOBODY GAVE. The commission records no limit,
    something reads that as no ceiling, and the client's case is given away by
    somebody who could not give it.

THE THIRD STATE IS THE SPINE OF ALL THREE. `Assessed.NOT_ASSESSED` on a
section, `Availability.NOT_ASSESSED` on a witness, `Methodology.NOT_ASSESSED`
on an expert, and "no limit is recorded, so nothing is authorised" on the
boundary. Each is a VALUE VISIBLE IN THE OUTPUT, which is §9's rule and the
single most repeated defect in this build's register.
"""
from __future__ import annotations

import pathlib

import pytest


pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ------------------------------------------------------------- fixtures ----


# ============= 1. Appendix E's two unimplemented records, implemented =======


# ================== 2. BK-57-AC2 -- preparation, never coaching =============


# ============ 3. BK-57-AC1 -- the concession boundary, derived ==============


# ============= 4. BK-57-AC3 -- hearing readiness, and its absence ===========


# =============== 5. BK-57-AC4 -- three buckets that never merge =============


# ================= 6. BK-57-AC5 -- an event reaches the pack ================


# ============================== 7. persistence ==============================


# ============================= 8. the served path ===========================

BRIEF = ("We act for Kiran Steels, the defendant in a cheque case. The cheque "
         "was handed over on 3 May 2023 as security for a loan since repaid.")


def _matter(client) -> tuple[str, int]:
    r = client.post("/api/turn", json={
        "message": BRIEF, "today": "2026-09-13",
        "parties": {"Kiran Steels": "client", "Ledger Traders": "adverse"},
        "release": {"scope": "resist the cheque case"},
        "capacity": {"state": "not_in_doubt",
                     "basis": "The advocate assessed that the client "
                              "instructs directly."}})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"], r.json()["matter_version"]


def _package(client, matter_id, version):
    r = client.post("/api/drafting-packages", json={
        "matter_id": matter_id, "document": "written statement",
        "audience": "the City Civil Court", "purpose": "resist the decree",
        "posture": "defendant",
        "cause_title": {"court": "City Civil Court"},
        "theory_sentence": "the cheque was security for a loan that was repaid",
        "reliefs": ["dismissal with costs"],
        "expected_matter_version": version})
    assert r.status_code == 201, r.text
    return r.json()["package"]["package_id"], r.json()["version"]


def _pack_on_wire(client, matter_id, package_id, version, **kw):
    body = {"matter_id": matter_id, "package_id": package_id,
            "expected_matter_version": version}
    body.update(kw)
    return client.post("/api/hearing-packs", json=body)


def test_the_wire_refuses_a_witness_plan_that_supplies_an_answer(client):
    """A contaminated plan is REFUSED, not stored and flagged: a warning
    beside a stored script does not un-say it."""
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _pack_on_wire(client, matter_id, pid, version).json()

    r = client.post(f"/api/hearing-packs/{made['pack']['pack_id']}/witnesses",
                    json={"matter_id": matter_id, "witness": "Ramesh",
                          "topics": ["You will say it was repaid in June"],
                          "expected_matter_version": made["version"]})
    assert r.status_code == 422, r.text
    assert "not saved" in r.json()["detail"]["said"]

    after = client.get(f"/api/hearing-packs/{made['pack']['pack_id']}",
                       params={"matter_id": matter_id})
    assert after.json()["pack"]["witnesses"] == []


def test_the_wire_records_a_proper_witness_plan_and_names_its_gaps(client):
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _pack_on_wire(client, matter_id, pid, version).json()

    r = client.post(f"/api/hearing-packs/{made['pack']['pack_id']}/witnesses",
                    json={"matter_id": matter_id, "witness": "Ramesh",
                          "topics": ["what he recalls of the handover"],
                          "expected_matter_version": made["version"]})
    assert r.status_code == 201, r.text
    assert any("necessary" in p for p in r.json()["problems"])


def test_the_wire_refuses_a_leading_expert_instruction(client):
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _pack_on_wire(client, matter_id, pid, version).json()

    r = client.post(f"/api/hearing-packs/{made['pack']['pack_id']}/experts",
                    json={"matter_id": matter_id, "expert": "Dr Rao",
                          "purpose": "Confirm that the endorsement was added later",
                          "expected_matter_version": made["version"]})
    assert r.status_code == 422, r.text
    assert "the expert states the answer" in r.json()["detail"]["said"]


def test_there_is_no_wire_field_for_testimony_or_a_conclusion(client):
    """The closed schema is the mechanism: `extra="forbid"`."""
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _pack_on_wire(client, matter_id, pid, version).json()
    pack_id = made["pack"]["pack_id"]

    r = client.post(f"/api/hearing-packs/{pack_id}/witnesses", json={
        "matter_id": matter_id, "witness": "Ramesh",
        "testimony": "he will say it was repaid",
        "expected_matter_version": made["version"]})
    assert r.status_code == 422, r.text

    r = client.post(f"/api/hearing-packs/{pack_id}/experts", json={
        "matter_id": matter_id, "expert": "Dr Rao",
        "report": {"conclusions": ["the endorsement was added later"]},
        "expected_matter_version": made["version"]})
    assert r.status_code == 422, r.text


def test_the_in_court_view_keeps_the_three_apart_on_the_wire(client):
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _pack_on_wire(client, matter_id, pid, version).json()

    r = client.get(f"/api/hearing-packs/{made['pack']['pack_id']}/in-court",
                   params={"matter_id": matter_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["verified"]).isdisjoint(body["uncertain"])
    assert "not interchangeable" in body["said"]


def test_the_concession_check_makes_no_concession(client):
    """It is a CHECK. Nothing is written and nothing is given up."""
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/concession-check",
                    json={"proposed": "settle at Rs 90,000"})
    assert r.status_code == 200, r.text
    assert r.json()["within_authority"] is False
    assert "No concession has been made" in r.json()["said"]
    assert r.json()["version"] == version


def test_a_pack_cannot_be_assembled_over_a_package_from_another_matter(client):
    matter_id, version = _matter(client)
    other_id, other_version = _matter(client)
    pid, version = _package(client, matter_id, version)
    r = _pack_on_wire(client, other_id, pid, other_version)
    assert r.status_code == 404, r.text
