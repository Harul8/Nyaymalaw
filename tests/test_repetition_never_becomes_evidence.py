"""THE ATTRIBUTED LIVING FILE. BK-64-AC1, J-4-AC1. P17.

THE RULE, stated without the summariser that would break it
-------------------------------------------------------------
**A fact is documented because a document says so, and never because it was
said again.**

Easy to agree with and easy to lose. A memory that promotes anything mentioned
twice, a UI that renders "mentioned 4x" beside a tick, a summariser that reads
consistency as corroboration -- each turns repetition into evidence, and the
advocate then argues a documented fact that no document supports.

WHAT IS ASSERTED
------------------
    repeating an assertion leaves it asserted
    a DOCUMENTED fact with no document is reported as an upgrade that happened
    extraction quality and human confirmation stay separate values
    `confirmed` has three states, because `bool | None` has three
    a correction supersedes and PRESERVES the version it replaced
    a contradiction is a link, visible from the entry that carries it
    one factual dispute does not become two records with two answers
    a fact with no document is named as such rather than called unsourced
"""
from __future__ import annotations

import pytest

from nm.core.casefile import (
    Attribution,
    build,
    one_dispute_stays_one,
    repetition_upgrades,
)
from nm.domain.intake import ReadQuality
from nm.domain.matter import Certainty, Fact, Matter, Provenance

pytestmark = pytest.mark.class_a

SAID = Provenance(kind="advocate_statement", turn="t1")
DOC = Provenance(kind="document", turn="t2", document="invoice.pdf", page=3,
                 span="lines 4-6")


def _matter(*facts: Fact) -> Matter:
    return Matter(id="mat_1", advocate_id="adv@example.test",
                  title="Kukatpally", facts=facts)


# ===================== repetition is not corroboration ======================

def test_saying_it_four_times_leaves_it_asserted():
    """THE POINT OF THE FILE."""
    repeated = tuple(
        Fact(id=f"f{n}", statement="the goods were delivered on 3 March",
             provenance=SAID) for n in range(4))
    casefile = build(_matter(*repeated))
    assert casefile["documented"] == []
    assert len(casefile["asserted"]) == 4


def test_a_documented_fact_with_no_document_is_reported_as_an_upgrade():
    """The check is not 'is this repeated' -- repetition is ordinary. It is:
    does a DOCUMENTED fact have a document to be documented by?"""
    forged = Fact(id="f9", statement="the goods were delivered",
                  provenance=SAID, certainty=Certainty.DOCUMENTED)
    found = repetition_upgrades((forged,))
    assert found and "f9" in found[0]
    assert "no document" in found[0]


def test_a_properly_documented_fact_is_not_flagged():
    """THE NEGATIVE CONTROL. A check that flagged every documented fact would
    make the documented state unusable and look rigorous doing it."""
    proper = Fact(id="f3", statement="the invoice was raised on 5 March",
                  provenance=DOC, certainty=Certainty.DOCUMENTED)
    assert repetition_upgrades((proper,)) == ()


def test_an_asserted_fact_is_never_flagged_however_often_it_appears():
    """Repetition itself is harmless; it is the UPGRADE that is not."""
    many = tuple(Fact(id=f"f{n}", statement="same thing", provenance=SAID)
                 for n in range(10))
    assert repetition_upgrades(many) == ()


# ================== extraction quality is not confirmation ==================

def test_read_quality_and_confirmation_are_separate_values():
    """A clear scan of a false statement is a clearly-read falsehood, and
    merging the two produces a number that means neither."""
    entry = build(_matter(
        Fact(id="f1", statement="x", provenance=DOC, confirmed=False)
    ))["live"][0]
    assert entry["confirmed"] == "disputed"
    assert entry["attribution"]["read_quality"] in {q.value for q in ReadQuality}
    assert "confirmed" not in entry["attribution"]


@pytest.mark.parametrize("value,expected", [
    (True, "confirmed"), (False, "disputed"), (None, "not_asked")])
def test_confirmation_has_three_states_because_the_field_does(value, expected):
    """Flattening `None` into False would tell the advocate a person had
    rejected something nobody had put to them."""
    entry = build(_matter(
        Fact(id="f1", statement="x", provenance=SAID, confirmed=value)
    ))["live"][0]
    assert entry["confirmed"] == expected


def test_an_unextracted_fact_is_unread_rather_than_clear():
    """The advocate typed it, so no machine read anything; claiming CLEAR
    would be an extraction confidence for an extraction that never happened."""
    entry = build(_matter(
        Fact(id="f1", statement="x", provenance=SAID)))["live"][0]
    assert entry["attribution"]["read_quality"] == ReadQuality.UNREAD.value


def test_recorded_extraction_quality_and_version_survive_sealed_restart(tmp_path):
    from dataclasses import replace

    from nm.adapters.store.file_store import FileMatterStore

    key = "casefile-test-key-" + "q" * 32
    store = FileMatterStore(tmp_path, key=key)
    original = Fact(id="f1", statement="x", provenance=DOC,
                    read_quality=ReadQuality.CLEAR, confirmed=False, version=3)
    saved = store.commit(_matter(original), expected_version=0)
    loaded = FileMatterStore(tmp_path, key=key).load(saved.id)
    entry = build(loaded)["live"][0]
    assert entry["attribution"]["read_quality"] == "clear"
    assert entry["confirmed"] == "disputed"
    assert entry["version"] == 3

    changed = loaded.amending(replace(loaded.facts[0], confirmed=True))
    saved = store.commit(changed, expected_version=loaded.version)
    again = FileMatterStore(tmp_path, key=key).load(saved.id)
    assert build(again)["live"][0]["version"] == 4
    assert again.facts[0].provenance == original.provenance
    assert original.confirmed is False


# ========================= the locator is inspectable =======================

def test_a_documented_fact_opens_at_a_page():
    """A conclusion an advocate cannot check against its original is one they
    have to take on trust."""
    entry = build(_matter(
        Fact(id="f3", statement="x", provenance=DOC)))["live"][0]
    assert entry["attribution"]["inspectable"] is True
    assert entry["attribution"]["document"] == "invoice.pdf"
    assert entry["attribution"]["page"] == 3
    assert "page 3" in entry["attribution"]["said"]


def test_a_document_with_no_page_is_not_inspectable():
    """It sends the advocate to a forty-page exhibit and tells them it is in
    there somewhere."""
    attribution = Attribution(kind="document", document="bundle.pdf")
    assert attribution.inspectable is False
    assert "no page recorded" in attribution.said()


def test_a_fact_with_no_document_is_named_without_being_called_unsourced():
    """An advocate's own statement HAS a source -- the advocate. Calling it
    unsourced reads as a defect in the record rather than the ordinary state
    of something nobody has documented yet."""
    casefile = build(_matter(
        Fact(id="f1", statement="x", provenance=SAID),
        Fact(id="f3", statement="y", provenance=DOC)))
    assert casefile["without_a_document"] == ["f1"]
    assert "unsourced" not in casefile


def test_the_projection_holds_nothing_the_matter_does_not():
    """A board that disagrees with the answer is worse than either alone."""
    casefile = build(_matter(Fact(id="f1", statement="x", provenance=SAID)))
    assert casefile["row_count"] == 1
    assert casefile["bounded_by"] == "live_fact_count"


# ============================== corrections =================================

def test_a_correction_supersedes_and_preserves_what_it_replaced():
    """The previous version is evidence: an advice given under it was correct
    work under it, and deleting it makes that advice look like a mistake."""
    original = Fact(id="f1", statement="delivered on 3 March",
                    provenance=SAID, superseded_by="f2")
    corrected = Fact(id="f2", statement="delivered on 13 March",
                     provenance=SAID)
    casefile = build(_matter(original, corrected))

    assert [e["fact_id"] for e in casefile["live"]] == ["f2"]
    assert casefile["superseded"] == [{"fact_id": "f1", "by": "f2"}]
    # AND THE ORIGINAL IS STILL THERE, in `entries` rather than only `live`.
    assert [e["fact_id"] for e in casefile["entries"]] == ["f1", "f2"]


def test_a_superseded_fact_leaves_the_live_view_without_leaving_the_file():
    casefile = build(_matter(
        Fact(id="f1", statement="old", provenance=SAID, superseded_by="f2"),
        Fact(id="f2", statement="new", provenance=SAID)))
    assert casefile["row_count"] == 1
    assert len(casefile["entries"]) == 2


# ============================== contradictions ==============================

def test_a_contradiction_is_visible_from_the_entry_that_carries_it():
    casefile = build(_matter(
        Fact(id="f1", statement="delivered on 3 March", provenance=SAID,
             conflicts_with=("f2",)),
        Fact(id="f2", statement="never delivered", provenance=SAID)))
    assert casefile["contradictions"] == [{"fact_id": "f1", "with": ["f2"]}]


def test_a_file_with_no_contradictions_says_so_with_an_empty_list():
    """The negative control: a projection that reported a contradiction on
    every file would be noise nobody reads."""
    assert build(_matter(
        Fact(id="f1", statement="x", provenance=SAID)))["contradictions"] == []


# ======================= one dispute stays one ==============================

def test_one_statement_recorded_twice_with_two_answers_is_reported():
    """J-4-AC1. A single factual dispute must stay coherent when several
    remedies or procedural questions concern it; two records with different
    certainty is one dispute answered two ways, and whichever the advice reads
    is chance."""
    casefile = build(_matter(
        Fact(id="f1", statement="the goods were delivered", provenance=SAID),
        Fact(id="f2", statement="The goods were delivered", provenance=DOC,
             certainty=Certainty.DOCUMENTED)))
    split = one_dispute_stays_one(casefile["live"])
    assert split and "different certainty" in split[0]


def test_the_same_statement_with_the_same_certainty_is_not_reported():
    """Recording one fact against two threads is ordinary. Splitting is
    legitimate; splitting into records that DISAGREE is not."""
    casefile = build(_matter(
        Fact(id="f1", statement="the goods were delivered", provenance=SAID),
        Fact(id="f2", statement="the goods were delivered", provenance=SAID)))
    assert one_dispute_stays_one(casefile["live"]) == ()


def test_a_superseded_duplicate_is_not_counted_as_a_split():
    """A correction is exactly the case where two records of one statement
    SHOULD disagree, and reporting it would make the check fire on every
    correction the product is designed to support."""
    casefile = build(_matter(
        Fact(id="f1", statement="delivered", provenance=SAID,
             superseded_by="f2"),
        Fact(id="f2", statement="delivered", provenance=DOC,
             certainty=Certainty.DOCUMENTED)))
    assert one_dispute_stays_one(casefile["live"]) == ()


def test_different_statements_are_never_reported_as_one_dispute():
    casefile = build(_matter(
        Fact(id="f1", statement="the goods were delivered", provenance=SAID),
        Fact(id="f2", statement="the invoice was paid", provenance=DOC,
             certainty=Certainty.DOCUMENTED)))
    assert one_dispute_stays_one(casefile["live"]) == ()
