"""The writer and the independent review are shown the figures added up by code (plan AN.27, P13d, slice 4; AN.28, D7; AN.29, D9;
invariant I6).

No step added figures, and a model was left to say whether a claim could be matched. Code now adds the transactions the papers record
(figures.py); the current writer and the review of its sections are shown the result - each subject's transactions by giver, what could
not be added, the sums, what a stated whole leaves, any remark on a transaction, and the caveat that a sum is only of the transactions
found - and told to use it exactly as given and never to add figures themselves. The earlier versions and the overview are shown
nothing. The papers are synthetic.
"""
import pytest

from nm.core_engine import answer_sources, figures, research, response_authorities, response_review, response_writer
from nm.core_engine.research import plan, retrieve
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_core_research import Model, searcher
from tests.test_the_chronology_of_each_document import row
from tests.test_the_plan_records_the_chronology import Beside, bundle, sent
from tests.test_the_plan_records_the_transfers import SOLD, transfer
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_and_review_are_shown_copies_read_differently import quiet
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a


def matter(transfers=SOLD):
    ctx = bundle()
    record = retrieve(plan(Beside({}, transfers=transfers), ctx), searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def test_the_current_writer_is_shown_each_subject_added_up_by_code_with_its_caveat():
    ctx, record, sources = matter()
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    prompt, payload = model.seen[0]
    first, second = payload["figures_added"]
    assert (first["subject"], first["givers"][0]["added"], first["complete"]) == ("Lot 487", "118 kilograms", False)
    assert first["givers"][0]["names"] == ["the supplier"] and "sum" not in first
    assert [(n["id"], n["why"]) for n in first["not_read"]] == [("X2", "its words were not found on the page")]
    # Research v13 (AN.28, D3): the whole the model gave is on no page, so it is listed and not used; the order's figure stands in
    # none of the words that record its transaction, so it is not added.
    assert (first["totals"][0]["as"], first["totals"][0]["read_as"]) == (None, figures.NOT_IN_WORDS)
    assert first["totals"][0]["by_giver"] == []
    assert (second["subject"], second["givers"], second["complete"]) == ("Lot 487/A", [], False)
    assert [(n["id"], n["why"]) for n in second["not_read"]] == [("X3", figures.NOT_IN_WORDS)]
    assert "makes the sum wrong" in first["caveat"] and prompt.system == response_writer.SYSTEM_V13


def test_nothing_is_shown_where_the_plan_kept_no_transactions_and_the_earlier_writer_is_shown_nothing():
    ctx, record, sources = matter(transfers={})
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert "figures_added" not in model.seen[0][1]
    ctx, record, sources = matter()
    earlier = Writer(lambda payload: {"units": [{"kind": "summary", "text": "In short.", "uses": []}], "checklist": [],
                                      "time_limit_ids": []})
    response_writer.write_section(earlier, ctx, record, sources, index=0)
    assert "figures_added" not in earlier.seen[0][1]
    assert response_writer._figures_shown({"contract": "core_research_v11", "plan": {"proposal": {}}}) is None


def test_the_review_of_a_section_is_shown_the_same_and_the_earlier_review_is_not():
    ctx, record, sources = matter()
    draft = response_writer.write_section(Writer(quiet), ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           contract=response_review.PRESENTED_CONTRACT)
    assert [p["subject"] for p in model.seen[0][1]["figures_added"]] == ["Lot 487", "Lot 487/A"]
    older = response_writer.write_section(Writer(lambda payload: {"units": [{"kind": "summary", "text": "In short.", "uses": []}],
                                                                 "checklist": [], "time_limit_ids": []}),
                                          ctx, record, sources, index=0)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, older, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, older),
                           contract=response_review.MISLEADS_CONTRACT)
    assert "figures_added" not in model.seen[0][1]


def copies_matter():
    """Two papers that hold a copy of one page, each read for the one sale it records, the receiver's name read two ways."""
    ctx = sent(row("t1", 1, "deed.pdf", 1, passage()), row("t1", 2, "scan.pdf", 1, passage()))
    said = "the supplier sold to the purchasers a quantity of 6.06 tonnes"
    transfers = {"deed.pdf": [transfer("5.1.1980", "Lot 487", "6.06 tonnes", said, to="Kiran Rao")],
                 "scan.pdf": [transfer("5.1.1980", "Lot 487", "6.06 tonnes", said, to="Kiran Raao")]}
    record = retrieve(plan(Beside({}, transfers=transfers), ctx), searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def test_one_sale_read_on_two_copies_of_a_page_is_shown_once_to_the_writer_and_to_the_review():
    ctx, record, sources = copies_matter()
    (subject,) = response_writer._figures_shown(record, ctx)
    (giver,) = subject["givers"]
    (only,) = giver["counted"]
    assert giver["added"] == "6.06 tonnes" and [p["document"] for p in only["papers"]] == ["deed.pdf", "scan.pdf"]
    assert only["to"] == "Kiran Rao" and only["also_read_as"] == ["Kiran Raao"]
    (twice,) = response_writer._figures_shown(record)
    assert twice["givers"][0]["added"] == "12.12 tonnes" and len(twice["givers"][0]["counted"]) == 2, \
        "without the pages it is added twice"
    model = Writer(quiet)
    draft = response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert model.seen[0][1]["figures_added"] == [subject]
    reviewer = Reviewer()
    response_review.review(reviewer, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           contract=response_review.PRESENTED_CONTRACT)
    assert reviewer.seen[0][1]["figures_added"] == [subject]


def test_the_date_check_is_given_the_dates_of_the_transactions_as_the_writer_is_shown_them_on_copies_too():
    ctx, record, sources = copies_matter()
    stated = {"contract": response_writer.PRESENTED_CONTRACT, "units": [{"id": "t1:b1", "text": "The supplier sold it."}]}
    assert response_writer._shown_dates(stated, record, ctx) == ["5.1.1980"], "one sale, as the writer is shown it"
    assert response_writer._shown_dates(stated, record) == ["5.1.1980", "5.1.1980"]


def test_a_remark_on_a_transaction_reaches_the_writer_and_the_review():
    # Plan AN.29, B17 (invented): a sale dated after the death of its giver, which the file records.
    ctx = sent(row("t1", 1, "agreement.pdf", 1, "Agreement No. 77 dated 5-6-2003. The supplier sold 500 kg of grain to the purchaser."),
               row("t1", 2, "certificate.pdf", 1, "Certificate. The supplier died on 4-4-2003 at the town hospital."))
    sale = transfer("5-6-2003", "Contract 77", "500 kg", "The supplier sold 500 kg of grain to the purchaser", to="the purchaser",
                    giver_died="4-4-2003", instrument="Agreement No. 77")
    record = retrieve(plan(Beside({}, transfers={"agreement.pdf": [sale]}), ctx), searcher(), ctx, model=Model())
    sources = answer_sources.build(ctx, record)
    (subject,) = response_writer._figures_shown(record, ctx)
    (counted,) = subject["givers"][0]["counted"]
    assert counted["remark"] == "dated after the death of the giver that the papers record (4-4-2003)"
    assert counted["as"] == "500 kilograms" and subject["givers"][0]["added"] == "500 kilograms"
    model = Writer(quiet)
    draft = response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.REPAIRED_CONTRACT)
    assert model.seen[0][1]["figures_added"][0]["givers"][0]["counted"][0]["remark"] == counted["remark"]
    reviewer = Reviewer()
    response_review.review(reviewer, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           contract=response_review.WORDED_CONTRACT)
    assert reviewer.seen[0][1]["figures_added"][0]["givers"][0]["counted"][0]["remark"] == counted["remark"]


def test_the_prompts_say_to_use_the_sums_exactly_as_given_and_never_to_add_figures_itself():
    writer = " ".join(response_writer.SYSTEM_V13.split())
    for part in ("Counting is code's work for figures as it is for days: do not add, subtract or convert any amount or quantity yourself",
                 "Where figures_added is given, code added up the transactions NM found in the papers, subject by subject and giver by "
                 "giver - whoever sold, gave, settled, lent or paid - sums of money with sums of money and each kind of quantity with "
                 "its own",
                 "use a giver's added, and what a stated whole leaves after it (leaves: if all of it was that giver's) or how far it "
                 "goes beyond it (exceeds), exactly as given, and never add one giver's figures to another's",
                 "Say what its caveat says - that the sums add every transaction the papers record, whoever states it, rival and "
                 "repeated accounts included, so a sum is a figure to check and never what anyone holds, owes or has paid - and which "
                 "transactions were listed and not added, and why",
                 "Where an entry has a remark, say it as given",
                 "Where exceeds is given, say that the papers do not fit together on that giver's transactions, as code found, and "
                 "not which account is right",
                 "Name no remainder for a subject whose complete is false, nor for a giver with no name",
                 "say what would be added or taken away and that it has not been worked out"):
        assert part in writer, part
    assert response_writer.SYSTEM_V14.count("Where figures_added is given") == 1
    review = " ".join(response_review.SYSTEM_V11.split())
    for part in ("adds, subtracts or converts figures (an amount, a quantity, a period) where the papers do not state the result",
                 "Where figures_added is given, code added up the transactions NM found, giver by giver",
                 "said as what that giver's transactions found add up to and not as what anyone holds, owes or has paid, and never "
                 "as a sum across givers",
                 "one for a subject whose complete is false, or one the piece worked out itself, is not",
                 "A transaction that carries a remark is not an ordinary one"):
        assert part in review, part
    assert " ".join(response_review.SYSTEM_V12.split()).count("Where figures_added is given") == 1
    for old in (response_writer.SYSTEM, response_review.SYSTEM_V10):
        assert "figures_added" not in old
