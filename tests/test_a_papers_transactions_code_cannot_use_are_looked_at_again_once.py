"""A paper's transactions that code cannot use are looked at again once (plan AN.28, D2 and D3; AN.29, D9; invariant I6).

The model reads each paper's transactions with the whole file in view, and reads each figure into numbers and units. Code checks the
words are on the paper's pages, that every number and unit of the figure and of any whole stands in those words, that a death the
transaction records for its giver stands on some page of the file, and that its date stands in its words or its paper; where it finds
what it cannot use, the paper is looked at again in one call, shown what code found, and what that gives replaces what was at fault.
What is still at fault is kept, listed and never added; a date the paper lacks is dropped; so is a death on no page. The papers are
invented.
"""
import pytest

from nm.core_engine import figures, research
from nm.core_engine.figures import ledger
from tests.test_core_research import _result
from tests.test_the_chronology_of_each_document import row
from tests.test_the_plan_records_the_chronology import Beside, sent
from tests.test_the_plan_records_the_transfers import transfer

pytestmark = pytest.mark.class_a


class LooksAgain(Beside):
    """A reader of transactions whose look again gives what `again` gives for its paper."""

    def __init__(self, first, again):
        super().__init__({}, transfers=first)
        self.again = again

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_transfers" and '"to_check"' in prompt.user:
            self.calls.append(prompt)
            return _result({"transfers": self.again.get(prompt.user.split('"')[1], [])}, tier)
        return super().structured(prompt, schema, tier, **kwargs)


PAPER = [row("t1", 1, "agreement.pdf", 1, "Agreement No. 77 dated 5-6-2003. The supplier sold 500 kg of grain out of 1,350 kg to the "
                                          "purchaser for Rs.2,00,000.")]


def sale(figure, words, *, whole="", date="5-6-2003", **more):
    return {**transfer(date, "Contract 77", figure, words, whole=whole, to="the purchaser", **more), "instrument": "Agreement No. 77"}


def test_a_transaction_code_cannot_use_is_looked_at_again_once_and_what_the_look_gives_is_kept():
    # Invented: the figure given is not the page's; looked at again, the model gives the page's own.
    model = LooksAgain({"agreement.pdf": [sale("510 kg", "The supplier sold 500 kg of grain")]},
                       {"agreement.pdf": [sale("500 kg", "The supplier sold 500 kg of grain out of 1,350 kg", whole="1,350 kg")]})
    (kept,), failures = research.transfers_of(model, sent(*PAPER))
    (checked,) = [prompt for prompt in model.calls if '"to_check"' in prompt.user]
    assert checked.system == research.TRANSACTIONS_CHECK and f'"why": "{figures.NOT_IN_WORDS}"' in checked.user and failures == []
    assert "nearest_words" not in checked.user, "its words were found; it is its figure that is not in them"
    assert (kept["figure"], kept["whole"], kept["anchored"]) == ("500 kg", "1,350 kg", True)
    (subject,) = ledger([kept])
    assert subject["givers"][0]["added"] == {"mass": 500_000}
    assert subject["totals"][0]["by_giver"] == [{"giver": "the supplier", "leaves": 850_000, "exceeds": None}]


def test_words_not_found_are_looked_at_again_with_the_pages_own_words_nearest_to_them():
    model = LooksAgain({"agreement.pdf": [sale("500 kg", "The suplier sold 500 kg of grain")]},
                       {"agreement.pdf": [sale("500 kg", "The supplier sold 500 kg of grain")]})
    (kept,), _ = research.transfers_of(model, sent(*PAPER))
    (checked,) = [prompt for prompt in model.calls if '"to_check"' in prompt.user]
    assert '"why": "its words are not found on the pages"' in checked.user and '"nearest_words"' in checked.user
    assert (kept["words"], kept["anchored"]) == ("The supplier sold 500 kg of grain", True)


def test_a_transaction_still_at_fault_is_kept_listed_and_never_added_and_a_date_its_paper_lacks_is_dropped():
    first = [sale("Rs.3,00,000", "The supplier sold 500 kg of grain", date="9-9-2009")]
    model = LooksAgain({"agreement.pdf": first}, {"agreement.pdf": first})
    (kept,), _ = research.transfers_of(model, sent(*PAPER))
    assert kept["date"] == "undated" and kept["sort"] == "", "a date on no page of its paper is not kept"
    (subject,) = ledger([kept])
    assert subject["givers"] == [] and subject["unread"][0]["why"] == figures.NOT_IN_WORDS


def test_a_paper_whose_transactions_all_check_out_needs_no_look_again():
    model = LooksAgain({"agreement.pdf": [sale("500 kg", "The supplier sold 500 kg of grain out of 1,350 kg", whole="1,350 kg")]}, {})
    research.transfers_of(model, sent(*PAPER))
    assert not [prompt for prompt in model.calls if '"to_check"' in prompt.user]


def test_a_look_again_that_gives_the_whole_list_again_adds_only_what_is_new():
    good = sale("500 kg", "The supplier sold 500 kg of grain out of 1,350 kg", whole="1,350 kg")
    bad = sale("900 kg", "The supplier sold 500 kg of grain", date="9-9-2009")
    model = LooksAgain({"agreement.pdf": [good, bad]}, {"agreement.pdf": [good, bad]})
    found, _ = research.transfers_of(model, sent(*PAPER))
    assert [(t["id"], t["figure"], t["date"]) for t in found] == [("X1", "500 kg", "5-6-2003"), ("X2", "900 kg", "undated")],         "the one that was right is not kept twice"


def test_a_reading_with_units_of_different_kinds_is_looked_at_again_and_a_share_is_no_fault():
    mixed = sale("500 kg", "The supplier sold 500 kg of grain",
                 quantity={"dimension": "mass", "parts": [{"number": "500", "unit": "rupee", "written": "kg"}]})
    model = LooksAgain({"agreement.pdf": [mixed]}, {"agreement.pdf": [sale("500 kg", "The supplier sold 500 kg of grain")]})
    (kept,), _ = research.transfers_of(model, sent(*PAPER))
    (checked,) = [prompt for prompt in model.calls if '"to_check"' in prompt.user]
    assert "its units are not all of the kind the figure is" in checked.user and kept["quantity"]["parts"][0]["unit"] == "kilogram"
    gift = [row("t1", 1, "gift.pdf", 1, "Gift deed dated 7-7-2007. The donor gave a third share of the shop to her son.")]
    share = transfer("7-7-2007", "Shop 4", "a third share", "The donor gave a third share of the shop to her son", kind="gift",
                     frm="the donor", to="her son", quantity={"dimension": "share", "parts": []})
    model = LooksAgain({"gift.pdf": [share]}, {})
    (kept,), _ = research.transfers_of(model, sent(*gift))
    assert not [prompt for prompt in model.calls if '"to_check"' in prompt.user] and kept["quantity"]["dimension"] == "share"


def test_the_look_again_prompt_says_what_code_found_and_asks_for_the_pages_own_words():
    prompt = " ".join(research.TRANSACTIONS_CHECK.split())
    for part in ("Message:", "Purpose:", "Outcome:", "transactions whose words it could not find on the pages",
                 "whose figure or whole it could not check against those words (a number or a unit not in them)",
                 "whose reading of a figure has a unit code cannot convert or units of different kinds",
                 "whose recorded death of the giver is on no page of the file",
                 "copied exactly from the page as they stand, a misread letter included",
                 "so that every number you give is in the words", "the death of the giver only if the papers record one",
                 "or leave it out if the paper does not record the transaction as you listed it", "Work in a loop"):
        assert part in prompt, part
    assert research.MAX_OUTPUT["transfers_check"] == 12000
