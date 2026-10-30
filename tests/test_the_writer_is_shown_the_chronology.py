"""The writer is shown the papers' chronology (plan AN.27, P11).

The plan keeps what the papers record, event by event (P8c); the current writer is now shown it with each event's paper and pages and
the short IDs of those pages, which it selects as document uses exactly as it selects any page, and is told to set out the events that
matter to its part in date order, keeping what a party alleges attributed and relying on no event whose words were not located. The
older writers see what they always saw. The papers here are synthetic; a bounded live run measures what a real writer does with it.
"""
import json

import pytest

from nm.core_engine import answer_sources, research, response_writer
from nm.core_engine.research import plan, retrieve
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.test_core_research import Model, searcher
from tests.test_core_writer_v13 import item, unit
from tests.test_the_plan_records_the_chronology import Beside, bundle

pytestmark = pytest.mark.class_a


class Writer:
    def __init__(self, write):
        self.write, self.seen = write, []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        self.seen.append((prompt, payload))
        return ModelResult(None, self.write(payload), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def papers():
    ctx = bundle()
    kept = plan(Beside(), ctx)
    record = retrieve(kept, searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def cites(payload):
    """The first located event of the deed, and the short ID of its page."""
    event = next(e for e in payload["papers_chronology"] if e["located"] and e["paper"] == "deed.pdf")
    return event, event["cite"][0]


def section(payload):
    event, page = cites(payload)
    return {"units": [
        unit("summary", "Appeal against the order", "row_action"),
        unit("summary", "Have the sale deed ready", "row_ready"),
        {"kind": "summary", "text": "The sale deed was made on 30-10-1985.", "place": "advice",
         "uses": [{"source_kind": "document", "source_id": page, "link_words": "sale deed was made"}]}],
        "checklist": [item(payload, "The sale deed", ["the sale deed"])], "time_limit_ids": [], "by_when": None}


def test_the_current_writer_is_shown_each_event_with_the_short_ids_of_its_pages():
    ctx, record, sources = papers()
    model = Writer(section)
    draft = response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    prompt, payload = model.seen[0]
    shown = payload["papers_chronology"]
    plan_events = record["plan"]["proposal"]["chronology"]
    assert [e["id"] for e in shown] == [e["id"] for e in plan_events] and len(shown) == 6
    assert set(shown[0]) == {"id", "date", "kind", "what", "said_by", "paper", "pages", "cite", "located"}
    deed, order = shown[0], shown[2]
    assert (deed["paper"], deed["pages"], deed["located"]) == ("deed.pdf", [1], True)
    assert len(deed["cite"]) == 1 and payload["source_kinds"][deed["cite"][0]] == "document"
    assert order["pages"] == [1] and len(order["cite"]) == 1 and order["cite"][0] != deed["cite"][0]
    run_over = next(e for e in shown if e["pages"] == [1, 2])
    assert len(run_over["cite"]) == 2 and all(payload["source_kinds"][c] == "document" for c in run_over["cite"])
    # An event whose words were not located is shown as that, with nothing to cite.
    lost = next(e for e in shown if not e["located"])
    assert lost["cite"] == [] and lost["pages"] == []
    # The short ID is the one the writer's own use is admitted by: the page is linked on the words of the unit.
    assert prompt.system == response_writer.SYSTEM_V13 and "papers_chronology" in response_writer.SYSTEM_V13
    cited = [use for unit_ in draft["units"] for use in unit_.get("uses", ())]
    assert len(cited) == 1 and cited[0]["source_id"] == "t1:d1p1" and cited[0]["role"] == "supplied_document"
    assert response_writer.validate(draft, ctx, sources) == draft


def test_the_shown_events_carry_no_sort_date_no_exact_words_and_no_owned_id():
    ctx, record, sources = papers()
    model = Writer(section)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    shown = json.dumps(model.seen[0][1]["papers_chronology"])
    for key in ("sort", "words", "anchored", "source"):
        assert f'"{key}":' not in shown, key
    assert "t1:d1" not in shown and "Sale Deed No. 100" not in shown, "the exact words and the owned IDs stay with the plan"


def test_the_earlier_writer_is_shown_what_it_always_was():
    ctx, record, sources = papers()

    def write(payload):
        return {"units": [{"kind": "summary", "text": "In short.", "uses": []}], "checklist": [], "time_limit_ids": []}
    model = Writer(write)
    response_writer.write_section(model, ctx, record, sources, index=0)
    prompt, payload = model.seen[0]
    assert "papers_chronology" not in payload and prompt.system == response_writer.SYSTEM
    assert "papers_chronology" not in response_writer.SYSTEM


def test_no_chronology_means_nothing_is_shown():
    offered = {}
    assert response_writer._chronology_shown({"contract": "core_research_v11", "plan": {"proposal": {}}}, offered) is None
    assert response_writer._chronology_shown({"contract": research.CONTRACT, "plan": {"proposal": {
        "chronology": [], "chronology_failures": []}}}, offered) is None
    ctx, record, sources = papers()
    plain = {**record, "plan": {**record["plan"], "proposal": {**record["plan"]["proposal"], "chronology": []}}}
    model = Writer(lambda payload: {"units": [{"kind": "summary", "text": "In short.", "uses": []}], "checklist": [],
                                    "time_limit_ids": [], "by_when": None})
    layout = response_writer.parts(plain)
    payload = response_writer._payload(ctx, plain, sources, None, None, layout, 0, None, worded=True)
    assert "papers_chronology" not in payload and model.seen == []


def test_the_prompt_says_what_to_do_with_the_chronology():
    prompt = response_writer.SYSTEM_V13
    for part in ("the history, the dates or a summary of the papers", "in date order", "leave out no order, direction or proceeding still pending",
                 "Keep what a party alleges attributed to that party", "whose located is false could not be found on its page",
                 "State no date or event that is neither in the chronology nor on a page"):
        assert " ".join(part.split()) in " ".join(prompt.split()), part
