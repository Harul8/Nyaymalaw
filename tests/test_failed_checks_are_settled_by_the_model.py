"""What code cannot check in the papers' reading is settled by the model, shown code's evidence, and nothing is lost for a slip
(plan AN.33, D18 and D22; research v14; piece 33b).

The owner, 1 Nov 2026: "pass these to model and let model decide whether this is a clerical error or a genuine failed test in which can
model can decide to drop only that failed portion". Code places each event, transaction and point read side by side with the tolerant
finder and keeps it in the page's own words; for a paper where some still cannot be checked - their words not found, or the numbers of
their date found nowhere in the papers - one call settles them, shown why and the page's nearest words; code places what it gives again.
A slip is corrected from the page; only a part the papers do not hold goes; an item they do not record is withdrawn and listed with why;
what stays unchecked is kept, marked so; no date is erased. The papers are invented.
"""
import json
import re
import threading

import pytest

from nm.core_engine import research
from nm.core_engine.research import (
    CONTRACT, SETTLE_EVENTS, SETTLE_POINTS, SETTLE_TRANSFERS, WHOLE_FILE_CONTRACT, accept, chronology_of, connections_of,
    transfers_of,
)
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import _result
from tests.test_the_chronology_of_each_document import event, row

pytestmark = pytest.mark.class_a

DEED = [(1, "Agreement No. 7 dated 3-9-2014. The supplier sold 42 kg of grain to the buyer at the depot."),
        (2, "Registered at the office. A survey was ordered on 11-2-2016 in file K/58/2014.")]
NOTE = [(1, "Note of the buyer. The supplier's agent signed for the stores on 21 March 2017.")]


def sent(*papers):
    rows = [row("t1", index, name, number, text) for index, (name, pages) in enumerate(papers, 1) for number, text in pages]
    return {"documents": rows, "conversation": [], "latest": {"text": "Read these."}}


class Settling:
    """Answers each paper's reading from `reading` and each settling call from `settling`, both keyed by the paper's name (a
    settling answer may be a function of the call's words); records every call."""

    def __init__(self, reading, settling=None, fail=()):
        self.reading, self.settling, self.fail = reading, settling or {}, set(fail)
        self.calls, self.lock = [], threading.Lock()

    def context_budget(self, tier):
        return 10 ** 9

    def structured(self, prompt, schema, tier, **kwargs):
        with self.lock:
            self.calls.append(prompt)
        if prompt.system in (SETTLE_EVENTS, SETTLE_TRANSFERS, SETTLE_POINTS):
            name = "together" if prompt.system == SETTLE_POINTS else re.search(
                r'The pages of the paper being checked:\nDocument: "(.*)"', prompt.user).group(1)
            if (name, "settle") in self.fail:
                raise SchemaViolation("scripted failure")
            answer = self.settling.get(name, {"settled": [], **({"added": []} if prompt.system == SETTLE_EVENTS else {})})
            return _result(answer(prompt.user) if callable(answer) else answer, tier)
        if prompt.operation == "core_research_connections":
            return _result(self.reading["together"], tier)
        name = re.search(r'^Document: "(.*)"', prompt.user, re.M).group(1)
        key = "transfers" if prompt.operation == "core_research_transfers" else "events"
        return _result({key: self.reading.get(name, [])}, tier)

    def settles(self):
        return [call for call in self.calls if call.system in (SETTLE_EVENTS, SETTLE_TRANSFERS, SETTLE_POINTS)]


def shown(call):
    """The evidence a settling call was shown."""
    return json.loads(call.user[call.user.rindex("\n\n{") + 2:])


def settled(index, verdict, item, reason="Checked against the page.", key="event"):
    return {"index": index, "verdict": verdict, "reason": reason, key: item}


SLIP = event("3-9-2014", "transaction", "A sale of 42 kg.", "The supplier sold 42 kg of grain to the buyr")
RIGHT = event("3-9-2014", "transaction", "A sale of 42 kg.", "The supplier sold 42 kg of grain to the buyer")


def test_a_slip_in_copying_is_settled_from_the_page_and_kept_in_the_pages_own_words():
    model = Settling({"deed.pdf": [SLIP]}, {"deed.pdf": {"settled": [settled(0, "clerical", RIGHT)], "added": []}})
    events, failures = chronology_of(model, sent(("deed.pdf", DEED)))
    [kept] = [e for e in events if e["kind"] == "transaction"]
    assert kept["anchored"] and kept["pages"] == [1] and kept["words"] == "The supplier sold 42 kg of grain to the buyer"
    assert (kept["settled"], kept["settled_why"]) == ("clerical", "Checked against the page.")
    assert failures == [] and len(model.settles()) == 1
    [check] = shown(model.settles()[0])["to_check"]
    assert check["index"] == 0 and check["words"] == SLIP["words"] and "not found" in check["why"]
    assert "grain to the buyer" in check["nearest_words"]


def test_a_difference_that_cannot_change_the_meaning_needs_no_settling_and_the_pages_words_are_kept():
    split = [(1, "Agreement No. 7 dated 3-9-2014. The supp lier sold 42 kg of grain to the buyer at the depot.")]
    model = Settling({"deed.pdf": [RIGHT]})
    [kept] = chronology_of(model, sent(("deed.pdf", split)))[0]
    assert kept["anchored"] and kept["words"] == "The supp lier sold 42 kg of grain to the buyer"
    assert kept["quoted"] == RIGHT["words"] and kept["settled"] == "" and model.settles() == []


def test_only_the_part_the_papers_do_not_hold_goes():
    two = event("3-9-2014", "transaction", "A sale, and a refund.",
                "The supplier sold 42 kg of grain to the buyer ... the buyer was refunded in full")
    part = event("3-9-2014", "transaction", "A sale.", "The supplier sold 42 kg of grain to the buyer")
    model = Settling({"deed.pdf": [two]}, {"deed.pdf": {"settled": [settled(0, "part", part, "No refund is recorded.")],
                                                        "added": []}})
    [kept] = chronology_of(model, sent(("deed.pdf", DEED)))[0]
    assert kept["anchored"] and kept["what"] == "A sale." and kept["settled"] == "part"


def test_an_item_the_papers_do_not_record_is_withdrawn_with_why_and_never_kept():
    ghost = event("5-5-2015", "order", "An order of the court.", "The court ordered the stores to be sealed")
    model = Settling({"deed.pdf": [RIGHT, ghost]},
                     {"deed.pdf": {"settled": [settled(0, "not_in_papers", ghost, "No such order is on the pages.")], "added": []}})
    withdrawn = []
    events, _ = chronology_of(model, sent(("deed.pdf", DEED)), withdrawn=withdrawn)
    assert [e["words"] for e in events] == [RIGHT["words"]]
    assert withdrawn == [{"kind": "event", "document": "deed.pdf", "what": "An order of the court.", "words": ghost["words"],
                          "why": "No such order is on the pages."}]


def test_what_cannot_be_checked_after_settling_is_kept_and_marked_so():
    model = Settling({"deed.pdf": [SLIP]}, {"deed.pdf": {"settled": [settled(0, "as_listed", SLIP, "The scan reads so.")],
                                                         "added": []}})
    [kept] = chronology_of(model, sent(("deed.pdf", DEED)))[0]
    assert not kept["anchored"] and kept["pages"] == [] and kept["words"] == SLIP["words"]
    assert (kept["settled"], kept["settled_why"]) == ("as_listed", "The scan reads so.")


def test_an_item_the_answer_names_no_verdict_for_stays_as_it_was_marked_unanswered():
    model = Settling({"deed.pdf": [SLIP]}, {"deed.pdf": {"settled": [settled(4, "clerical", RIGHT)], "added": []}})
    [kept] = chronology_of(model, sent(("deed.pdf", DEED)))[0]
    assert kept["words"] == SLIP["words"] and kept["settled"] == "unanswered" and not kept["anchored"]


def test_a_settling_call_that_fails_keeps_its_items_marked_unavailable():
    model = Settling({"deed.pdf": [SLIP]}, fail={("deed.pdf", "settle")})
    [kept] = chronology_of(model, sent(("deed.pdf", DEED)))[0]
    assert kept["words"] == SLIP["words"] and kept["settled"] == "unavailable"


def test_no_date_is_erased_and_code_says_where_it_stands():
    elsewhere = event("21 March 2017", "other", "The agent signed for the stores.", "The supplier sold 42 kg of grain to the buyer")
    nowhere = event("9-9-1999", "other", "A sale of 42 kg.", "The supplier sold 42 kg of grain to the buyer at the depot")
    model = Settling({"deed.pdf": [elsewhere, nowhere]},
                     {"deed.pdf": {"settled": [settled(0, "as_listed", nowhere, "The date is the one I read.")], "added": []}})
    events = chronology_of(model, sent(("deed.pdf", DEED), ("note.pdf", NOTE)))[0]
    found = {e["date"]: e["date_found"] for e in events}
    assert found == {"21 March 2017": "file", "9-9-1999": "nowhere"}
    assert [c["date"] for c in shown(model.settles()[0])["to_check"]] == ["9-9-1999"]


def test_one_settling_call_for_each_paper_with_failures_none_for_the_others():
    model = Settling({"deed.pdf": [SLIP], "note.pdf": [event("21 March 2017", "other", "Signed.", "signed for the stores on 21 March 2017")]},
                     {"deed.pdf": {"settled": [settled(0, "clerical", RIGHT)], "added": []}})
    chronology_of(model, sent(("deed.pdf", DEED), ("note.pdf", NOTE)))
    [call] = model.settles()
    assert call.operation == "core_research_chronology" and call.system == SETTLE_EVENTS
    assert 'The pages of the paper being checked:\nDocument: "deed.pdf"' in call.user and "Paper \"note.pdf\"" in call.user


def test_a_date_no_event_carries_is_asked_about_and_an_event_it_marks_is_added():
    added = event("11-2-2016", "order", "A survey was ordered.", "A survey was ordered on 11-2-2016 in file K/58/2014")
    model = Settling({"deed.pdf": [RIGHT]}, {"deed.pdf": {"settled": [], "added": [added]}})
    events = chronology_of(model, sent(("deed.pdf", DEED)))[0]
    assert shown(model.settles()[0])["not_carried"] == [{"date": "11-2-2016", "page": 2}]
    assert [e["what"] for e in events] == ["A sale of 42 kg.", "A survey was ordered."]
    assert events[1]["anchored"] and events[1]["date_found"] == "words"


SALE = {"date": "3-9-2014", "kind": "sale", "subject": "the grain", "figure": "42 kg",
        "quantity": {"dimension": "mass", "parts": [{"number": "42", "unit": "kilogram", "written": "kg"}]}, "whole": "",
        "whole_quantity": {"dimension": "none", "parts": []}, "from": "the supplier", "to": "the buyer", "instrument": "Agreement No. 7",
        "giver_died": "", "words": "Agreement No. 7 dated 3-9-2014. The supplier sold 42 kg of grain to the buyer"}


def test_a_death_the_papers_do_not_record_is_kept_and_never_used():
    sale = {**SALE, "giver_died": "1-1-2001"}
    model = Settling({"deed.pdf": [sale]}, {"deed.pdf": {"settled": [settled(0, "as_listed", sale, "Read so.", "transfer")]}})
    [kept] = transfers_of(model, sent(("deed.pdf", DEED)))[0]
    assert kept["giver_died"] == "1-1-2001" and not kept["giver_died_found"] and kept["giver_died_sort"] == ""
    assert kept["settled"] == "as_listed" and model.settles()[0].system == SETTLE_TRANSFERS


def test_a_transaction_code_can_check_needs_no_settling():
    [kept] = transfers_of(Settling({"deed.pdf": [SALE]}), sent(("deed.pdf", DEED)))[0]
    assert kept["anchored"] and kept["date_found"] == "words" and kept["settled"] == "" and not kept["giver_died_found"]


def test_a_point_read_side_by_side_is_settled_the_papers_together():
    point = {"kind": "other", "point": "The agent signed after the sale.", "why_it_matters": "It bears on the sale.",
             "words": "The supplier sold 42 kg of grain to the buyer ... the agent signd for the stores"}
    right = {**point, "words": "The supplier sold 42 kg of grain to the buyer ... The supplier's agent signed for the stores"}
    model = Settling({"together": {"client_people": [], "connections": [point]}},
                     {"together": {"settled": [settled(0, "clerical", right, key="connection")]}})
    [kept] = connections_of(model, sent(("deed.pdf", DEED), ("note.pdf", NOTE)))[0]
    assert kept["anchored"] and kept["settled"] == "clerical" and [p["document"] for p in kept["places"]] == ["deed.pdf", "note.pdf"]
    assert model.settles()[0].system == SETTLE_POINTS


def test_the_understanding_is_checked_with_the_tolerant_finder_and_never_told_to_drop_a_fact_for_a_slip():
    context = {**sent(("deed.pdf", [(1, "The supp lier sold 42 kg of grain to the buyer at the depot.")])), "latest": {"text": "Read."}}
    facts = {"facts": [{"id": "F1", "fact": "A sale.", "advocate_words": "The supplier sold 42 kg of grain to the buyer",
                        "certainty": "reported"}], "disputes": [], "related_points": [], "needs_research": False}
    assert research.code_checks(facts, context) == []
    facts["facts"][0]["advocate_words"] = "The supplier sold 42 kg of grain to the buyr"
    [problem] = research.code_checks(facts, context)
    assert "slip" in problem["fix"] and "remove the fact" not in problem["fix"]
    assert "only part of this fact" in problem["fix"]


def test_a_v14_record_is_checked_with_the_finder_it_was_made_under():
    model = Settling({"deed.pdf": [SLIP]}, {"deed.pdf": {"settled": [settled(0, "clerical", RIGHT)], "added": []}})
    context = sent(("deed.pdf", DEED))
    events, failures = chronology_of(model, context)
    issues = research._chronology_issues(events, failures, context, True, research.TOLERANT_FINDER)
    assert issues == []
    tampered = [{**events[0], "date_found": "file"}]
    with pytest.raises(SchemaViolation):
        research._chronology_issues(tampered, failures, context, True, research.TOLERANT_FINDER)
    assert research.SETTLED_CONTRACT == "core_research_v14" and WHOLE_FILE_CONTRACT == "core_research_v13"
    assert {CONTRACT, research.SETTLED_CONTRACT} <= set(research.SETTLED) and WHOLE_FILE_CONTRACT not in research.SETTLED
    assert all(CONTRACT in group for group in (research.QUESTION_PLANS, research.JUDGMENT_PICKS, research.BY_DISPUTE,
                                                research.JUDGMENTS_READ, research.CHRONICLED, research.WHOLE_FILE))
    assert accept  # the v14 plan's own round trip is exercised by the plan tests


def test_the_settling_prompt_says_what_code_checked_and_asks_for_a_verdict_never_a_worked_out_date():
    for prompt in (SETTLE_EVENTS, SETTLE_TRANSFERS, SETTLE_POINTS):
        assert prompt.startswith("Message: You ") and "\n\nPurpose: " in prompt and "\n\nLook for:\n" in prompt
        assert "\n\nOutcome: settled" in prompt and "Never work out a date or a figure" in prompt
        for verdict in research.VERDICTS:
            assert f"verdict {verdict}" in prompt or f"(verdict {verdict})" in prompt
    assert "not_carried" in SETTLE_EVENTS and "added" in SETTLE_EVENTS and "not_carried" not in SETTLE_TRANSFERS


def test_a_paper_is_read_for_every_legally_significant_point_and_each_kind_is_kept_as_an_event_is():
    # Research v14 (AN.33, D17): findings, statements, documents' particulars, relationships and status are points of their own.
    page = [(1, "ORDER of 3-9-2014. The board found that the lessor had consented to the transfer. The board directed the entry "
                "to be restored. The lessee says he paid the rent. Deed No. 41 was presented for registration on 5-1-2013. "
                "Sri T. Ramesh, son of the late lessor, holds a power of attorney. The appeal is still pending.")]
    points = [event("3-9-2014", "order", "The board directed the entry to be restored.", "The board directed the entry to be restored"),
              event("3-9-2014", "finding", "In its order, the board found the lessor had consented.",
                    "The board found that the lessor had consented to the transfer", "the board"),
              event("undated", "statement", "The lessee says he paid the rent.", "The lessee says he paid the rent", "the lessee"),
              event("5-1-2013", "document", "Deed No. 41 was presented on 5-1-2013.",
                    "Deed No. 41 was presented for registration on 5-1-2013"),
              event("undated", "relationship", "Sri T. Ramesh is the lessor's son and holds a power of attorney.",
                    "Sri T. Ramesh, son of the late lessor, holds a power of attorney"),
              event("undated", "pending", "The appeal is pending.", "The appeal is still pending")]
    model = Settling({"order.pdf": points})
    events, failures = chronology_of(model, sent(("order.pdf", page)))
    assert failures == [] and model.settles() == []
    assert sorted(e["kind"] for e in events) == ["document", "finding", "order", "pending", "relationship", "statement"]
    assert all(e["anchored"] for e in events)
    [reading] = [call for call in model.calls if call.system == research.CHRONOLOGY_V14
                 and research.SECOND_PASS.splitlines()[0] not in call.user]
    assert reading.operation == "core_research_chronology" and "(kind finding)" in reading.system


# Piece 33e (AN.33, D17): completeness by code - identifiers and pages of a paper no point carries are asked about once, in its
# settling call, beside the dates no point carries.
LEDGER = [(1, "Register of the depot. Agreement No. 7 dated 3-9-2014: the supplier sold 42 kg of grain to the buyer. Entry made "
              "by the clerk in the presence of the keeper of the stores, who signed the register as its witness."),
          (2, "The buyer's claim, Claim No. 58 of 2014, stands referred to the board, which has kept it pending for its next "
              "sitting, the parties being told to bring their papers and their witnesses to it, and the keeper of the stores being "
              "told to bring the register of the depot with them.")]


def test_an_identifier_and_a_page_no_point_carries_are_asked_about_and_what_the_model_adds_is_kept():
    claim = event("undated", "pending", "Claim No. 58 of 2014 is pending before the board.",
                  "Claim No. 58 of 2014, stands referred to the board, which has kept it pending")
    model = Settling({"ledger.pdf": [RIGHT]}, {"ledger.pdf": {"settled": [], "added": [claim]}})
    events = chronology_of(model, sent(("ledger.pdf", LEDGER)))[0]
    evidence = shown(model.settles()[0])
    assert evidence["identifiers_not_carried"] == [{"identifier": "No. 58 of 2014", "page": 2}]
    assert evidence["pages_without_points"] == [2] and evidence["to_check"] == []
    assert [e["kind"] for e in events] == ["transaction", "pending"] and events[1]["anchored"]


def test_what_a_point_carries_a_copy_of_a_covered_page_and_a_short_page_are_not_asked_about():
    claim = event("undated", "pending", "Claim No. 58/2014 is pending.", "Claim No. 58 of 2014, stands referred to the board")
    copy = [(1, LEDGER[0][1])]
    model = Settling({"ledger.pdf": [RIGHT, claim], "copy.pdf": []})
    chronology_of(model, sent(("ledger.pdf", LEDGER), ("copy.pdf", copy), ("cover.pdf", [(1, "Cover of the file.")])))
    assert model.settles() == [], "the identifier is carried, the copy's page is read, and the cover holds too little"


def test_a_date_is_no_identifier_and_the_numbers_of_an_identifier_are_what_count():
    assert research._cores("dated 12/07/2021, in O.S. No. 4418 of 2016 and in file K / 58 / 2014") == {"4418/2016", "58/2014"}
    assert research._cores("No. 7") == set(), "fewer than three digits says too little"
