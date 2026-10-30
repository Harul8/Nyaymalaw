"""A checklist item that cannot be grounded does not cost the section (plan AN.27, P17).

In a live run the largest dispute's section was refused three times - and its narrative, which set out the civil route and the orders,
lost - because a checklist item failed its mechanical grounding each time: a status resting on a document page where only the
advocate's own words can show it, a quotation that was not exact, an item resting on neither held law nor the matter's checklist. The
current writer's admission now keeps what can be checked. An item whose status cannot be confirmed is kept as not yet given, with a
note that says so; an item whose law or shape cannot be checked is left out; and the strict checks that remain admit everything kept.
The earlier writers are as strict as they were. The papers are synthetic.
"""
import pytest

from nm.core_engine import response_writer
from nm.shared.model_port import SchemaViolation
from tests.test_core_writer_v13 import item
from tests.test_the_writer_is_shown_the_chronology import Writer, cites, papers, section

pytestmark = pytest.mark.class_a

SALE = "Sale Deed No. 100 dated 30-10-1985"


def message(payload):
    return payload["original_context"]["latest"]["source_id"]


def page(payload):
    return cites(payload)[1]


def written(*makers):
    """A current section whose checklist is the items the makers make from what the writer was shown."""
    def write(payload):
        out = section(payload)
        out["checklist"] = [make(payload) for make in makers]
        return out
    model = Writer(write)
    ctx, record, sources = papers()
    draft = response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert response_writer.validate(draft, ctx, sources) == draft, "saved and read again exactly as admitted"
    return draft["checklists"][0]["items"], model


def good(payload):
    return item(payload, "The sale deed", ["the sale deed"])


def named(label, **changes):
    return lambda payload: {**item(payload, label), **changes}


def standing(need, status, evidence, **changes):
    return lambda payload: {**item(payload, need), "status": status, "evidence": evidence(payload) if evidence else None, **changes}


def test_a_status_a_document_cannot_show_is_kept_as_not_yet_given_and_says_so():
    items, _ = written(good, standing("Current orders", "coming_or_unclear", lambda p: {"source_id": page(p), "quote": SALE}))
    assert [i["need"] for i in items] == ["The sale deed", "Current orders"]
    orders = items[1]
    assert (orders["status"], orders["evidence"], orders["note"]) == ("not_given", None, response_writer.UNCONFIRMED)
    assert orders["law"] is not None and orders["group"] == "needed", "what the law requires of it is kept"


def test_a_status_whose_words_are_not_exact_is_kept_as_not_yet_given():
    items, _ = written(standing("Current orders", "coming_or_unclear",
                                lambda p: {"source_id": message(p), "quote": "words the advocate never wrote"}))
    assert (items[0]["status"], items[0]["evidence"], items[0]["note"]) == ("not_given", None, response_writer.UNCONFIRMED)


def test_a_status_that_names_no_words_is_kept_as_not_yet_given():
    items, _ = written(standing("Current orders", "in_hand", None))
    assert (items[0]["status"], items[0]["evidence"], items[0]["note"]) == ("not_given", None, response_writer.UNCONFIRMED)


def test_an_item_not_given_that_names_words_is_kept_without_them_and_without_a_note():
    items, _ = written(standing("Current orders", "not_given", lambda p: {"source_id": message(p), "quote": "Find the applicable law"}))
    assert (items[0]["status"], items[0]["evidence"], items[0]["note"]) == ("not_given", None, None)


def test_a_status_that_can_be_confirmed_is_kept_as_the_writer_gave_it():
    items, _ = written(
        standing("Deed in hand", "in_hand", lambda p: {"source_id": page(p), "quote": SALE}),
        standing("Order promised", "coming_or_unclear", lambda p: {"source_id": message(p), "quote": "Find the applicable law"},
                 note="promised tomorrow"))
    assert [(i["status"], i["note"]) for i in items] == [("in_hand", None), ("coming_or_unclear", "promised tomorrow")]
    assert items[0]["evidence"]["source_id"] == "t1:d1p1" and items[1]["evidence"]["source_id"] == "t2:advocate"


@pytest.mark.parametrize("label,change", [
    ("law and no item of the matter's checklist", {"law": None}),
    ("law that is not held words", {"law": {"source_id": "P1", "quote": "words no held passage holds"}}),
    ("a need that says nothing", {"need": "  "}),
    ("a reason that says nothing", {"why": " "}),
    ("an item of the matter's checklist that is not on it", {"carries": "t0:c9"}),
])
def test_an_item_whose_law_or_shape_cannot_be_checked_is_left_out_and_the_rest_is_kept(label, change):
    items, _ = written(named("Unsupported item", **change), good)
    assert [i["need"] for i in items] == ["The sale deed"]
    assert items[0]["id"].endswith("s0c1"), "the items that stand are numbered from one"


def test_the_ask_of_an_item_stays_with_that_item_when_another_is_left_out():
    items, _ = written(named("Unsupported item", law=None, asked_words=["Appeal against the order"]), good)
    (kept,) = items
    assert [a["text"] for a in kept["asked"]] == ["the sale deed"] and kept["asked"][0]["unit_id"].endswith("b2")


def test_a_section_whose_every_item_is_left_out_is_still_the_section():
    items, _ = written(named("Unsupported item", law=None))
    assert items == []


def test_the_earlier_writers_are_as_strict_as_they_were():
    ctx, record, sources = papers()
    _, model = written(good)
    payload = model.seen[0][1]
    bad = {**item(payload, "Unsupported item"), "law": None}
    proposal = {"units": [{"kind": "summary", "text": "In short.", "uses": []}],
                "checklists": [{"checklist": [bad], "time_limit_ids": []}]}
    with pytest.raises(SchemaViolation, match="never both or neither"):
        response_writer.accept(proposal, ctx, sources, contract=response_writer.SECTION_CONTRACT,
                               parts=[{"dispute_id": "D1", "units": 1}], section=0)


def test_the_prompt_says_what_an_items_status_may_rest_on_and_that_an_unsupported_item_is_not_listed():
    prompt = " ".join(response_writer.SYSTEM_V13.split())
    for part in ("A document page can show an item in_hand and nothing else: where a document speaks to an item without holding it, "
                 "the item is not_given, with no words.",
                 "An item that no held passage requires is not on the checklist, however useful it would be: put it in your next steps instead."):
        assert part in prompt, part
    assert "A document page can show an item in_hand" not in response_writer.SYSTEM
