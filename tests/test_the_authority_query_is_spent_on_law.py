"""AN AUTHORITY QUERY IS SPENT ON WORDS THAT CAN FIND LAW.

THE MEASURED DEFECT, 23 September 2026: every authority query served on that
day's live matters -- fifteen -- read with `_primary_terms`, which took the
FIRST EIGHT distinct words of a selected sentence in order. The budget went on:

    list numbering     "one, eviction"   "first, dissolution"
    function words     "land, at, kandi, resisting, ramulu, possession, ..."
    this file's dates  "her, father, died, intestate, february, 2018, ..."
    this file's names  "tenant, prakash, rao, occupation, since, august, ..."
    nothing at all     "three, connected, but, separate, matters, do, not, them"

and the judgments that came back matched on "at", "not", "88" and a party's
name. `_terms` had always said "the caller puts the resolved provision's
subject FIRST"; the one caller that searches authority supplied a literal
sentence and nothing else, while the cause the turn had already read sat
unused on the need.

Re-measured on the real index, same sentences: the intestacy question moved
from a 1940 fact pattern to a partition suit and an intestate-succession
holding; the charge-sheet question to supply of a charge-sheet copy; rent
arrears from an Income-Tax case to default in payment of rent.

THE RULE, each half asserted below: grammar never occupies a slot (closed
sets -- function words, list numbering, months); a number is kept only where
it is a provision the question cites; the matter's own parties are never
searched for; and the cause already read leads, from the product's own
vocabulary and never from model text.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
from nm.ports.evidence import EvidenceNeed

pytestmark = pytest.mark.class_a

terms = CorpusEvidenceAdapter._terms

#: The focus sentences the live matters actually produced.
LIVE = (
    "One, eviction.",
    "First, dissolution.",
    "On the land at Kandi we are resisting - Ramulu is in possession and "
    "Narsimha's sons are the ones claiming.",
    "Her father died intestate on 2 February 2018 leaving the house to be "
    "shared between her and her brother Ravi.",
    "The tenant Prakash Rao has been in occupation since 1 August 2019 under "
    "a registered lease for three years.",
    "We filed RC 88/2025 before the Rent Controller and he has filed his "
    "written statement.",
    "Three connected but separate matters and I do not want them merged.",
)
PARTIES = frozenset({"prakash rao", "sattaru ramulu", "bandaru narsimha", "ravi"})

NOISE = {"one", "first", "three", "at", "her", "he", "but", "do", "not", "them",
         "since", "before", "february", "august", "2018", "2019", "88", "2025"}


def _need(question, cause=None, parties=frozenset()):
    return EvidenceNeed(question=question, governing_date=date(2026, 9, 23),
                        want_authority=True, cause_of_action=cause, parties=parties)


@pytest.mark.parametrize("question", LIVE)
def test_no_slot_goes_to_grammar_numbering_or_the_files_own_dates(question):
    spent = set(terms(_need(question, parties=PARTIES)))
    wasted = spent & NOISE
    assert not wasted, f"{question!r} spent slots on {sorted(wasted)}"


@pytest.mark.parametrize("question", LIVE)
def test_the_matters_own_parties_are_never_searched_for(question):
    spent = set(terms(_need(question, parties=PARTIES)))
    assert not spent & {"prakash", "rao", "ramulu", "narsimha", "ravi"}, spent


def test_a_provision_the_question_cites_keeps_its_number():
    """The other half: a number is not noise when it is the provision."""
    spent = terms(_need("Is a cheque case under section 138 barred after 30 days?"))
    assert "138" in spent, spent
    assert "30" not in spent


def test_the_cause_already_read_leads_the_query():
    spent = terms(_need("Rent of 45,000 a month unpaid from 1 February 2024.",
                        cause="arrears_of_rent"))
    assert spent[:2] == ["arrears", "rent"], spent


def test_an_unestablished_cause_adds_nothing():
    """An unknown subject is not searched for as though it were known."""
    assert terms(_need("First, dissolution.", cause="not_established")) == ["dissolution"]
    assert terms(_need("First, dissolution.", cause=None)) == ["dissolution"]


def test_the_subject_words_come_from_the_products_vocabulary_not_model_text():
    """`cause_of_action` is a CauseOfAction value -- the closed list -- so
    nothing a model wrote reaches the query through this route."""
    from nm.domain.matter import CauseOfAction
    for cause in CauseOfAction:
        subject = CorpusEvidenceAdapter._subject_terms(_need("x", cause=cause.value))
        for word in subject:
            assert word in cause.value.split("_"), (cause, word)


def test_a_designation_mixing_digits_and_letters_is_always_kept():
    """"53A" is a provision with or without "s." in front of it; only BARE
    numbers -- this file's dates, amounts and case numbers -- are dropped."""
    spent = terms(_need("53A possession title, RC 88/2025, 45,000 a month"))
    assert "53a" in spent, spent
    assert not {"88", "2025", "45", "000"} & set(spent), spent
