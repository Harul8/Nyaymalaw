"""The board says what has not been assessed (plan AN.27, P6; invariant I3).

A dispute NM had set no legal questions for showed "0 legal questions", which reads as though the law had been looked at and nothing was
required. The board now says, for each dispute, whether the law has been assessed - by a researched answer's checklist, researched
without one (an earlier conversation's), or not at all, in plain words - and whether NM's own check of its understanding was satisfied.
"""
import pytest

from nm.core_engine import matter_board, research

pytestmark = pytest.mark.class_a

SOUND = {"code_problems": [], "verdict": "sound", "problems": []}
REVISE = {"code_problems": [], "verdict": "revise", "problems": [
    {"problem": "The understanding does not set out the chronology.", "fix": "Add it."},
    {"problem": "A fact is stated more strongly than the page.", "fix": "Correct it."}]}


def dispute(number, questions=0):
    return {"id": f"D{number}", "name": f"Dispute {number}", "between": ["a", "b"], "fact_ids": ["F1"],
            "legal_questions": [{"id": f"D{number}Q{n}", "question": f"Question {n}?", "why_needed": "It decides the advice.",
                                 "open_alternative": "", "law_to_check": []} for n in range(1, questions + 1)],
            "rights_at_stake": [], "relief_sought": [], "missing_facts": ["The deed."]}


def row(disputes, rounds, *, researched=(), failed=(), checklists=()):
    understanding = {"summary": "s", "asked": [], "ruled_out": [], "parties": [], "related_points": [],
                     "facts": [{"id": "F1", "fact": "A fact.", "certainty": "reported", "advocate_words": "a fact"}],
                     "disputes": disputes}
    work = [{"id": f"w-{q['id']}", "question_id": q["id"]} for d in disputes for q in d["legal_questions"]]
    record = {"contract": research.CONTRACT, "plan": {"proposal": {"understanding": understanding, "review_rounds": rounds},
                                                      "work": work, "issues": []},
              "searches": {f"w-{q}": {} for q in researched}, "failures": {f"w-{q}": {} for q in failed}}
    listed = [{"id": f"D{n}", "name": f"Dispute {n}", "answered_in": "t1", "time_limits": [],
               "items": [{"id": "K1", "need": "The signed deed", "group": "needed", "status": "in_hand", "evidence": None,
                          "asked_in": None, "noted_in": "t1", "law": {"title": "An Act", "locator": "s 1", "words": "w"}}]}
              for n in checklists]
    return {"turn_id": "t1", "message": "m", "documents": [], "response": {"at": "2026-10-28T10:00:00+00:00"},
            "records": {"checklist": {"contract": "core_checklist_v2", "turn_id": "t1", "disputes": listed}} if listed else {},
            "activities": {"research": record}}


def board(*args, **kw):
    return matter_board.board([row(*args, **kw)])


def test_a_dispute_with_no_legal_questions_says_the_law_has_not_been_researched_for_it():
    shown = board([dispute(1)], [REVISE])
    law = shown["disputes"][0]["law"]
    assert law["state"] == "not_assessed"
    assert law["why"] == "NM has not researched the law for this dispute, so what the law requires of it has not been assessed."


def test_a_dispute_whose_research_did_not_finish_says_so():
    shown = board([dispute(1, 2)], [SOUND], failed=["D1Q1"])
    assert shown["disputes"][0]["law"] == {"state": "not_assessed", "why": (
        "NM's research of the law for this dispute did not finish, so what the law requires of it has not been assessed.")}
    assert board([dispute(1, 1)], [SOUND])["disputes"][0]["law"]["state"] == "not_assessed", "a question never searched"


def test_a_dispute_with_a_checklist_from_a_researched_answer_is_assessed():
    shown = board([dispute(1, 1), dispute(2)], [SOUND], researched=["D1Q1"], checklists=[1])
    by_name = {d["name"]: d for d in shown["disputes"]}
    assert by_name["Dispute 1"]["law"] == {"state": "assessed", "why": ""} and "checklist" in by_name["Dispute 1"]
    assert by_name["Dispute 2"]["law"]["state"] == "not_assessed" and "checklist" not in by_name["Dispute 2"]


def test_a_checklist_saved_for_another_dispute_of_the_same_id_is_not_this_disputes():
    renamed = dispute(1, 1)
    renamed["name"] = "A dispute NM now sets out differently"
    shown = board([renamed], [SOUND], researched=["D1Q1"], checklists=[1])   # the checklist was saved under "Dispute 1"
    d = shown["disputes"][0]
    assert "checklist" not in d and d["law"] == {"state": "researched", "why": ""}


def test_a_researched_dispute_of_an_earlier_conversation_without_a_checklist_is_researched_not_assessed():
    law = board([dispute(1, 2)], [SOUND], researched=["D1Q1"])["disputes"][0]["law"]
    assert law == {"state": "researched", "why": ""}


def test_the_board_says_its_understanding_was_not_confirmed_where_the_last_check_still_said_revise():
    shown = board([dispute(1)], [SOUND, REVISE])
    assert shown["understanding"] == {"confirmed": False, "open_points": [
        "The understanding does not set out the chronology.", "A fact is stated more strongly than the page."]}


def test_a_sound_last_check_with_no_mechanical_problem_confirms_it_and_names_no_points():
    assert board([dispute(1)], [REVISE, SOUND])["understanding"] == {"confirmed": True, "open_points": []}


def test_a_mechanical_problem_left_after_a_sound_check_leaves_it_unconfirmed_and_names_code_s_point():
    # Plan AN.28, B11 (owner, 31 Oct 2026): "not confirmed" never stands without its reason; code's own point is named.
    left = {"code_problems": [{"problem": "Fact F1: the quoted words do not appear", "fix": "Quote them."}],
            "verdict": "sound", "problems": []}
    assert board([dispute(1)], [left])["understanding"] == {
        "confirmed": False, "open_points": ["Fact F1: the quoted words do not appear"]}


@pytest.mark.parametrize("rounds", [[], [{"code_problems": [], "verdict": "unavailable", "problems": []}]])
def test_a_check_that_never_ran_or_could_not_is_not_a_confirmation(rounds):
    assert board([dispute(1)], rounds)["understanding"] == {"confirmed": False, "open_points": []}


def test_the_points_are_at_most_five_and_each_is_cut():
    long = {"code_problems": [], "verdict": "revise",
            "problems": [{"problem": "x" * 700, "fix": "f"}] + [{"problem": f"Point {n}.", "fix": "f"} for n in range(7)]}
    points = board([dispute(1)], [long])["understanding"]["open_points"]
    assert len(points) == 5 and points[0] == "x" * 600 + "..." and points[1] == "Point 0."


def test_what_the_board_showed_before_is_unchanged():
    shown = board([dispute(1, 1)], [SOUND], researched=["D1Q1"])
    d = shown["disputes"][0]
    assert d["questions"] == [{"question": "Question 1?", "why": "It decides the advice.", "open": "", "status": "researched"}]
    assert d["still_needed"] == ["The deed."] and d["fact_ids"] == ["F1"] and d["between"] == ["a", "b"]
    assert {"id", "name", "between", "fact_ids", "questions", "still_needed", "rights_at_stake", "relief_sought", "law"} <= set(d)
