"""Where blocking cuts statements out of a paragraph, the paragraph may be written again around what remains, once in a piece (plan
AN.33, D18 and D25; research v14; piece 33l).

The owner, 1 Nov 2026: "let model decide whether this is a clerical error or a genuine failed test in which can model can decide to drop
only that failed portion". When a piece's second looks are spent and code blocks what still fails, only the sentences at fault go;
but what remains of a paragraph may then lean on what went, or have lost the action it asked for. So, once in a piece, one more second
look is shown each paragraph a cut left, as it now stands, with what went and why: it writes the paragraph again around what remains -
adding nothing the cut statements said - keeps it as it stands, or takes it out. Code admits what it gives as any paragraph, and the
review judges it again. The papers are synthetic.
"""
import json

import pytest

from nm.core_engine import answer_sections, response_writer
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import _result
from tests.test_the_rounds_of_repair_are_set_up_front_from_the_matter import answer

pytestmark = pytest.mark.class_a

FIRST = "In short, the claim was allowed."
REST = "File the appeal within thirty days."


class Cutting:
    """Writes one section whose summary holds a statement every review finds misleading; each second look at it writes it again,
    still misleading; the second look at a paragraph a cut left answers as `mending` says. Keeps every second look."""

    knows_second_look = True

    def __init__(self, mending, faulty=(FIRST,)):
        self.mending, self.faulty, self.looks, self.mends, self.reviews = mending, faulty, [], [], 0

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        if prompt.operation == "core_response_writer":
            units = [{"kind": "summary", "text": f"{FIRST} {REST}", "uses": [], "place": "row_action"},
                     {"kind": "next_step", "text": "Check the records.", "uses": [], "place": "next_steps"}]
            return _result({"units": units, "checklist": [], "time_limit_ids": [], "by_when": None}, tier)
        if prompt.operation == "core_response_review":
            self.reviews += 1
            misleading = [{"kind": "unsupported", "where": [unit["id"]], "evidence": [], "why": "Not borne out.", "words": [words]}
                          for unit in payload["complete_draft_proposal"]["units"] for words in self.faulty if words in unit["text"]]
            return _result({"misleading": misleading, "could_be_better": [], "keep_shown": [], "missing": []}, tier)
        if prompt.operation == "core_response_repair":
            cut = [entry for entry in payload["to_check"] if response_writer.MEND_WHY in entry["why"]]
            (self.mends if cut else self.looks).append(payload)
            repairs = []
            for entry in payload["to_check"]:
                if not cut:
                    repairs.append({"paragraph": entry["paragraph"], "action": "rewrite", "why": "Written again.", "page_words": None,
                                    "question": None, "rewritten": {"kind": "summary", "text": f"{FIRST} {REST}", "uses": [],
                                                                    "place": "row_action"}})
                else:
                    repairs.append(self.mending(entry, payload))
            return _result({"repairs": repairs}, tier)
        raise AssertionError(prompt.operation)


def rewrite(entry, payload):
    return {"paragraph": entry["paragraph"], "action": "rewrite", "why": "It leaned on what went.", "page_words": None,
            "question": None, "rewritten": {"kind": "summary", "text": "File the appeal within thirty days of the order.", "uses": [],
                                            "place": "row_action"}}


def texts(section):
    piece = answer_sections.shown(section)
    return [unit["text"] for unit in piece["draft"]["units"]]


def test_a_paragraph_a_cut_left_is_shown_as_it_stands_and_written_again_around_what_remains():
    model = Cutting(rewrite)
    ctx, sections, elements, activity = answer(model)          # the turn is replayed as saved inside
    (section,) = sections
    assert len(model.looks) == answer_sections.SECTION_ALLOWANCE and len(model.mends) == 1
    (mend,) = model.mends
    shown = {paragraph["id"]: paragraph["text"] for paragraph in mend["your_paragraphs"]}
    assert shown["U1"] == REST, "the paragraph as the cut left it"
    (entry,) = mend["to_check"]
    assert [words.strip() for words in entry["words_at_fault"]] == [FIRST] and entry["why"] == [response_writer.MEND_WHY]
    assert texts(section) == ["File the appeal within thirty days of the order.", "Check the records."]
    looks = section[answer_sections.LOOKS]
    assert len(looks) == answer_sections.SECTION_ALLOWANCE + 1 and looks[-1]["faults"][0]["kind"] == "cut"
    assert looks[-1]["decisions"][0]["action"] == "rewrite"


def test_a_paragraph_that_reads_whole_as_cut_is_kept_and_one_with_nothing_worth_keeping_goes():
    keep = Cutting(lambda entry, payload: {"paragraph": entry["paragraph"], "action": "same_thing", "why": "It reads whole.",
                                           "page_words": REST, "question": None, "rewritten": None})
    (kept,) = answer(keep)[1]
    assert texts(kept) == [REST, "Check the records."]
    drop = Cutting(lambda entry, payload: {"paragraph": entry["paragraph"], "action": "withdraw", "why": "Nothing remains.",
                                           "page_words": None, "question": None, "rewritten": None})
    (dropped,) = answer(drop)[1]
    assert texts(dropped) == ["Check the records."]


def test_a_piece_is_mended_once_and_what_still_fails_after_is_cut_as_before():
    model = Cutting(rewrite, faulty=(FIRST, "of the order"))
    ctx, sections, elements, activity = answer(model)
    (section,) = sections
    assert len(model.mends) == 1, "never a second mend in one piece"
    assert texts(section) == ["Check the records."], "the mended paragraph, found at fault again, is blocked as before"


def test_the_mend_has_an_allowance_of_its_own_that_the_rounds_and_a_saved_answer_count():
    assert answer_sections.MENDS == 1
    assert answer_sections.allowances(1) == (2, 1)
    from tests.test_the_rounds_of_repair_are_set_up_front_from_the_matter import ONE, with_items
    from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import matter
    ctx, record, sources = matter()
    many = with_items(record, ctx, 400)
    found = {pieces: answer_sections.rounds(many, ONE * pieces, ctx) for pieces in (3, 4, 5, 6)}
    assert found == {3: 4, 4: 3, 5: 2, 6: 1}
    for pieces, allowed in found.items():
        assert pieces * (sum(answer_sections.allowances(allowed)) + answer_sections.MENDS) <= answer_sections.ALLOWANCE


def test_a_mend_that_says_again_what_was_cut_is_set_aside_and_the_paragraph_stays_as_cut():
    back = Cutting(lambda entry, payload: {"paragraph": entry["paragraph"], "action": "rewrite", "why": "Restored.",
                                           "page_words": None, "question": None,
                                           "rewritten": {"kind": "summary", "text": f"{FIRST} {REST}", "uses": [],
                                                         "place": "row_action"}})
    ctx, sections, elements, activity = answer(back)
    (section,) = sections
    assert texts(section) == [REST, "Check the records."]
    mend = section[answer_sections.LOOKS][-1]
    assert mend["decisions"] == [] and mend["set_aside"] == [{"repair": 1,
                                                              "why": "U1: written again, it says again what was taken out"}]
