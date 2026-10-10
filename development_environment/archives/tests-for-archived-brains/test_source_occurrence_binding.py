"""A dispute allocation names the occurrence and turn that supplied its words."""

import pytest

from nm.Archives.legal_brain.understand.dispute import Described
from nm.Archives.legal_brain.understand.threading import bind
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance


pytestmark = pytest.mark.class_a


def _fact(words):
    return Fact.create(words, Provenance(kind="advocate_statement", turn="current"))


def test_identical_current_and_pending_sentences_keep_distinct_sources():
    sentence = "The gate is locked."
    accounts = (("current", sentence), ("earlier", sentence))
    described = (
        Described(sentence, "Current access", allocation_unit_ids=("S1",)),
        Described(sentence, "Earlier access", allocation_unit_ids=("S2",)),
    )

    result = bind(Matter.create("adv", "File"), "\n".join(text for _, text in accounts),
                  _fact(sentence), described=described, source_accounts=accounts)

    assert not result.blocks and len(result.source_allocations) == 2
    assert [rows[0].origin_turn for _, rows in result.source_allocations] == [
        "current", "earlier"]
    assert [rows[0].unit_id for _, rows in result.source_allocations] == ["S1", "S2"]
    assert [spans for _, spans in result.allocations] == [(sentence,), (sentence,)]


def test_a_dispute_without_sentence_numbers_is_refused_never_matched_by_words():
    """Words cannot say which of two identical sentences was meant, so a dispute is
    placed by its sentence numbers alone -- refused without them, even where the
    words happen to be unique."""
    sentence = "The gate is locked."
    accounts = (("current", sentence), ("earlier", sentence))
    message = "\n".join(text for _, text in accounts)

    for words, sources in ((message, accounts), (sentence, (("current", sentence),))):
        unnumbered = bind(Matter.create("adv", "File"), words, _fact(sentence),
                          described=(Described(sentence, "Access"),),
                          source_accounts=sources)
        assert unnumbered.blocks and not unnumbered.source_allocations

    numbered = bind(Matter.create("adv", "File"), sentence, _fact(sentence),
                    described=(Described(sentence, "Access", allocation_unit_ids=("S1",)),),
                    source_accounts=(("current", sentence),))
    assert not numbered.blocks
    assert numbered.source_allocations[0][1][0].origin_turn == "current"


def test_source_unit_ids_must_resolve_to_the_described_words():
    accounts = (("current", "The gate is locked."),
                ("earlier", "The price is unpaid."))
    wrong = Described("The gate is locked.", "Access",
                      allocation_unit_ids=("S2",))
    result = bind(Matter.create("adv", "File"), "\n".join(text for _, text in accounts),
                  _fact(accounts[0][1]), described=(wrong,), source_accounts=accounts)
    assert result.blocks and not result.source_allocations
