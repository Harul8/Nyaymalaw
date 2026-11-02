"""The held law is searched for the understanding's questions as soon as the understanding and its search phrases are final, beside
the papers' side-by-side reading and the weighing (plan AN.33, D28; research v14; piece 33q).

The owner, 2 Nov 2026: "The answer is slow - it must be complete, however, check if there any other issues causing delay that can
reduce time without reducing quality." The second measuring run found the search began only after the weighing and its check. The
plan now hands its research work over as soon as its understanding and search phrases are final; the turn starts their searches
there, and the research uses each search begun so once, for the work item it was made for where that item still searches exactly
so - the record is what it would have been. A question the weighing raises, and any work item whose search would differ, is searched
after the weighing, as before; a search begun for nothing the plan keeps is cancelled where it has not started. Matters are invented.
"""
from collections import Counter
from concurrent.futures import Future

import pytest

from nm.core_engine import answer_sections, research
from nm.core_engine.retrieval import HybridSearcher
from nm.shared.store_file_store import FileMatterStore
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import Model as ResearchModel, _result, proposal
from tests.test_core_response_writer import TwoDisputeLibrary
from tests.test_core_understanding import context
from tests.test_the_plan_records_the_chronology import Beside, bundle

pytestmark = pytest.mark.class_a


class Counted:
    """The two-dispute library, counting the searches it makes by the work item and the question each is made for."""

    def __init__(self):
        self.library, self.made = TwoDisputeLibrary.searcher(), Counter()
        search = self.library.search

        def counted(queries, instruments=None, **kw):
            self.made[queries[0]["query_id"].rsplit(":", 1)[0], queries[0]["context"]] += 1
            return search(queries, instruments, **kw)
        self.library.search = counted


def whole(plan, searcher, ctx, started=None):
    return answer_sections.Researched(ctx, plan, research.retrieve_parts(plan, searcher, ctx, model=ResearchModel(),
                                                                         started=started)).whole()


def test_the_plan_hands_its_research_work_over_before_the_points_are_weighed():
    order, handed = [], []

    class Weighed(Beside):
        def structured(self, prompt, schema, tier, **kwargs):
            if prompt.operation in ("core_research_weigh", "core_research_weigh_check"):
                order.append(prompt.operation)
                key = "weights" if prompt.operation == "core_research_weigh" else "corrections"
                return _result({key: []}, tier)
            return super().structured(prompt, schema, tier, **kwargs)

    def early(work):
        order.append("handed")
        handed.append(work)
    record = research.plan(Weighed(), bundle(), early=early)
    assert order[0] == "handed" and order.count("handed") == 1 and "core_research_weigh" in order
    assert handed == [record["work"]] and record["work"], "where the weighing raises no question, the work handed is the plan's"


def test_no_work_is_handed_over_where_there_is_no_matter_or_the_plan_refuses_the_proposal(monkeypatch):
    handed = []
    assert research.plan(Beside(), bundle(), wanted=lambda: False, early=handed.append)["work"] == [] and handed == []
    checked = research.accept

    def refusing(proposal_, ctx, **kw):
        if "weights" not in proposal_ and "transfers" not in proposal_:
            raise SchemaViolation("scripted refusal")
        return checked(proposal_, ctx, **kw)
    monkeypatch.setattr(research, "accept", refusing)
    research.plan(Beside(), bundle(), early=handed.append)
    assert handed == [], "a proposal the plan's check refuses starts no search"


def test_a_search_begun_early_is_used_once_and_the_record_is_what_it_would_have_been():
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 2), ctx)
    alone, together = Counted(), Counted()
    expected = whole(plan, alone.library, ctx)
    started = research.start_search(together.library, plan["work"])
    assert set(started) == {research._search_key(work, research.search_queries(work), research.search_instruments(work))
                            for work in plan["work"]} and len(started) == len(plan["work"]) == 2
    assert whole(plan, together.library, ctx, started) == expected
    assert together.made == alone.made == Counter({(work["id"], work["question"]): 1 for work in plan["work"]}), (
        "each question is searched once")
    assert research.start_search(None, plan["work"]) == {}


def test_a_work_item_whose_search_differs_is_searched_after_and_a_search_begun_for_nothing_is_cancelled():
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 2), ctx)
    first, second = plan["work"]
    expected = whole(plan, Counted().library, ctx)
    counted = Counted()
    # As where a question the weighing raises numbers the work after it on: the second item searches otherwise than it began.
    earlier = "An earlier wording of the question?"
    started = research.start_search(counted.library, [first, {**second, "question": earlier}])
    waiting = Future()
    started["a search for nothing the plan keeps"] = waiting
    assert whole(plan, counted.library, ctx, started) == expected
    assert counted.made[first["id"], first["question"]] == counted.made[second["id"], second["question"]] == 1
    assert counted.made[second["id"], earlier] <= 1 and waiting.cancelled(), "the search begun otherwise is set aside, or cancelled"


def test_the_turn_starts_the_search_from_the_plan_and_searches_each_question_once(tmp_path, monkeypatch):
    from tests.test_core_turn import ScriptedModel, run
    given, made = [], Counter()
    start, search = research.start_search, HybridSearcher.search

    def starting(searcher, work):
        given.append([item["id"] for item in work])
        return start(searcher, work)

    def counted(self, queries, instruments=None, **kw):
        made[queries[0]["query_id"].rsplit(":", 1)[0]] += 1
        return search(self, queries, instruments, **kw)
    monkeypatch.setattr(research, "start_search", starting)
    monkeypatch.setattr(HybridSearcher, "search", counted)
    response = run(FileMatterStore(tmp_path, key="synthetic-turn-fixture"), ScriptedModel(legal=True))
    assert response["committed"] == "committed"
    assert len(given) == 1 and given[0] and made == Counter(dict.fromkeys(given[0], 1))
