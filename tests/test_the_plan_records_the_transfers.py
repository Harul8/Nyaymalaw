"""The plan records the transfers of land the papers record (plan AN.27, P13d, slice 2; invariant I6).

Each document is read, beside the chronology and the understanding, for the transfers of land it records - who gave an extent of
which parcel to whom, the extent exactly as the page writes it, the parcel's whole extent where the passage states it. Code finds the
words on the pages, reads the date, orders and numbers them X1..., and keeps them with the plan, which is refused if what it keeps is
not what the papers show; the extents themselves are read and added by extents.py, never here. The fields are optional in research v12
so every plan saved before validates as it did. The papers here are synthetic.
"""
import threading
from copy import deepcopy

import pytest

from nm.core_engine import extents, research
from nm.core_engine.research import accept, plan, retrieve, transfers_of
from nm.shared.model_port import SchemaViolation, UsageLimitReached
from tests.test_core_research import Model, operations, proposal, searcher
from tests.test_core_understanding import context as typed
from tests.test_the_chronology_of_each_document import DEED, SCRIPT, row
from tests.test_the_plan_records_the_chronology import Beside, bundle, sent

pytestmark = pytest.mark.class_a


def transfer(date, parcel, extent, words, *, total="", frm="the vendor", to="the purchasers", kind="sale"):
    return {"date": date, "kind": kind, "parcel": parcel, "extent": extent, "total": total, "from": frm, "to": to, "words": words}


SOLD = {
    "deed.pdf": [
        transfer("30-10-1985", "Sy.No.487", "Ac.1.18 guntas", "The vendor sold Ac.1.18 guntas to the purchasers", total="Ac.8.24 guntas"),
        transfer("1 January 2020", "Sy.No.487", "Ac.0.10", "A sale made on a day the page lacks")],
    "order.pdf": [
        transfer("undated", "Sy.No.487/A", "Ac.0.29", "Suits O.S. 891 of 2014 and 892 of 2014 are pending before the District Court")]}


def kept():
    return plan(Beside(SCRIPT, transfers=SOLD), bundle())


def test_each_documents_transfers_are_anchored_dated_ordered_and_numbered():
    model = Beside(SCRIPT, transfers=SOLD)
    found, failures = transfers_of(model, bundle())
    assert failures == []
    assert [(t["id"], t["sort"], t["document"], t["pages"], t["anchored"]) for t in found] == [
        ("X1", "1985-10-30", "deed.pdf", [1], True), ("X2", "2020-01-01", "deed.pdf", [], False), ("X3", "", "order.pdf", [2], True)]
    first = found[0]
    assert (first["parcel"], first["extent"], first["total"], first["from"], first["to"], first["kind"]) == (
        "Sy.No.487", "Ac.1.18 guntas", "Ac.8.24 guntas", "the vendor", "the purchasers", "sale")
    reads = [prompt.user for prompt in model.calls if prompt.operation == "core_research_transfers" and '"to_check"' not in prompt.user]
    assert len(reads) == 2 and all(sum(f'Document: "{name}"' in text for name in ("deed.pdf", "order.pdf")) == 1 for text in reads)
    # Research v13 (AN.28, D2): each paper with a transaction code cannot use as listed is looked at again once - here a whole and a
    # figure on no page, and words not found.
    checks = [prompt.user for prompt in model.calls if '"to_check"' in prompt.user]
    assert sorted(text.split('"')[1] for text in checks) == ["deed.pdf", "order.pdf"]
    assert transfers_of(model, bundle(), wanted=lambda: False) == ([], []) and transfers_of(model, typed("Hello.")) == ([], [])


def test_transfers_are_ordered_by_the_dates_code_reads_not_by_the_papers_order():
    backwards = {"deed.pdf": list(reversed(SOLD["deed.pdf"])), "order.pdf": SOLD["order.pdf"]}
    found, _ = transfers_of(Beside(SCRIPT, transfers=backwards), bundle())
    assert [t["sort"] for t in found] == ["1985-10-30", "2020-01-01", ""] and [t["id"] for t in found] == ["X1", "X2", "X3"]


def test_the_plan_keeps_the_transfers_and_replays_from_its_own_proposal():
    ctx, made = bundle(), kept()
    assert [t["id"] for t in made["proposal"]["transfers"]] == ["X1", "X2", "X3"] and made["proposal"]["transfers_failures"] == []
    assert made["proposal"]["transfers"] == transfers_of(Beside(SCRIPT, transfers=SOLD), ctx)[0]
    assert accept(made["proposal"], ctx) == made and made["issues"] == [], "a transfer not located is marked, not an issue"
    record = retrieve(made, searcher(), ctx, model=Model())
    assert research.validate(record, made, ctx) == record


def test_the_readings_of_the_papers_and_the_understanding_are_all_in_flight_together():
    class Trio(Beside):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.gate = threading.Barrier(3)

        def structured(self, prompt, schema, tier, **kwargs):
            if (prompt.operation in ("core_research_understand", "core_research_chronology", "core_research_transfers")
                    and '"to_check"' not in prompt.user):
                self.gate.wait(timeout=10)          # the look again comes after the readings, on its own
            return super().structured(prompt, schema, tier, **kwargs)
    made = plan(Trio({"deed.pdf": SCRIPT["deed.pdf"]}, transfers={"deed.pdf": SOLD["deed.pdf"]}),
                sent(*[row("t1", 1, "deed.pdf", n, text) for n, text in DEED]))
    assert len(made["proposal"]["transfers"]) == 2


def _renumber(items):
    for number, found in enumerate(items, 1):
        found["id"] = f"X{number}"


CASES = [
    ("a number out of turn", lambda p: p["transfers"][0].update(id="X2"), "numbered"),
    ("a transfer of no document of this turn", lambda p: p["transfers"][0].update(source="t9:d9"), "no document of this turn"),
    ("a transfer under another document's name", lambda p: p["transfers"][0].update(document="order.pdf"), "no document of this turn"),
    ("a sort date its date does not give", lambda p: p["transfers"][0].update(sort="1999-01-01"), "dated otherwise"),
    ("a later date before an earlier", lambda p: (p["transfers"].insert(0, p["transfers"].pop(1)), _renumber(p["transfers"])),
     "out of the order"),
    ("words said to be found that are not", lambda p: p["transfers"][1].update(anchored=True, pages=[1]), "not anchored as"),
    ("words found that are said not to be", lambda p: p["transfers"][0].update(anchored=False, pages=[]), "not anchored as"),
    ("pages that are not the words' pages", lambda p: p["transfers"][0].update(pages=[2]), "not anchored as"),
    ("a stretch that failed in a document not sent",
     lambda p: p.update(transfers_failures=[{"document": "nope.pdf", "pages": "1", "reason": "x"}]), "names no document"),
    ("a kind outside the vocabulary", lambda p: p["transfers"][0].update(kind="gossip"), "vocabulary"),
    ("a transfer with a field left out", lambda p: p["transfers"][0].pop("extent"), "missing"),
]


@pytest.mark.parametrize("label,change", [(case[0], case[1]) for case in CASES], ids=[case[0] for case in CASES])
def test_a_plan_whose_transfers_are_not_what_the_papers_show_is_refused(label, change):
    proposed = deepcopy(kept()["proposal"])
    change(proposed)
    message = next(case[2] for case in CASES if case[0] == label)
    with pytest.raises(SchemaViolation, match=message):
        accept(proposed, bundle())


def test_a_stretch_whose_transfers_could_not_be_read_is_an_issue_and_the_rest_is_kept():
    made = plan(Beside(SCRIPT, transfers=SOLD, transfers_unreadable=["order.pdf"]), bundle())
    assert made["proposal"]["transfers_failures"] == [{"document": "order.pdf", "pages": "1-2", "reason": "SchemaViolation"}]
    assert [issue["mismatch"] for issue in made["issues"]] == ["transfers unavailable for order.pdf (pages 1-2): SchemaViolation"]
    assert {t["document"] for t in made["proposal"]["transfers"]} == {"deed.pdf"}


def test_a_usage_limit_in_reading_the_transfers_stops_the_plan():
    with pytest.raises(UsageLimitReached):
        plan(Beside(SCRIPT, transfers=SOLD, transfers_usage_limit=["deed.pdf"]), bundle())


def test_no_documents_make_no_transfers_without_a_call_and_a_plan_saved_before_them_validates():
    model = Beside()
    none = plan(model, typed("Find the applicable law."))
    assert none["proposal"]["transfers"] == [] and "core_research_transfers" not in operations(model)
    before = accept(proposal(), typed("Find the applicable law."))
    assert "transfers" not in before["proposal"] and accept(before["proposal"], typed("Find the applicable law.")) == before


def test_the_transfers_of_the_plan_are_added_up_by_extents_and_only_those_whose_words_were_found():
    (parcel, other) = extents.ledger(kept()["proposal"]["transfers"])
    assert parcel["parcel"] == "Sy.No.487" and parcel["sellers"][0]["added"] == {"area": 58} and not parcel["complete"]
    assert [(u["id"], u["why"]) for u in parcel["unread"]] == [("X2", "its words were not found on the page")]
    # Research v13 (AN.28, D3): the whole the model gave and the order's figure stand in none of the words that record their
    # transactions - they are on no page - so the whole is listed and not used, and the figure is not added.
    assert parcel["totals"][0]["text"] == "Ac.8.24 guntas" and parcel["totals"][0]["value"] is None
    assert parcel["totals"][0]["how"] == "its figure is not in the words that record it" and parcel["totals"][0]["by_seller"] == []
    assert other["parcel"] == "Sy.No.487/A" and other["sellers"] == [] and not other["complete"]
    assert [(u["id"], u["why"]) for u in other["unread"]] == [("X3", "its figure is not in the words that record it")]


def test_the_prompt_states_the_message_the_purpose_what_to_look_for_and_the_outcome():
    prompt = " ".join(research.TRANSFERS.split())
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "so that code can add the extents up for each parcel",
                 "You are not adding or working out anything yourself", "exactly as the page writes it",
                 "Do not list a transfer that gives no extent, do not add or work out an extent the page does not give",
                 "Work in a loop"):
        assert part in prompt, part
    assert research.MAX_OUTPUT["transfers"] == 12000 and research.TRANSFER_KINDS == (
        "sale", "partition", "gift", "settlement", "decree", "other")
