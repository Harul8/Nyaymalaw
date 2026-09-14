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
from nm.core import drafting as dr
from nm.domain.advice_decision import AdviceDecision, Disposition, supersede
from nm.domain.drafting import (
    DECLARED_FIELDS,
    Claim,
    DrafterBrief,
    Provenance,
    Readiness,
    refuse_filing_claim,
)

pytestmark = pytest.mark.class_a

SPAN = "the goods were delivered on 14 March 2023"


def _claim(**kw) -> Claim:
    base = dict(text="delivery is admitted", provenance=Provenance.EXTRACTED_TEXT,
                locator="inv_1::p2", source_version="v1", quoted=SPAN)
    base.update(kw)
    return Claim(**base)


def _brief(**kw) -> DrafterBrief:
    base = dict(
        package_id="pkg_1", matter_id="m1", document="plaint",
        audience="the City Civil Court, Hyderabad",
        purpose="recover the price of goods sold", posture="plaintiff",
        cause_title={"court": "City Civil Court", "parties": ["A", "B"]},
        theory_sentence="the price is due and unpaid",
        material_facts=(_claim(),), reliefs=("a decree for the price",),
        lossless=True)
    base.update(kw)
    return DrafterBrief(**base)


# ================================== 1. the record is Appendix E's ============

def test_the_brief_carries_every_field_the_appendix_declares():
    """BK-56-AC2, asserted against `assurance/specification/schemas.yaml` rather than a copy.

    A test that checked a list inside this repository against another list
    inside this repository would pass while both drifted from the contract.
    """
    import dataclasses

    import yaml
    schemas = yaml.safe_load(
        open("assurance/specification/schemas.yaml", encoding="utf8"))["schemas"]
    declared = next(s for s in schemas if s["name"] == "DrafterBrief")
    required = {f["field"] for f in declared["fields"] if f["required"]}

    have = {f.name for f in dataclasses.fields(DrafterBrief)}
    missing = sorted(required - have)
    assert not missing, (
        f"Appendix E declares DrafterBrief fields the type does not carry: "
        f"{missing}")
    assert set(DECLARED_FIELDS) == required, (
        f"the module's own list has drifted from the contract: "
        f"{set(DECLARED_FIELDS) ^ required}")


# ============================ 2. provenance does not collapse ================

def test_the_seven_kinds_are_distinct_and_not_a_severity_scale():
    assert len(set(Provenance)) == 7
    pleadable = {p for p in Provenance if p.may_be_pleaded_as_fact}
    assert pleadable == {Provenance.SUPPLIED_TEXT, Provenance.EXTRACTED_TEXT,
                         Provenance.ESTABLISHED_FACT}
    assert not Provenance.INFERENCE.may_be_pleaded_as_fact
    assert not Provenance.DISPUTED_PROPOSITION.may_be_pleaded_as_fact


def test_an_inference_among_the_material_facts_is_reported():
    """THE DEFECT THIS PACKET EXISTS FOR. Both are sentences; only one is
    entitled to be read as established."""
    brief = _brief(material_facts=(
        _claim(), _claim(text="the buyer intended to pay",
                         provenance=Provenance.INFERENCE, quoted="", locator="")))
    reported = dr.misused_provenance(brief)
    assert len(reported) == 1
    assert "inference" in reported[0]


def test_extracted_text_without_a_locator_is_refused():
    """Extracted text that cannot be found again is an assertion wearing a
    citation-shaped label."""
    problems = _claim(locator="", source_version="").problems()
    assert any("names no locator" in p for p in problems)


def test_an_unresolved_gap_must_say_what_is_missing():
    gap = Claim(text="the date of the notice", provenance=Provenance.UNRESOLVED_GAP)
    assert any("does not say what is missing" in p for p in gap.problems())


# ================================= 3. quotations are checked =================

def test_a_quotation_is_verified_against_the_source_it_names():
    brief = dr.verify(_brief(), {"inv_1::p2": f"Recital. {SPAN}. Signed."})
    assert brief.material_facts[0].verified is True
    assert dr.unverified_quotations(brief) == ()


def test_a_paraphrase_is_not_verified():
    """P21's `quote_fidelity` folds whitespace and keeps punctuation and case,
    so a paraphrase cannot pass as VERBATIM. Reused rather than re-answered."""
    brief = dr.verify(_brief(), {"inv_1::p2": "the goods were delivered in March"})
    assert brief.material_facts[0].verified is False
    assert dr.unverified_quotations(brief)


def test_a_source_the_product_could_not_read_leaves_the_claim_unverified():
    """AND DOES NOT CALL THE CITATION WRONG. The failure is the retrieval's,
    and reporting it as a mismatch would send the advocate to fix a citation
    that is correct."""
    brief = dr.verify(_brief(), {})
    assert brief.material_facts[0].verified is False


def test_verification_never_marks_a_claim_it_did_not_check():
    """The direction matters: defaulting to verified and clearing on failure
    makes an unreadable source look like one that agreed."""
    assert _claim().verified is False


# ============================== 4. readiness is not filing ===================

def test_readiness_has_no_member_meaning_ready_to_file():
    """A member meaning that would be read as that, whatever its docstring
    said. CHOICE-09 disables the connectors; `approval` reads None."""
    assert {r.value for r in Readiness} == {
        "not_assessed", "incomplete", "ready_to_review"}


def test_a_complete_package_is_ready_to_review_and_still_refuses_filing():
    """THE POSITIVE CONTROL and the packet's whole point in one test."""
    brief = dr.verify(_brief(), {"inv_1::p2": SPAN})
    assert brief.problems() == (), brief.problems()
    assert brief.readiness() is Readiness.READY_TO_REVIEW

    note = refuse_filing_claim(brief)
    assert "NOT ready to file" in note
    assert "CHOICE-09" in note
    assert "has been filed" in note


def test_an_incomplete_package_names_what_is_missing():
    brief = _brief(theory_sentence="", reliefs=(), lossless=False)
    problems = brief.problems()
    assert brief.readiness() is Readiness.INCOMPLETE
    assert any("theory sentence" in p for p in problems)
    assert any("relief" in p for p in problems)
    assert any("lossless" in p or "dropped" in p for p in problems)


def test_readiness_is_derived_and_not_a_field():
    import dataclasses
    names = {f.name for f in dataclasses.fields(DrafterBrief)}
    assert "readiness" not in names, (
        "readiness is a field, so a caller can declare a package ready")


# ============================ 5. stale advice and decisions ==================

def test_a_superseded_decision_makes_the_package_stale():
    decided = AdviceDecision(
        decision_id="d1", disposition=Disposition.ACCEPT, decided_by="adv",
        decided_at="2026-09-13", advice_version="v1", scope="s", owner="adv",
        review_trigger="on filing")
    fresh = dr.stale_against(_brief(advice_version="v1"), (decided,))
    assert fresh == ()

    withdrawn = supersede(decided, by="d2")
    stale = dr.stale_against(_brief(advice_version="v1"), (withdrawn,))
    assert len(stale) == 1 and "superseded" in stale[0]


def test_a_decision_taken_on_another_advice_version_is_reported():
    decided = AdviceDecision(
        decision_id="d1", disposition=Disposition.ACCEPT, decided_by="adv",
        decided_at="2026-09-13", advice_version="v1", scope="s", owner="adv",
        review_trigger="on filing")
    stale = dr.stale_against(_brief(advice_version="v2"), (decided,))
    assert len(stale) == 1 and "v1" in stale[0] and "v2" in stale[0]


def test_a_stale_dependency_keeps_the_package_out_of_review():
    brief = dr.verify(_brief(), {"inv_1::p2": SPAN})
    from dataclasses import replace
    stale = replace(brief, stale_dependencies=("the delivery date moved",))
    assert stale.readiness() is Readiness.INCOMPLETE


# ================================= 6. the export =============================

def test_the_export_carries_no_dispatch_authority_and_says_so():
    """BK-92-AC3 ends with those words, and CHOICE-09 is why."""
    out = dr.export(dr.verify(_brief(), {"inv_1::p2": SPAN}))
    assert out["dispatch_authority"] is False
    assert "NOT ready to file" in out["filing_note"]


def test_the_renditions_say_not_built_rather_than_returning_nothing():
    """A stub returning empty bytes would satisfy a parity check between two
    things that do not exist."""
    out = dr.export(_brief())
    assert out["renditions"]["docx"] == "not_built"
    assert out["renditions"]["pdf"] == "not_built"
    assert out["renditions"]["parity"] == "not_assessed"


def test_the_export_marks_an_unverified_quotation_in_the_body():
    """The reader of the export must see it. A problem listed only in a
    sibling field is a problem somebody prints without."""
    out = dr.export(_brief())
    assert "[QUOTATION UNVERIFIED]" in out["body"]
    verified = dr.export(dr.verify(_brief(), {"inv_1::p2": SPAN}))
    assert "[QUOTATION UNVERIFIED]" not in verified["body"]


def test_the_export_carries_the_adverse_material_and_the_reservations():
    """A package that quietly omits the adverse material is the one that gets
    an advocate ambushed, and the omission is invisible on the face of it."""
    out = dr.export(_brief(adverse=("the acknowledgement is disputed",),
                           reservations=("limitation is conditional",)))
    assert out["adverse"] == ["the acknowledgement is disputed"]
    assert out["reservations"] == ["limitation is conditional"]


def test_one_content_digest_is_what_any_rendition_must_reproduce():
    """BK-92-AC3's parity rests on there being ONE accepted content version."""
    brief = dr.verify(_brief(), {"inv_1::p2": SPAN})
    a, b = dr.export(brief), dr.export(brief)
    assert a["content_digest"] == b["content_digest"]
    from dataclasses import replace
    moved = dr.export(replace(brief, material_facts=(
        _claim(text="delivery is denied", verified=True),)))
    assert moved["content_digest"] != a["content_digest"]


# ================================ 7. persistence =============================

def test_a_package_survives_the_round_trip():
    brief = dr.verify(_brief(), {"inv_1::p2": SPAN})
    back = dr.from_dict(dr.as_dict(brief))
    assert back.claims == brief.claims
    assert back.readiness() is brief.readiness()


def test_an_unreadable_provenance_falls_to_the_kind_that_claims_least():
    """ADVERSARIAL. A corrupt row must not become an established fact: that is
    the one value that would let it be pleaded."""
    row = dr.as_dict(_brief())
    row["material_facts"][0]["provenance"] = "obviously_true"
    back = dr.from_dict(row)
    assert back.material_facts[0].provenance is Provenance.UNRESOLVED_GAP


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
