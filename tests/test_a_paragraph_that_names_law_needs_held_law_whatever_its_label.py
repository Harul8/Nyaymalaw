"""A paragraph that names law needs held law, whatever its label; and no paragraph says NM did something (plan AN.51, pieces
51d and 51f; D198, D203, D251, D252; the review's F-04 and F-33; AN.48 register item 11).

The writer gives each paragraph a kind, and only account, law and analysis had to carry a source: "under section 17 time runs
from discovery" inside a next step passed every mechanical check. Code now reads the words as a paragraph is written. A
provision named by its number that no source the paragraph uses is or names is the paragraph's own fault - the writer gets
its second look, and what still stands is cut by its sentence; so is a statement that NM filed, saved or will do something.
An answer already saved is read back as it was saved. Invented matter and Act; scripted writer and reviewer.
"""
import json

import pytest

from nm.core_engine import answer_sections, law_named, response_writer
from tests.test_core_response_writer import two_disputes
from tests.test_only_the_failing_piece_is_looked_at_again_and_blocked import V14, Looking, answered, para, section_of

pytestmark = pytest.mark.class_a

HELD_17 = {"kind": "provision", "locator": "s. 17", "text": "17. Effect of fraud or mistake. Where the suit is for relief ..."}
HELD_SCHEDULE = {"kind": "provision", "locator": "Schedule 1 part 2",
                 "text": "54. For specific performance of a contract: three years."}
JUDGMENT = {"kind": "judgment", "locator": "para 12", "text": "The bar under Section 53A of the Act does not arise here."}
PAPER = {"kind": "document", "locator": "page 2", "text": "Notice under section 80 of the Code was issued on the date shown."}


# --- the two rules by themselves ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Under section 17 of the Imagined Act time runs from discovery.", [("17", "section 17")]),
    ("Sections 3, 5 and 9 apply.", [("3", "Sections 3"), ("5", "Sections 3, 5 and 9"), ("9", "Sections 3, 5 and 9")]),
    ("See S. 53A and s.65B.", [("53A", "S. 53A"), ("65B", "s.65B")]),
    ("Order XXXIX, rules 1 and 2 govern it.", [("XXXIX", "Order XXXIX, rules 1 and 2")]),
    ("Article 54 of the Schedule gives three years.", [("54", "Article 54")]),
    ("Paragraph 12 of the plaint, clause 5 of the agreement, 17 March 2019 and Survey No. 45 name no provision.", []),
])
def test_what_a_paragraph_names_is_read_by_the_owners_patterns(text, expected):
    assert law_named.named(text) == expected


@pytest.mark.parametrize("kind, text, used, missing", [
    ("next_step", "Apply under section 17 for more time.", [], ["section 17"]),
    ("next_step", "Apply under section 17 for more time.", [HELD_17], []),
    ("summary", "Section 17 extends time.", [PAPER], ["Section 17"]),
    ("analysis", "Article 54 gives three years.", [HELD_SCHEDULE], []),
    ("analysis", "Section 53A does not bar the claim.", [JUDGMENT], []),
    ("law", "Section 17 and section 21 both apply.", [HELD_17], ["section 21"]),
    ("account", "The notice was given under section 80.", [PAPER], []),
    ("analysis", "The notice was given under section 80.", [PAPER], ["section 80"]),
    ("question", "Was a notice under section 80 served?", [], []),
    ("limitation", "We do not hold the Act, so section 5 of it was not read.", [], []),
    ("next_step", "File the suit this month.", [], []),
])
def test_a_named_provision_needs_a_source_that_is_or_names_it(kind, text, used, missing):
    assert law_named.named_without_source(kind, text, used) == missing


@pytest.mark.parametrize("text", [
    "I have filed the caveat.", "We have now saved the correction.", "NM has updated the date in your matter.",
    "We will file the application tomorrow.", "Nyaymalaw recorded the change.", "I've corrected the figure.",
    "This is saved in your matter.", "Your correction has been recorded in the record.",
])
def test_a_statement_that_nm_did_something_is_found(text):
    assert law_named.effect_claimed(text)


@pytest.mark.parametrize("text", [
    "The plaintiff filed the suit in 2019.", "The suit was filed within time.", "The court recorded its finding.",
    "The deed was registered and the notice was served.", "File the application and serve a copy.",
    "The Bench said \"we have recorded our satisfaction\" and dismissed the appeal.",
    "The claim is saved by the proviso.", "Schedule I amended the rates.", "You should file a caveat.",
    "The seller has sent no reply.", "As we read the deed, the term is five years.",
])
def test_what_the_parties_and_the_courts_did_is_no_such_statement(text):
    assert law_named.effect_claimed(text) == []


# --- through the writing loop ------------------------------------------------------------------------------------------------

def texts_of(activity, part=0):
    piece = activity["sections"][part]
    draft = piece["trims"][-1]["draft"] if piece["trims"] else piece["reviewed"]["draft"]
    return [unit["text"] for unit in draft["units"]]


def rewriting(kind, text, place):
    return lambda dispute, round_, to_check: [{"paragraph": entry["paragraph"], "action": "rewrite",
                                               "rewritten": para(kind, text, place), "why": "Corrected.",
                                               "page_words": None, "question": None} for entry in to_check]


def section_with(dispute, kind, text, place="next_steps"):
    return [para("summary", f"In short for {dispute}.", "row_action"), para("limitation", "Nothing more is known.", "risks"),
            para(kind, text, place)]


def test_a_next_step_that_names_a_section_with_no_held_source_gets_its_second_look():
    model = Looking({"D1": lambda: section_with("D1", "next_step", "Apply under section 17 of the Imagined Act for more "
                                                                    "time. Then write to the other side.")},
                    rewriting("next_step", "Ask for more time. Then write to the other side.", "next_steps"))
    ctx, elements, activity = answered(model)
    (dispute, looked), = model.second_looks
    entry, = looked["to_check"]
    assert dispute == "D1" and entry["paragraph"] == "U3" and entry["words_at_fault"] == ["section 17"]
    assert "names section 17" in entry["why"][0] and "held passage" in entry["why"][0]
    assert texts_of(activity)[2] == "Ask for more time. Then write to the other side."
    assert "section 17" not in json.dumps(elements)


def test_what_still_names_it_after_the_second_looks_loses_only_that_sentence():
    said = "Apply under section 17 of the Imagined Act for more time. Then write to the other side."
    model = Looking({"D1": lambda: section_with("D1", "next_step", said)}, rewriting("next_step", said, "next_steps"))
    ctx, elements, activity = answered(model)
    assert activity["sections"][0]["fallback"] is None
    assert "Then write to the other side." in texts_of(activity)[2] and "section 17" not in json.dumps(elements)
    assert texts_of(activity)[:2] == ["In short for D1.", "Nothing more is known."]


def test_a_paragraph_saying_nm_filed_something_gets_its_second_look():
    model = Looking({"D1": lambda: section_with("D1", "next_step", "I have filed the caveat. Check the cause list.")},
                    rewriting("next_step", "File a caveat. Check the cause list.", "next_steps"))
    ctx, elements, activity = answered(model)
    (dispute, looked), = model.second_looks
    entry, = looked["to_check"]
    assert entry["words_at_fault"] == ["I have filed"] and entry["why"] == [response_writer.EFFECT_CLAIMED]
    assert texts_of(activity)[2] == "File a caveat. Check the cause list."


def test_a_question_or_a_limit_that_names_a_section_is_left_as_written():
    model = Looking({"D1": lambda: [para("summary", "In short for D1.", "row_action"),
                                    para("limitation", "We do not hold the Imagined Act, so section 17 of it was not read.", "risks"),
                                    para("question", "Was a notice under section 80 served?", "ask"),
                                    para("next_step", "Take the next step for D1.", "next_steps")]})
    ctx, elements, activity = answered(model)
    assert model.second_looks == [] and len(texts_of(activity)) == 4


def test_an_answer_saved_before_the_rule_is_read_back_as_it_was_saved():
    """Admission without the collecting of faults is how a saved draft is read back: the rule made after it does not refuse it."""
    ctx, record, sources = two_disputes()
    dispute = response_writer.parts(record)[1]["dispute_id"]
    proposal = {"units": section_with("D1", "next_step", "Apply under section 17 of the Imagined Act for more time."),
                "checklists": [{"checklist": [], "time_limit_ids": [], "by_when": None}]}
    shape = {"context": ctx, "sources": sources, "contract": V14, "parts": [{"dispute_id": dispute, "units": 3}], "section": 1}
    saved = response_writer.accept(proposal, shape["context"], shape["sources"], contract=V14, parts=shape["parts"], section=1)
    assert [unit["text"] for unit in saved["units"]][2].startswith("Apply under section 17")
    with pytest.raises(response_writer.UnitFaults) as written:
        response_writer.accept(proposal, shape["context"], shape["sources"], contract=V14, parts=shape["parts"], section=1,
                               faults=[], limits={})
    assert [(fault["position"], fault["words"]) for fault in written.value.faults] == [(3, ["section 17"])]
    assert answer_sections.LOOKS  # the loop that gives such a fault its second look is the writer v14 one, unchanged
