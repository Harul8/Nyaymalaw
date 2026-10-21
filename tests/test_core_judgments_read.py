"""The research chooses judgments, not paragraphs (owner decision P31, 20-21 Oct 2026).

Each judgment a dispute's pick chose, at most five in the order chosen, is read whole when no
longer than about 8,000 tokens; a longer one is read as an extract that says so - its opening,
its conclusion and order, the paragraphs search found with one or two either side, and the
paragraphs those name and where the court sets out the issues. The paragraphs search found are
marked either way. Scripted picks and a small held store prove the reading, not the law.
"""
import json
import sqlite3
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, research
from nm.core_engine.retrieval import DIMENSIONS, EMBED_MODEL, HybridSearcher, LocalCollection
from tests.test_core_research import Model, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


class _NoModels:
    def load(self):
        return None


def paragraph(case, number, text, kind="reasoning"):
    return {"doc_type": "case_law", "chunk_id": f"{case}_P{number:03d}", "case_id": case,
            "case_name": f"{case.title()} v State", "court": "Supreme Court of India", "year": "2001",
            "cited_by_count": 10, "paragraph_num": str(number), "paragraph_type": kind, "full_text": text}


def held(tmp_path, rows):
    """A judgment store holding `rows` in order, searched as its words say."""
    database = tmp_path / "judgments.db"
    with sqlite3.connect(database) as db:
        db.execute("create table chunks (doc_type text not null, pos integer not null, chunk_id text not null, "
                   "act_id text, case_id text, parent_chunk_id text, atom_type text, section_number text, "
                   "blob text not null, primary key (doc_type, pos))")
        db.executemany("insert into chunks values (?,?,?,?,?,?,?,?,?)", [
            ("case_law", position, row["chunk_id"], None, row["case_id"], None, "paragraph", None, json.dumps(row))
            for position, row in enumerate(rows)])
    db.close()
    lineage = tmp_path / "judgments.lineage.json"
    lineage.write_text(json.dumps({"schema": 1, "doc_type": "case_law", "model": EMBED_MODEL, "dimensions": DIMENSIONS,
                                   "passages": len(rows), "vector_index": {"path": "none.index"},
                                   "bm25": {"path": "none-bm25"}, "passage_store": {"path": "judgments.db"}}),
                       encoding="utf-8")
    store = LocalCollection(corpus_dir=tmp_path, lineage=lineage, doc_type="case_law", models=_NoModels())
    found = [position for position, row in enumerate(rows) if "FOUND" in row["full_text"]]
    store.lexical = store.semantic = lambda query, depth: list(found)
    store.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    return store


def researched(tmp_path, rows, choose=lambda ids: ids):
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(), ctx)
    searcher = HybridSearcher({"provision": Collection(), "judgment": held(tmp_path, rows)})
    record = research.retrieve(plan, searcher, ctx, model=Model(choose_judgments=choose))
    return ctx, plan, record


def short_judgment(case="alpha", paragraphs=8):
    return [paragraph(case, n, f"Paragraph {n} of {case}." + (" FOUND the rule applies." if n == 4 else ""))
            for n in range(1, paragraphs + 1)]


def test_a_short_judgment_chosen_is_read_whole_with_what_search_found_marked(tmp_path):
    ctx, plan, record = researched(tmp_path, short_judgment())
    (entry,) = record["judgments"]["D1"]
    assert entry["whole"] and entry["paragraphs"] == 8 and len(entry["read"]) == 8
    assert entry["found"] == entry["chosen"] == [3]
    assert research.validate(record, plan, ctx) == record
    sources = answer_sources.build(ctx, record)
    judged = [row for row in sources.values() if row["kind"] == "judgment"]
    assert len(judged) == 8 and {row["coverage"][0]["scope"] for row in judged} == {"whole_judgment"}
    shown = answer_sources.presentation(sources, aliased=True, compact=True, work_ids=["t2:w1"])
    found = [passage for passage in shown["passages"] if passage.get("found")]
    assert [passage["text"] for passage in found] == ["Paragraph 4 of alpha. FOUND the rule applies."]


def test_a_long_judgment_is_read_as_an_extract_that_keeps_what_matters(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "WHOLE_JUDGMENT_CHARACTERS", 1500)
    rows = [paragraph("beta", 1, "IN THE SUPREME COURT OF INDIA. Beta v State. JUDGMENT. Hon'ble Judge, J.")]
    rows += [paragraph("beta", n, f"Paragraph {n} recites the facts at length. " * 3) for n in range(2, 21)]
    rows[5]["full_text"] = "6. The questions that arise for our consideration are these."
    rows[12]["full_text"] = "13. FOUND: the rule applies, as held in para 9 above."
    rows[19] = paragraph("beta", 20, "20. The appeal is dismissed. No costs.", kind="order")
    ctx, plan, record = researched(tmp_path, rows)
    (entry,) = record["judgments"]["D1"]
    assert not entry["whole"] and entry["paragraphs"] == 20
    why = {int(p["row"]["paragraph_num"]): p["why"] for p in entry["read"]}
    assert why[1] == ["opening"] and "order" in why[20] and "chosen" in why[13]
    assert "beside" in why[11] and "beside" in why[15] and "named" in why[9] and "issues" in why[6]
    assert research.validate(record, plan, ctx) == record
    sources = answer_sources.build(ctx, record)
    coverage = next(row for row in sources.values() if row["kind"] == "judgment")["coverage"][0]
    assert coverage["scope"] == "judgment_extract" and coverage["bounded"]
    assert (coverage["held_paragraphs"], coverage["read_paragraphs"]) == (20, len(entry["read"]))
    stripped = deepcopy(record)
    stripped["judgments"]["D1"][0]["read"] = stripped["judgments"]["D1"][0]["read"][1:]  # its opening dropped
    with pytest.raises(ValueError, match="P31"):
        research.validate(stripped, plan, ctx)


def test_at_most_five_judgments_a_dispute_in_the_order_chosen(tmp_path):
    rows = [row for case in ("one", "two", "three", "four", "five", "six")
            for row in short_judgment(case, paragraphs=4)]
    ctx, plan, record = researched(tmp_path, rows)
    assert [entry["case_id"] for entry in record["judgments"]["D1"]] == ["one", "two", "three", "four", "five"]
    assert research.validate(record, plan, ctx) == record
    changed = deepcopy(record)
    changed["judgments"]["D1"] = changed["judgments"]["D1"][:4]
    with pytest.raises(ValueError, match="the pick chose"):
        research.validate(changed, plan, ctx)


def test_a_judgment_that_cannot_be_read_keeps_the_paragraphs_chosen_of_it(tmp_path):
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(), ctx)
    store = held(tmp_path, short_judgment())
    store.judgment_paragraphs = lambda case_id: (_ for _ in ()).throw(ValueError("unreadable"))
    record = research.retrieve(plan, HybridSearcher({"provision": Collection(), "judgment": store}), ctx,
                               model=Model())
    assert record["judgments"]["D1"] == [{"case_id": "alpha", "unread": "unreadable"}]
    assert research.validate(record, plan, ctx) == record
    judged = [row for row in answer_sources.build(ctx, record).values() if row["kind"] == "judgment"]
    assert judged and {row["coverage"][0]["scope"] for row in judged} <= {"adjacent_indexed_segments",
                                                                           "selected_indexed_segment"}
