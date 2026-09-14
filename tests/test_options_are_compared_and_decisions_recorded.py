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
from nm.core import options as op
from nm.domain import advice_decision as ad
from nm.domain.options import (
    Certainty,
    Comparison,
    Figure,
    Option,
    Route,
    compare,
)

pytestmark = pytest.mark.class_a


def _option(route=Route.LITIGATE, **kw) -> Option:
    base = dict(summary="sue for the price", why_it_loses="")
    base.update(kw)
    return Option(route=route, **base)


# ================================================ 1. a view, never a menu ====

def test_a_comparison_with_no_view_and_no_reason_is_refused():
    """BK-96-AC1: NM states its supported view *without replacing it with a
    neutral menu*. Having no view is permitted; having no view and no reason
    for having none is the menu."""
    menu = Comparison(options=(_option(), _option(Route.SETTLE)))
    assert any("menu" in p for p in menu.problems())


def test_no_view_with_a_stated_reason_is_a_legitimate_answer():
    """THE NEGATIVE CONTROL. Sometimes the honest answer is that the file does
    not yet decide between two routes, and saying so is not a failure."""
    honest = Comparison(
        options=(_option(why_it_loses="n/a"),
                 _option(Route.SETTLE, why_it_loses="n/a")),
        no_view_because="the client's tolerance for delay is not recorded, "
                        "and it decides between these two")
    assert not any("menu" in p for p in honest.problems())


def test_every_losing_route_says_why_it_loses():
    """An option in the comparison with no reason for losing is a menu item
    that happens to be next to a recommendation."""
    lopsided = compare(
        (_option(), _option(Route.ARBITRATE)),
        supported=Route.LITIGATE, because="the only route that recovers")
    assert any("arbitrate" in p and "why it loses" in p
               for p in lopsided.problems())


def test_a_view_for_a_route_nobody_compared_is_refused():
    """ADVERSARIAL. A recommendation for a route that is not in the comparison
    rests on nothing -- and reads as though four routes were weighed."""
    with pytest.raises(ValueError, match="not among the options"):
        compare((_option(),), supported=Route.ARBITRATE)


def test_settling_and_doing_nothing_are_routes_and_not_omissions():
    """A comparison that cannot express them is rigged toward acting, and
    doing nothing is frequently right where the relief is hollow."""
    assert Route.DO_NOTHING in set(Route)
    assert Route.SETTLE in set(Route)


# ======================================= 2. established, estimate, unknown ===

def test_an_established_figure_must_name_what_it_rests_on():
    """Established means checkable. A figure nobody can check is an estimate
    whatever it is labelled -- and the label is what the client repeats."""
    guessed = Figure(text="Rs 2,00,000", certainty=Certainty.ESTABLISHED)
    assert any("names nothing it rests on" in p for p in guessed.problems())

    real = Figure(text="Rs 2,00,000", certainty=Certainty.ESTABLISHED,
                  basis="the invoice at page 14")
    assert real.problems() == ()


def test_an_unknown_renders_as_not_established_and_never_as_blank():
    """CLAUDE.md §9's third state, visible in the OUTPUT. An empty cell in a
    table of numbers reads as zero to whoever is scanning it."""
    assert Figure().render() == "not established"
    assert "estimate" in Figure(text="6 months",
                                certainty=Certainty.ESTIMATE,
                                basis="typical listing delay").render()


def test_the_projection_renders_every_figure_through_the_same_owner():
    """A second renderer is a second answer to *what does an unknown look
    like*, and the two drift the first time one is changed."""
    served = op.comparison_projection(compare(
        (_option(cost=Figure(text="Rs 50,000", certainty=Certainty.ESTIMATE,
                             basis="counsel's fee note")),),
        supported=Route.LITIGATE, because="only route that recovers"))
    row = served["options"][0]
    assert row["useful_recovery"] == "not established"
    assert "estimate" in row["cost"]
    assert row["unknowns"] == 4


def test_proportionality_never_removes_a_route_from_the_comparison():
    """E3's NEVER, and `nm.core.relief` keeps proportionality out of its
    `_DELIVERS` set for the same reason: a disproportionate route the client
    insists on is still their decision to take."""
    served = op.comparison_projection(compare(
        (_option(proportionate=False, why_it_loses=""),
         _option(Route.SETTLE, proportionate=True,
                 why_it_loses="recovers less")),
        supported=Route.LITIGATE, because="the client wants the principle"))
    routes = [o["route"] for o in served["options"]]
    assert "litigate" in routes, "a disproportionate route was withheld"
    assert served["options"][0]["proportionate"] is False


def test_an_unassessed_proportionality_says_so_rather_than_reading_as_false():
    served = op.comparison_projection(compare(
        (_option(why_it_loses=""),), supported=Route.LITIGATE,
        because="the only route"))
    assert served["options"][0]["proportionate"] == "not assessed"


# ============================ 3. a decision is not authority to act ==========

def test_a_recorded_acceptance_does_not_authorise_an_external_act():
    """BK-55-AC3's last clause, and the whole reason `authorises` exists as a
    function rather than a comment."""
    decided = ad.AdviceDecision(
        decision_id="d1", disposition=ad.Disposition.ACCEPT,
        decided_by="adv_1", decided_at="2026-09-13", advice_version="v3",
        scope="the recovery thread", owner="adv_1",
        review_trigger="if the defence pleads limitation")
    permitted, why = ad.authorises(decided)
    assert permitted is False
    assert "not authority to file" in why
    assert "DecisionRecord" in why, (
        "the refusal does not name what WOULD authorise an act, so the reader "
        "is told no without being told what is missing")


def test_silence_is_not_acceptance():
    """A recommendation, silence and a decision are three states. Reading the
    middle one as the last is how advice becomes an instruction nobody gave."""
    undecided = ad.AdviceDecision(decision_id="d0")
    assert undecided.disposition is ad.Disposition.NOT_DECIDED
    permitted, why = ad.authorises(undecided)
    assert permitted is False and "silence is not acceptance" in why


def test_a_decision_records_all_five_things_the_criterion_names():
    """Actor, advice version, scope, owner, review trigger."""
    bare = ad.AdviceDecision(decision_id="d1",
                             disposition=ad.Disposition.ACCEPT)
    assert len(bare.absent()) == len(ad.REQUIRED)


def test_an_undecided_record_reports_nothing_absent():
    """There is nothing yet to record. Reporting five gaps against advice
    nobody has looked at would bury the real gaps."""
    assert ad.AdviceDecision(decision_id="d0").absent() == ()


def test_a_narrowing_must_say_what_survived():
    """A narrowing that does not name what remains is a rejection nobody
    called a rejection."""
    narrowed = ad.AdviceDecision(
        decision_id="d2", disposition=ad.Disposition.NARROW,
        decided_by="adv_1", decided_at="2026-09-13", advice_version="v3",
        scope="the recovery thread", owner="adv_1", review_trigger="on filing")
    assert "what the advice was narrowed to" in narrowed.absent()


def test_a_decision_is_withdrawn_by_a_later_record_and_never_by_deletion():
    first = ad.AdviceDecision(decision_id="d1",
                              disposition=ad.Disposition.ACCEPT)
    later = ad.supersede(first, by="d2")
    assert later.is_current is False and later.superseded_by == "d2"
    with pytest.raises(ValueError, match="deletion with extra steps"):
        ad.supersede(first, by="")


def test_a_corrupt_disposition_reads_as_not_decided_and_never_as_accept():
    """ADVERSARIAL, and the direction is the point: an acceptance nobody gave
    is the one value that changes what the product believes it was told."""
    row = op.decision_as_dict(ad.AdviceDecision(
        decision_id="d1", disposition=ad.Disposition.ACCEPT))
    row["disposition"] = "authorised-for-filing"
    assert op.decision_from_dict(row).disposition is ad.Disposition.NOT_DECIDED


def test_the_served_decision_always_carries_the_authority_note():
    """A consumer that had to ask separately whether a decision authorises an
    act is a consumer that will not ask."""
    served = op.decision_projection(ad.AdviceDecision(
        decision_id="d1", disposition=ad.Disposition.ACCEPT,
        decided_by="adv_1", decided_at="2026-09-13", advice_version="v3",
        scope="thread 1", owner="adv_1", review_trigger="on filing"))
    assert served["authorises_action"] is False
    assert served["authority_note"]


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
