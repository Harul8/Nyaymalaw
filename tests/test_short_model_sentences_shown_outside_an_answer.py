"""One door for the short model sentences NM shows outside an answer (plan AN.51, piece 51b; D196; the review's F-09).

Two small steps return a sentence to the advocate - how NM took a follow-up, and how it took a message sent while a matter
waits - and each was admitted as any text that was not empty, then shown where the advocate expects NM's own status. Code's own
fixed sentence for the kind now always stands first; a model's wording is shown only after it, marked as NM's reading, and only
where it carries no link, asks for no secret, claims nothing was, is being or will be done, and is no longer than the cap. No
model is called: the judgements are invented.
"""
from __future__ import annotations

import pytest

from nm.core_engine import follow_up, message_reader, shown_words

pytestmark = pytest.mark.class_a

FIXED = "Taken as new information for the matter."


@pytest.mark.parametrize("words", [
    "I have saved the correction. See https://example.test/next for the rest.",
    "See www.example.test for how this was taken.",
    "I have corrected the date and re-worked the limitation period.",
    "I've updated the chronology with the new date.",
    "NM has now recorded your correction.",
    "We saved this to the matter.",
    "The date has been changed to the third of March.",
    "The chronology is now updated.",
    "Your correction was applied.",
    "I will re-work the limitation period with this date.",
    "NM will update the board.",
    "To go on, send me your password.",
    "Reply with the one-time code you were sent.",
])
def test_wording_with_a_link_a_request_for_a_secret_or_a_claim_of_something_done_is_left_out_whole(words):
    assert shown_words.reading(words) == ""
    assert shown_words.said(FIXED, words) == FIXED, "code's fixed sentence stands alone"


@pytest.mark.parametrize("words", [
    "You are telling us the notice reached your client on the third of March, not the first.",
    "You want the research to begin on the first dispute only",
    "You are asking whether the suit is still within time.",
    "This reads as a correction to the date of the agreement.",
])
def test_wording_that_only_says_how_the_message_was_read_is_shown_after_codes_sentence_and_marked(words):
    shown = shown_words.said(FIXED, words)
    assert shown.startswith(FIXED + " NM's reading: "), "code's sentence first, the model's wording marked"
    assert words.rstrip(".") in shown and shown[-1] in ".?!"


@pytest.mark.parametrize("words", [None, 7, ["a"], "", "   \n "])
def test_no_wording_leaves_codes_sentence_alone(words):
    assert shown_words.said(FIXED, words) == FIXED


def test_a_long_reading_is_cut_at_a_word_and_several_lines_are_one():
    long = "You are telling us " + "the notice was late and " * 30
    shown = shown_words.reading(long)
    assert len(shown) <= shown_words.LONGEST + 1 and shown.endswith("…") and not shown[:-1].endswith(" ")
    assert shown_words.reading("You ask\n\n  whether   it is in time?") == "You ask whether it is in time?"


def test_the_question_put_where_nm_could_not_tell_is_the_models_only_where_it_may_be_shown_and_is_a_question():
    fixed = message_reader.ASK
    assert shown_words.asked(fixed, "Do you mean the first notice or the second?") == "Do you mean the first notice or the second?"
    assert shown_words.asked(fixed, "I have noted both notices.") == fixed
    assert shown_words.asked(fixed, "Tell me at https://example.test which notice?") == fixed
    assert shown_words.asked(fixed, "It is about the notice.") == fixed, "not a question"
    assert shown_words.asked(fixed, None) == fixed


def test_what_code_says_comes_first_and_an_admitted_reading_is_marked_after_it():
    assert shown_words.after("NM read the whole matter again.", "") == "NM read the whole matter again."
    assert shown_words.after("NM read the whole matter again.", "You add a date.") == (
        "NM read the whole matter again. NM's reading: You add a date.")


# ---- the follow-up reader's admission (the review's smallest failing test) ----

CLAIM = "I have saved the correction. See https://example.test/saved for what changed."
BEFORE = {"plan": {"proposal": {"understanding": {"disputes": [], "facts": []}, "chronology": []}}}


@pytest.mark.parametrize("kind", follow_up.KINDS)
def test_a_follow_ups_sentence_claiming_a_saved_correction_with_a_link_is_admitted_as_codes_fixed_sentence(kind):
    judgement, why = follow_up.admitted({"kind": kind, "new_questions": [], "said": CLAIM}, BEFORE)
    assert why is None and judgement["said"] == follow_up.SAID[kind] and judgement["reading"] == ""


def test_a_follow_ups_own_wording_is_kept_apart_from_codes_sentence_as_its_reading():
    judgement, _ = follow_up.admitted({"kind": "same_matter", "new_questions": [],
                                       "said": " You are asking whether  the suit is still within time. "}, BEFORE)
    assert judgement["said"] == follow_up.SAID["same_matter"], "the status is code's"
    assert judgement["reading"] == "You are asking whether the suit is still within time."
