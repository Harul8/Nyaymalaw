"""P24 / BK-54-AC3 and BK-91-AC3 -- the adaptive briefing, and C1 NEVER[4].

C1's fifth NEVER clause had no witness (TRACE-C1):

    Never equate completing a conversation turn with completing intake. Never
    promote an unknown answer to no, re-ask a confirmed fact without a new
    reason, or loop indefinitely on unavailable material.

This file closes it. Readiness is derived from the OPEN GAPS, not from a turn
finishing, so a completed turn does not complete intake while a controlling gap
remains. A need the advocate cannot obtain is PAUSED with a resume trigger --
not answered, not re-asked -- so the loop on unavailable material stops with a
stop-or-resume decision. The adaptive lead (P46) chooses the next move from the
LIVE gaps, so the briefing is not a fixed questionnaire.

`model_eval` and `counsel_review` (BK-54-AC2/AC3, BK-91-AC3) are NOT run here.
"""
from __future__ import annotations

import pytest
from nm.core import briefing
from nm.domain.lead import Action
from nm.domain.matter import Matter
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a


# ============================ C1 NEVER[4], witnessed ======================

@refuses("C1", 4)
def test_a_completed_turn_does_not_complete_intake_and_unavailable_is_not_looped():
    """THE WITNESS for C1's fifth NEVER clause.

    A controlling gap open -> intake is NOT ready however the turn finished, and
    completion is refused with the gap named. The same gap marked unavailable ->
    it is paused (dropped from the live gaps, so not re-asked) and readiness is
    `blocked` with a stop/resume decision owed, never `ready`. An unavailable
    answer is never promoted to a settled one: the gap stays uncompleted."""
    gaps = ("the date of delivery", "the delivery receipt")

    # A turn can finish cleanly and intake is still not complete.
    open_state = briefing.readiness(gaps, frozenset())
    assert open_state.state == "open"
    assert briefing.refuse_completion(gaps, frozenset())

    # Mark one unavailable: it is not in the live gaps (not re-asked)...
    paused = frozenset({"the delivery receipt"})
    assert "the delivery receipt" not in briefing.live_gaps(gaps, paused)
    # ...but intake is still open on the OTHER gap.
    assert briefing.readiness(gaps, paused).state == "open"

    # When every remaining gap is unavailable, readiness is BLOCKED (a
    # stop/resume decision) -- not ready, and not looping.
    all_paused = frozenset(gaps)
    blocked = briefing.readiness(gaps, all_paused)
    assert blocked.state == "blocked"
    assert "stop or resume" in blocked.why
    assert briefing.refuse_completion(gaps, all_paused)
    assert briefing.live_gaps(gaps, all_paused) == ()


def test_no_gaps_is_ready_and_completion_is_not_refused():
    assert briefing.readiness((), frozenset()).state == "ready"
    assert briefing.refuse_completion((), frozenset()) == ""


def test_the_next_move_comes_from_the_lead_and_skips_paused_needs():
    """BK-91-AC3. The next briefing action is the adaptive lead's, chosen from
    the LIVE gaps -- an open gap retrieves, and when every gap is paused nothing
    is proposed to re-ask (it stops)."""
    gaps = ("the date of delivery",)
    assert briefing.next_step(gaps, frozenset()).action is Action.RETRIEVE
    # every gap paused -> the lead stops rather than re-asking.
    assert briefing.next_step(gaps, frozenset(gaps)).action is Action.STOP


# ============================ the matter ledger ===========================

def _matter(**kw):
    return Matter(id="m1", advocate_id="adv", title="t", **kw)


def test_pause_and_resume_survive_and_do_not_answer():
    """A paused need is recorded with a resume trigger, is NOT answered, and is
    cleared by resume. Re-pausing the same need updates rather than duplicates."""
    m = _matter().pause_need("the delivery receipt", "the receipt is located",
                             by="adv", at="2026-09-13")
    assert m.paused_need_texts == frozenset({"the delivery receipt"})
    (row,) = m.paused_needs
    assert row["resume_when"] == "the receipt is located" and row["by"] == "adv"

    again = m.pause_need("the delivery receipt", "the file is found")
    assert len(again.paused_needs) == 1  # updated, not duplicated
    assert again.paused_needs[0]["resume_when"] == "the file is found"

    resumed = again.resume_need("the delivery receipt")
    assert resumed.paused_need_texts == frozenset()


def test_paused_needs_round_trip_through_the_store(tmp_path):
    from nm.adapters.store.file_store import FileMatterStore

    from tests.test_turn_contract import KEY

    store = FileMatterStore(tmp_path, key=KEY)
    m = Matter(id="mat_paused", advocate_id="adv", title="Paused",
               paused_needs=({"need": "the receipt", "resume_when": "found",
                              "by": "adv", "at": "2026-09-13"},))
    store.commit(m, expected_version=0)
    back = store.load("mat_paused")
    assert back is not None
    assert back.paused_need_texts == frozenset({"the receipt"})


# ============================ served through the routes ===================

def _client(tmp_path):
    from fastapi.testclient import TestClient

    from assurance.journeys.served import PASSWORD, served

    box = served(tmp_path / "store")
    advocate = box.enrol("adv_brief")
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
    return c


def _open_matter(c):
    r = c.post("/api/turn", json={
        "message": "We act for the plaintiff. Goods supplied on 14 March 2023, "
                   "unpaid.", "today": "2026-09-04",
        "parties": {"A Traders": "client", "B Co": "adverse"},
        "release": {"scope": "recover"},
        "capacity": {
            "state": "not_in_doubt",
            "basis": "The advocate assessed that the client instructs directly.",
        }})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"], r.json()["matter_version"], r.json()


def test_the_served_turn_carries_an_intake_readiness_block(tmp_path):
    """BK-91-AC3. Every served turn reports intake readiness distinct from the
    turn having completed."""
    c = _client(tmp_path)
    _mid, _ver, body = _open_matter(c)
    assert "briefing" in body
    assert body["briefing"]["state"] in ("ready", "open", "blocked",
                                          "not_assessed")


def test_marking_a_need_unavailable_pauses_it_and_resume_reopens_it(tmp_path):
    """BK-54-AC3, served. The advocate marks a need unavailable: it is paused
    with a resume trigger and is not answered. Resume reopens it. A stale version
    is refused -- accepted input survives without duplication."""
    c = _client(tmp_path)
    mid, ver, _ = _open_matter(c)

    r = c.post(f"/api/matters/{mid}/briefing/unavailable", json={
        "need": "the original delivery receipt",
        "resume_when": "the receipt is located", "expected_version": ver})
    assert r.status_code == 201, r.text
    assert r.json()["state"] == "paused"
    new_ver = r.json()["version"]

    m = c.box.application.store.load(mid)
    assert "the original delivery receipt" in m.paused_need_texts
    # It is NOT recorded as an answered question -- intake stays incomplete on it.
    assert not any(not q.open for q in m.asked
                   if "receipt" in q.text.lower())

    # A stale version is refused (no duplicate pause).
    stale = c.post(f"/api/matters/{mid}/briefing/unavailable", json={
        "need": "x", "expected_version": ver})
    assert stale.status_code == 409

    resumed = c.post(f"/api/matters/{mid}/briefing/resume", json={
        "need": "the original delivery receipt", "expected_version": new_ver})
    assert resumed.status_code == 201
    m2 = c.box.application.store.load(mid)
    assert m2.paused_need_texts == frozenset()


def test_a_paused_gap_stops_the_loop_and_blocks_completion(tmp_path):
    """BK-54-AC3 end to end. A matter with an open gap, then that gap marked
    unavailable: the served briefing drops it from the live needs (not re-asked)
    and reports it paused with completion refused -- the loop stops without
    claiming intake done."""
    from dataclasses import replace

    from nm.core.gaps import Gap, GapKind

    c = _client(tmp_path)
    mid, ver, _ = _open_matter(c)
    store = c.box.application.store
    m = store.load(mid)
    thread = m.threads[0]
    gap = Gap(what="the original delivery receipt",
              blocks="proving delivery", thread=thread.id,
              kind=GapKind.INFORMATION_VALUE)
    m = m.with_thread(replace(thread, gaps=(gap,)))
    committed = store.commit(m, expected_version=ver)

    # The served briefing block is the one owner (`briefing.block`), the same
    # projection the served turn and the byte boundary use.
    before = briefing.block(store.load(mid))
    assert before["state"] == "open"
    assert "the original delivery receipt" in before["open_needs"]

    paused = store.load(mid).pause_need("the original delivery receipt", "found")
    store.commit(paused, expected_version=committed.version)
    after = briefing.block(store.load(mid))
    assert after["state"] == "blocked"
    assert after["open_needs"] == []
    assert any(p["need"] == "the original delivery receipt"
               for p in after["paused"])
    assert after["intake_complete_refused"]
