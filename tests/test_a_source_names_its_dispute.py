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

import inspect

import pytest
from nm.domain.binding import (
    Basis,
    SourceBinding,
    rebind,
    refuse_contribution,
    supersede,
)

pytestmark = pytest.mark.class_a


def _bound(thread_id="t1", basis=Basis.INFERRED) -> SourceBinding:
    return SourceBinding(source_id="doc_1", source_version="v1",
                         thread_id=thread_id, basis=basis, bound_by="nm",
                         bound_at="2026-09-13")


# ============================================== 1. there is no silent default =

def test_an_admitted_source_contributes_nothing_until_it_names_a_dispute():
    """The gate BK-94-AC5 asks for: a visible binding BEFORE contributing
    facts. And the refusal is a question for the advocate, not a log line."""
    unbound = SourceBinding(source_id="doc_1", source_version="v1")
    refused = refuse_contribution(unbound)
    assert refused
    assert "which one it belongs to" in refused
    assert "nothing in it is on the file" in refused


def test_nothing_in_the_binding_module_is_ever_given_a_list_of_threads():
    """THE STRUCTURAL INVARIANT, and it is the whole packet.

    A rule that says "do not default to the first thread" is a rule somebody
    breaks helpfully. A module that never receives the threads CANNOT pick
    one -- the same argument `retention.request` makes by taking no state and
    `advice.maturity_of` makes by taking no maturity.
    """
    from nm.domain import binding

    for name, fn in vars(binding).items():
        if not callable(fn) or name.startswith("_") or not inspect.isfunction(fn):
            continue
        params = set(inspect.signature(fn).parameters)
        for suspicious in ("threads", "matter", "candidates", "thread_ids"):
            assert suspicious not in params, (
                f"binding.{name} takes {suspicious!r}; a function holding the "
                f"threads is one refactor away from choosing between them")


def test_a_binding_that_claims_a_basis_without_a_thread_is_refused():
    """"Bound" must mean something. A STATED binding naming no thread would
    let the word travel with nothing behind it."""
    for basis in (Basis.STATED, Basis.INFERRED):
        with pytest.raises(ValueError, match="names no thread"):
            SourceBinding(source_id="d", source_version="v1", basis=basis)


def test_an_unbound_binding_carrying_a_thread_is_refused():
    """THE OTHER DIRECTION, and it is the one that matters. A thread sitting
    on an UNBOUND record is precisely the silent default -- a choice nobody
    made, ready to be read as one somebody did."""
    with pytest.raises(ValueError, match="silent default"):
        SourceBinding(source_id="d", source_version="v1", thread_id="t1")


# ================================= 2. stated and inferred stay distinguishable =

def test_an_inferred_binding_is_provisional_and_a_stated_one_is_not():
    """The shape the product already uses for posture and for the accrual
    premise. An inference the advocate never saw must not become the thing
    they are held to."""
    assert _bound(basis=Basis.INFERRED).provisional is True
    assert _bound(basis=Basis.STATED).provisional is False


def test_a_bound_source_may_contribute():
    """THE NEGATIVE CONTROL. A gate that refuses everything is an outage, and
    it would satisfy every refusal above."""
    assert refuse_contribution(_bound()) == ""


# ========================================= 3. correction preserves custody ====

def test_rebinding_keeps_the_source_and_its_version_untouched():
    """What moves is which dispute the document is about. The document, its
    version and its custody are not touched -- correcting the filing must not
    look like republishing the evidence."""
    before = _bound()
    after, was = rebind(before, thread_id="t2", basis=Basis.STATED,
                        by="adv_1", at="2026-09-14",
                        because="the advocate said it is the second dispute")
    assert after.source_id == before.source_id
    assert after.source_version == before.source_version
    assert after.thread_id == "t2" and was == "t1"
    assert after.basis is Basis.STATED, (
        "a correction by the advocate stayed provisional; their instruction "
        "is not an inference")


def test_rebinding_reports_the_old_thread_and_does_not_invalidate_anything():
    """P28's ledger owns invalidation. A second path marking things stale from
    here would be two answers to *is this still true* -- the §4 defect on the
    subject where disagreement is most expensive."""
    from nm.domain import binding

    # WHAT THE MODULE CAN REACH, not what its prose mentions. A first version
    # grepped the source and failed on the docstring explaining this very
    # rule -- the second time today that a check matched an explanation
    # instead of the code. A module cannot invalidate what it cannot import.
    reachable = {n for n in dir(binding) if not n.startswith("__")}
    assert "invalidate" not in reachable and "dependency" not in reachable, (
        f"the binding module can reach {reachable & {'invalidate', 'dependency'}}; "
        f"it reports what moved and nm.core.dependency decides what that "
        f"reaches")
    assert binding.__name__.startswith("nm.domain"), (
        "a domain module importing core would invert the layering that keeps "
        "invalidation in one place")
    _after, was = rebind(_bound(), thread_id="t2", basis=Basis.STATED,
                         by="adv_1", at="2026-09-14")
    assert was == "t1", "the caller is not told which thread's work is affected"


def test_a_rebinding_that_changes_nothing_is_refused():
    """It would bump the record and lose the original's timestamp for no
    reason -- and a history full of no-op corrections is a history nobody
    reads."""
    with pytest.raises(ValueError, match="already attached"):
        rebind(_bound(), thread_id="t1", basis=Basis.STATED, by="adv_1",
               at="2026-09-14")


def test_detaching_requires_superseding_rather_than_blanking_the_thread():
    """`rebind` will not take an UNBOUND basis. Blanking the thread in place
    would erase which dispute the document was filed against, which is the
    fact somebody later needs."""
    with pytest.raises(ValueError, match="requires a thread"):
        rebind(_bound(), thread_id="", basis=Basis.UNBOUND, by="adv_1",
               at="2026-09-14")


def test_a_superseded_binding_stops_contributing_and_says_why():
    withdrawn = supersede(_bound(), by="bind_2")
    assert withdrawn.is_current is False
    assert "superseded by" in refuse_contribution(withdrawn)
    with pytest.raises(ValueError, match="deletion with extra steps"):
        supersede(_bound(), by="")


# ==================== 4. the correction reaches P28's reassessment ===========

def test_a_rebinding_makes_exactly_the_old_threads_advice_reopen():
    """THE JOIN P25 IS FOR: attribution, corrected, invalidating the derived
    state that rested on it -- through P18's ledger, driven by P28, with no
    third mechanism in between."""
    from nm.core import reassessment as ra
    from nm.core.dependency import InputKind, Ledger, Rest

    led = ra.record_advice(
        Ledger(), thread_id="t1", position="sue on the delivery note",
        rests_on=(Rest(kind=InputKind.FACT, id="doc_1", version=1),),
        at="2026-09-13")
    led = ra.record_advice(
        led, thread_id="t2", position="defend the trespass",
        rests_on=(Rest(kind=InputKind.FACT, id="doc_other", version=1),),
        at="2026-09-13")

    _after, was = rebind(_bound(), thread_id="t2", basis=Basis.STATED,
                         by="adv_1", at="2026-09-14")
    led, reached = ra.reopen(
        led, (Rest(kind=InputKind.FACT, id="doc_1", version=1),),
        reason=f"the advocate re-attached doc_1 from thread {was} to t2",
        at="2026-09-14")

    assert ra.advice_node_name("t1") in reached
    assert ra.advice_node_name("t2") not in reached, (
        "the untouched dispute was reopened; a correction on one file must "
        "not reopen the other")


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
