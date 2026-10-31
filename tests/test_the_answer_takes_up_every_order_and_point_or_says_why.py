"""The answer takes up every order and point the record holds, or says why not (plan AN.28, stage 5; findings A1-A7, A12, A13).

The writers were shown nearly two hundred timeline events and used fewer than twenty; an order that keeps a predecessor's name in the records was called only
"pending", a member of the client's family among an appeal's respondents went unsaid, and a review's finding that something important
was missing was a suggestion that lapsed. Now code lists every order, direction and proceeding still pending in the papers' timeline,
and every point the papers read side by side show; the writer v14 and its overview take up each that bears on their part or say why
not; the review v12 holds an item passed over in silence a must-fix, and such a piece is rewritten once for it - what still stays out
is said beside it. The papers are synthetic.
"""
import json

import pytest

from nm.core_engine import (answer_sections, answer_sources, calculation, research, response_authorities, response_rendering,
                            response_review, response_writer, turn)
from nm.core_engine.calls import TurnCalls
from nm.core_engine.research import plan, retrieve
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.test_core_research import Model, searcher
from tests.test_the_chronology_of_each_document import SCRIPT
from tests.test_the_plan_records_the_chronology import Beside, bundle
from tests.test_the_plan_records_the_transfers import SOLD
from tests.test_the_writer_and_review_are_shown_copies_read_differently import quiet
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a

V14 = response_writer.REPAIRED_CONTRACT


def matter():
    ctx = bundle()
    record = retrieve(plan(Beside(SCRIPT, transfers=SOLD), ctx), searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def _result(data, tier):
    return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def test_the_writer_v14_is_given_every_order_pending_proceeding_and_point_to_take_up_or_say_why():
    ctx, record, sources = matter()
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=V14)
    prompt, payload = model.seen[0]
    coverage = payload["coverage"]
    assert coverage and {item["kind"] for item in coverage} <= {"order", "pending"}
    assert all(item["cite"] for item in coverage), "each with the pages to cite"
    assert [item["id"] for item in coverage] == [event["id"] for event in payload["papers_chronology"]
                                                 if event["kind"] in ("order", "pending") and event["located"]]
    earlier = Writer(quiet)
    response_writer.write_section(earlier, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert "coverage" not in earlier.seen[0][1], "the v13 writer is shown what it was"
    writer = " ".join(response_writer.SYSTEM_V14.split())
    for part in ("Where coverage is given, it lists every order, direction and proceeding still pending",
                 "every point the papers read side by side show", "Take up each that bears on your part, citing its pages",
                 "say so in a limitation unit, with why", "Pass over none of them in silence", "Set out the papers' events once",
                 "the chronology across the disputes is the opening overview's", "keep a part's dated events together, in date order"):
        assert part in writer, part
    overview = " ".join(response_writer.OVERVIEW_SYSTEM_V14.split())
    assert "each that bears on the matter and that no section took up" in overview and "repeat nothing a section already says" in overview
    assert "Where coverage is given" not in response_writer.SYSTEM_V13 + response_writer.OVERVIEW_SYSTEM_V13


class Reviewing:
    """A review v12 that reports as missing what `missing(payload)` gives, and keeps what it was shown."""

    def __init__(self, missing):
        self.missing, self.seen = missing, []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        self.seen.append(payload)
        return _result({"misleading": [], "could_be_better": [], "keep_shown": [], "missing": self.missing(payload)}, tier)


def test_the_review_v12_holds_an_item_passed_over_in_silence_a_must_fix_said_by_what_it_is():
    ctx, record, sources = matter()
    draft = response_writer.write_section(Writer(quiet), ctx, record, sources, index=0, contract=V14)
    reviewer = Reviewing(lambda payload: [{"id": payload["coverage"][0]["id"], "why": "It decides who holds the land."},
                                          {"id": "E99", "why": "Something."}])
    reviewed = response_review.review(reviewer, ctx, record, sources, draft, research.execution(record),
                                      authority_evidence=response_authorities.check(ctx, record, sources, draft),
                                      contract=response_review.WORDED_CONTRACT)
    item = reviewer.seen[0]["coverage"][0]
    (left,) = reviewed["proposal"]["findings"]
    assert left["category"] == response_review.LEFT_OUT and left["unit_ids"] == [] and not reviewed["accepted"]
    assert left["mismatch"] == f"{item['date']} {item['kind']}: {item['what']} - It decides who holds the land."
    assert "names no item of the coverage list: 'E99'" in [entry["why"] for entry in reviewed["proposal"]["set_aside"]]
    assert "give it in missing" in response_review.SYSTEM_V12 and "missing" not in response_review.SYSTEM_V11


class Covering:
    """Writes the one section from a script and reviews it as `missing(round)` says, round by round."""

    def __init__(self, missing):
        self.missing, self.writes, self.reviews = missing, [], 0

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        if prompt.operation == "core_response_writer":
            self.writes.append(payload)
            units = [{"kind": "summary", "text": "In short, the revision was allowed.", "uses": [], "place": "row_action"},
                     {"kind": "next_step", "text": "Check the records.", "uses": [], "place": "next_steps"}]
            return _result({"units": units, "checklist": [], "time_limit_ids": [], "by_when": None}, tier)
        if prompt.operation == "core_response_review":
            self.reviews += 1
            return _result({"misleading": [], "could_be_better": [], "keep_shown": [],
                            "missing": self.missing(self.reviews, payload)}, tier)
        raise AssertionError(prompt.operation)


def answered(model):
    ctx, record, sources = matter()
    calls, worked, execution = TurnCalls(model), calculation.skipped(), turn.execution_record(record)
    sections, crossed, overview = answer_sections.answer(calls, ctx, record, sources, interpretation={"units": []},
                                                         execution=execution, worked=worked, contract=V14)
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=crossed, overview=overview,
                                                  time_limits=worked, contract=response_rendering.REPAIRED_CONTRACT)
    activity = {"contract": turn.CONTRACT, "interpretation": {"units": []}, "research": record, "sources": sources,
                "execution": execution, "calculation": worked, "rendering_contract": response_rendering.REPAIRED_CONTRACT,
                "sections": sections, "cross_check": crossed, "overview": overview}
    assert turn.validate_activity(activity, ctx, elements) == activity, "the turn replays as saved"
    return sections, elements


def test_a_piece_that_passes_over_an_item_is_rewritten_once_for_it_and_what_still_stays_out_is_said_beside_it():
    first = lambda payload: [{"id": payload["coverage"][-1]["id"], "why": "The suits are still pending."}]  # noqa: E731
    model = Covering(lambda round_, payload: first(payload))
    sections, elements = answered(model)
    assert len(model.writes) == 2 and model.writes[1]["correction"]["purpose"] == answer_sections.COVERAGE_PURPOSE
    told = model.writes[1]["correction"]["mismatch"]
    assert told[0]["category"].startswith("left out: an item of coverage") and "The suits are still pending." in told[0]["mismatch"]
    (section,) = sections
    assert section["fallback"] is None and section["trims"] == [], "an item passed over never withholds a section"
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert "does not take up something your papers record that bears on it" in note["text"]
    assert "The suits are still pending." in note["text"] and "E" + "1" not in note["text"].split(":")[0]


def test_a_rewrite_that_takes_the_item_up_is_shown_with_nothing_beside_it():
    model = Covering(lambda round_, payload: ([{"id": payload["coverage"][0]["id"], "why": "It is the order in issue."}]
                                              if round_ == 1 else []))
    sections, elements = answered(model)
    assert len(model.writes) == 2 and model.reviews == 2
    assert not [element for element in elements if element["kind"] == "NOTE"]
    assert sections[0]["reviewed"]["review"]["accepted"] is True
