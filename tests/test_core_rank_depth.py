"""The reranker reads only the strongest candidates (owner decision, 14 Oct 2026;
search contract v8).

For each corpus, the first RANK_DEPTH positions of the fused shortlist are read and
ranked (provisions 40, judgments 100); later positions are never read. Saved v7 records
replay unchanged.
"""
from copy import deepcopy

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
    assert result["contract"] == retrieval.CONTRACT == "hybrid_retrieval_v8"
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
    saved_v7 = deepcopy(result)
    saved_v7["contract"] = retrieval.JUDGMENT_ORDER_CONTRACT
    assert validate_search(saved_v7, QUERIES) == saved_v7
