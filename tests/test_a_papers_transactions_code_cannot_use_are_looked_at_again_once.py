"""A paper's transactions that code cannot use are looked at again once (plan AN.28, D2 and D3; AN.29, D9; invariant I6).

The model reads each paper's transactions with the whole file in view, and reads each figure into numbers and units. Code checks the
words are on the paper's pages, that every number and unit of the figure and of any whole stands in those words, that a death the
transaction records for its giver stands on some page of the file, and that its date stands in its words or its paper; where it finds
what it cannot use, the paper is looked at again in one call, shown what code found, and what that gives replaces what was at fault.
What is still at fault is kept, listed and never added. From research v14 (AN.33, D18) the look again settles each transaction by its
index, a date found nowhere in the papers is kept and marked so, and a death on no page is kept and never used. The papers are
invented.
"""
import json
import re
import pytest

from nm.core_engine import figures, reasoning, research
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
            # Research v14 (AN.33): the model settles each transaction code could not use, by its index, as `again` gives it.
            name = re.search(r'The pages of the paper being checked:\nDocument: "(.*)"', prompt.user).group(1)
            return _result({"settled": [{"index": index, "verdict": "clerical", "reason": "As the page has it.", "transfer": given}
                                        for index, given in enumerate(self.again.get(name, []))]}, tier)
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
    assert checked.system == research.SETTLE_TRANSFERS and f'"why": "{figures.NOT_IN_WORDS}"' in checked.user and failures == []
    assert '"nearest_words": "agreement no. 77' in checked.user, "the page's own words beside them, whatever failed"
    assert (kept["figure"], kept["whole"], kept["anchored"]) == ("500 kg", "1,350 kg", True)
    (subject,) = ledger([kept])
    assert subject["givers"][0]["added"] == {"mass": 500_000}
    assert subject["totals"][0]["by_giver"] == [{"giver": "the supplier", "leaves": 850_000, "exceeds": None}]


def test_words_not_found_are_looked_at_again_with_the_pages_own_words_nearest_to_them():
    model = LooksAgain({"agreement.pdf": [sale("500 kg", "The suplier sold 500 kg of grain")]},
                       {"agreement.pdf": [sale("500 kg", "The supplier sold 500 kg of grain")]})
    (kept,), _ = research.transfers_of(model, sent(*PAPER))
    (checked,) = [prompt for prompt in model.calls if '"to_check"' in prompt.user]
    assert '"why": "its words are not found, word for word, on the pages of its paper"' in checked.user
    assert '"nearest_words"' in checked.user
    assert (kept["words"], kept["anchored"]) == ("The supplier sold 500 kg of grain", True)


def test_a_transaction_still_at_fault_is_kept_listed_and_never_added_and_a_date_the_papers_lack_is_kept_marked_so():
    first = [sale("Rs.3,00,000", "The supplier sold 500 kg of grain", date="9-9-2009")]
    model = LooksAgain({"agreement.pdf": first}, {"agreement.pdf": first})
    (kept,), _ = research.transfers_of(model, sent(*PAPER))
    assert (kept["date"], kept["sort"], kept["date_found"]) == ("9-9-2009", "2009-09-09", "nowhere"), "kept, never erased"
    assert kept["settled"] == "clerical", "what the model said of it stands beside it"
    (subject,) = ledger([kept])
    assert subject["givers"] == [] and subject["unread"][0]["why"] == figures.NOT_IN_WORDS


def test_a_paper_whose_transactions_all_check_out_needs_no_look_again():
    model = LooksAgain({"agreement.pdf": [sale("500 kg", "The supplier sold 500 kg of grain out of 1,350 kg", whole="1,350 kg")]}, {})
    research.transfers_of(model, sent(*PAPER))
    assert not [prompt for prompt in model.calls if '"to_check"' in prompt.user]


def test_settling_answers_for_each_transaction_at_fault_by_its_index_and_the_one_that_was_right_is_kept_once():
    good = sale("500 kg", "The supplier sold 500 kg of grain out of 1,350 kg", whole="1,350 kg")
    bad = sale("900 kg", "The supplier sold 500 kg of grain", date="9-9-2009")
    # The model settles the one at fault (index 0 of what it is shown) as it still reads it; the one that was right is not shown.
    model = LooksAgain({"agreement.pdf": [good, bad]}, {"agreement.pdf": [bad]})
    found, _ = research.transfers_of(model, sent(*PAPER))
    assert [(t["id"], t["figure"], t["date"], t["settled"]) for t in found] == [
        ("X1", "500 kg", "5-6-2003", ""), ("X2", "900 kg", "9-9-2009", "clerical")]
    (checked,) = [prompt for prompt in model.calls if '"to_check"' in prompt.user]
    shown = json.loads(checked.user[checked.user.rindex('{"to_check"'):])
    assert [(c["index"], c["words"]) for c in shown["to_check"]] == [(0, bad["words"])], "only what failed is shown, by its index"


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


def test_the_settling_prompt_says_what_code_checked_and_asks_for_the_pages_own_words():
    prompt = " ".join(research.SETTLE_TRANSFERS.split())
    for part in ("Message:", "Purpose:", "Outcome:", "that its words stand on the pages of its paper, word for word",
                 "that its figure and any whole it states can be checked against those words",
                 "that the death it records of the giver stands in the papers",
                 "copied from the page exactly as they stand there, the slip included",
                 "so that every number you give is in the words", "give the death of the giver only where the papers record one",
                 "(verdict not_in_papers); it is withdrawn", "Work in a loop"):
        assert part in prompt, part
    assert research.MAX_OUTPUT["transfers_check"] == reasoning.MOST_OUTPUT, "it may write its room (D27)"
