"""Legal premises are established before the arithmetic, and stated by the advocate.
BK-65-AC2, BK-35-AC1, BK-35-AC2. P22.

The domain half is `nm/core/premise.py`: three kinds, four bases, the block on
unestablished and the conditional on inferred. The served half drives the real
ASGI app: a cause with no curated accrual trigger and two dated events computes
CONDITIONAL -- a date shown with its alternatives, NOT a deadline on the
register -- until the advocate states the accrual, after which the same
arithmetic becomes a real deadline. The adversarial half: a trigger date
corrected after calculation cannot be served as current (P18 currency), and a
cover and a register on different premise versions read `inconsistent`.

`model_eval` and `counsel_review` for BK-65-AC2 and BK-35-AC1 are NOT RUN and
no code here runs them; this is their foundation.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.class_a

# --- a cause with no curated accrual trigger and two dated events -----------
CONDITIONAL_BRIEF = (
    "We act for the plaintiff at Hyderabad. We lent the defendant money on "
    "3 February 2016. The defendant promised to repay by 3 February 2018. "
    "Nothing has been repaid.")


# ================================================= the domain, no server ====

def test_the_three_premises_are_separate_and_none_derivable_from_arithmetic():
    from nm.core import premise as pr

    good = pr.Premises((
        pr.Premise(pr.Kind.APPLICABLE_LAW, "Article 22", pr.Basis.ATTRIBUTED,
                  source="act:art22"),
        pr.Premise(pr.Kind.ACCRUAL_RULE, "runs from the fixed repayment date",
                  pr.Basis.ATTRIBUTED, source="curated"),
        pr.Premise(pr.Kind.JURISDICTION, "Telangana", pr.Basis.ATTRIBUTED,
                  source="scope"),
    ))
    assert good.unestablished() == () and good.inferred() == ()
    assert not pr.blocks(good)

    # AN INFERRED ACCRUAL is not unestablished -- it is a question, and it is
    # what makes a computation conditional rather than blocked.
    inferred = pr.Premises((
        good.of(pr.Kind.APPLICABLE_LAW),
        pr.Premise(pr.Kind.ACCRUAL_RULE, "ran from the earliest dated entry",
                  pr.Basis.INFERRED, inferred_from="no curated trigger",
                  alternatives=("3 February 2018",)),
        good.of(pr.Kind.JURISDICTION),
    ))
    assert inferred.unestablished() == ()
    assert pr.Kind.ACCRUAL_RULE in inferred.inferred()


def test_an_unestablished_premise_is_named_by_its_kind():
    from nm.core import premise as pr

    missing = pr.Premises((
        pr.Premise(pr.Kind.ACCRUAL_RULE, "x", pr.Basis.ATTRIBUTED, source="s"),
        pr.Premise(pr.Kind.JURISDICTION, "Telangana", pr.Basis.ATTRIBUTED, source="s"),
    ))
    assert pr.Kind.APPLICABLE_LAW in missing.unestablished()
    assert "provision" in pr.english_of(pr.Kind.APPLICABLE_LAW)


def test_a_premise_carries_its_review_state_and_survives_storage():
    from nm.core import premise as pr

    attributed = pr.Premise(pr.Kind.APPLICABLE_LAW, "Article 22", pr.Basis.ATTRIBUTED,
                           source="act:art22")
    assert attributed.review_state == "not_assessed"
    stated = pr.Premise(pr.Kind.ACCRUAL_RULE, "from the repayment date",
                       pr.Basis.STATED, source="the advocate",
                       reviewed_by="adv_1", reviewed_at="2026-09-12")
    assert stated.review_state == "reviewed"
    back = pr.Premise.from_stored(stated.as_dict())
    assert back == stated
    # AN UNREADABLE BASIS IS UNESTABLISHED, never dropped and never STATED.
    broken = pr.Premise.from_stored({"kind": "accrual_rule", "statement": "x",
                                    "basis": "nonsense"})
    assert broken.basis is pr.Basis.UNESTABLISHED


def test_the_digest_moves_when_a_premise_moves():
    from nm.core import premise as pr

    a = pr.Premises((pr.Premise(pr.Kind.ACCRUAL_RULE, "from delivery",
                              pr.Basis.ATTRIBUTED, source="s"),))
    b = pr.Premises((pr.Premise(pr.Kind.ACCRUAL_RULE, "from refusal",
                              pr.Basis.ATTRIBUTED, source="s"),))
    assert a.digest() != b.digest()
    assert pr.invalidated(a.digest(), b) is not None
    assert pr.invalidated(a.digest(), a) is None


def test_the_same_dates_expire_differently_under_different_triggers():
    from datetime import date

    from nm.core.limitation import Period, expiry_from

    p = Period(years=3, months=0, days=0, read_from="three years")
    assert expiry_from(date(2016, 2, 3), p) == date(2019, 2, 3)
    assert expiry_from(date(2018, 2, 3), p) == date(2021, 2, 3)


# ===================================================== the served path =======

def _client(tmp_path):
    from fastapi.testclient import TestClient

    from tools.served import PASSWORD, served

    box = served(tmp_path / "store")
    advocate = box.enrol("adv_premise")
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
    c.box = box
    c.advocate = advocate
    return c


def _turn(c, message, matter_id=None):
    payload = {"message": message, "today": "2026-09-04"}
    if matter_id:
        payload["matter_id"] = matter_id
    else:
        payload["parties"] = {"A Traders": "client", "B Co": "adverse"}
        payload["release"] = {"scope": "recover"}
        payload["capacity"] = {
            "state": "not_in_doubt",
            "basis": "The advocate assessed that the client instructs directly.",
        }
    r = c.post("/api/turn", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_an_inferred_accrual_computes_conditional_and_enters_no_deadline(tmp_path):
    """BK-35-AC1. EVAL-015's shape: the date is conditional and the unreviewed
    premise is identified; it is never a deadline on the register."""
    c = _client(tmp_path)
    out = _turn(c, CONDITIONAL_BRIEF)
    matter_id = out["matter_id"]
    fired = {g["gate"]: g["state"] for g in out["metrics"]["gates_fired"]}
    assert fired.get("G-PREMISE") == "conditional", fired

    cover = c.get(f"/api/matters/{matter_id}/cover").json()
    prem = cover["premises"]
    assert prem["state"] == "conditional", prem
    (thread,) = prem["threads"]
    kinds = {p["kind"]: p for p in thread["premises"]}
    assert kinds["accrual_rule"]["basis"] == "inferred"
    assert kinds["applicable_law"]["basis"] == "attributed"
    assert kinds["accrual_rule"]["alternatives"], "no competing triggers shown"

    # NOT A DEADLINE. The register row has no date; the conditional figure is
    # carried apart, and the board never leads with it.
    m = c.box.application.store.load(matter_id)
    (d,) = m.threads[0].deadlines
    assert d.get("on") is None and d.get("conditional_on"), d
    board = c.get(f"/api/matters/{matter_id}").json()["threads"][0]
    assert board["next_deadline"] is None
    assert board["next_deadline_status"] == "not_computed"
    assert board["uncomputed_deadlines"][0]["conditional_on"] == d["conditional_on"]


def test_stating_the_premise_makes_the_next_computation_definitive(tmp_path):
    """EVAL-015 step 3: record an authorised premise and recalculate. The same
    arithmetic, now under a stated accrual, is a real deadline."""
    c = _client(tmp_path)
    out = _turn(c, CONDITIONAL_BRIEF)
    matter_id, version = out["matter_id"], out["matter_version"]
    thread_id = c.get(f"/api/matters/{matter_id}").json()["threads"][0]["thread_id"]

    r = c.post(f"/api/matters/{matter_id}/threads/{thread_id}/premises/accrual_rule",
               json={"statement": "time runs from 3 February 2018, the promised "
                                  "repayment date", "source": "the advocate",
                     "expected_version": version})
    assert r.status_code == 201, r.text
    assert r.json()["premise"]["by"] == c.advocate

    after = _turn(c, "And the limitation now?", matter_id)
    fired = {g["gate"]: g["state"] for g in after["metrics"]["gates_fired"]}
    assert fired.get("G-PREMISE") == "established", fired

    m = c.box.application.store.load(matter_id)
    (d,) = m.threads[0].deadlines
    assert d.get("on") is not None, "a stated premise did not yield a deadline"
    prem = {p["kind"]: p for p in
            c.get(f"/api/matters/{matter_id}/cover").json()["premises"]["threads"][0]["premises"]}
    assert prem["accrual_rule"]["basis"] == "stated"
    assert prem["accrual_rule"]["review_state"] == "reviewed"
    assert prem["accrual_rule"]["reviewed_by"] == c.advocate


def test_an_unknown_premise_kind_is_refused(tmp_path):
    c = _client(tmp_path)
    out = _turn(c, CONDITIONAL_BRIEF)
    matter_id, version = out["matter_id"], out["matter_version"]
    thread_id = c.get(f"/api/matters/{matter_id}").json()["threads"][0]["thread_id"]
    r = c.post(f"/api/matters/{matter_id}/threads/{thread_id}/premises/whimsy",
               json={"statement": "x", "expected_version": version})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_REQUEST"


def test_stating_a_premise_on_a_moved_matter_is_refused(tmp_path):
    c = _client(tmp_path)
    out = _turn(c, CONDITIONAL_BRIEF)
    matter_id = out["matter_id"]
    thread_id = c.get(f"/api/matters/{matter_id}").json()["threads"][0]["thread_id"]
    r = c.post(f"/api/matters/{matter_id}/threads/{thread_id}/premises/accrual_rule",
               json={"statement": "x", "expected_version": 0})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "STALE_VERSION"


def test_correct_arithmetic_never_certifies_the_law_the_disclosure_reaches_the_advocate(tmp_path):
    """G-PREMISE's served proof (BK-65-AC2): the CONDITIONAL disclosure is in
    the answer's own elements, not only in the metrics, and it names what must
    be established."""
    c = _client(tmp_path)
    # THE HTTP BODY, read directly, so the disclosure is proven on the bytes
    # the advocate receives (`resp.json`) and not on the metrics.
    resp = c.post("/api/turn", json={
        "message": CONDITIONAL_BRIEF, "today": "2026-09-04",
        "parties": {"A Traders": "client", "B Co": "adverse"},
        "release": {"scope": "recover"},
        "capacity": {
            "state": "not_in_doubt",
            "basis": "The advocate assessed that the client instructs directly.",
        }})
    assert resp.status_code == 200, resp.text
    texts = " ".join(e["text"] for e in resp.json()["elements"]).lower()
    assert "conditional" in texts and "not a deadline" in texts
    assert "confirm the accrual" in texts or "becomes one" in texts


# ================================================ BK-35-AC2: one version =====

def test_a_corrected_trigger_date_is_not_served_as_current(tmp_path):
    """BK-35-AC2's planted negative: change the trigger date after calculation.
    The correction supersedes the fact the limitation rests on, and P18's
    currency marks the deadline stale -- it cannot be served as current."""
    c = _client(tmp_path)
    # A curated cause so the first computation is a real (COMPUTED) deadline.
    out = _turn(c, "We act for the plaintiff at Hyderabad. Goods were supplied "
                   "against invoices on 14 March 2023 and were never paid for.")
    matter_id = out["matter_id"]
    board = c.get(f"/api/matters/{matter_id}").json()["threads"][0]
    assert board["next_deadline"], "no deadline to correct"

    casefile = c.get(f"/api/matters/{matter_id}/casefile").json()
    dated = min((e for e in casefile["live"] if "2023" in (e.get("date") or "")
                 or "2023" in e["statement"]), key=lambda e: len(e["statement"]))
    r = c.post(f"/api/matters/{matter_id}/facts/{dated['fact_id']}/corrections",
               json={"date": "2019-03-14", "reason": "the invoices are dated 2019",
                     "expected_version": casefile["version"]})
    assert r.status_code == 201, r.text
    stale = {s["name"] for s in r.json()["currency"]["stale"]}
    assert any("deadline" in n for n in stale), r.json()["currency"]
    board = c.get(f"/api/matters/{matter_id}").json()["threads"][0]
    assert board["next_deadline_status"] == "stale"
    assert board["next_deadline"] is None, "a corrected trigger is still served as current"


def test_the_cover_and_register_share_one_premise_version(tmp_path):
    """BK-35-AC2. The cover's premise digest and the register row's premise
    digest are the same, so the two cannot silently disagree about the law."""
    c = _client(tmp_path)
    out = _turn(c, "We act for the plaintiff at Hyderabad. Goods were supplied "
                   "against invoices on 14 March 2023 and were never paid for.")
    matter_id = out["matter_id"]
    cover = c.get(f"/api/matters/{matter_id}/cover").json()["premises"]
    assert cover["state"] in ("established", "conditional")
    (thread,) = cover["threads"]
    assert thread["consistent_with_register"] is True
    m = c.box.application.store.load(matter_id)
    digests = {d.get("premise_digest") for d in m.threads[0].deadlines}
    assert thread["digest"] in digests
