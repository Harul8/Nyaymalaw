"""A question not yet searched is not a failed search (plan AN.48, D297; the owner: "yes", 18 Nov 2026).

A matter worked step by step stops after its understanding for the go-ahead to research. Its record lists each question of a dispute
not yet researched as a failure whose reason is that the answer stopped before it (research.assemble's `unfinished`), and the board
said "search failed" for every one, and that the research "did not finish" - though no search had been asked for (the live run of
18 Nov 2026, D296). A question the answer stopped before is now not researched, and a dispute none of whose questions has been
searched says that its law has not been researched yet; a search that was made and failed still says so.
"""
from nm.core_engine import matter_board, research
from tests.test_the_board_says_what_has_not_been_assessed import SOUND, dispute, row

STOPPED_BEFORE = {"stage": "search", "reason": research.UNFINISHED}
FAILED = {"stage": "search", "reason": "Held-law search is not configured"}
NOT_YET = "NM has not researched the law for this dispute yet, so what the law requires of it has not been assessed."


def board_of(failures, researched=()):
    made = row([dispute(1, len(failures))], [SOUND], researched=researched)
    made["activities"]["research"]["failures"] = {f"w-D1Q{n}": failure for n, failure in enumerate(failures, 1)}
    return matter_board.board([made])["disputes"][0]


def test_questions_the_answer_stopped_before_are_not_researched_and_the_law_not_researched_yet():
    shown = board_of([STOPPED_BEFORE, STOPPED_BEFORE])
    assert [question["status"] for question in shown["questions"]] == ["not_researched", "not_researched"]
    assert shown["law"] == {"state": "not_assessed", "why": NOT_YET}


def test_a_search_that_was_made_and_failed_still_says_so():
    shown = board_of([FAILED, STOPPED_BEFORE])
    assert [question["status"] for question in shown["questions"]] == ["search_failed", "not_researched"]
    assert shown["law"]["why"].startswith("NM's research of the law for this dispute did not finish")


def test_a_failure_saved_without_its_reason_is_a_failed_search_as_before():
    shown = board_of([{}])
    assert shown["questions"][0]["status"] == "search_failed"


def test_a_researched_question_beside_one_not_yet_searched_leaves_the_dispute_researched():
    made = row([dispute(1, 2)], [SOUND], researched=["D1Q1"])
    made["activities"]["research"]["failures"] = {"w-D1Q2": STOPPED_BEFORE}
    shown = matter_board.board([made])["disputes"][0]
    assert [question["status"] for question in shown["questions"]] == ["researched", "not_researched"]
    assert shown["law"] == {"state": "researched", "why": ""}


def test_the_stopped_turns_record_is_the_shape_this_reads():
    # What research.assemble writes for a dispute with no research yet (a turn stopped before it): read from its own source, so
    # that a change of the reason's words or shape there fails here.
    import inspect
    source = inspect.getsource(research.assemble)
    assert '{"stage": "search", "reason": unfinished}' in source
