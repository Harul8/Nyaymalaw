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
from nm.domain.closure import (
    CLOSURE_FIELDS,
    ClosureRecord,
    Lifecycle,
    Obligation,
    refuse_closure,
    reopen_checks,
)
from nm.domain.handover import (
    SUMMARY_FIELDS,
    Assessed,
    CaseSummary,
    HandoverState,
    Section,
    accept,
    decline,
    offer,
)

pytestmark = pytest.mark.class_a


def _full_summary(**kw) -> CaseSummary:
    base = {name: Section(state=Assessed.EMPTY)
            for name in CaseSummary(matter="m").sections}
    base.update(matter="m1", instruction="defend the possession claim",
                next_responsibility="file the written statement by 1 October")
    base.update(kw)
    return CaseSummary(**base)


def _offer(**kw):
    base = dict(handover_id="h1", matter_id="m1", from_actor="adv_a",
                to_actor="adv_b", offered_at="2026-09-13",
                summary=_full_summary(),
                outstanding=("file the written statement by 1 October",))
    base.update(kw)
    return offer(**base)


# ============================ 1. the records are Appendix E's ================

@pytest.mark.parametrize("name,declared", [
    ("CaseSummary", SUMMARY_FIELDS), ("ClosureRecord", CLOSURE_FIELDS)])
def test_the_module_lists_match_the_declared_contract(name, declared):
    """Asserted against `assurance/specification/schemas.yaml`. A list in this repository checked
    against another list in this repository passes while both drift."""
    import yaml
    schemas = yaml.safe_load(
        open("assurance/specification/schemas.yaml", encoding="utf8"))["schemas"]
    required = {f["field"] for f in next(s for s in schemas if s["name"] == name)
                ["fields"] if f["required"]}
    assert set(declared) == required, (
        f"{name} has drifted from the contract: {set(declared) ^ required}")


# ================== 2. "none" and "nobody looked" are different ==============

def test_an_unassessed_section_never_renders_as_none():
    """BK-39-AC2's *unassessed sections explicit*. The receiving advocate acts
    differently on "there are no authorities" and "nobody searched"."""
    assert "not assessed" in Section().render()
    assert "none, and that was checked" in Section(state=Assessed.EMPTY).render()


def test_a_section_carrying_items_cannot_claim_nobody_looked():
    """That shape would let a populated section be skipped as unassessed."""
    assert Section(items=("Article 65",)).state is Assessed.ASSESSED


def test_a_summary_names_every_section_nobody_assessed():
    """AND DOES NOT REFUSE THE HANDOVER FOR IT.

    A first version treated an unassessed section as a blocker, which would
    refuse almost every real matter -- and the pressure that creates is to
    mark sections assessed to get the handover through, destroying the exact
    distinction the criterion is about. BK-39-AC2 asks for them to be
    EXPLICIT; BK-58-AC3's blocking condition is the acknowledgement.
    """
    bare = CaseSummary(matter="m1", instruction="x", next_responsibility="y")
    assert len(bare.unassessed()) == 13
    assert bare.handover_complete is True
    assert bare.handover_blockers == ()


def test_a_summary_with_no_instruction_or_next_responsibility_is_refused():
    """What DOES block: the receiving advocate not knowing what they are asked
    to do, or nobody saying whose it becomes."""
    blank = CaseSummary(matter="m1")
    assert blank.handover_complete is False
    assert any("instruction" in b for b in blank.handover_blockers)
    assert any("next responsibility" in b for b in blank.handover_blockers)


def test_completeness_is_derived_and_not_a_stored_claim():
    """A summary that could assert its own completeness will, and it is read
    as a checked statement."""
    import dataclasses
    names = {f.name for f in dataclasses.fields(CaseSummary)}
    assert "handover_complete" not in names


# ======================= 3. offered is not accepted ==========================

def test_an_offer_cannot_be_created_already_accepted():
    """A caller that could construct an accepted handover could move
    responsibility onto somebody who never agreed to take it."""
    assert _offer().state is HandoverState.OFFERED
    names = offer.__code__.co_varnames[
        :offer.__code__.co_argcount + offer.__code__.co_kwonlyargcount]
    assert "state" not in names


def test_responsibility_stays_with_the_offeror_until_acceptance():
    """THE PACKET'S WHOLE POINT. A handover that completes because it was sent
    leaves a deadline with nobody watching, and both people believe the other
    has it."""
    offered = _offer()
    assert offered.owner_of_outstanding() == "adv_a"
    assert offered.state.responsibility_moved is False

    taken = accept(offered, by="adv_b", at="2026-09-14")
    assert taken.owner_of_outstanding() == "adv_b"
    assert taken.state.responsibility_moved is True


def test_there_is_no_sent_state():
    """Sending is a thing that happened to a message, not a state of the
    responsibility."""
    assert "sent" not in {s.value for s in HandoverState}


def test_only_the_named_recipient_can_accept():
    """BK-58-AC3's *authorised recipient acknowledgement*. Accepting on
    somebody's behalf is how responsibility arrives with a person who does not
    know they have it."""
    with pytest.raises(ValueError, match="is not the recipient"):
        accept(_offer(), by="adv_c", at="2026-09-14")


def test_a_declined_handover_leaves_the_work_where_it_was_and_says_why():
    refused = decline(_offer(), by="adv_b", because="I am in trial that week")
    assert refused.state is HandoverState.DECLINED
    assert refused.owner_of_outstanding() == "adv_a"
    with pytest.raises(ValueError, match="records why"):
        decline(_offer(), by="adv_b", because="")


def test_a_handover_to_nobody_is_refused():
    with pytest.raises(ValueError, match="names its recipient"):
        _offer(to_actor="")


def test_a_handover_to_yourself_is_refused():
    """Nothing moves, and the record would suggest something did."""
    with pytest.raises(ValueError, match="same actor"):
        _offer(to_actor="adv_a")


def test_a_snapshot_with_no_instruction_cannot_be_offered():
    """The receiving advocate would not know what they are being asked to do."""
    with pytest.raises(ValueError, match="not fit to hand over"):
        _offer(summary=CaseSummary(matter="m1"))


def test_a_second_acceptance_is_refused():
    taken = accept(_offer(), by="adv_b", at="2026-09-14")
    with pytest.raises(ValueError, match="only an offered one"):
        accept(taken, by="adv_b", at="2026-09-15")


# ============================ 4. closure refuses the live ====================

def test_closure_refuses_an_obligation_that_is_still_owed():
    """BK-59-AC2. A closure that swallows a live obligation is the most
    expensive kind of tidy: the deadline still exists."""
    record = ClosureRecord(
        matter="m1", closed_by="adv_a", retention="rr_1",
        work_product={"exported_at": "2026-09-13"},
        continuing_obligations=(Obligation(what="file the WS", until="2026-10-01"),))
    blockers = refuse_closure(record)
    assert any("still owed" in b for b in blockers)
    assert record.complete is False


def test_a_transferred_obligation_does_not_block_and_a_resolved_one_does_not():
    """THE POSITIVE CONTROL: a rule that refuses every closure is an outage."""
    record = ClosureRecord(
        matter="m1", closed_by="adv_a", retention="rr_1",
        work_product={"exported_at": "2026-09-13"},
        continuing_obligations=(
            Obligation(what="file the WS", resolved=True),
            Obligation(what="return the originals", transferred_to="adv_b")))
    assert refuse_closure(record) == ()
    assert record.complete is True


def test_closing_without_a_retention_decision_is_refused():
    """P33 owns what happens to the material. Closing with no retention
    request leaves the file held on nobody's authority."""
    record = ClosureRecord(matter="m1", closed_by="adv_a",
                           work_product={"exported_at": "x"})
    assert any("retention" in b for b in refuse_closure(record))


def test_closing_without_exporting_the_work_product_is_refused():
    record = ClosureRecord(matter="m1", closed_by="adv_a", retention="rr_1")
    assert any("work product" in b for b in refuse_closure(record))


def test_an_unowned_obligation_is_reported_as_unowned():
    """ADVERSARIAL. The type must be able to express an obligation nobody
    owns -- that is the state the check exists to find."""
    record = ClosureRecord(matter="m1", closed_by="adv_a", retention="rr_1",
                           work_product={"x": 1},
                           continuing_obligations=(Obligation(what="chase the fee"),))
    assert any("nobody owns it" in b for b in refuse_closure(record))


# ===================== 5. archive, close and delete are three ================

def test_archived_is_a_distinct_state_and_is_not_deletion():
    """BK-59-AC3. P33 makes the same separation for material, and this is the
    matter-level half of it."""
    values = {m.value for m in Lifecycle}
    assert {"open", "closed", "archived", "reopened"} <= values
    assert "deleted" not in values, (
        "deletion is a Lifecycle member, so a matter can be 'deleted' without "
        "any retention request having erased anything")
    assert Lifecycle.ARCHIVED.is_live is False
    assert Lifecycle.REOPENED.is_live is True


def test_reopening_returns_work_to_do_rather_than_a_refusal():
    """A matter reopens because something happened. Refusing until the checks
    pass leaves the advocate unable to act on the very development that made
    them reopen it."""
    record = ClosureRecord(matter="m1", closed_by="adv_a", retention="rr_1",
                           work_product={"x": 1})
    checks = reopen_checks(record)
    assert any("permitted to act" in c for c in checks)
    assert any("current instruction" in c for c in checks)
    assert any("legal position" in c for c in checks)
    assert any("rr_1" in c for c in checks)


def test_a_long_closed_matter_treats_derived_values_as_stale():
    record = ClosureRecord(matter="m1", closed_by="adv_a", retention="rr_1",
                           work_product={"x": 1})
    assert any("stale" in c for c in reopen_checks(record, months_closed=8))
    assert not any("stale" in c for c in reopen_checks(record, months_closed=1))


def test_restoring_an_archived_matter_is_a_separate_decision_from_reopening():
    record = ClosureRecord(matter="m1", closed_by="adv_a", retention="rr_1",
                           work_product={"x": 1}, lifecycle=Lifecycle.ARCHIVED)
    assert any("separate decision" in c for c in reopen_checks(record))


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
