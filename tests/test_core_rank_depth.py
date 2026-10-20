"""The reranker reads only the strongest candidates (owner decision, 14 Oct 2026;
search contract v8).

For each corpus, the first RANK_DEPTH positions of the fused shortlist are read and
ranked (provisions 40, judgments 100); later positions are never read. Saved v7 records
replay unchanged.
"""
from copy import deepcopy

import pytest

from nm.core_engine import retrieval
from nm.core_engine.retrieval import HybridSearcher, validate_search
from tests.test_core_judgment_order import Judgments, paragraph
from tests.test_current_brain_retrieval import Collection, QUERIES


class ManyProvisions(Collection):
    def __init__(self, count):
        super().__init__()
        self.rows = {p: {"chunk_id": f"s{p}", "full_text": f"Section {p} text.", "act_id": "act",
                         "act_name": "Act", "section_number": str(p)} for p in range(count)}
        self.read_positions, self.ranked = [], 0

    def lexical(self, query, depth): return list(self.rows)
    def semantic(self, query, depth): return list(self.rows)
    def read(self, positions):
        self.read_positions.append(list(positions))
        return super().read(positions)
    def rerank(self, pairs, *, anchors=None):
        self.ranked += len(pairs)
        return [1.0] * len(pairs)


def test_provisions_rank_only_the_first_positions_of_the_fused_shortlist():
    depth = retrieval.RANK_DEPTH["provision"]
    provisions = ManyProvisions(depth + 20)
    result = HybridSearcher({"provision": provisions, "judgment": Collection("judgment")}).search(QUERIES)
    assert result["contract"] == retrieval.CONTRACT == "hybrid_retrieval_v9"
    assert provisions.read_positions == [list(range(depth))]
    assert provisions.ranked == depth
    assert result["state"] == "ready"
    assert validate_search(result, QUERIES) == result


def test_judgments_rank_only_the_first_positions_and_v7_records_replay():
    depth = retrieval.RANK_DEPTH["judgment"]
    rows = [paragraph(f"case-{n}", n, f"Judgment {n} in the court's words.") for n in range(depth + 30)]
    judgments = Judgments(rows, {row["full_text"]: 0.5 for row in rows})
    # Each query reaches a different part of the corpus, so the fused shortlist
    # (PER_QUERY_POOL from each query) is longer than the ranking depth.
    order = {QUERIES[0]["text"]: list(judgments.rows), QUERIES[1]["text"]: list(judgments.rows)[::-1]}
    judgments.lexical = judgments.semantic = lambda query, depth: order[query]
    reads, ranked = [], []
    read, rerank = judgments.read, judgments.rerank
    judgments.read = lambda positions: reads.append(list(positions)) or read(positions)
    judgments.rerank = lambda pairs, *, anchors=None: ranked.extend(pairs) or rerank(pairs, anchors=anchors)
    result = HybridSearcher({"provision": Collection(), "judgment": judgments}).search(QUERIES)
    assert len(set(order[QUERIES[0]["text"]][:retrieval.PER_QUERY_POOL])
               | set(order[QUERIES[1]["text"]][:retrieval.PER_QUERY_POOL])) > depth
    assert len(reads) == 1 and len(reads[0]) == depth and len(ranked) == depth
    assert validate_search(result, QUERIES) == result
    for older in (retrieval.JUDGMENT_ORDER_CONTRACT, retrieval.RANK_DEPTH_CONTRACT):
        saved = deepcopy(result)
        saved["contract"] = older
        for field in ("connected", "connections", "links"):  # v9 added them (P32)
            del saved[field]
        assert validate_search(saved, QUERIES) == saved


def test_a_caller_that_chooses_among_more_candidates_can_ask_for_them():
    provisions = ManyProvisions(30)
    searcher = HybridSearcher({"provision": provisions, "judgment": Collection("judgment")})
    default = searcher.search(QUERIES)
    assert sum(c["kind"] == "provision" for c in default["candidates"]) == retrieval.RESULTS_PER_KIND
    more = searcher.search(QUERIES, results={"provision": 20})
    assert sum(c["kind"] == "provision" for c in more["candidates"]) == 20
    assert validate_search(more, QUERIES) == more
    for wrong in ({"provision": 0}, {"provision": 51}, {"statute": 6}, {"provision": "20"}):
        with pytest.raises(ValueError, match="between 1 and 50"):
            searcher.search(QUERIES, results=wrong)
