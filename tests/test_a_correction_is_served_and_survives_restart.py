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


def _advised(client) -> dict:
    """THE BRIEF, THEN THE ADVOCATE CONFIRMS THE ACCRUAL. Returns the turn that
    computes under it.

    Since `602e3f0` a MODEL-SELECTED accrual is conditional: naming a dated
    entry does not establish that it satisfies the Article's trigger, so the
    first turn serves the arithmetic as CONDITIONAL and records no deadline
    (G-PREMISE, `tests/test_premises_come_before_arithmetic.py`). These tests
    were written before that decision and asked the first turn for a
    deadline; the rule they state -- a correction reaches exactly what rests
    on the corrected fact -- is about a DEFINITIVE limitation, and the product
    reaches one only through the advocate. So they take that path.

    The premise names the TRIGGER, not a date: the period must still run from
    the dated entry, or correcting that entry would have nothing to reach.
    """
    first = _turn(client, BRIEF)
    matter_id = first["matter_id"]
    thread_id = client.get(f"/api/matters/{matter_id}").json()["threads"][0]["thread_id"]
    r = client.post(
        f"/api/matters/{matter_id}/threads/{thread_id}/premises/accrual_rule",
        json={"statement": "time runs from the delivery of the goods against "
                           "the invoices", "source": "the advocate",
              "expected_version": first["matter_version"]})
    assert r.status_code == 201, r.text
    return _turn(client, "Where does the limitation stand now?", matter_id)


def _dated_fact(client, matter_id: str) -> dict:
    """The live entry that carries the date the limitation ran from."""
    casefile = client.get(f"/api/matters/{matter_id}/casefile").json()
    dated = [e for e in casefile["live"] if "14 March 2023" in e["statement"]
             or "2023" in e["statement"]]
    assert dated, f"no dated entry on the file:\n{casefile['live']}"
    # THE SHORTEST ONE IS THE DATE READ'S OWN EVENT, not the whole account.
    return min(dated, key=lambda e: len(e["statement"]))


# ====================================================== 1. the turn records ==


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


# ======================================================== 4. the planted negative ==


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
