"""A reranker or a search leg that cannot be used stops the research of its question; it is never a fallback (plan AN.52,
piece 52b; D208, D238; the review's F-10; AN.48 register item 14).

Until 17 Nov 2026 a failed ranking offered its shortlist in first-stage order, and a failed leg left the other to stand in
for it; the result was marked 'partial' and looked like any ranked result, and an answer's authorities were chosen from it.
On a hosted server the ranking machine is started on demand and can be away. Now such a search gives nothing: the research
step records the question as a search that failed, with code's sentence, admits no evidence from it, and the other questions
are unaffected. Invented matter; stand-in library and model.
"""
from __future__ import annotations

import pytest

from nm.core_engine.research import accept as accept_plan
from nm.core_engine.research import retrieve
from nm.core_engine.retrieval import HybridSearcher, SearchUnavailable, StageUnavailable
from tests.test_core_research import Model as ResearchModel
from tests.test_core_research import proposal as research_proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection
from tests.test_search_failures_are_diagnosable import Failing

pytestmark = pytest.mark.class_a


def researched(searcher):
    ctx = context("Find the applicable law.")
    return retrieve(accept_plan(research_proposal(1, 2), ctx), searcher, ctx, model=ResearchModel())


@pytest.mark.parametrize("stage", ["rerank", "lexical"])
def test_the_question_is_recorded_as_a_search_that_failed_and_nothing_is_admitted_from_it(stage):
    away = HybridSearcher({"provision": Failing(stage, SearchUnavailable("the ranking machine is away")),
                           "judgment": Collection("judgment")})
    record = researched(away)
    assert record["searches"] == {}, "no search record, so no candidate, ranked-looking or not"
    assert record["failures"] and all(failure["stage"] == "search" for failure in record["failures"].values())
    for failure in record["failures"].values():
        assert failure["reason"].startswith("The held Acts could not be searched for this question")
        assert "Nothing was taken from a partial search" in failure["reason"]
        assert "the ranking machine is away" not in failure["reason"], "the device's own words stay in the log"
    assert record["state"] != "evaluated"


def test_with_every_stage_at_work_the_same_questions_are_searched():
    record = researched(HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")}))
    assert record["failures"] == {} and record["searches"]


def test_the_failure_says_which_corpus_which_stage_and_why():
    stopped = StageUnavailable("judgment", "rerank", "TimeoutError")
    assert (stopped.kind, stopped.stage, stopped.cause) == ("judgment", "rerank", "TimeoutError")
    assert str(stopped) == ("The held judgments could not be searched for this question: the ranking of what was found could "
                            "not be used (TimeoutError). Nothing was taken from a partial search.")
    assert isinstance(stopped, SearchUnavailable), "every place that takes a search as failed takes this one"
