"""Each dispute in its own pipeline (owner, 21 Oct 2026: step 4, P26 as first decided).

A dispute's section is written as soon as its own questions are searched and picked, while the
other disputes are still being researched; each section is written, and replays, from its own
dispute's part of the research; a turn that stops part way saves what it showed, recording
what it never researched. Scripted models prove the order and the bindings, not the writing.
"""
import json
import threading

import pytest

from nm.core_engine import answer_sections, calculation, research, response_rendering, turn
from nm.core_engine.calls import TurnCalls
from tests.test_core_answer_sections import Scripted
from tests.test_core_research import Model as ResearchModel, proposal
from tests.test_core_response_writer import TwoDisputeLibrary
from tests.test_core_understanding import context

pytestmark = pytest.mark.class_a


def _held(until):
    """The two-dispute library, its second dispute's search waiting for `until`."""
    library, waited = TwoDisputeLibrary.searcher(), []
    search = library.search

    def held_back(queries, instruments=None, **kw):
        if "D2Q1" in queries[0]["text"]:
            waited.append(until.wait(timeout=10))
        return search(queries, instruments, **kw)
    library.search = held_back
    return library, waited


class Writing(Scripted):
    """The scripted writer and review, telling when the first dispute's section is written."""

    def __init__(self, first_written):
        super().__init__()
        self.first_written = first_written

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_writer":
            if ((json.loads(prompt.user)["this_part"]["dispute"] or {}).get("id")) == "D1":
                self.first_written.set()
        return super().structured(prompt, schema, tier, **kwargs)


def _activity(record, sources, execution, worked, sections, crossed, overview):
    # Written by writer v13 through the loop of turn v8, which saved turns replay.
    return {"contract": turn.PRESENTED_CONTRACT, "interpretation": {"units": []}, "research": record, "sources": sources,
            "execution": execution, "calculation": worked, "rendering_contract": response_rendering.PRESENTED_CONTRACT,
            "sections": sections, "cross_check": crossed, "overview": overview}


def test_a_disputes_section_is_written_while_another_is_still_being_researched():
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 2), ctx)
    first_written = threading.Event()
    library, waited = _held(first_written)
    researched = answer_sections.Researched(ctx, plan, research.retrieve_parts(plan, library, ctx, model=ResearchModel()))
    worked = calculation.skipped()
    sections, crossed, overview = answer_sections.answer(
        TurnCalls(Writing(first_written)), ctx, None, None, interpretation={"units": []}, execution=None,
        worked=worked, researched=researched)
    assert waited == [True]  # the second dispute was still searching when the first was written
    record, sources, execution = researched.whole()
    assert record["contract"] == research.CONTRACT and set(record["picks"]) == {"D1", "D2"}
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=crossed,
                                                  overview=overview, time_limits=worked,
                                                  contract=response_rendering.PRESENTED_CONTRACT)
    activity = _activity(record, sources, execution, worked, sections, crossed, overview)
    assert turn.validate_activity(activity, ctx, elements) == activity
    # Each section was written from its own dispute's part alone.
    part = research.part_of(record, "D1")
    assert set(part["searches"]) == {w["id"] for w in plan["work"] if w["dispute"]["id"] == "D1"}
    assert research.execution(part)["searches"] == [{"work_id": w["id"], "state": "evaluated"} for w in plan["work"]
                                                    if w["dispute"]["id"] == "D1"]


def test_a_turn_stopped_while_a_dispute_is_researched_saves_what_it_showed():
    """P27 with step 4: what the page showed while the second dispute was still being
    researched is what a stopped turn saves; its questions are recorded as not researched."""
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 2), ctx)
    shown_once = threading.Event()
    library, _ = _held(shown_once)
    researched = answer_sections.Researched(ctx, plan, research.retrieve_parts(plan, library, ctx, model=ResearchModel()))
    worked, held = calculation.skipped(), {}

    def released(state):
        if not held:
            record, sources, execution = researched.provisional()
            held.update(_activity(record, sources, execution, worked, state["sections"], state["cross_check"],
                                  state["overview"]), waiting=state["waiting"])
            shown_once.set()
    answer_sections.answer(TurnCalls(Scripted()), ctx, None, None, interpretation={"units": []}, execution=None,
                           worked=worked, researched=researched, released=released)
    record = held["research"]
    second = [w["id"] for w in plan["work"] if w["dispute"]["id"] == "D2"]
    assert record["failures"] == {identity: {"stage": "search", "reason": research.UNFINISHED} for identity in second}
    assert record["picks"]["D2"]["reason"] == research.UNFINISHED and record["state"] == "partial"
    activity = turn.interrupted(held)
    elements = response_rendering.render_sections(
        ctx, activity["research"], activity["sources"], sections=activity["sections"],
        cross_check=activity["cross_check"], overview=activity["overview"], time_limits=worked,
        contract=activity["rendering_contract"])
    assert [saved["fallback"] for saved in activity["sections"]] == [None, {"reason": "interrupted"}]
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_dispute_research_that_was_never_finished_cannot_pass_as_whole():
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 2), ctx)
    parts = research.retrieve_parts(plan, TwoDisputeLibrary.searcher(), ctx, model=ResearchModel())
    first = parts["D1"].result()
    with pytest.raises(ValueError, match="missing"):
        research.assemble(plan, [first])
    stopped = research.assemble(plan, [first], unfinished=research.UNFINISHED)
    assert research.validate(stopped, plan, ctx) == stopped
    whole = research.assemble(plan, [first, parts["D2"].result()])
    assert research.part_of(whole, "D1") == first and research.validate(first, plan, ctx) == first


def test_the_overview_reads_each_section_by_the_catalogue_it_was_written_from():
    """Live run 6 (21 Oct 2026): a section written from its dispute's part names its sources by
    that part's short IDs; the overview's review re-bound them to the whole answer's IDs, found
    its quotations in the wrong passages and could not be completed."""
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 2), ctx)
    researched = answer_sections.Researched(
        ctx, plan, research.retrieve_parts(plan, TwoDisputeLibrary.searcher(), ctx, model=ResearchModel()))

    def citing(round_, payload):
        held = next(p for p in payload["held_passages"]["passages"] if p["kind"] == "judgment")
        assert held["id"] == "J1"  # the second dispute's first judgment, J1 of its own part
        return [{"kind": "summary", "text": "In short for D2.", "uses": []},
                {"kind": "law", "text": "The court states the rule applies.",
                 "uses": [{"source_kind": "judgment", "source_id": "J1", "role": "court_reasoning",
                           "speaker": None, "court_treatment": {"status": "not_shown"},
                           "link_words": "the rule applies"}]}]
    worked = calculation.skipped()
    sections, crossed, overview = answer_sections.answer(
        TurnCalls(Scripted({"D2": citing})), ctx, None, None, interpretation={"units": []}, execution=None,
        worked=worked, researched=researched)
    assert overview["fallback"] is None and crossed is not None and "unavailable" not in crossed
    record, sources, execution = researched.whole()
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=crossed,
                                                  overview=overview, time_limits=worked,
                                                  contract=response_rendering.PRESENTED_CONTRACT)
    activity = _activity(record, sources, execution, worked, sections, crossed, overview)
    assert turn.validate_activity(activity, ctx, elements) == activity
