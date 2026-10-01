"""A read points at the advocate's words by sentence NUMBER, never by retyping them.

LB-76 change 2 (owner, 30 September 2026). On the Farah Begum brief the cause read
named the right cause for all three disputes and every one was refused: the
retyped quote joined sentences that were not next to each other, and once garbled
the rupee sign. The same check dropped four sound issues. A number cannot drift;
a number that is not one of the advocate's sentences settles nothing.

THE RULES:
1. The prompt shows the advocate's sentences numbered, and the answer is read back
   through the SAME numbering -- one value, `Quotable`, for both.
2. Sentences named out of order, or far apart, are read back as the advocate wrote
   them.
3. A number that is not theirs, or none at all, is refused.
"""
from __future__ import annotations

import pytest

from nm.Archives.legal_brain.common.quotable_contracts import Quotable
from nm.Archives.legal_brain.reason import cause, issues

pytestmark = pytest.mark.class_a

SAID = Quotable(
    turn=("We act for Farah Begum. She owns a house and plot under a registered conveyance. "
          "There are several problems. First, Raghav Reddy has used a three-foot strip "
          "since June 2019. Yesterday, 27 September 2026, he built a wall enclosing it."),
    file="Imran agreed to sell her a plot for ₹40 lakh.",
    context="Active working dispute: the strip.")


def test_the_prompt_numbers_the_sentences_the_answer_is_read_back_through():
    shown = cause.build_prompt(SAID).user
    for number, sentence in SAID.sentences.items():
        assert f"{number}: {sentence}" in shown
    assert "Active working dispute" in shown and "S7:" not in shown.split("FOR CONTEXT")[1]
    enum = cause.schema_for(SAID)["properties"]["sentences"]["items"]["enum"]
    assert enum == list(SAID.sentences)


def test_sentences_named_apart_are_read_back_as_written():
    read = cause.interpret(SAID, {"cause": "possession_on_title",
                                  "sentences": ["S5", "S2", "S4"], "why": "x"})
    assert read.resolved and read.refused is None
    assert read.quoted == " ".join(SAID.sentences[k] for k in ("S2", "S4", "S5"))
    assert "₹40 lakh" in SAID.cite(["S6"])


@pytest.mark.parametrize("named", [["S99"], [], ["S1", "S99"], ["the house"], "S1"])
def test_a_number_that_is_not_theirs_settles_nothing(named):
    read = cause.interpret(SAID, {"cause": "possession_on_title", "sentences": named,
                                  "why": "x"})
    assert not read.resolved and read.refused


def test_an_issue_is_refused_on_a_number_that_is_not_theirs_and_kept_on_one_that_is():
    read = issues.read({"issues": [
        {"statement": "Whether the wall is a trespass", "kind": "substantive",
         "runs_against": "defending", "sentences": ["S5"], "restates": ""},
        {"statement": "Invented", "kind": "substantive", "runs_against": "defending",
         "sentences": ["S42"], "restates": ""},
    ]}, "th_1", SAID)
    assert [i.statement for i in read.issues] == ["Whether the wall is a trespass"]
    assert read.issues[0].proof == SAID.sentences["S5"] and len(read.refused) == 1
    enum = (issues.schema_for(SAID)["properties"]["issues"]["items"]["properties"]
            ["sentences"]["items"]["enum"])
    assert enum == list(SAID.sentences)
