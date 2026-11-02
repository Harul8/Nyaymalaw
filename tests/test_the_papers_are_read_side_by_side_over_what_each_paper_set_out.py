"""The papers are read side by side over what each paper's reading set out, with the points code finds may be one act set beside each
other, and a difference between papers on one act is a point of its own (plan AN.33, D17 and D18; research v14; piece 33f).

The owner, 1 Nov 2026: "how do we ensure all these and in principle all the legally important details are extracted and considered by
NM?" In AN.31 the points a reading missed were mostly those that show only when two papers are read together. The side-by-side reading
now comes after each paper's reading and is shown, after the papers, every point that reading set out, by its ID, and the points of
different papers that code finds may be one act or one matter - those that name the same number of a document, case or file, and those
of one kind on one day - for the model to judge: code judges none. Where papers record one act differently, the difference is a point of
its own, with each paper's words, placed on both papers' pages and settled as any point. The papers, names and numbers are invented.
"""
import json

import pytest

from nm.core_engine import reasoning, research
from nm.core_engine.research import CONNECTIONS_V14, _comparisons, chronology_of, connections_of, plan
from tests.test_core_research import _result, understanding
from tests.test_the_chronology_of_each_document import event, row
from tests.test_the_plan_records_the_chronology import Beside, sent

pytestmark = pytest.mark.class_a

DEED = ("Sale deed No. 418/2003 dated 4-5-2003. The vendor sold 15 acres of the orchard to the buyer. The boundaries are the canal on "
        "the east, the village road on the west, the school land on the north and the river bank on the south. The price was paid in "
        "full before the sub-registrar, and the vendor handed over possession of the orchard on the same day.")
LETTER = "Letter of the buyer. By deed No. 418/2003 of 14-5-2003 the vendor sold 12 acres of the orchard to me."
SCRIPT = {"deed.pdf": [event("4-5-2003", "transaction", "A sale of 15 acres.", "Sale deed No. 418/2003 dated 4-5-2003")],
          "copy.pdf": [event("4-5-2003", "transaction", "A sale of 15 acres.", "Sale deed No. 418/2003 dated 4-5-2003")],
          "letter.pdf": [event("14-5-2003", "statement", "The buyer says the vendor sold him 12 acres.",
                               "By deed No. 418/2003 of 14-5-2003 the vendor sold 12 acres of the orchard to me", "the buyer")]}
DIFFER = {"kind": "papers_differ", "point": "The deed and the buyer's letter give the sale a different date and extent.",
          "why_it_matters": "Which date and extent bind the parties is open.",
          "words": "Sale deed No. 418/2003 dated 4-5-2003 ... By deed No. 418/2003 of 14-5-2003 the vendor sold 12 acres"}


def papers(*names):
    texts = {"deed.pdf": DEED, "copy.pdf": DEED, "letter.pdf": LETTER}
    return {**sent(*[row("t1", index, name, 1, texts[name]) for index, name in enumerate(names, 1)]),
            "latest": {**sent()["latest"], "text": "We act for the buyer. Look at the sale."}}


def read(*names):
    """The papers' chronology as research v14 numbers it, from the script."""
    ctx = papers(*names)
    events, _ = chronology_of(Beside({name: SCRIPT[name] for name in names}), ctx)
    return ctx, events


class Together(Beside):
    """The research double that reads the papers side by side as `points` says, and keeps every call."""

    def __init__(self, script, points=None):
        super().__init__(script, transfers={}, subject=understanding(words="We act for the buyer"))
        self.points = points or {"client_people": [], "connections": []}

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_connections":
            self.calls.append(prompt)
            if '"to_check"' in prompt.user:
                return _result({"settled": []}, tier)
            return _result(self.points, tier)
        return super().structured(prompt, schema, tier, **kwargs)


def shown(user):
    """What the side-by-side reading was shown after the papers: the points read, and code's comparisons."""
    listed, _, compared = user.partition("Points of different papers that code found may be one act or one matter (comparisons):\n")
    points = [json.loads(line) for line in listed.split("point by point (id, paper, date, kind, what, said_by):\n")[1].split("\n")
              if line.startswith("{")]
    return points, [json.loads(line) for line in compared.split("\n") if line.startswith("{")]


def test_code_sets_beside_each_other_the_points_of_different_papers_that_name_one_number_or_are_one_kind_on_one_day():
    ctx, events = read("deed.pdf", "letter.pdf")
    by_paper = {e["document"]: e["id"] for e in events}
    assert _comparisons(events) == [{"points": [by_paper["deed.pdf"], by_paper["letter.pdf"]], "because": "each names 418/2003"}]
    alone = [{**e, "source": "t1:d1", "document": "deed.pdf"} for e in events]
    assert _comparisons(alone) == [], "points of one paper are no comparison"
    same_day = [{**e, "sort": "2003-05-04", "kind": "transaction", "words": "", "what": "A sale."} for e in events]
    assert _comparisons(same_day) == [{"points": [e["id"] for e in same_day], "because": "each is a point of kind transaction of "
                                                                                          "2003-05-04"}]


def test_an_event_a_copy_of_a_page_records_again_is_compared_once():
    from nm.core_engine import copy_figures
    ctx, events = read("deed.pdf", "copy.pdf", "letter.pdf")
    pages = [{"document": row["document"]["name"], "key": row["source_id"].rsplit("p", 1)[0], "page": row["document"]["page"],
              "id": row["source_id"], "text": row["text"]} for row in ctx["documents"]]
    copied = copy_figures.copies(pages)
    assert copied, "the copy is found"
    [group] = _comparisons(events, copied)
    assert len(group["points"]) == 2 and group["because"] == "each names 418/2003", "the deed and its copy count once"


def test_the_side_by_side_reading_is_shown_every_point_read_and_codes_comparisons_after_the_papers():
    ctx, events = read("deed.pdf", "letter.pdf")
    model = Together({})
    connections_of(model, ctx, events=events)
    [call] = [p for p in model.calls if p.operation == "core_research_connections"]
    assert call.system == CONNECTIONS_V14 and call.user.index('Paper "letter.pdf"') < call.user.index("What each paper's reading")
    points, compared = shown(call.user)
    assert [p["id"] for p in points] == [e["id"] for e in events] and points[0]["paper"] in ("deed.pdf", "letter.pdf")
    assert set(points[0]) == {"id", "paper", "date", "kind", "what", "said_by"}
    assert compared == _comparisons(events)


def test_a_difference_between_papers_on_one_act_is_a_point_of_its_own_placed_on_both_papers():
    ctx, events = read("deed.pdf", "letter.pdf")
    model = Together({}, {"client_people": [], "connections": [DIFFER]})
    [differ], people, appearances, failures = connections_of(model, ctx, events=events)
    assert differ["kind"] == "papers_differ" and differ["anchored"] and failures == []
    assert sorted(place["document"] for place in differ["places"]) == ["deed.pdf", "letter.pdf"]


def test_in_the_plan_the_side_by_side_reading_follows_the_papers_reading_it_is_shown():
    ctx = papers("deed.pdf", "letter.pdf")
    model = Together({name: SCRIPT[name] for name in ("deed.pdf", "letter.pdf")}, {"client_people": [], "connections": [DIFFER]})
    record = plan(model, ctx)
    proposal = record["proposal"]
    [call] = [p for p in model.calls if p.operation == "core_research_connections"]
    points, _ = shown(call.user)
    assert [p["id"] for p in points] == [e["id"] for e in proposal["chronology"]] and len(points) == 2
    assert [c["kind"] for c in proposal["connections"]] == ["papers_differ"] and record["issues"] == []
    assert research.accept(proposal, ctx)["issues"] == []


def test_the_prompt_asks_for_the_differences_and_leaves_the_judgment_to_the_model():
    words = " ".join(CONNECTIONS_V14.split())
    for part in ("after them, what each paper's reading set out, point by point, and the points of different papers that code found "
                 "may be one act or one matter (comparisons)",
                 "Read the list of points as well as the pages: a point read in one paper may matter only beside one read in another",
                 "Where papers record one act or matter differently - a different date, figure, party, number or outcome: the "
                 "difference, as a point of its own (kind papers_differ), with each paper's words",
                 "Judge each of the comparisons - whether its points are one act or matter, and whether the papers differ on it - and "
                 "look for any other; a comparison whose points are different acts, or agree, needs nothing",
                 "except the handwriting a note transcribes, which is the page's",
                 "kind (client_appears, against_client, after_death, after_time_limit, further_subject, papers_differ, or other)"):
        assert part in words, part
    assert research.CONNECTION_KINDS_V14 == ("client_appears", "against_client", "after_death", "after_time_limit",
                                             "further_subject", "papers_differ", "other")
    assert research.MAX_OUTPUT["connections"] == reasoning.MOST_OUTPUT
    assert "papers_differ" not in research.CONNECTIONS_V13, "the prompt of the records made before is kept as it was"
