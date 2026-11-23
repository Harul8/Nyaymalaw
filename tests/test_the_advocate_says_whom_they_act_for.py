"""Whom the advocate acts for is taken only from the advocate's own words (plan AN.63; owner decisions D311 and D328, 22 Nov 2026;
register of exceptions, item 21).

The understanding marks the party the advocate acts for with the words of the advocate's own message that say so (acts_for), and
code finds those words in the advocate's messages alone - never in a paper they sent and never in NM's own notes. A party a paper
names, or one the papers suggest is the client, is not one the advocate has said they act for. The client flag - the client's side,
shown on the board - is unchanged. The parties, papers and messages here are invented.
"""
import pytest

from nm.core_engine import research
from tests.test_core_research import proposal, understanding
from tests.test_core_understanding import context as typed
from tests.test_the_chronology_of_each_document import row

pytestmark = pytest.mark.class_a

PAPER = "The plaint is filed by the buyer against the seller. The advocate acts for the seller in this suit."


def matter(message, *, added=(), paper=True):
    ctx = {**typed(message), "documents": [row("t2", 1, "plaint.pdf", 1, PAPER)] if paper else [], "unread_document_pages": []}
    if added:
        ctx["added"] = [{"source_id": f"t2:added{n}", "turn_id": "t2", "speaker": "advocate", "record_role": "original_account",
                         "text": text} for n, text in enumerate(added, 1)]
    return ctx


def parties(**acts_for):
    return [{"who": who, "role": role, "client": who == "the seller", "parts": [],
             "acts_for": acts_for.get(key, "")}
            for key, who, role in (("seller", "the seller", "defendant"), ("buyer", "the buyer", "plaintiff"))]


def test_the_understanding_asks_for_the_advocates_own_words_and_code_takes_no_other():
    prompt = " ".join(research.UNDERSTAND.split())
    assert ("Where the advocate's own messages say whom they act for, give for that party the words of the advocate's message "
            "that say so, copied exactly (acts_for)") in prompt
    assert "does not tell us whom the advocate acts for" in prompt
    party = research.UNDERSTANDING_V13["properties"]["parties"]["items"]
    assert set(party["required"]) == {"who", "role", "client", "parts", "acts_for"}
    record = research.UNDERSTANDING_V13_RECORD["properties"]["parties"]["items"]
    assert record["required"] == ["who", "role"] and "acts_for" in record["properties"], "a plan saved without it reads as before"


def test_a_party_is_the_advocates_only_by_words_code_finds_in_their_own_messages():
    said = "I act for the seller. Please look at the plaint."
    subject = {**understanding(words=said), "parties": parties(seller="I act for the seller")}
    ctx = matter(said)
    assert research.code_checks(subject, ctx) == []
    assert research.acting_for(subject, ctx) == [{"who": "the seller", "words": "I act for the seller"}]
    # The same words in the paper only: not the advocate's.
    paper_only = {**understanding(words="Please look at the plaint."), "parties": parties(seller="The advocate acts for the seller")}
    ctx = matter("Please look at the plaint.")
    problems = [p["problem"] for p in research.code_checks(paper_only, ctx)]
    assert problems == ["the seller is marked as the party the advocate acts for, but those words do not appear in the "
                        "advocate's own messages ('The advocate acts for the seller')."]
    assert research.acting_for(paper_only, ctx) == []


def test_words_added_while_the_matter_waited_are_the_advocates_and_none_marked_finds_none():
    ctx = matter("Please look at the plaint.", added=["I act for the buyer."])
    subject = {**understanding(words="Please look at the plaint."), "parties": parties(buyer="I act for the buyer")}
    assert research.code_checks(subject, ctx) == []
    assert research.acting_for(subject, ctx) == [{"who": "the buyer", "words": "I act for the buyer"}]
    unmarked = {**understanding(words="Please look at the plaint."), "parties": parties()}
    assert research.acting_for(unmarked, ctx) == [] and research.code_checks(unmarked, ctx) == []
    # A plan saved before acts_for: its parties give none, and are admitted as before.
    older = {**understanding(words="Please look at the plaint."),
             "parties": [{"who": "the seller", "role": "defendant", "client": True, "parts": []}]}
    assert research.acting_for(older, ctx) == []
    admitted = research.accept({**proposal(), "understanding": older}, matter("Please look at the plaint.", paper=False))
    assert admitted["proposal"]["understanding"]["parties"] == older["parties"]
