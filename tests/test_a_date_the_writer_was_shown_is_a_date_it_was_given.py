"""A date the writer was shown is a date it was given (plan AN.27, P19).

Code checks that an answer works out no date itself (owner, 15 Oct 2026): each date it states must be in the conversation or documents,
the sources, the time limits code worked out or today. A High Court paper that writes its date in words gave the plan "9 June 2022",
the writer was shown that in the papers' chronology, and the check - made before the writer was shown anything else - found the date
nowhere and left the paragraph out of the overview and of both sections of the reviewed bundle's first turn. The check now counts as
given the dates of the events and of the transfers of land the writer was shown, those located on a page, taken from the same two
functions its payload is built from. The papers here are synthetic.
"""
import json

import pytest

from nm.core_engine import answer_sections, answer_sources, calculation, research, response_writer, turn
from nm.core_engine.calls import TurnCalls
from nm.core_engine.research import plan, retrieve
from tests.test_core_answer_sections import Scripted, paragraph
from tests.test_core_research import Model, searcher, understanding
from tests.test_the_chronology_of_each_document import event, row
from tests.test_the_plan_records_the_chronology import Beside, sent
from tests.test_the_plan_records_the_transfers import transfer

pytestmark = pytest.mark.class_a

ORDER = [(1, "THURSDAY, THE NINTH DAY OF JUNE\nTWO THOUSAND AND TWENTY TWO\nORDER. The Court directs notice to the respondents."),
         (2, "The matter stands posted to 15.09.2022. A petition was filed on a day no page gives.")]
DEED = [(1, "SALE. Made on the twelfth day of June nineteen ninety one, the vendor sold Ac.3.10 guntas of Sy.No.201 to the purchasers.")]
SCRIPT = {
    "order.pdf": [event("9 June 2022", "order", "The Court directed notice to the respondents.",
                        "THE NINTH DAY OF JUNE\nTWO THOUSAND AND TWENTY TWO"),
                  event("1 January 2021", "filing", "A petition was filed.", "A petition was filed on a day the page lacks"),
                  event("undated", "order", "Notice is returnable in six weeks, that is by 21 July 2022.",
                        "The Court directs notice to the respondents")],
    "deed.pdf": [event("undated", "transaction", "A sale.", "the vendor sold Ac.3.10 guntas of Sy.No.201")]}
SOLD = {"deed.pdf": [
    transfer("12 June 1991", "Sy.No.201", "Ac.3.10 guntas", "the vendor sold Ac.3.10 guntas of Sy.No.201 to the purchasers"),
    transfer("1 February 2019", "Sy.No.201", "Ac.0.10", "A sale made on a day the page lacks")]}


def matter():
    ctx = sent(*[row("t1", 1, "order.pdf", n, text) for n, text in ORDER], *[row("t1", 2, "deed.pdf", n, text) for n, text in DEED])
    kept = plan(Beside(SCRIPT, transfers=SOLD, subject=understanding(1, 2)), ctx)
    record = retrieve(kept, searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def draft(*texts, contract=response_writer.PRESENTED_CONTRACT):
    return {"contract": contract, "units": [{"id": f"t1:b{n}", "text": text} for n, text in enumerate(texts, 1)]}


def flagged(stated, ctx, sources, record=None):
    return [finding["unit_ids"][0] for finding in response_writer.dates_not_given(stated, ctx, sources, None, record)]


def test_a_date_a_paper_writes_in_words_is_given_by_the_chronology_the_writer_was_shown():
    ctx, record, sources = matter()
    order = next(e for e in record["plan"]["proposal"]["chronology"] if e["date"] == "9 June 2022")
    assert order["anchored"] and order["sort"] == "2022-06-09"
    stated = draft("The Court made its order on 9 June 2022.", "Notice is returnable from 09/06/2022.", "The order of June 9, 2022.")
    assert flagged(stated, ctx, sources) == ["t1:b1", "t1:b2", "t1:b3"], "the pages as the paper writes them do not show it"
    assert flagged(stated, ctx, sources, record) == []


def test_a_date_of_a_transfer_of_land_the_writer_was_shown_is_given_and_one_not_read_is_not():
    ctx, record, sources = matter()
    sold = draft("The vendor sold Ac.3.10 guntas on 12 June 1991.")
    assert flagged(sold, ctx, sources) == ["t1:b1"] and flagged(sold, ctx, sources, record) == []
    # A transfer whose words were not found on the page was not shown with a date.
    unread = next(t for t in record["plan"]["proposal"]["transfers"] if t["date"] == "1 February 2019")
    assert unread["anchored"] is False
    assert flagged(draft("A sale on 1 February 2019."), ctx, sources, record) == ["t1:b1"]


def test_an_event_whose_words_were_not_found_gives_no_date_and_a_date_found_nowhere_stays_a_finding():
    ctx, record, sources = matter()
    lost = next(e for e in record["plan"]["proposal"]["chronology"] if e["date"] == "1 January 2021")
    assert lost["anchored"] is False
    stated = draft("A petition was filed on 1 January 2021.", "The order was made on 10 June 2022.", "Or on 9 June 2023.",
                   "It is posted to 15.09.2022.", "It was returnable by 21 July 2022.")
    # The date of an event is given, not every date the plan wrote in its account of it: 21 July 2022 is the plan's own sum.
    assert flagged(stated, ctx, sources, record) == ["t1:b1", "t1:b2", "t1:b3", "t1:b5"], "15.09.2022 is on a page as written"


def test_a_writer_that_was_not_shown_the_chronology_is_given_none_of_it():
    ctx, record, sources = matter()
    for contract in (response_writer.SECTION_CONTRACT, None):
        assert flagged(draft("The Court made its order on 9 June 2022.", contract=contract), ctx, sources, record) == ["t1:b1"]
    before = {**record, "contract": research.JUDGMENTS_READ_CONTRACT}
    assert flagged(draft("The Court made its order on 9 June 2022."), ctx, sources, before) == ["t1:b1"]


def test_a_section_and_the_overview_that_state_a_date_they_were_shown_are_not_sent_back_for_it():
    ctx, record, sources = matter()

    def states(round_, payload):
        order = next(e for e in payload["papers_chronology"] if e["located"] and e["date"] == "9 June 2022")
        return [{"kind": "summary", "text": "The Court directs notice to the respondents (order of 9 June 2022).",
                 "uses": [{"source_kind": "document", "source_id": order["cite"][0], "link_words": "directs notice to the respondents"}]},
                paragraph("next_step", "Take notice for the respondents.")]
    model = Scripted(writes={"D1": states, "D2": states}, overview=states)
    sections, crossed, overview = answer_sections.answer(
        TurnCalls(model), ctx, record, sources, interpretation={"units": []}, execution=turn.execution_record(record),
        worked=calculation.skipped())
    pieces = [section["reviewed"] for section in sections] + [overview["reviewed"]]
    assert all(piece is not None and piece["date_findings"] == [] for piece in pieces)
    assert all("9 June 2022" in json.dumps(piece["draft"]["units"]) for piece in pieces)
    writing = model.payloads("core_response_writer") + model.payloads("core_response_overview")
    assert len(writing) == 3 and not any("correction" in payload for payload in writing)
