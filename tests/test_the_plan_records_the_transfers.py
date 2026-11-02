"""The plan records the transactions the papers record (plan AN.27, P13d, slice 2; AN.28, D7; AN.29, D9; invariant I6).

Each document is read, beside the chronology and the understanding, for the transactions it records - who gave what to whom, what it
concerns (the subject), the figure exactly as the page writes it and the model's reading of it into numbers and units, any whole the
passage states, and the death of the giver where the papers record one. Code finds the words on the pages, reads the dates, orders and
numbers them X1..., has a paper looked at again once where a number or a unit is not in its words, and keeps the plan with what is
left; the plan is refused if what it keeps is not what the papers show. The figures themselves are added by figures.py, never here.
The fields are optional in research v12 so every plan saved before validates as it did. The papers here are synthetic.
"""
import re
import threading
from copy import deepcopy

import pytest

from nm.core_engine import figures, research
from nm.core_engine.research import accept, plan, retrieve, transfers_of
from nm.shared.model_port import SchemaViolation, UsageLimitReached
from tests.test_core_research import Model, operations, proposal, searcher
from tests.test_core_understanding import context as typed
from tests.test_the_chronology_of_each_document import DEED, SCRIPT, row
from tests.test_the_plan_records_the_chronology import Beside, bundle, sent

pytestmark = pytest.mark.class_a


def reading(figure):
    """The model's reading of a figure that is one number against one unit (invented): the number and the unit as the page writes
    them, the unit named from the table of units. A figure with no unit beside a number is read as no figure."""
    found = figures.quantities_in(figure or "")
    if not found:
        return {"dimension": "none", "parts": []}
    text, number, unit = found[0]
    return {"dimension": figures.UNITS[unit].dimension,
            "parts": [{"number": number.replace(",", ""), "unit": unit, "written": re.sub(r"[\d,.\s]+", "", text)}]}


def transfer(date, subject, figure, words, *, whole="", frm="the supplier", to="the purchasers", kind="sale", quantity=None,
             whole_quantity=None, instrument="", giver_died=""):
    """A transaction as the model lists it (invented), its figure and whole read as `reading` reads them unless told otherwise."""
    return {"date": date, "kind": kind, "subject": subject, "figure": figure, "quantity": quantity or reading(figure),
            "whole": whole, "whole_quantity": whole_quantity or reading(whole), "from": frm, "to": to, "instrument": instrument,
            "giver_died": giver_died, "words": words}


SOLD = {
    "deed.pdf": [
        transfer("30-10-1985", "Lot 487", "118 kg", "The supplier sold 118 kg to the purchasers", whole="824 kg"),
        transfer("1 January 2020", "Lot 487", "10 kg", "A sale made on a day the page lacks")],
    "order.pdf": [
        transfer("undated", "Lot 487/A", "29 kg", "Suits O.S. 891 of 2014 and 892 of 2014 are pending before the District Court")]}


def kept():
    return plan(Beside(SCRIPT, transfers=SOLD), bundle())


def test_each_documents_transactions_are_anchored_dated_ordered_and_numbered():
    model = Beside(SCRIPT, transfers=SOLD)
    found, failures = transfers_of(model, bundle())
    assert failures == []
    assert [(t["id"], t["sort"], t["document"], t["pages"], t["anchored"]) for t in found] == [
        ("X1", "1985-10-30", "deed.pdf", [1], True), ("X2", "2020-01-01", "deed.pdf", [], False), ("X3", "", "order.pdf", [2], True)]
    first = found[0]
    assert (first["subject"], first["figure"], first["whole"], first["from"], first["to"], first["kind"]) == (
        "Lot 487", "118 kg", "824 kg", "the supplier", "the purchasers", "sale")
    assert first["quantity"] == {"dimension": "mass", "parts": [{"number": "118", "unit": "kilogram", "written": "kg"}]}
    reads = [prompt.user for prompt in model.calls if prompt.operation == "core_research_transfers" and '"to_check"' not in prompt.user]
    assert len(reads) == 2 and all(sum(f'Document: "{name}"' in text for name in ("deed.pdf", "order.pdf")) == 1 for text in reads)
    # Research v13 (AN.28, D2): each paper with a transaction code cannot use as listed is looked at again once - here a whole on no
    # page and words not found, and a figure whose number is not in its words.
    checks = [prompt.user for prompt in model.calls if '"to_check"' in prompt.user]
    # Each settling call names the paper it checks after the whole file (plan AN.34, piece 34b), as a reading does.
    assert sorted(re.search(r'^Document: "(.*)"', text, re.M).group(1) for text in checks) == ["deed.pdf", "order.pdf"]
    assert transfers_of(model, bundle(), wanted=lambda: False) == ([], []) and transfers_of(model, typed("Hello.")) == ([], [])


def test_transactions_are_ordered_by_the_dates_code_reads_not_by_the_papers_order():
    backwards = {"deed.pdf": list(reversed(SOLD["deed.pdf"])), "order.pdf": SOLD["order.pdf"]}
    found, _ = transfers_of(Beside(SCRIPT, transfers=backwards), bundle())
    assert [t["sort"] for t in found] == ["1985-10-30", "2020-01-01", ""] and [t["id"] for t in found] == ["X1", "X2", "X3"]


def test_the_plan_keeps_the_transactions_and_replays_from_its_own_proposal():
    ctx, made = bundle(), kept()
    assert [t["id"] for t in made["proposal"]["transfers"]] == ["X1", "X2", "X3"] and made["proposal"]["transfers_failures"] == []
    assert made["proposal"]["transfers"] == transfers_of(Beside(SCRIPT, transfers=SOLD), ctx)[0]
    assert accept(made["proposal"], ctx) == made and made["issues"] == [], "a transaction not located is marked, not an issue"
    record = retrieve(made, searcher(), ctx, model=Model())
    assert research.validate(record, made, ctx) == record


def test_the_readings_of_the_papers_and_the_understanding_are_all_in_flight_together():
    class Trio(Beside):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.gate = threading.Barrier(3)

        def structured(self, prompt, schema, tier, **kwargs):
            if (prompt.operation in ("core_research_understand", "core_research_chronology", "core_research_transfers")
                    and '"to_check"' not in prompt.user and research.SECOND_PASS.splitlines()[0] not in prompt.user):
                self.gate.wait(timeout=10)          # the look again and the second pass come after the readings, on their own
            return super().structured(prompt, schema, tier, **kwargs)
    made = plan(Trio({"deed.pdf": SCRIPT["deed.pdf"]}, transfers={"deed.pdf": SOLD["deed.pdf"]}),
                sent(*[row("t1", 1, "deed.pdf", n, text) for n, text in DEED]))
    assert len(made["proposal"]["transfers"]) == 2


def _renumber(items):
    for number, found in enumerate(items, 1):
        found["id"] = f"X{number}"


CASES = [
    ("a number out of turn", lambda p: p["transfers"][0].update(id="X2"), "numbered"),
    ("a transaction of no document of this turn", lambda p: p["transfers"][0].update(source="t9:d9"), "no document of this turn"),
    ("a transaction under another document's name", lambda p: p["transfers"][0].update(document="order.pdf"), "no document of this turn"),
    ("a sort date its date does not give", lambda p: p["transfers"][0].update(sort="1999-01-01"), "dated otherwise"),
    ("a sort date of the giver's death that it does not give",
     lambda p: p["transfers"][0].update(giver_died="4-4-2003", giver_died_sort="1999-01-01"), "recorded death reads"),
    ("a later date before an earlier", lambda p: (p["transfers"].insert(0, p["transfers"].pop(1)), _renumber(p["transfers"])),
     "out of the order"),
    ("words said to be found that are not", lambda p: p["transfers"][1].update(anchored=True, pages=[1]), "not anchored as"),
    ("words found that are said not to be", lambda p: p["transfers"][0].update(anchored=False, pages=[]), "not anchored as"),
    ("pages that are not the words' pages", lambda p: p["transfers"][0].update(pages=[2]), "not anchored as"),
    ("a stretch that failed in a document not sent",
     lambda p: p.update(transfers_failures=[{"document": "nope.pdf", "pages": "1", "reason": "x"}]), "names no document"),
    ("a kind outside the vocabulary", lambda p: p["transfers"][0].update(kind="gossip"), "vocabulary"),
    ("a transaction with a field left out", lambda p: p["transfers"][0].pop("subject"), "missing"),
    ("a transaction whose reading of its figure is left out", lambda p: p["transfers"][0].pop("quantity"), "missing"),
]


@pytest.mark.parametrize("label,change", [(case[0], case[1]) for case in CASES], ids=[case[0] for case in CASES])
def test_a_plan_whose_transactions_are_not_what_the_papers_show_is_refused(label, change):
    proposed = deepcopy(kept()["proposal"])
    change(proposed)
    message = next(case[2] for case in CASES if case[0] == label)
    with pytest.raises(SchemaViolation, match=message):
        accept(proposed, bundle())


def test_a_stretch_whose_transactions_could_not_be_read_is_an_issue_and_the_rest_is_kept():
    made = plan(Beside(SCRIPT, transfers=SOLD, transfers_unreadable=["order.pdf"]), bundle())
    assert made["proposal"]["transfers_failures"] == [{"document": "order.pdf", "pages": "1-2", "reason": "SchemaViolation"}]
    assert [issue["mismatch"] for issue in made["issues"]] == ["transfers unavailable for order.pdf (pages 1-2): SchemaViolation"]
    assert {t["document"] for t in made["proposal"]["transfers"]} == {"deed.pdf"}


def test_a_usage_limit_in_reading_the_transactions_stops_the_plan():
    with pytest.raises(UsageLimitReached):
        plan(Beside(SCRIPT, transfers=SOLD, transfers_usage_limit=["deed.pdf"]), bundle())


def test_no_documents_make_no_transactions_without_a_call_and_a_plan_saved_before_them_validates():
    model = Beside()
    none = plan(model, typed("Find the applicable law."))
    assert none["proposal"]["transfers"] == [] and "core_research_transfers" not in operations(model)
    before = accept(proposal(), typed("Find the applicable law."))
    assert "transfers" not in before["proposal"] and accept(before["proposal"], typed("Find the applicable law.")) == before


PAPERS = [row("t1", 1, "agreement.pdf", 1, "Agreement No. 77 dated 5-6-2003. The supplier sold 500 kg of grain to the purchaser."),
          row("t1", 2, "certificate.pdf", 1, "Certificate. The supplier died on 4-4-2003 at the town hospital.")]


def agreement(giver_died):
    return {"agreement.pdf": [transfer("5-6-2003", "Contract 77", "500 kg", "The supplier sold 500 kg of grain to the purchaser",
                                       giver_died=giver_died, instrument="Agreement No. 77", to="the purchaser")]}


def test_the_death_of_a_giver_that_some_paper_of_the_file_records_is_kept_and_read_as_a_date():
    # Invented: the death is recorded in another paper than the transaction.
    model = Beside({}, transfers=agreement("4-4-2003"))
    (found,), _ = transfers_of(model, sent(*PAPERS))
    assert (found["giver_died"], found["giver_died_sort"]) == ("4-4-2003", "2003-04-04")
    assert not [prompt for prompt in model.calls if '"to_check"' in prompt.user], "nothing to look at again"


def test_a_death_that_no_page_of_the_file_records_is_settled_once_and_then_kept_but_never_used():
    # Research v14 (AN.33, D18): kept as the papers' reading, marked as not found, never read as a date to judge what came after.
    model = Beside({}, transfers=agreement("9-9-1999"))
    (found,), _ = transfers_of(model, sent(*PAPERS))
    (checked,) = [prompt.user for prompt in model.calls if '"to_check"' in prompt.user]
    assert "the death it records for the giver stands on no page of the papers" in checked
    assert (found["giver_died"], found["giver_died_found"], found["giver_died_sort"]) == ("9-9-1999", False, "")
    assert found["figure"] == "500 kg" and found["anchored"] is True and found["date"] == "5-6-2003"


def test_a_transaction_whose_date_stands_nowhere_in_the_papers_keeps_it_marked_so_and_keeps_its_words():
    wrong = {"agreement.pdf": [transfer("9-9-2009", "Contract 77", "500 kg", "The supplier sold 500 kg of grain to the purchaser")]}
    (found,), _ = transfers_of(Beside({}, transfers=wrong), sent(*PAPERS))
    assert (found["date"], found["sort"], found["anchored"], found["date_found"]) == ("9-9-2009", "2009-09-09", True, "nowhere")


def test_the_transactions_prompts_are_for_any_matter_and_each_paper_is_read_with_the_whole_file_in_view():
    prompt = " ".join(research.TRANSACTIONS_V13.split())
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "whatever passes from one person to another",
                 "so that code can add the figures up for each subject", "You are not adding or working out", "Work in a loop",
                 "(subject: the asset, account, contract or case, named as the papers most commonly name it",
                 "where the papers record that the giver had died by then, the date of that death as the papers give it (giver_died",
                 "its dimension - money, area, length, mass or volume", "share where it is a part of a whole",
                 "each number exactly as the page writes it, in digits", "You convert and add nothing",
                 "do not add or work out a figure the page does not give"):
        assert part in prompt, part
    check = " ".join(research.SETTLE_TRANSFERS.split())
    for part in ("Message:", "Purpose:", "Outcome:", "that its figure and any whole it states can be checked against those words",
                 "the death it records of the giver stands in the papers", "copied from the page exactly as they stand there",
                 "so that every number you give is in the words", "Work in a loop"):
        assert part in check, part
    model = Beside(SCRIPT, transfers=SOLD)
    transfers_of(model, bundle())
    reads = [prompt for prompt in model.calls if prompt.operation == "core_research_transfers" and '"to_check"' not in prompt.user]
    assert len(reads) == 2 and all(prompt.system == research.TRANSACTIONS_V13 for prompt in reads)
    for prompt in reads:
        mine, rest = prompt.user.split("The pages you read for:")[1], prompt.user.split("The pages you read for:")[0]
        other = "order.pdf" if 'Document: "deed.pdf"' in mine else "deed.pdf"
        assert f'Paper "{other}"' in rest and "The advocate's messages, oldest first:" in rest
    assert research.TRANSACTION_KINDS == ("sale", "partition", "gift", "settlement", "decree", "lease", "mortgage", "loan", "payment",
                                          "other")
    wire = research.TRANSACTIONS_SCHEMA["properties"]["transfers"]["items"]["properties"]
    assert set(wire) == {"date", "kind", "subject", "figure", "quantity", "whole", "whole_quantity", "from", "to", "instrument",
                         "giver_died", "words"}
    assert wire["quantity"]["properties"]["dimension"]["enum"] == list(figures.FIGURE_KINDS)
    unit = wire["quantity"]["properties"]["parts"]["items"]["properties"]["unit"]
    assert "enum" not in unit, "the model names a unit in plain words; code resolves it by its table"
