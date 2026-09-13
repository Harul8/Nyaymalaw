"""BK-70 / E2 — the recommendation changes when the relief is not worth pursuing.

THE CRITERION, AND THE TRAP IT NAMES
--------------------------------------
BK-70-AC1: *advice changes when identical merits have unavailable, hollow, late
or disproportionate relief, and it explains the enforceability basis for the
recommendation.* The trap is the one CLAUDE.md records the whole product against
-- a right answer to a question nobody asked. A claim can be legally
unanswerable and worth nothing: the debtor has no assets, the order arrives too
late, the decree cannot be executed, the suit costs more than it recovers.

TWO HALVES, TESTED WHERE EACH BELONGS
---------------------------------------
The DOMAIN tests hold the objective constant and vary only the relief, and
prove the position and the claims it raises change for the relief reason and no
other -- including the negative control, that a step pursuing a defeated relief
contradicts the claim while one carrying the reservation does not, and the E3
control, that proportionality never removes a legally available route.

The SERVED tests drive the whole engine: a claim whose limitation has RUN makes
its relief LATE on the file, the enforceability basis reaches the advocate as a
disclosure, and a planted step that pursues the defeated relief is blocked for
the relief reason -- through the same G-CONSISTENT path a run-limitation step is.

`model_eval` and `counsel_review` -- whether the PRODUCT correctly reads
availability and enforceability off a real brief -- are the substance of the
other two required methods and are NOT run here; nothing in this file judges a
real brief's enforceability.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from nm.adapters.model.scripted import SCRIPTED_READS, ScriptedModelAdapter
from nm.adapters.store.file_store import FileMatterStore
from nm.core import consistency
from nm.core import relief as relief_r
from nm.core.premise import Basis
from nm.core.turn import TurnEngine, TurnInput
from nm.domain.answer import ElementKind
from tests.test_factors_on_a_served_turn import _Corpus
from tests.test_turn_contract import KEY, _model_config, briefed

pytestmark = pytest.mark.class_a

OBJECTIVE = "recover the price of the goods"


def _obj(basis: Basis = Basis.STATED) -> relief_r.Objective:
    return relief_r.Objective(OBJECTIVE, basis=basis, source="the advocate")


def _relief(**kw) -> relief_r.Relief:
    base = dict(
        remedy="a money decree for the price", objective=OBJECTIVE,
        forum="the civil court",
        availability=relief_r.Availability.AVAILABLE, value=relief_r.Value.SUBSTANTIAL,
        timing=relief_r.Timing.TIMELY, enforceability=relief_r.Enforceability.ENFORCEABLE,
    )
    base.update(kw)
    return relief_r.Relief(**base)


# ============================ DOMAIN: the model ============================

def test_all_four_load_bearing_coordinates_decide_delivery():
    """Merits held constant (one objective, one remedy), each coordinate moved
    in turn from favourable to adverse. Every one defeats delivery -- and the
    verdict names WHICH, so the advocate reads a reason, not a boolean."""
    assert relief_r.assess(_obj(), (_relief(),)).state is relief_r.ReliefState.SERVEABLE

    for kw, coord in (
        (dict(availability=relief_r.Availability.UNAVAILABLE), "availability"),
        (dict(value=relief_r.Value.HOLLOW), "value"),
        (dict(timing=relief_r.Timing.LATE), "timing"),
        (dict(enforceability=relief_r.Enforceability.UNENFORCEABLE), "enforceability"),
    ):
        pos = relief_r.assess(_obj(), (_relief(
            basis=Basis.ATTRIBUTED, source="the file", reason="on the file",
            **kw),))
        assert pos.state is relief_r.ReliefState.DEFEATED, (coord, pos.state)
        assert pos.defeated and pos.defeated[0][1] == coord, pos.defeated
        assert not pos.useful


def test_proportionality_is_never_a_reason_to_withhold_a_route():
    """E3's NEVER, made structural. A disproportionate route STILL delivers --
    it is `useful` and the position is SERVEABLE -- and the only obligation is
    to STATE the cost, never to remove the route. There is no branch in which
    proportionality empties `useful`."""
    pos = relief_r.assess(_obj(), (_relief(
        proportionality=relief_r.Proportionality.DISPROPORTIONATE,
        basis=Basis.ATTRIBUTED, source="the fee schedule",
        reason="a 40,000 claim pursued through a 200,000 route"),))
    assert pos.state is relief_r.ReliefState.SERVEABLE
    assert pos.useful, "a disproportionate route was withheld -- E3 forbids that"
    assert pos.disproportionate, "the cost-to-value was not stated alongside"
    ids = {cid for cid, _s in relief_r.consistency_claims(pos)}
    # The claim asks the step to SAY the cost exceeds recovery, not to drop it.
    assert ids == {"proportionality"}, ids


def test_an_inferred_shortfall_is_a_question_not_a_defeat():
    """P22's discipline, on relief. An enforceability shortfall the product
    only INFERRED is CONTINGENT -- a question -- not DEFEATED. The same
    shortfall STATED or ATTRIBUTED is a defeat."""
    inferred = relief_r.assess(_obj(), (_relief(
        enforceability=relief_r.Enforceability.UNENFORCEABLE, basis=Basis.INFERRED,
        inferred_from="no assets were mentioned in the brief",
        reason="enforceability is unconfirmed"),))
    assert inferred.state is relief_r.ReliefState.CONTINGENT
    assert inferred.contingent and not inferred.defeated

    established = relief_r.assess(_obj(), (_relief(
        enforceability=relief_r.Enforceability.UNENFORCEABLE, basis=Basis.STATED,
        source="the advocate says the debtor is insolvent",
        reason="the debtor is insolvent and holds no attachable assets"),))
    assert established.state is relief_r.ReliefState.DEFEATED
    assert established.defeated and not established.contingent


def test_nobody_looked_is_not_the_same_as_nothing_to_pursue():
    """§9's third state. No reliefs assessed is NOT_ASSESSED, which is not
    DEFEATED -- 'we looked and there is nothing worth pursuing' and 'nobody
    looked' are opposite facts, and G-REMEDY reads them differently."""
    pos = relief_r.assess(_obj(), ())
    assert pos.state is relief_r.ReliefState.NOT_ASSESSED
    assert relief_r.gate_state(pos) == "not_assessed"
    assert relief_r.consistency_claims(pos) == ()
    assert relief_r.disclosure(pos) == ""


def test_a_step_pursuing_a_defeated_relief_contradicts_and_a_reservation_clears_it():
    """THE NEGATIVE CONTROL, at the guard. The relief becomes a claim in the
    ONE consistency owner; a step that pursues it as though it will deliver is
    `contradicted` on the `relief` id, and a step that carries the reservation
    the claim names is not. The guard can fail, and the escape is exactly the
    'explicit justified reservation' the criterion requires."""
    pos = relief_r.assess(_obj(), (_relief(
        enforceability=relief_r.Enforceability.UNENFORCEABLE, basis=Basis.STATED,
        source="the advocate says the debtor is insolvent",
        reason="the debtor is insolvent and holds no attachable assets"),))
    claims = consistency.claims_for(None, None, "moving", date(2026, 9, 4),
                                    relief_position=pos)
    by_id = {c.id: c for c in claims}
    assert "relief" in by_id, "the defeated relief did not become a claim"
    # The claim offers the reservation escape in its own words.
    assert "reservation" in by_id["relief"].sentence.lower()

    step = "File the recovery suit to recover the price in full."
    contra = consistency.interpret(
        {"claim_id": "relief", "quoted": "File the recovery suit",
         "why": "the decree cannot be enforced against an insolvent debtor"},
        step, frozenset(by_id))
    assert contra.contradicted and contra.claim_id == "relief"

    # A read that finds no contradiction (the step carried its reservation)
    # leaves the step standing -- the guard fails toward serving, by design.
    ok = consistency.interpret({"claim_id": "", "quoted": "", "why": ""},
                               step, frozenset(by_id))
    assert not ok.contradicted and ok.ran


def test_relief_and_the_position_survive_storage():
    """A relief and an objective round-trip through the store's generic decoder,
    and the position digest is stable across the trip -- the same move the
    premise digest makes so the answer and the cover cannot silently disagree."""
    r = _relief(enforceability=relief_r.Enforceability.UNENFORCEABLE, basis=Basis.STATED,
                source="the advocate", reason="no attachable assets",
                prerequisites=("a decree", "an execution petition"))
    back = relief_r.Relief.from_stored(r.as_dict())
    assert back == r
    o = _obj()
    assert relief_r.Objective.from_stored(o.as_dict()) == o
    pos = relief_r.assess(o, (r,))
    rebuilt = relief_r.assess(relief_r.Objective.from_stored(o.as_dict()),
                       relief_r.reliefs_from_stored(pos.as_rows()))
    assert rebuilt.digest == pos.digest
    # An unreadable row is dropped, not fatal.
    assert relief_r.reliefs_from_stored([{"nonsense": 1}, r.as_dict()]) == (r,)


# ============================ SERVED: the engine ==========================

BRIEF = ("We act for the plaintiff, a supplier at Hyderabad. Goods were "
         "supplied against invoices on 14 March 2010 and were never paid for.")
TODAY = date(2026, 9, 4)


def _engine(tmp_path, responses=None):
    model = ScriptedModelAdapter(_model_config(), responses=responses or {
        "__default__": "File the recovery suit to recover the price in full."})
    return briefed(TurnEngine(store=FileMatterStore(tmp_path, key=KEY),
                              evidence=_Corpus(), model=model))


def _fired(out):
    return {g.gate_id: g.state for g in out.metrics.gates_fired}


def test_a_run_limitation_makes_the_relief_late_and_reaches_the_advocate(tmp_path):
    """SERVED, end to end. A goods claim whose three-year window ran in 2013 is
    still legally a debt -- and its relief is LATE, because it cannot be filed
    in time. G-REMEDY discloses `no_useful_relief`, the enforceability basis is
    a disclosure the advocate reads, and the relief is persisted on the thread,
    ATTRIBUTED to the computed limitation rather than guessed."""
    engine = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF, today=TODAY))

    fired = _fired(out)
    assert fired.get("G-REMEDY") == "no_useful_relief", fired

    disc = [e for e in out.answer.elements
            if e.disclosure and "Relief for" in e.text]
    assert disc, "the enforceability basis did not reach the advocate"
    low = disc[0].text.lower()
    assert ("delivers it" in low or "confirmed to deliver" in low), disc[0].text
    assert "cannot be filed in time" in low, disc[0].text

    (thread,) = out.matter.threads
    rows = relief_r.reliefs_from_stored(thread.reliefs)
    assert rows and rows[0].timing is relief_r.Timing.LATE
    # ATTRIBUTED where the limitation was COMPUTED, INFERRED where it was
    # CONDITIONAL -- never UNESTABLISHED, because the lateness rests on the
    # computed limitation, a typed fact that can be re-read, not a guess.
    assert rows[0].basis in (Basis.ATTRIBUTED, Basis.INFERRED)
    assert "limitation" in rows[0].reason.lower()


def _names_relief(user: str) -> str:
    """A consistency responder that contradicts the step ON THE RELIEF CLAIM,
    quoting the step's own opening words -- the planted violation."""
    offered = re.findall(r"^\s+(\w+)\t", user, flags=re.M)
    step = re.search(r"THE STEP:\n(.*?)\n\nWhich", user, flags=re.S)
    words = " ".join((step.group(1) if step else "").split()[:4])
    cid = "relief" if "relief" in offered else (offered[0] if offered else "")
    return json.dumps({"claim_id": cid, "quoted": words,
                       "why": "the step pursues a remedy the file says cannot deliver"})


def test_a_planted_step_pursuing_the_defeated_relief_is_blocked_for_the_relief_reason(
        tmp_path, monkeypatch):
    """THE NEGATIVE CONTROL, SERVED. The relief is defeated (limitation run), so
    the relief claim is offered; a step that pursues it is caught by
    G-CONSISTENT and the advocate gets the computed position and a question
    rather than a sentence that pursues a remedy the file says is dead."""
    monkeypatch.setitem(SCRIPTED_READS, "consistency", _names_relief)
    engine = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF, today=TODAY))

    action = next((e for e in out.answer.elements
                   if e.kind is ElementKind.ACTION), None)
    blocked = next((e for e in out.answer.elements
                    if e.kind is ElementKind.QUESTION and e.gate == "G-CONSISTENT"),
                   None)
    assert action is None, "a step pursuing a defeated relief was served unchanged"
    assert blocked is not None, "the planted step was not blocked by G-CONSISTENT"


# ============================ SERVED: the route ===========================

def _client(tmp_path):
    from fastapi.testclient import TestClient

    from tools.served import PASSWORD, served

    box = served(tmp_path / "store")
    advocate = box.enrol("adv_relief")
    c = TestClient(box.app)

    def carry(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            request.headers.setdefault("origin", str(c.base_url).rstrip("/"))
            v = c.cookies.get("nm_csrf")
            if v and "x-nm-csrf" not in request.headers:
                request.headers["x-nm-csrf"] = v
    c.event_hooks["request"].append(carry)
    assert c.post("/api/login", json={"advocate_id": advocate,
                                      "password": PASSWORD}).status_code == 200
    c.advocate = advocate
    return c


def _open_matter(c):
    r = c.post("/api/turn", json={
        "message": "We act for the plaintiff at Hyderabad. Goods supplied on "
                   "14 March 2023, unpaid.",
        "today": "2026-09-04",
        "parties": {"A Traders": "client", "B Co": "adverse"},
        "release": {"scope": "recover"},
        "capacity": {
            "state": "not_in_doubt",
            "basis": "The advocate assessed that the client instructs directly.",
        }})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"], r.json()["matter_version"]


def test_the_advocate_can_state_a_relief_and_the_cover_reflects_it(tmp_path):
    """SERVED THROUGH THE ROUTE. The advocate states that the only useful remedy
    is unenforceable; the cover reports `no_useful_relief` and names the
    enforceability shortfall, and an unknown coordinate value is refused rather
    than blanked -- the same discipline the premise route keeps for its kind."""
    c = _client(tmp_path)
    mid, ver = _open_matter(c)
    tid = c.get(f"/api/matters/{mid}").json()["threads"][0]["thread_id"]

    r = c.post(f"/api/matters/{mid}/threads/{tid}/relief", json={
        "remedy": "a money decree for the price",
        "objective": "recover the price of the goods",
        "availability": "available", "value": "substantial", "timing": "timely",
        "enforceability": "unenforceable", "proportionality": "proportionate",
        "reason": "the debtor is insolvent with no attachable assets",
        "expected_version": ver})
    assert r.status_code == 201, r.text

    cover = c.get(f"/api/matters/{mid}/cover").json()
    assert cover["relief"]["state"] == "no_useful_relief", cover["relief"]
    thread = cover["relief"]["threads"][0]
    assert thread["state"] == "defeated"
    assert thread["defeated"][0]["coordinate"] == "enforceability"
    assert thread["objective"]["basis"] == "stated"

    bad = c.post(f"/api/matters/{mid}/threads/{tid}/relief", json={
        "remedy": "x", "objective": "y", "enforceability": "nonsense",
        "expected_version": cover["version"]})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "INVALID_REQUEST"


def test_a_disproportionate_route_is_stated_alongside_never_withheld_served(tmp_path):
    """E3, SERVED. A route that costs more than it recovers is still available:
    the cover keeps it serveable and lists it under `disproportionate` so the
    advocate is told the cost, not denied the route."""
    c = _client(tmp_path)
    mid, ver = _open_matter(c)
    tid = c.get(f"/api/matters/{mid}").json()["threads"][0]["thread_id"]
    r = c.post(f"/api/matters/{mid}/threads/{tid}/relief", json={
        "remedy": "a recovery suit", "objective": "recover the price",
        "availability": "available", "value": "substantial", "timing": "timely",
        "enforceability": "enforceable", "proportionality": "disproportionate",
        "reason": "a 40,000 claim through a 200,000 route",
        "expected_version": ver})
    assert r.status_code == 201, r.text
    thread = c.get(f"/api/matters/{mid}/cover").json()["relief"]["threads"][0]
    assert thread["state"] == "serveable", thread
    assert "a recovery suit" in thread["useful"]
    assert thread["disproportionate"], "the cost was not stated alongside"
