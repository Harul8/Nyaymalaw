"""A turn as turns were answered before 19 Oct 2026 (turn v5): the whole answer written in
parts (writer v11), reviewed as one reply (review v8) and rendered (v16).

New turns are answered dispute by dispute (turn v6, owner decisions P25-P27). Conversations
saved before then keep their turns, and reopening them replays those turns exactly; the
tests that check that replay build such turns here, and earlier ones from them. Only an
answer its review accepted is built: the earlier rewrites, held sections and withheld turns
are retired with the v5 preparer (P25).
"""
from __future__ import annotations

from nm.core_engine import (
    answer_sources, calculation, response_authorities, response_rendering, response_review, response_writer, turn,
)
from nm.core_engine.calls import TurnCalls


def prepare(model, context, searcher, *, case_index=None, provision_reader=None, held_acts=None):
    """One accepted v5 turn's elements, activity and metrics, as v5 saved them."""
    calls = model if isinstance(model, TurnCalls) else TurnCalls(model)
    interpreted, record, limits = turn.understood(calls, context, searcher, lambda stage, **detail: None, held_acts)
    time_limits = calculation.for_answer(limits)
    sources = answer_sources.build(context, record)
    execution = turn.execution_record(record)
    draft = response_writer.write(calls, context, record, sources, interpretation=interpreted, execution=execution,
                                  time_limits=time_limits)
    authorities = response_authorities.check(context, record, sources, draft, case_index=case_index,
                                             provision_reader=provision_reader)
    reviewed = response_review.review(calls, context, record, sources, draft, execution=execution,
                                      authority_evidence=authorities, time_limits=time_limits)
    if not reviewed["accepted"] or response_writer.dates_not_given(draft, context, sources, time_limits):
        raise AssertionError("A saved v5 turn is built here only from an answer its review accepted")
    elements = response_rendering.render(context, record, sources, draft, reviewed, execution=execution,
                                         authority_evidence=authorities, time_limits=limits)
    activity = {"contract": turn.RECORDS_CONTRACT, "interpretation": interpreted, "research": record,
                "sources": sources, "draft": draft, "review": reviewed, "execution": execution,
                "rendering_contract": response_rendering.CONTRACT, "authority_evidence": authorities,
                "calculation": limits, "release": None}
    return elements, activity, calls.metrics()
