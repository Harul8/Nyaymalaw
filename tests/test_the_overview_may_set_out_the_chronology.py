"""The overview may set out the papers' chronology where the advocate asked for it (plan AN.27, P18).

An answer of several disputes is written dispute by dispute and opened by an overview; the papers' dated events reached each dispute's
section (P11) but no part of the answer could set out the history across the disputes, which is what the advocate asked for in the
reviewed bundle's first turn. The overview's writer, and the review of the overview, are now shown the same events and told to set
out the ones that matter across the disputes, in date order, with their pages, where the history, the dates or a chronology was asked
for. The papers here are synthetic.
"""
import json

import pytest

from nm.core_engine import answer_sources, research, response_authorities, response_review, response_writer
from nm.core_engine.research import plan, retrieve
from tests.test_core_research import Model, searcher, understanding
from tests.test_the_chronology_of_each_document import SCRIPT
from tests.test_the_plan_records_the_chronology import Beside, bundle
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a

SECTIONS = [{"dispute": "Dispute 1", "paragraphs": [{"kind": "summary", "text": "File by Wednesday."}]},
            {"dispute": "Dispute 2", "paragraphs": [{"kind": "summary", "text": "Serve the notice."}]}]


def matter():
    ctx = bundle()
    kept = plan(Beside(SCRIPT, subject=understanding(1, 2)), ctx)
    record = retrieve(kept, searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def chronology(payload):
    return {"units": [
        {"kind": "next_step", "text": "File the revision petition first.", "uses": []},
        {"kind": "summary", "text": "The papers show the revision was allowed on 17 August 2019, and two suits are still pending.",
         "uses": [{"source_kind": "document", "source_id": next(e for e in payload["papers_chronology"] if e["located"] and
                                                                e["paper"] == "order.pdf")["cite"][0],
                   "link_words": "17 August 2019"}]}]}


def test_the_overview_is_shown_the_events_the_sections_were_and_a_page_it_cites_is_admitted():
    ctx, record, sources = matter()
    assert len(response_writer.parts(record)) == 3
    model = Writer(chronology)
    draft = response_writer.write_overview(model, ctx, record, sources, sections=SECTIONS,
                                           contract=response_writer.PRESENTED_CONTRACT)
    prompt, payload = model.seen[0]
    assert [e["id"] for e in payload["papers_chronology"]] == [e["id"] for e in record["plan"]["proposal"]["chronology"]]
    assert set(payload["papers_chronology"][0]) == {"id", "date", "kind", "what", "said_by", "paper", "pages", "cite", "located"}
    assert prompt.system == response_writer.OVERVIEW_SYSTEM_V13
    (cited,) = [use for unit in draft["units"] for use in unit.get("uses", ())]
    assert cited["role"] == "supplied_document" and cited["source_id"] == "t1:d2p1"
    assert response_writer.validate(draft, ctx, sources) == draft


def test_the_earlier_overview_and_a_matter_with_no_chronology_are_shown_nothing():
    ctx, record, sources = matter()
    model = Writer(lambda payload: {"units": [{"kind": "greeting", "text": "Hello.", "uses": []}]})
    response_writer.write_overview(model, ctx, record, sources, sections=SECTIONS)
    assert "papers_chronology" not in model.seen[0][1], "the v12 overview"
    plain = {**record, "plan": {**record["plan"], "proposal": {**record["plan"]["proposal"], "chronology": []}}}
    assert response_writer._chronology_shown(plain, {}) is None


def test_the_review_of_the_overview_is_shown_the_events_too():
    ctx, record, sources = matter()
    draft = response_writer.write_overview(Writer(chronology), ctx, record, sources, sections=SECTIONS,
                                           contract=response_writer.PRESENTED_CONTRACT)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           sections=[], contract=response_review.PRESENTED_CONTRACT)
    prompt, payload = model.seen[0]
    assert payload["what_you_review"]["piece"].startswith("the overview")
    assert [e["id"] for e in payload["papers_chronology"]] == [e["id"] for e in record["plan"]["proposal"]["chronology"]]
    assert "copies_read_differently" not in payload, "the copies stay with the sections"


def test_the_prompts_say_when_the_overview_sets_out_the_history_and_how_it_is_judged():
    overview = " ".join(response_writer.OVERVIEW_SYSTEM_V13.split())
    for part in ("The papers' chronology (papers_chronology) comes with documents the advocate sent",
                 "Where the advocate asked for the history, the dates or a chronology of the papers, give one summary unit that sets "
                 "out, in date order, the events that matter across the disputes",
                 "the orders, and the proceedings still pending among them - each with its date and, as a document use, the page it "
                 "comes from",
                 "rely on no event whose located is false, and leave the detail to the sections",
                 "Where the advocate did not ask, leave it unused"):
        assert part in overview, part
    assert "papers_chronology" not in " ".join(response_writer.OVERVIEW_SYSTEM.split())
    review = " ".join(response_review.SYSTEM_V11.split())
    assert "An overview is judged the same way where it sets out the chronology the advocate asked for" in review
