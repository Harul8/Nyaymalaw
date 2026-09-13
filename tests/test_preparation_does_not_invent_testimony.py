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
import yaml

from nm.core.dependency import Currency, InputKind, Ledger, Rest, invalidate
from nm.core.hearing import (
    NO_LOCATOR,
    PACK_SECTIONS,
    REQUIRED_SECTIONS,
    HearingPack,
    as_dict,
    assemble,
    concession_boundary,
    from_dict,
    in_court,
    node_name,
    owner_and_next,
    record_pack,
    refuse_concession,
    stale,
    unlocated,
)
from nm.domain.authority import ActingAs
from nm.domain.commission import Commission, Deadline, Party, WorkProduct
from nm.domain.drafting import Claim, DrafterBrief, Provenance, Readiness
from nm.domain.handover import Assessed
from nm.domain.witness import (
    EXPERT_FIELDS,
    WITNESS_FIELDS,
    Availability,
    ExpertInstruction,
    Methodology,
    WitnessPlan,
    refuse_leading,
    refuse_scripting,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ------------------------------------------------------------- fixtures ----

def _brief(**kw) -> DrafterBrief:
    base = dict(
        package_id="pkg_1", matter_id="m1", document="written statement",
        audience="the City Civil Court", purpose="resist the decree",
        posture="defendant", cause_title={"court": "City Civil Court"},
        theory_sentence="the cheque was security for a loan that was repaid",
        reliefs=("dismissal with costs",),
        proof_positions=("repayment is established by the bank statement",),
        authorities=(Claim(text="s.139 raises a presumption",
                           provenance=Provenance.LEGAL_PREMISE,
                           source_id="ni_act", locator="s.139",
                           verified=True),),
        material_facts=(Claim(text="the cheque was handed over on 3 May 2023",
                              provenance=Provenance.SUPPLIED_TEXT,
                              source_id="brief_1", verified=True,
                              locator="para 4"),),
        adverse=("the endorsement on the reverse is in the client's hand",),
        lossless=True)
    base.update(kw)
    return DrafterBrief(**base)


def _commission(**kw) -> Commission:
    base = dict(
        version=3, objective="resist the summary decree",
        work_product=WorkProduct.HEARING, scope="the recovery suit only",
        instructing=Party(party_id="sol_1", described_as="the solicitor",
                          capacity=ActingAs.INSTRUCTING),
        deciding=Party(party_id="cl_1", described_as="the client",
                       capacity=ActingAs.DECIDING),
        forum="City Civil Court, Hyderabad",
        deadline=Deadline.on_date("2026-11-02", "the order dated 2 Sep 2026"),
        constraints=("settle at or above Rs 4,00,000",),
        recorded_by="adv_1", recorded_at="2026-09-13")
    base.update(kw)
    return Commission(**base)


def _pack(**kw) -> HearingPack:
    return assemble(pack_id="hp_1", brief=_brief(), commission=_commission(),
                    actor_id="adv_1", acting_as=ActingAs.DECIDING,
                    hard_questions=({"question": "why was it not returned?",
                                     "answer": "it was, on 2 June"},),
                    adverse_assessed=True, risk_assessed=True,
                    risk=("the endorsement is unexplained",), **kw)


# ============= 1. Appendix E's two unimplemented records, implemented =======

def _schema(name: str) -> dict:
    rows = yaml.safe_load(
        (ROOT / "spec" / "schemas.yaml").read_text(encoding="utf-8"))["schemas"]
    return next(r for r in rows if r["name"] == name)


@pytest.mark.parametrize("name,declared", [
    ("WitnessPlan", WITNESS_FIELDS), ("ExpertInstruction", EXPERT_FIELDS)])
def test_the_record_carries_appendix_e_exactly_and_both_ways(name, declared):
    """READ FROM THE CONTRACT, NOT COPIED FROM IT.

    Both directions: a field in the schema and absent from the dataclass is a
    contract this product does not answer, and a required field on the
    dataclass that the schema never asked for is an invention.
    """
    required = tuple(f["field"] for f in _schema(name)["fields"]
                     if f.get("required"))
    assert set(declared) == set(required), sorted(
        set(declared) ^ set(required))
    cls = {"WitnessPlan": WitnessPlan, "ExpertInstruction": ExpertInstruction}[name]
    missing = [f for f in required if f not in cls.__dataclass_fields__]
    assert not missing, missing


def test_neither_record_has_a_field_testimony_could_be_written_into():
    """THE MECHANISM IS THE ABSENCE OF THE FIELD, not the text check.

    `refuse_scripting` is a backstop over prose that arrived from a model. The
    reason a caller cannot store an answer is that there is nowhere to put one.
    """
    banned = {"testimony", "evidence_text", "answers", "script", "statement",
              "what_they_will_say", "conclusion", "opinion", "finding"}
    assert not banned & set(WitnessPlan.__dataclass_fields__)
    assert not banned & set(ExpertInstruction.__dataclass_fields__)


# ================== 2. BK-57-AC2 -- preparation, never coaching =============

@pytest.mark.parametrize("line", [
    "You will say the cheque was security.",
    "Tell them that the money was repaid in June.",
    "Confirm that you never signed the endorsement.",
    "Do not mention the second cheque.",
])
def test_a_line_that_supplies_the_answer_is_named(line):
    """THE NEGATIVE CONTROL from the backlog: *ask the system to fill a
    witness memory gap or suppress a contradictory statement*."""
    named = refuse_scripting((line,))
    assert named, line
    assert "supplies the answer" in named[0]


@pytest.mark.parametrize("line", [
    "What do you recall about the meeting on 3 May?",
    "The handover of the cheque, and who was present.",
    "Whether any repayment was discussed, and when.",
])
def test_a_line_that_asks_a_question_is_not_refused(line):
    """THE POSITIVE CONTROL. A check that refuses everything refuses nothing:
    it would be turned off within a week and the population would grow behind
    it."""
    assert refuse_scripting((line,)) == ()


def test_a_contaminated_plan_says_so_on_the_plan_itself():
    plan = WitnessPlan(thread="t1", witness="Ramesh",
                       topics=("You will say it was repaid",))
    assert plan.contaminated is True
    assert any("supplies the answer" in p for p in plan.problems())


def test_a_prior_statement_with_no_contact_entry_is_reported():
    """Appendix E's reason for `contact_log`: the log is what makes the
    no-coaching rule auditable rather than asserted."""
    plan = WitnessPlan(thread="t1", witness="Ramesh",
                       prior_statements=({"where": "office", "when": "May",
                                          "gist": "he recalls the handover"},))
    assert any("contact log" in p for p in plan.unlogged_contact())


def test_a_logged_contact_answers_it():
    plan = WitnessPlan(
        thread="t1", witness="Ramesh",
        prior_statements=({"where": "office", "when": "May", "gist": "x"},),
        contact_log=({"when": "2026-05-02", "by": "adv_1",
                      "purpose": "take a statement",
                      "present": ["the solicitor"]},))
    assert plan.unlogged_contact() == ()


def test_availability_not_assessed_is_a_problem_and_not_a_silence():
    """§9: the third state must be VISIBLE IN THE OUTPUT. A witness nobody
    checked on reads as available unless something says otherwise."""
    plan = WitnessPlan(thread="t1", witness="Ramesh", necessity="he was there",
                       materiality=("f1",), logistics_owner="the clerk")
    assert plan.availability is Availability.NOT_ASSESSED
    assert any("can attend" in p for p in plan.problems())


def test_a_summons_needed_and_not_filed_is_a_missed_hearing():
    plan = WitnessPlan(thread="t1", witness="Ramesh",
                       summons={"needed": True, "filed_at": None})
    assert any("summons" in p for p in plan.problems())


@pytest.mark.parametrize("purpose", [
    "Confirm that the signature is a forgery.",
    "Establish that the ink post-dates the document.",
    "We need you to find that the endorsement was added later.",
])
def test_a_leading_instruction_to_an_expert_is_named(purpose):
    assert refuse_leading((purpose,))


def test_an_instruction_marked_balanced_that_reads_as_leading_is_contradicted():
    """A boolean somebody set is not evidence about the sentence beside it."""
    instruction = ExpertInstruction(
        thread="t1", expert="Dr Rao", discipline="questioned documents",
        purpose="Confirm that the endorsement was added later.",
        material_supplied=("the original cheque",),
        assumptions=("the cheque is the original",),
        instruction_balanced=True,
        independence_statement="the duty is to the court",
        conflicts={"declared": [], "assessed_by": "adv_1"})
    assert any("contradicted by its own text" in p
               for p in instruction.problems())


def test_an_expert_supports_no_conclusion_before_a_report_arrives():
    instruction = ExpertInstruction(thread="t1", expert="Dr Rao")
    assert instruction.report is None
    assert any("no report" in p for p in instruction.unsupported_by_report())


def test_methodology_untested_and_not_assessed_are_different_positions():
    assert Methodology.UNTESTED is not Methodology.NOT_ASSESSED
    assert Methodology.not_established() is Methodology.NOT_ASSESSED


# ============ 3. BK-57-AC1 -- the concession boundary, derived ==============

def test_the_boundary_reads_the_commission_and_the_one_authority_policy():
    section = concession_boundary(_commission(), "adv_1", ActingAs.DECIDING)
    rendered = section.render()
    assert "the client" in rendered
    assert "the solicitor" in rendered
    assert "not for that reason permitted to concede" in rendered
    assert "settle at or above Rs 4,00,000" in rendered


def test_an_unrecorded_limit_is_not_an_unlimited_one():
    """THE SENTENCE THIS PACKET EXISTS FOR. The opposite reading is how a
    concession gets taken from somebody who could not give it."""
    bare = _commission(constraints=())
    why = refuse_concession(bare, actor_id="adv_1",
                            acting_as=ActingAs.DECIDING,
                            proposed="settle at Rs 1,00,000")
    assert "no settlement limit is recorded" in why
    assert "not an unlimited one" in why


def test_a_concession_beyond_the_recorded_limit_is_refused():
    """THE BACKLOG'S NEGATIVE CONTROL: *raise an offer beyond the approved
    settlement limit*."""
    why = refuse_concession(_commission(), actor_id="adv_1",
                            acting_as=ActingAs.DECIDING,
                            proposed="settle at Rs 90,000")
    assert "is not among the limits recorded" in why
    assert "the client decides this" in why


def test_the_recorded_limit_itself_is_permitted():
    """THE POSITIVE CONTROL."""
    assert refuse_concession(_commission(), actor_id="adv_1",
                             acting_as=ActingAs.DECIDING,
                             proposed="settle at or above Rs 4,00,000") == ""


def test_an_advising_advocate_may_not_concede_however_reasonable():
    """The refusal comes from `permits`, which is the SAME call the served
    `/concede` route makes. Two answers to one question would be worse than
    none."""
    why = refuse_concession(_commission(), actor_id="adv_1",
                            acting_as=ActingAs.ADVISING,
                            proposed="settle at or above Rs 4,00,000")
    assert why


def test_a_commission_with_no_decision_maker_authorises_nothing():
    why = refuse_concession(_commission(deciding=None), actor_id="adv_1",
                            acting_as=ActingAs.DECIDING, proposed="anything")
    assert "no decision maker is recorded" in why


# ============= 4. BK-57-AC3 -- hearing readiness, and its absence ===========

def test_a_pack_cannot_be_assembled_over_an_unassessed_package():
    """Provisional is what gets ignored at 10:29, so this refuses instead."""
    empty = DrafterBrief(package_id="p", matter_id="m1", document="plaint",
                         audience="the City Civil Court",
                         purpose="recover the price", posture="plaintiff")
    assert empty.readiness() is Readiness.NOT_ASSESSED
    with pytest.raises(ValueError, match="has not been assessed"):
        assemble(pack_id="hp", brief=empty, commission=_commission(),
                 actor_id="adv_1", acting_as=ActingAs.DECIDING)


def test_the_pack_carries_the_theory_relief_propositions_and_locators():
    pack = _pack()
    assert "cheque was security" in pack.position.render()
    assert "dismissal with costs" in pack.position.render()
    assert "bank statement" in pack.propositions.render()
    assert "s.139" in pack.authorities.render()


def test_an_authority_with_no_locator_is_shown_and_blocks():
    """THE BACKLOG'S NEGATIVE CONTROL: *a polished hearing pack with obsolete
    facts or missing controlling authority*. Dropping the line would make the
    pack look complete, which is the failure."""
    pack = assemble(
        pack_id="hp_2",
        brief=_brief(authorities=(Claim(text="the leading case",
                                        provenance=Provenance.LEGAL_PREMISE,
                                        source_id="c1", locator="",
                                        verified=False),)),
        commission=_commission(), actor_id="adv_1",
        acting_as=ActingAs.DECIDING, adverse_assessed=True)
    assert unlocated(pack)
    assert NO_LOCATOR in pack.authorities.render()
    assert any("no locator" in b for b in pack.blockers())


def test_an_unexamined_countercase_and_an_empty_one_render_differently():
    """THE MOST DANGEROUS SENTENCE IN THE PACK is "there is no countercase"
    produced by nobody having looked."""
    looked = assemble(pack_id="a", brief=_brief(adverse=()),
                      commission=_commission(), actor_id="adv_1",
                      acting_as=ActingAs.DECIDING, adverse_assessed=True)
    did_not = assemble(pack_id="b", brief=_brief(adverse=()),
                       commission=_commission(), actor_id="adv_1",
                       acting_as=ActingAs.DECIDING, adverse_assessed=False)
    assert looked.adverse.state is Assessed.EMPTY
    assert did_not.adverse.state is Assessed.NOT_ASSESSED
    assert looked.adverse.render() != did_not.adverse.render()
    assert "not assessed" in did_not.adverse.render()
    assert "adverse" in did_not.unassessed()


def test_every_required_section_blocks_when_nobody_assessed_it():
    """The population is `REQUIRED_SECTIONS`, read rather than restated."""
    bare = HearingPack(pack_id="p", matter_id="m", package_id="pkg")
    named = " ".join(bare.blockers())
    for section in REQUIRED_SECTIONS:
        assert section.replace("_", " ") in named
    assert bare.fit_to_argue is False


def test_readiness_never_reaches_a_filing_state():
    """P29 made it unrepresentable rather than merely undocumented, and this
    packet is a READER of that judgement."""
    assert not any("FILE" in m.name for m in Readiness)
    assert _pack().readiness is _brief().readiness()


def test_the_projection_says_this_is_not_an_accomplished_act():
    from nm.core.hearing import projection

    shown = projection(_pack())
    assert "rather than an accomplished step" in shown["said"]
    assert "conceded" in shown["said"]


# =============== 5. BK-57-AC4 -- three buckets that never merge =============

def test_verified_uncertain_and_proposed_are_three_keys():
    brief = _brief(material_facts=(
        Claim(text="the loan was repaid in June",
              provenance=Provenance.INFERENCE, source_id="brief_1",
              verified=False),))
    pack = assemble(pack_id="p", brief=brief, commission=_commission(),
                    actor_id="adv_1", acting_as=ActingAs.DECIDING,
                    adverse_assessed=True)
    shown = in_court(pack, brief)
    assert set(shown["verified"]).isdisjoint(shown["uncertain"])
    assert set(shown["verified"]).isdisjoint(shown["proposed"])
    assert any("inference" in u for u in shown["uncertain"])
    assert all("PROPOSED" in p for p in shown["proposed"])


def test_the_concession_boundary_travels_with_the_in_court_view():
    """A limit on another screen is a limit nobody reads at 10:29."""
    shown = in_court(_pack(), _brief())
    assert "the client" in shown["concession_boundary"]
    assert "not interchangeable" in shown["said"]


def test_no_function_in_the_module_concatenates_the_three_buckets():
    """STRUCTURAL, over the compiled module rather than its prose -- three
    checks in this build have matched a docstring and passed for it."""
    import nm.core.hearing as mod

    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    for pair in ('verified"] +', 'uncertain"] +', '"verified"]+'):
        assert pair not in source


# ================= 6. BK-57-AC5 -- an event reaches the pack ================

def test_a_pack_that_is_not_registered_is_never_reported_current():
    """§9. THE ABSENCE IS THE DANGEROUS ONE: a pack nobody registered is a
    pack no change can reach, which is indistinguishable from a pack nothing
    has changed."""
    why = stale(_pack(), Ledger())
    assert why and "not registered" in why[0]


def test_a_registered_pack_is_current_until_something_moves():
    pack = _pack()
    ledger = record_pack(Ledger(), pack, at="2026-09-13")
    assert ledger.node(node_name(pack)).currency is Currency.CURRENT
    assert stale(pack, ledger) == ()


def test_a_change_to_the_commission_reaches_the_pack():
    """THE BACKLOG'S NEGATIVE CONTROL: *withdraw settlement authority after a
    draft offer*. The pack rests on the commission as a typed, versioned edge,
    so P18's own closure reaches it -- there is no second walk here."""
    pack = _pack()
    ledger = record_pack(Ledger(), pack, at="2026-09-13")
    moved = (Rest(kind=InputKind.FACT, id=f"commission:{pack.matter_id}",
                  version=pack.commission_version + 1),)
    ledger, reached = invalidate(ledger, moved,
                                 reason="settlement authority withdrawn",
                                 at="2026-09-14")
    assert node_name(pack) in reached
    why = stale(pack, ledger)
    assert why and "settlement authority withdrawn" in why[0]


def test_a_change_to_the_package_reaches_the_pack():
    pack = _pack()
    ledger = record_pack(Ledger(), pack, at="2026-09-13")
    _, reached = invalidate(
        ledger, (Rest(kind=InputKind.DERIVED, id=pack.package_id, version=2),),
        reason="the package was re-verified", at="2026-09-14")
    assert node_name(pack) in reached


def test_reopened_work_names_the_owner_and_the_next_obligation():
    """BK-57-AC5: *preserves the prior record, responsible owner and next
    obligation*. Work reopened with no owner is a deadline nobody watches."""
    said = owner_and_next(_pack(), _commission())
    assert said["responsible"] == "the client"
    said = owner_and_next(_pack(), _commission(deciding=None))
    assert said["responsible"] == "NOT RECORDED"
    assert "no decision maker" in said["why"]


def test_an_unfit_pack_names_its_first_obligation_rather_than_a_count():
    bare = HearingPack(pack_id="p", matter_id="m", package_id="pkg")
    said = owner_and_next(bare, _commission())
    assert said["outstanding"] == len(bare.blockers())
    assert said["next_obligation"] in bare.blockers()


# ============================== 7. persistence ==============================

def test_a_pack_survives_a_round_trip_unchanged():
    pack = _pack(witnesses=(WitnessPlan(thread="t1", witness="Ramesh",
                                        availability=Availability.CONFIRMED,
                                        topics=("what he recalls",)),),
                 experts=(ExpertInstruction(
                     thread="t1", expert="Dr Rao",
                     methodology_tested=Methodology.TESTED),))
    back = from_dict(as_dict(pack))
    assert back == pack


def test_an_unreadable_section_state_reads_as_nobody_looked():
    """The direction `Rest.from_stored` takes: the reading that keeps the
    advocate checking is the safe one."""
    row = as_dict(_pack())
    row["sections"]["adverse"]["state"] = "sort_of"
    row["sections"]["adverse"]["items"] = []
    assert from_dict(row).adverse.state is Assessed.NOT_ASSESSED


def test_an_unreadable_availability_reads_as_not_assessed():
    row = as_dict(_pack(witnesses=(
        WitnessPlan(thread="t1", witness="Ramesh",
                    availability=Availability.CONFIRMED),)))
    row["witnesses"][0]["availability"] = "probably"
    assert from_dict(row).witnesses[0].availability is Availability.NOT_ASSESSED


def test_every_declared_section_round_trips():
    """The population is `PACK_SECTIONS`, so a section added tomorrow is
    carried by this test without anybody editing it."""
    back = from_dict(as_dict(_pack()))
    assert set(back.sections) == set(PACK_SECTIONS)


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


def test_a_pack_is_assembled_and_read_back_with_its_currency(client):
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _pack_on_wire(client, matter_id, pid, version)
    assert made.status_code == 201, made.text
    pack_id = made.json()["pack"]["pack_id"]

    got = client.get(f"/api/hearing-packs/{pack_id}",
                     params={"matter_id": matter_id})
    assert got.status_code == 200, got.text
    assert got.json()["pack"]["stale"] == []
    assert "rather than an accomplished step" in got.json()["pack"]["said"]


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
