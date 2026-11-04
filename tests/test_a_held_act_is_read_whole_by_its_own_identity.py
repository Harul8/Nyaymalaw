"""A held Act is read whole by its own identity (plan AN.39, D53; owner, 4 Nov 2026: "only the paragraph with reading the whole doc act
or judgement as optional"). The reading pane shows a passage of an Act; reading the whole Act is the advocate's option, and the Act is
read by the passage's own Act identity - every held part in stored order, each checked as a search result is - never by a name or a
search; a store that cannot be read is said to be unavailable. A small invented store proves the reading, not the law."""
import json
import sqlite3

import pytest

from nm.core_engine.retrieval import DIMENSIONS, EMBED_MODEL, HybridSearcher, LocalCollection, SearchUnavailable

pytestmark = pytest.mark.class_a


class _NoModels:
    def load(self):
        return None


def part(act, number, section, text):
    return {"doc_type": "bare_act", "chunk_id": f"{act}_s{section}_{number}", "act_id": act, "act_name": f"The {act.title()} Act, 1901",
            "section_number": section, "section_title": f"Heading {section}", "full_text": text}


def held(tmp_path, rows):
    database = tmp_path / "acts.db"
    with sqlite3.connect(database) as db:
        db.execute("create table chunks (doc_type text not null, pos integer not null, chunk_id text not null, "
                   "act_id text, case_id text, parent_chunk_id text, atom_type text, section_number text, "
                   "blob text not null, primary key (doc_type, pos))")
        db.executemany("insert into chunks values (?,?,?,?,?,?,?,?,?)", [
            ("bare_act", position, row["chunk_id"], row["act_id"], None, None, "section", row["section_number"], json.dumps(row))
            for position, row in enumerate(rows)])
    db.close()
    lineage = tmp_path / "acts.lineage.json"
    lineage.write_text(json.dumps({"schema": 1, "doc_type": "bare_act", "model": EMBED_MODEL, "dimensions": DIMENSIONS,
                                   "passages": len(rows), "vector_index": {"path": "none.index"},
                                   "bm25": {"path": "none-bm25"}, "passage_store": {"path": "acts.db"}}), encoding="utf-8")
    return LocalCollection(corpus_dir=tmp_path, lineage=lineage, doc_type="bare_act", models=_NoModels())


ROWS = [part("alpha", 1, "1", "1. Short title."), part("beta", 1, "1", "1. Another Act."), part("alpha", 1, "2", "2. Definitions."),
        part("alpha", 2, "2", "(b) more definitions."), part("alpha", 1, "3", "3. The rule.")]


def test_an_act_is_read_whole_by_its_own_identity_in_stored_order(tmp_path):
    store = held(tmp_path, ROWS)
    read = HybridSearcher({"provision": store}).read_act("alpha")
    assert read["corpus_revision"] == store.revision()
    assert [(position, row["full_text"]) for position, row in read["parts"]] == [
        (0, "1. Short title."), (2, "2. Definitions."), (3, "(b) more definitions."), (4, "3. The rule.")]
    assert {row["act_id"] for _, row in read["parts"]} == {"alpha"}, "nothing of another Act"


def test_an_act_not_held_or_a_store_that_cannot_be_read_is_unavailable_never_something_else(tmp_path):
    store = held(tmp_path, ROWS)
    with pytest.raises(SearchUnavailable, match="cannot be read"):
        HybridSearcher({"provision": store}).read_act("gamma")
    with pytest.raises(ValueError, match="its own identity"):
        store.act_parts(" ")
    with pytest.raises(SearchUnavailable, match="Held Acts cannot be read"):
        HybridSearcher({}).read_act("alpha")
