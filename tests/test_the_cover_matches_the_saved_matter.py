"""The cover must describe the same saved file as the list and thread board."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.store.file_store import FileMatterStore
from nm.core.deadlines import Deadline, DeadlineKind, read_matter
from nm.domain.commission import Commission
from nm.domain.commission import Deadline as InstructionDeadline
from nm.domain.engagement import Engagement
from nm.domain.matter import Basis, Matter, Posture, PostureConflict, Role, Thread
from nm.edge.api import application
from nm.edge.projections import board_projection, cover_projection, matter_list_projection
from tests.test_the_matter_cover_tells_ten_files_apart import BRIEF
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 12)


def _matter(*threads, **changes):
    return replace(Matter.create(advocate_id="adv", title="Synthetic file"),
                   threads=threads, **changes)


def _thread(role=Role.PLAINTIFF, **changes):
    return replace(Thread.create(label="Synthetic dispute"),
                   posture=Posture(role=role, basis=Basis.STATED), **changes)


def _deadline(thread, on):
    return Deadline(thread=thread.id, kind=DeadlineKind.OTHER, source="Synthetic saved order",
                    action="Review the recorded obligation", owner="Instructing advocate",
                    consequence="The recorded window may be lost", on=on)


def test_served_intake_turn_and_fresh_reader_keep_list_board_and_cover_consistent(
    client, tmp_path, monkeypatch,
):
    opened = client.post("/api/turn", json={
        "message": BRIEF, "today": TODAY.isoformat(), "turn_id": "cover-opening",
        "parties": {"Synthetic CedarClient": "client", "Synthetic CedarOpponent": "adverse"},
        "release": {"scope": "Review the supplied invoice"},
        "capacity": {"state": "not_in_doubt", "basis": "Advocate assessed capacity to instruct"},
    })
    assert opened.status_code == 200, opened.text
    assert opened.json()["input_admitted"] is True
    matter_id = opened.json()["matter_id"]
    continued = client.post("/api/turn", json={
        "matter_id": matter_id, "expected_version": opened.json()["matter_version"],
        "turn_id": "cover-followup", "message": "Retain the supplied invoice date.",
        "today": TODAY.isoformat(),
    })
    assert continued.status_code == 200, continued.text

    def views():
        listing = client.get("/api/matters").json()
        listed = next(row for row in listing["matters"] if row["matter_id"] == matter_id)
        board = client.get(f"/api/matters/{matter_id}").json()
        cover = client.get(f"/api/matters/{matter_id}/cover").json()
        assert cover["client"] == listed["client"] == "Synthetic CedarClient"
        assert cover["title"] == listed["matter"] == board["title"]
        assert cover["last_activity"] == listed["last_touched"] == TODAY.isoformat()
        assert cover["last_activity_state"] == "recorded"
        assert cover["posture"] == "plaintiff"
        assert {row["our_client_is"] for row in board["threads"]} == {"plaintiff"}
        case = cover["case_deadlines"]
        assert case["deadline_entries"], "the real turn must have produced a deadline"
        assert case["next_deadline"] == listed["next_deadline"]
        assert case["next_deadline_status"] == listed["next_deadline_status"]
        board_dates = {row["on"] for thread in board["threads"]
                       for row in (thread["passed_deadlines"] or [])}
        board_dates.update(thread["next_deadline"] for thread in board["threads"]
                           if thread["next_deadline"])
        assert {row["on"] for row in case["deadline_entries"] if row["on"]} == board_dates
        assert cover["stage"] != "advising"
        return listed, board, cover

    before = views()
    fresh = FileMatterStore(tmp_path, key=KEY)
    assert fresh.load(matter_id) is not None
    monkeypatch.setattr(application(), "store", fresh)
    assert views() == before


@pytest.mark.parametrize(("postures", "expected"), [
    ((Posture(),), "not_established"),
    ((Posture(role=Role.PLAINTIFF, basis=Basis.STATED),), "recorded"),
    ((Posture(role=Role.PLAINTIFF, basis=Basis.STATED), Posture()), "partial"),
    ((Posture(role=Role.PLAINTIFF, basis=Basis.STATED),
      Posture(role=Role.DEFENDANT, basis=Basis.STATED)), "mixed"),
    ((Posture(role=Role.PLAINTIFF, basis=Basis.STATED,
              conflicts=(PostureConflict(Role.PLAINTIFF, Role.DEFENDANT),)),), "conflicted"),
])
def test_the_cover_never_promotes_one_posture_to_the_whole_file(postures, expected):
    matter = _matter(*(replace(_thread(), posture=posture) for posture in postures))
    cover = cover_projection(matter, read_matter(matter), TODAY)
    assert cover["posture_state"] == expected
    assert len(cover["postures"]) == len(postures)
    assert [row["role"] for row in cover["postures"]] == [p.role.value for p in postures]
    if expected != "recorded":
        assert cover["posture"] != "plaintiff"
    if expected == "conflicted":
        assert cover["postures"][0]["conflicts"][0]["now_suggested"] == "defendant"


@pytest.mark.parametrize(("threads", "stage"), [
    ((), "opening"), ((Thread.create(label="Unassessed dispute"),), "blocked"),
    ((_thread(),), "work_in_progress"),
    ((_thread(deferred_reason="Awaiting the instructed document"),), "blocked"),
])
def test_stage_requires_real_persisted_evidence_and_never_thread_presence_as_advice(threads, stage):
    assert cover_projection(_matter(*threads), None, TODAY)["stage"] == stage


@pytest.mark.parametrize(("parties", "engagement", "client"), [
    ({}, None, None), ({}, Engagement(client="Legacy named client"), "Legacy named client"),
    ({"Intake named client": "client"}, Engagement(client="Legacy description"),
     "Intake named client"),
])
def test_cover_and_list_use_the_same_party_owner(parties, engagement, client):
    matter = _matter(intake_parties=parties, engagement=engagement)
    cover = cover_projection(matter, None, TODAY)
    listed = matter_list_projection([matter])["matters"][0]
    assert cover["client"] == client
    assert listed["client"] == (client or "not recorded")
    assert cover["last_activity"] is None


def test_passed_unknown_and_live_case_dates_remain_separate_from_instructions():
    thread = _thread(assessed=("deadlines",))
    held = (_deadline(thread, date(2026, 1, 1)), _deadline(thread, None),
            _deadline(thread, date(2026, 10, 1)))
    thread = replace(thread, deadlines=held)
    commission = Commission(deadline=InstructionDeadline.on_date(
        "2027-03-03", "Instruction milestone"))
    matter = _matter(thread, commission=commission)
    cover = cover_projection(matter, read_matter(matter), TODAY)
    case = cover["case_deadlines"]
    assert case["deadline_assessment"] == "assessed"
    assert case["next_deadline"] == "2026-10-01"
    assert [row["on"] for row in case["passed_deadlines"]] == ["2026-01-01"]
    assert len(case["uncomputed_deadlines"]) == 1
    assert {row["status"] for row in case["deadline_entries"]} == {"passed", "near", "not_computed"}
    assert cover["deadline_scope"] == "commission"
    assert cover["deadline_assessment"] == "assessed"
    assert "2027-03-03" in cover["deadline_said"]
    assert "2027-03-03" not in str(case)


def test_a_commission_date_cannot_establish_an_unassessed_case_register():
    matter = _matter(commission=Commission(
        deadline=InstructionDeadline.on_date("2027-03-03", "Instruction milestone")))
    cover = cover_projection(matter, read_matter(matter), TODAY)
    assert cover["deadline_assessment"] == "assessed"
    assert cover["case_deadlines"]["deadline_assessment"] == "not_assessed"
    assert cover["case_deadlines"]["next_deadline"] is None
    assert cover["case_deadlines"]["passed_deadlines"] is None


def test_partial_empty_and_malformed_registers_are_not_a_clean_empty_file():
    assessed = _thread(assessed=("deadlines",))
    untouched = _thread()
    matter = _matter(assessed, untouched)
    case = cover_projection(matter, read_matter(matter), TODAY)["case_deadlines"]
    assert case["deadline_assessment"] == "incomplete"
    assert case["deadline_unassessed"] == [untouched.id]
    corrupted = replace(assessed, deadlines=({"on": "2026-09-13"},))
    matter = _matter(corrupted, untouched)
    case = cover_projection(matter, read_matter(matter), TODAY)["case_deadlines"]
    assert case["deadline_assessment"] == "incomplete"
    assert case["deadline_unreadable"]
    assert case["next_deadline_status"] == "not_assessed"
    board = board_projection(matter, read_matter(matter), TODAY)
    assert board["threads"][0]["deadline_unreadable"] or board["threads"][1]["deadline_unreadable"]


def test_a_legacy_known_deadline_is_visible_without_manufacturing_assessment():
    thread = _thread()
    thread = replace(thread, deadlines=(_deadline(thread, date(2026, 1, 1)),))
    matter = _matter(thread)
    case = cover_projection(matter, read_matter(matter), TODAY)["case_deadlines"]
    assert case["deadline_assessment"] == "incomplete"
    assert case["next_deadline_status"] == "passed"
    assert case["next_deadline"] is None
    assert case["passed_deadlines"][0]["on"] == "2026-01-01"
    assert case["deadline_unassessed"] == [thread.id]
