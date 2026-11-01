"""A page's own dots - a form's leader, an ellipsis - do not break the check of what was read from it (research v14; found by the
measuring run of plan AN.33, 1 Nov 2026).

Research v14 keeps each point in the page's own words, which may hold the page's dots ("Name of the vendor .......... ", "The
petitioner ... prays"). The plan's check found those words again and split them at the dots, and a passage on its own may stand on
another page too: the check then refused a reading code had placed rightly, and the turn's research with it. A v14 record is now
checked by placing it again exactly as it was made - from the words the model gave, by the tolerant finder - for events, transactions
and the points read side by side alike; a record that claims a placing code does not make is still refused. The papers are invented.
"""
import pytest

from nm.core_engine import research
from nm.core_engine.research import chronology_of, connections_of, transfers_of
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import _result
from tests.test_failed_checks_are_settled_by_the_model import Settling, sent
from tests.test_the_chronology_of_each_document import event

pytestmark = pytest.mark.class_a

PRAYER = [(1, "Earlier: prays that the suit be decreed with costs, as the plaint says."),
          (2, "The petitioner ... prays that the suit be decreed with costs.")]
FORM = [(1, "Lalit Verghese signed the receipt for the advance of 9 acres' price."),
        (2, "Name of the vendor .......... Lalit Verghese. Area sold .......... 9 acres for Rs 4,000.")]
SAID = event("undated", "statement", "The petitioner prays for a decree with costs.", "The petitioner prays that the suit be decreed",
             "the petitioner")
SOLD = {"date": "undated", "kind": "sale", "subject": "the land", "figure": "9 acres", "whole": "",
        "quantity": {"dimension": "area", "parts": [{"number": "9", "unit": "acre", "written": "acres"}]},
        "whole_quantity": {"dimension": "none", "parts": []}, "from": "Lalit Verghese", "to": "the buyer", "instrument": "",
        "giver_died": "", "words": "Name of the vendor Lalit Verghese. Area sold 9 acres"}


def test_an_event_kept_in_a_pages_own_words_with_its_dots_passes_the_plans_check():
    ctx = sent(("petition.pdf", PRAYER))
    [kept] = [e for e in chronology_of(Settling({"petition.pdf": [SAID]}), ctx)[0] if e["kind"] == "statement"]
    assert kept["anchored"] and kept["pages"] == [2] and " ... " in kept["words"] and kept["quoted"] == SAID["words"]
    research._chronology_issues([kept], [], ctx, True, research.TOLERANT_FINDER)
    with pytest.raises(SchemaViolation, match="not anchored as its words are found"):
        research._chronology_issues([{**kept, "pages": [1, 2]}], [], ctx, True, research.TOLERANT_FINDER)


def test_a_transaction_and_a_point_read_side_by_side_kept_so_pass_too():
    ctx = sent(("form.pdf", FORM))
    [moved] = transfers_of(Settling({"form.pdf": [SOLD]}), ctx)[0]
    assert moved["anchored"] and moved["pages"] == [2] and ".........." in moved["words"]
    research._transfer_issues([moved], [], ctx, True, research.TOLERANT_FINDER)
    together = {"client_people": [], "connections": [{"kind": "other", "point": "The form names the vendor.",
                                                      "why_it_matters": "It says who sold.",
                                                      "words": "Name of the vendor Lalit Verghese"}]}
    [point], _, _, _ = connections_of(Settling({"together": together}), ctx)
    assert point["anchored"] and [place["page"] for place in point["places"]] == [2]
    research._connection_issues({"connections": [point]}, ctx, research.TOLERANT_FINDER)
    with pytest.raises(SchemaViolation, match="not anchored as its words are found"):
        research._connection_issues({"connections": [{**point, "places": []}]}, ctx, research.TOLERANT_FINDER)
