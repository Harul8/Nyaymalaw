"""The research keeps and reads every relevant judgment it chooses, and chooses by relevance alone (plan AN.35, D30; research v15;
piece 35a).

The owner, 2 Nov 2026: complete research "with a focus on relevancy as well as completeness", and - of removing the fixed counts -
"we also need to ensure that we are only retrieving the relevant passages and reading only the relevant judgments ... We don't want
to get into a spiral." The newest saved turn chose 30 judgments and read 15: each dispute read at most five. Now every judgment a
dispute's pick chooses is read (whole, or as an extract when long); each question is offered twenty judgment paragraphs, the most
relevant first, as it is twenty provisions - the breadth of what the model looks at, never a cut of what it keeps; and the picks are
told to choose every paragraph a lawyer would rely on and no other, never a count. Each question gets the search phrases it needs.
"""
import pytest

from nm.core_engine import research
from tests.test_core_research import Model, proposal
from tests.test_core_response_writer import TwoDisputeLibrary
from tests.test_core_understanding import context

pytestmark = pytest.mark.class_a


def test_each_question_is_offered_as_many_judgment_paragraphs_as_provisions():
    assert research.FOR_PICK == {"provision": research.PROVISIONS_FOR_PICK, "judgment": research.JUDGMENTS_FOR_PICK}
    assert research.JUDGMENTS_FOR_PICK == research.PROVISIONS_FOR_PICK == 20
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 2), ctx)
    library, asked = TwoDisputeLibrary.searcher(), []
    many = library.search_many
    library.search_many = lambda searches, **kwargs: asked.append(kwargs["results"]) or many(searches, **kwargs)
    research.retrieve(plan, library, ctx, model=Model())
    started = research.start_search(library, plan["work"])
    assert asked == [research.FOR_PICK, research.FOR_PICK] and len(started) == 2, "the search begun early asks the same"


def test_the_picks_and_the_phrases_are_asked_for_by_relevance_never_by_a_count():
    judged = " ".join(research.JUDGMENT_PICK.split())
    assert "up to twenty paragraphs, the most relevant first" in judged
    assert "choose every paragraph a lawyer would rely on to answer it, and no other" in judged
    assert "A paragraph that does not decide or explain that point is not chosen, however near its words are" in judged
    assert "one to three" not in judged and "Choose only what is needed" in research.PICK
    for prompt in (research.PHRASES, research.JUDGMENT_PHRASES):
        words = " ".join(prompt.split())
        assert "as many as the question needs - each a different way in, none a repeat of another" in words
        assert "two or three" not in words


def test_records_before_v15_read_at_most_five_judgments_and_v15_every_one_chosen():
    # v17 (plan AN.36) reads in full only the few the picks name; v15 and v16 read every one chosen.
    assert research.EVERY_CHOSEN == (research.NAMED_CONTRACT, research.FURTHER_CONTRACT) and research.NAMED_CONTRACT == "core_research_v15"
    assert research.SETTLED_CONTRACT in research.JUDGMENTS_READ and research.SETTLED_CONTRACT not in research.EVERY_CHOSEN
    assert research.JUDGMENTS_PER_DISPUTE == 5
