"""The timeline's prompt dates a numbered case or document and lists an order a later proceeding relies on (plan AN.29, D10; findings B13
and B5).

The third paid replay left 83 of 231 events undated, 49 of them with a year in their own words - a case or document number carries the
year it was filed or registered - and held no event for an order or decree that a later proceeding enforces or challenges. Each is a
rule about a kind of thing, not about a kind of matter: a numbered case or document, and an order, decree or judgment that other
proceedings turn on. A prompt is pinned here, not proved: what the model does with it is measured by a bounded replay. The papers here
are invented.
"""
import pytest

from nm.core_engine import research

pytestmark = pytest.mark.class_a

DATED = ('A case or document number carries the year it was filed or registered: where that year is all the page gives of when the case '
         'was filed or the document registered, give it as the date of that filing or registration, not "undated".')
RELIED_ON = ("An order, decree or judgment that a later proceeding enforces, challenges, reviews or relies on is an event of its own at "
             "its own date, even where the page only recites it: list it once, and let the later proceeding refer to it.")


def words(prompt):
    return " ".join(prompt.split())


def test_a_case_or_document_number_carries_the_year_it_was_filed_or_registered():
    prompt = words(research.CHRONOLOGY_V14)
    assert DATED in prompt
    assert prompt.index("Where the page gives no date for this event, say undated.") < prompt.index(DATED), \
        "said after the rule for an event the page does not date, as its exception"


def test_an_order_decree_or_judgment_that_a_later_proceeding_relies_on_is_an_event_of_its_own_listed_once():
    prompt = words(research.CHRONOLOGY_V14)
    assert RELIED_ON in prompt
    assert prompt.index(RELIED_ON) < prompt.index("One point for each act, finding, statement, particular or relationship."),         "and the one-point rule that follows keeps it listed once"


def test_the_earlier_timeline_prompt_is_what_it_was():
    assert DATED not in words(research.CHRONOLOGY) and RELIED_ON not in words(research.CHRONOLOGY)
    assert research.CHRONOLOGY != research.CHRONOLOGY_V14
