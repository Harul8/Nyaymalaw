"""EVAL-010 on the wire. BK-65-AC1's integration and adversarial evidence. P18.

WHAT THE UNIT TESTS COULD NOT SAY
-----------------------------------
`tests/test_a_correction_reaches_exactly_what_it_touched.py` proves the
ledger: a transitive closure, an invalidation that leaves the independent node
alone, a rework that fails rather than certifying. It proves nothing about
whether a served turn ever WRITES the ledger, whether a correction typed into
the case file reaches it, whether the cover and the board read it, or whether
any of it survives the process that computed it going away. Every defect the
first external review found lived in exactly that gap (CLAUDE.md §8).

So this file drives the real ASGI application:

    1. one turn derives a limitation and a deadline from a dated fact, and a
       party role from a different fact;
    2. the advocate corrects the DATE through the case-file route;
    3. THE APPLICATION IS REBUILT ON THE SAME STORE -- a restart -- and the
       cover, the board and the ledger are read back;
    4. the deadline is stale with its prior value and the reason, the role is
       current, and nothing calls the old date the nearest live deadline.

THE PLANTED NEGATIVE is EVAL-010's: serve the version-1 figure as current
after version 2 is accepted. It is planted by building a projection WITHOUT
the ledger and asserting that it does what the wired one refuses to.

WHAT IS SYNTHETIC. The matter, the dates and the brief are invented; the
evidence double returns the same Article on every turn; the model is scripted.
Nothing here is a claim about Indian law.
"""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 4)

#: One dated event, one stated role. The limitation rests on the date; the
#: role rests on the sentence that names our client's side. Correcting the
#: date must reach the first and not the second -- EVAL-010's `dependent` and
#: `independent` on ONE thread, which is the harder version of the test.
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")


# ------------------------------------------------------------- the helpers ---

def _turn(client, message: str, matter_id: str | None = None) -> dict:
    payload = {"message": message, "today": TODAY.isoformat()}
    if matter_id:
        payload["matter_id"] = matter_id
    r = client.post("/api/turn", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _dated_fact(client, matter_id: str) -> dict:
    """The live entry that carries the date the limitation ran from."""
    casefile = client.get(f"/api/matters/{matter_id}/casefile").json()
    dated = [e for e in casefile["live"] if "14 March 2023" in e["statement"]
             or "2023" in e["statement"]]
    assert dated, f"no dated entry on the file:\n{casefile['live']}"
    # THE SHORTEST ONE IS THE DATE READ'S OWN EVENT, not the whole account.
    return min(dated, key=lambda e: len(e["statement"]))


def _restart(client, tmp_path):
    """A NEW application on the SAME store, signed in again.

    This is what a restart is to the persisted file: a process that never
    saw the correction, reading what the last one wrote. `client.sign_in`
    would return the same process; this builds another.
    """
    from fastapi.testclient import TestClient

    from nm.adapters.model.config import ModelConfig, TierConfig
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.store.file_store import FileMatterStore
    from nm.bootstrap.composition import Application
    from nm.bootstrap.main import create_app
    from nm.ports.model import Tier
    from tests.test_turn_contract import KEY, _Evidence, briefed

    config = ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "scripted", "scripted-1", None, None),
        Tier.EMBED: TierConfig(Tier.EMBED, "scripted", "text-embedding-3-large",
                               None, None),
    })
    application = Application(
        store=FileMatterStore(tmp_path, key=KEY), evidence=_Evidence(),
        directory=client.directory,
        model=ScriptedModelAdapter(config, responses={
            "__default__": "Issue the statutory notice and diarise the window."}))
    application.engine = briefed(application.engine)
    fresh = TestClient(create_app(application))

    def carry(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            request.headers.setdefault("origin", str(fresh.base_url).rstrip("/"))
            value = fresh.cookies.get("nm_csrf")
            if value and "x-nm-csrf" not in request.headers:
                request.headers["x-nm-csrf"] = value
    fresh.event_hooks["request"].append(carry)
    r = fresh.post("/api/login", json={"advocate_id": "adv_demo",
                                       "password": "Fixture-password-not-a-secret-1"})
    assert r.status_code == 200, r.text
    return fresh


def _names(matter_id: str, client) -> dict:
    from nm.core.dependency import names_for

    board = client.get(f"/api/matters/{matter_id}").json()
    assert board["threads"], "the turn opened no thread"
    thread_id = board["threads"][0]["thread_id"]
    n = names_for(thread_id)
    return {"thread": thread_id, "limitation": n.limitation,
            "deadline": n.deadline, "role": n.role}


# ====================================================== 1. the turn records ==

def test_a_served_turn_records_what_it_derived_and_what_each_rests_on(client):
    """THE FIRST HALF OF THE WIRING: the ledger exists on the matter after a
    turn, and the three nodes name their inputs by kind."""
    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    names = _names(matter_id, client)

    deps = client.get(f"/api/matters/{matter_id}/dependencies").json()
    assert deps["state"] == "current", deps
    by_name = {n["name"]: n for n in deps["nodes"]}
    assert names["limitation"] in by_name, sorted(by_name)
    assert names["deadline"] in by_name, sorted(by_name)
    assert names["role"] in by_name, sorted(by_name)

    kinds = {r["kind"] for r in by_name[names["limitation"]]["rests_on"]}
    assert "fact" in kinds, "the limitation names no fact it rests on"
    assert "authority" in kinds, (
        "the limitation names no Article it rests on, so a republished "
        "provision would never reach it")
    assert by_name[names["deadline"]]["rests_on"] == [
        {"kind": "derived", "id": names["limitation"], "version": 1}], (
        "the deadline does not rest on the limitation, so a corrected date "
        "cannot reach the register two hops away")
    assert {r["kind"] for r in by_name[names["role"]]["rests_on"]} == {"fact"}

    for name in (names["limitation"], names["deadline"], names["role"]):
        assert by_name[name]["currency"] == "current", by_name[name]
        assert by_name[name]["usable"] is True


def test_the_turn_fires_the_gate_it_discloses_under(client):
    """G-CURRENCY is in the matrix as built; the turn must consult it."""
    out = _turn(client, BRIEF)
    fired = {g["gate"] for g in out["metrics"]["gates_fired"]}
    assert "G-CURRENCY" in fired, sorted(fired)


# ============================================= 2. the correction, and the closure ==

def _correct_the_date(client, matter_id: str) -> tuple[dict, dict]:
    entry = _dated_fact(client, matter_id)
    version = client.get(f"/api/matters/{matter_id}/casefile").json()["version"]
    r = client.post(
        f"/api/matters/{matter_id}/facts/{entry['fact_id']}/corrections",
        json={"date": "2019-03-14",
              "reason": "the invoices are dated 2019; 2023 was a typing error",
              "expected_version": version})
    assert r.status_code == 201, r.text
    return entry, r.json()


def test_correcting_the_date_invalidates_the_deadline_and_not_the_role(client):
    """BK-65-AC1, BOTH HALVES, THROUGH THE ROUTE.

    `changing a material predicate invalidates every dependent conclusion
    and no unrelated conclusion, while preserving the prior state and reason
    for change.`
    """
    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    names = _names(matter_id, client)

    entry, corrected = _correct_the_date(client, matter_id)

    assert corrected["state"] == "corrected"
    assert corrected["fact"]["was"] == entry["fact_id"]
    assert corrected["fact"]["was_date"] == "2023-03-14"
    assert corrected["fact"]["now_date"] == "2019-03-14"

    # EVERY DEPENDENT, transitively -- the deadline is two hops from the date.
    assert set(corrected["affected"]) == {names["limitation"], names["deadline"]}, (
        f"the closure reached {corrected['affected']}; it should reach exactly "
        f"the limitation and the deadline that rests on it")
    # AND NO UNRELATED ONE.
    assert names["role"] in corrected["unaffected"], (
        "the party role was invalidated by a corrected date it never rested on "
        "-- the over-broad closure that trains advocates to ignore invalidation")

    currency = corrected["currency"]
    assert currency["state"] == "stale"
    stale = {s["name"]: s for s in currency["stale"]}
    assert set(stale) == {names["limitation"], names["deadline"]}
    assert stale[names["deadline"]]["because"], "stale with no reason"
    assert "fed into" in stale[names["deadline"]]["because"], (
        "the deadline's reason does not say it is INDIRECTLY affected; the "
        "advocate goes looking for a correction to the deadline they never made")

    # THE PRIOR STATE AND THE REASON ARE KEPT. EVAL-010: the advocate sees the
    # old and the corrected date and who changed it.
    history = {h["name"]: h for h in currency["history"]}
    assert names["limitation"] in history
    assert history[names["limitation"]]["was"], "the prior value was not kept"
    assert "adv_demo" in history[names["limitation"]]["reason"], (
        "the revision does not say who changed it")
    assert "typing error" in history[names["limitation"]]["reason"]
    moved = corrected["moved"]
    assert any(r["kind"] == "fact" and r["id"] == entry["fact_id"]
               and r["version"] == 2 for r in moved), moved


def test_the_correction_needs_the_version_it_was_composed_against(client):
    """STALE_VERSION. A correction to an entry on a file that has moved is
    refused with the two versions, never applied to whatever is there now."""
    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    entry = _dated_fact(client, matter_id)
    version = client.get(f"/api/matters/{matter_id}/casefile").json()["version"]

    r = client.post(
        f"/api/matters/{matter_id}/facts/{entry['fact_id']}/corrections",
        json={"date": "2019-03-14", "reason": "typo",
              "expected_version": version - 1})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "STALE_VERSION"
    assert r.json()["detail"]["committed"] == "not_committed"

    deps = client.get(f"/api/matters/{matter_id}/dependencies").json()
    assert deps["state"] == "current", "a refused correction still invalidated"


def test_a_withdrawn_entry_cannot_be_corrected_twice(client):
    """One correction is one revision. Correcting the superseded entry again
    would make one change read as two, and leave a chain nothing walks."""
    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    entry, _ = _correct_the_date(client, matter_id)
    version = client.get(f"/api/matters/{matter_id}/casefile").json()["version"]

    r = client.post(
        f"/api/matters/{matter_id}/facts/{entry['fact_id']}/corrections",
        json={"date": "2018-01-01", "reason": "again",
              "expected_version": version})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "INVALID_TRANSITION"

    deps = client.get(f"/api/matters/{matter_id}/dependencies").json()
    limitation = [h for h in deps["history"]
                  if h["name"] == _names(matter_id, client)["limitation"]]
    assert len(limitation) == 1, "one correction produced two revisions"


def test_a_correction_that_changes_nothing_is_refused(client):
    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    entry = _dated_fact(client, matter_id)
    version = client.get(f"/api/matters/{matter_id}/casefile").json()["version"]
    r = client.post(
        f"/api/matters/{matter_id}/facts/{entry['fact_id']}/corrections",
        json={"reason": "no change", "expected_version": version})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "INVALID_REQUEST"


# ================================================= 3. the restart, and the reads ==

def test_a_stale_conclusion_is_labelled_stale_on_the_served_cover(client, tmp_path):
    """EVAL-010, SEQUENCE STEP 3: restart and request both records.

    `dependent.current_without_reassessment == false`
    `independent.invalidated == false`
    `history.source_versions == {1, 2}`

    The process that made the correction is gone. What the new one serves
    is read from the file, and the file must say the deadline is stale, keep
    the role current, and never put the old date at the top of the board.
    """
    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    names = _names(matter_id, client)
    board_before = client.get(f"/api/matters/{matter_id}").json()
    row_before = board_before["threads"][0]
    assert row_before["next_deadline"], "no deadline to go stale"
    assert row_before["next_deadline_currency"] == "current"
    old_date = row_before["next_deadline"]

    _correct_the_date(client, matter_id)

    fresh = _restart(client, tmp_path)

    # THE COVER -- the advocate's first screen on the file.
    resp = fresh.get(f"/api/matters/{matter_id}/cover")
    assert resp.status_code == 200, resp.text
    cover = resp.json()
    assert cover["currency"]["state"] == "stale", cover["currency"]
    stale = {s["name"] for s in cover["currency"]["stale"]}
    assert names["deadline"] in stale and names["limitation"] in stale
    assert names["role"] not in stale, "the independent conclusion was invalidated"

    # THE BOARD -- the old date must not lead.
    board = fresh.get(f"/api/matters/{matter_id}").json()
    row = board["threads"][0]
    assert row["next_deadline"] != old_date, (
        "the corrected date is still the nearest deadline on the board")
    assert row["next_deadline_status"] == "stale", row
    assert row["stale_deadline"] == old_date, (
        "the stale window vanished instead of being shown labelled stale -- "
        "an advocate reads that as a file with no deadline")
    # THE REASON IS NOT ON THE BOARD (A2: never analysis on a board). It is
    # on the cover, in the ledger's own words.
    assert "because" not in str(row), row
    assert cover["currency"]["stale"][0]["because"]

    # THE MATTER LIST -- the same rule, one board up.
    listing = fresh.get("/api/matters").json()
    mine = next(m for m in listing["matters"] if m["matter_id"] == matter_id)
    assert mine["next_deadline"] != old_date
    assert mine["next_deadline_status"] == "stale"
    assert mine["stale_deadlines"] == 1

    # THE LEDGER -- both versions are on record.
    deps = fresh.get(f"/api/matters/{matter_id}/dependencies").json()
    node = next(n for n in deps["nodes"] if n["name"] == names["limitation"])
    assert set(node["source_versions"]) >= {1, 2}, node["source_versions"]
    assert node["usable"] is False
    role = next(n for n in deps["nodes"] if n["name"] == names["role"])
    assert role["currency"] == "current" and role["usable"] is True


def test_the_next_turn_recomputes_and_closes_the_revision(client):
    """REWORK THROUGH THE EXISTING MECHANISM: the next turn derives the
    limitation again, from the corrected date, and the revision closes with
    `was` AND `now`."""
    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    names = _names(matter_id, client)
    _correct_the_date(client, matter_id)

    again = _turn(client, "And where does the limitation stand now?", matter_id)
    assert again["matter_id"] == matter_id

    deps = client.get(f"/api/matters/{matter_id}/dependencies").json()
    assert deps["state"] == "current", deps["stale"]
    revision = next(h for h in deps["history"] if h["name"] == names["limitation"])
    assert revision["was"] and revision["now"], revision
    assert revision["was"] != revision["now"], (
        "the limitation was recomputed from a date six years earlier and did "
        "not move")
    assert revision["now"] < revision["was"], "a 2019 accrual expires after a 2023 one?"

    board = client.get(f"/api/matters/{matter_id}").json()
    row = board["threads"][0]
    assert row["next_deadline_currency"] == "current"
    assert row["stale_deadline"] is None


# ======================================================== 4. the planted negative ==

def test_planted_serving_the_old_figure_as_current_is_refused(client):
    """EVAL-010's planted negative: *serve meeting-timeline derived from
    source version 1 as current after version 2 is accepted* -- expected
    refusal `source_version_stale`.

    THE MUTATION IS A PROJECTION BUILT WITHOUT THE LEDGER. That is exactly
    what the board did before P18, and exactly what a caller who forgets the
    `currency` argument would rebuild -- so the control is asserted by
    showing that the unwired projection leads with the stale date and the
    wired one refuses to.
    """
    from nm.core.dependency import Ledger, presentable
    from nm.edge.api import _register_of
    from nm.edge.projections import _thread_row

    out = _turn(client, BRIEF)
    matter_id = out["matter_id"]
    names = _names(matter_id, client)
    _correct_the_date(client, matter_id)

    from nm.edge.api import application
    matter = application().store.load(matter_id)
    register = _register_of(matter)
    thread = matter.threads[0]

    # THE PLANT: no ledger. The old date leads, labelled nothing.
    unwired = _thread_row(thread, register, TODAY, currency=None)
    assert unwired["next_deadline"] is not None
    assert unwired["next_deadline_currency"] == "not_established", (
        "a projection with no ledger claims currency it cannot have")

    # THE CONTROL: with the ledger, the same date is stale and does not lead.
    wired = _thread_row(thread, register, TODAY, currency=matter.dependencies)
    assert wired["next_deadline"] is None
    assert wired["next_deadline_status"] == "stale"
    assert wired["stale_deadline"] == unwired["next_deadline"]

    # AND THE REFUSAL NAMES THE STALE SOURCE VERSION, at the ledger.
    ledger = Ledger.from_stored(matter.dependencies)
    ok, why = presentable(ledger, names["deadline"])
    assert ok is False
    assert "version" in why or "fed into" in why, why


def test_an_unrecorded_conclusion_is_not_assessed_rather_than_current(client):
    """A matter no turn has derived on has no ledger. The cover says so as a
    VALUE -- `not_assessed` -- and never `current`, because an empty list of
    stale nodes is not a certificate."""
    # NO SIDE IS STATED, so the posture question blocks the turn before
    # anything side-dependent is computed: no limitation, no deadline, and
    # no role -- a matter with a file and no conclusions on it.
    out = _turn(client, "Goods were supplied against invoices last year and "
                        "were never paid for.")
    matter_id = out["matter_id"]
    assert matter_id, "the brief opened no matter"
    resp = client.get(f"/api/matters/{matter_id}/cover")
    assert resp.status_code == 200, resp.text
    cover = resp.json()
    assert cover["currency"]["nodes"] == [], cover["currency"]["nodes"]
    assert cover["currency"]["state"] == "not_assessed", cover["currency"]
    assert "cannot be certified" in cover["currency"]["said"]
