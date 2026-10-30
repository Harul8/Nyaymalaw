"""The writer and the independent review are shown the land extents added up by code (plan AN.27, P13d, slice 4; invariant I6).

No step added extents, and a model was left to say whether a claim could be matched. Code now adds the transfers of land the papers
record (extents.py); the current writer and the review of its sections are shown the result - each parcel's transfers, what could not
be added, the sum, what a stated whole extent leaves, and the caveat that a sum is only of the transfers found - and told to use it
exactly as given and never to add extents themselves. The earlier versions and the overview are shown nothing. The papers are synthetic.
"""
import pytest

from nm.core_engine import answer_sources, research, response_authorities, response_review, response_writer
from nm.core_engine.research import plan, retrieve
from tests.test_core_research import Model, searcher
from tests.test_the_plan_records_the_chronology import Beside, bundle
from tests.test_the_plan_records_the_transfers import SOLD
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_and_review_are_shown_copies_read_differently import quiet
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a


def matter(transfers=SOLD):
    ctx = bundle()
    record = retrieve(plan(Beside({}, transfers=transfers), ctx), searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def test_the_current_writer_is_shown_each_parcel_added_up_by_code_with_its_caveat():
    ctx, record, sources = matter()
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    prompt, payload = model.seen[0]
    first, second = payload["land_extents"]
    assert (first["parcel"], first["sum"], first["complete"]) == ("Sy.No.487", "1 acre 18 guntas (Ac.1.18)", False)
    assert [(n["id"], n["why"]) for n in first["not_read"]] == [("X2", "its words were not found on the page")]
    assert first["totals"][0]["as"] == "8 acres 24 guntas (Ac.8.24)" and first["totals"][0]["leaves"] is None
    assert (second["parcel"], second["sum"], second["complete"]) == ("Sy.No.487/A", "29 guntas (Ac.0.29)", True)
    assert "makes the sum wrong" in first["caveat"] and prompt.system == response_writer.SYSTEM_V13


def test_nothing_is_shown_where_the_plan_kept_no_transfers_and_the_earlier_writer_is_shown_nothing():
    ctx, record, sources = matter(transfers={})
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert "land_extents" not in model.seen[0][1]
    ctx, record, sources = matter()
    earlier = Writer(lambda payload: {"units": [{"kind": "summary", "text": "In short.", "uses": []}], "checklist": [],
                                      "time_limit_ids": []})
    response_writer.write_section(earlier, ctx, record, sources, index=0)
    assert "land_extents" not in earlier.seen[0][1]
    assert response_writer._extents_shown({"contract": "core_research_v11", "plan": {"proposal": {}}}) is None


def test_the_review_of_a_section_is_shown_the_same_and_the_earlier_review_is_not():
    ctx, record, sources = matter()
    draft = response_writer.write_section(Writer(quiet), ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           contract=response_review.PRESENTED_CONTRACT)
    assert [p["parcel"] for p in model.seen[0][1]["land_extents"]] == ["Sy.No.487", "Sy.No.487/A"]
    older = response_writer.write_section(Writer(lambda payload: {"units": [{"kind": "summary", "text": "In short.", "uses": []}],
                                                                 "checklist": [], "time_limit_ids": []}),
                                          ctx, record, sources, index=0)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, older, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, older),
                           contract=response_review.MISLEADS_CONTRACT)
    assert "land_extents" not in model.seen[0][1]


def test_the_prompts_say_to_use_the_sums_exactly_as_given_and_never_to_add_extents_itself():
    writer = " ".join(response_writer.SYSTEM_V13.split())
    for part in ("Counting is code's work for extents as it is for days: do not add, subtract or convert acres, guntas or cents yourself",
                 "Where land_extents is given, code added the transfers of land NM found in the papers, parcel by parcel",
                 "use its sums, and what they leave of a stated whole extent, exactly as given",
                 "say what its caveat says - that they add every transfer the papers record, whoever states it, rival and repeated "
                 "accounts included, so a sum is a figure to check and never the extent anyone holds or has transferred - and which "
                 "transfers were not added and why",
                 "name no remainder for a parcel whose complete is false",
                 "say what would be added or taken away and that it has not been worked out"):
        assert part in writer, part
    review = " ".join(response_review.SYSTEM_V11.split())
    for part in ("adds, subtracts or converts extents (acres, guntas, cents) where the papers do not state the result",
                 "Where land_extents is given, code added the transfers of land NM found",
                 "said as what the transfers found add up to and not as an extent anyone holds or has transferred",
                 "one for a parcel whose complete is false, or one the piece worked out itself, is not"):
        assert part in review, part
    assert "land_extents" not in response_writer.SYSTEM and "land_extents" not in response_review.SYSTEM_V10
