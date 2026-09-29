"""Appending bare acts to the search: cut the way the store is cut, and never a vector
mapped onto the wrong passage. LB-106.

Owner, 29 September 2026: *"... and also adding more docs to the vector index as append
and rebuild BM25"*. The job is `pipeline/append_bare_acts.py`; the owner runs it.

THE RULES:
1. A section number is a section once. Numbered rows -- a table, a list inside a section,
   a schedule, an arrangement of sections printed first -- are words, never sections;
   the section after them opens as a section. What is not appended is said.
2. Passages are cut as the store cuts them: a head carrying the whole section, each
   division carrying only its own words under a header citing it, in the store's row
   shape -- except where the store's chunker was wrong ("(i)" after "(h)" is a letter).
3. Vector n is passage n after an append, as before it: the new vectors, the rebuilt
   BM25 and the new passages all take the next positions, and the lineage record is
   rewritten to agree.
4. Nothing changes when an append is refused -- an Act already held, a set that does not
   agree, a BM25 rebuild that is short -- or when it is a dry run.

The parser was measured against the library (29 September 2026): all 1,649 parseable
raw Acts start at section 1 and none numbers a section twice (the store's chunker left
21,947 passage identifiers used twice); 90% of the passages cut from a 74-Act sample are
word for word the store's own.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from nm.legal_brain.retrieve import hybrid_sections as hybrid
from pipeline import append_bare_acts as job

pytestmark = pytest.mark.class_a

ACT = """Tools for analyzing structure and cite text of judgments
The Synthetic Tenancy Act, 1999
1.
Short title and commencement.
(1)
This Act may be called the Synthetic Tenancy Act, 1999.
(2)
It comes into force at once.
2.
Definitions.
- In this Act, unless the context otherwise requires,-
(a)
"landlord" means the owner;
(h)
"premises" means a building;
(i)
"tenant" means the occupier;
(j)
"rent" means the sum paid.
3.
Eviction.
(1)
No tenant shall be evicted except-
(a)
for default, where-
(i)
rent is unpaid for two months; or
(ii)
the tenant sublets;
(b)
for bona fide need.
Provided that no order shall be made within one year.
Provided further that the Controller may extend time.
Explanation.- "need" includes a family member's need.
The fees are-
1.
Filing, ten rupees.
2.
Copies, five rupees.
4.
Appeal.
- An appeal lies to the District Judge.
{|
| first row
5.
Row five of a table.
6.
Row six of a table.
7.
Row seven of a table.
|}
4A. Limitation for appeal.- An appeal shall be filed within thirty days.
5.
Power to make rules.
- The Government may make rules.
THE SCHEDULE
1.
Form of notice.
2.
Form of appeal.
"""


def _act(tmp_path, text=ACT, name="1999_7_The Synthetic Tenancy Act, 1999.txt",
         jurisdiction="Union of India"):
    path = tmp_path / name
    path.write_text(text, encoding="utf8")
    return job.parse_act(path, jurisdiction)


def _ids(rows):
    return {r["chunk_id"].split("_SECTION_", 1)[1]: r for r in rows}


# ===================== 1. a section number is a section once =====================

def test_the_act_s_sections_are_found_and_its_rows_are_not(tmp_path):
    act = _act(tmp_path)
    assert [s.number for s in act.sections] == ["1", "2", "3", "4", "4A", "5"], (
        "a table row, a list item or a schedule entry was taken for a section")
    three = next(s for s in act.sections if s.number == "3")
    assert "Filing, ten rupees." in three.lines, "a list inside a section lost its words"
    four = next(s for s in act.sections if s.number == "4")
    assert "Row five of a table." in four.lines, "a table inside a section lost its words"
    assert not any("Form of notice." in s.lines for s in act.sections)
    assert any("THE SCHEDULE" in note and "not appended" in note for note in act.notes), (
        "text not appended must be said")


def test_a_schedule_without_a_heading_is_not_appended_even_past_the_last_section(tmp_path):
    """Wild Life (Protection) Act, 1972: section 66, then a schedule numbered from 1 to
    past 66, with no heading line before it."""
    text = "\n".join([
        *[line for n in range(1, 5) for line in (f"{n}.", f"Section {n}.", f"- Text {n}.")],
        *[line for n in range(1, 9) for line in (f"{n}.", f"Animal {n}")],
    ])
    act = _act(tmp_path, text, name="1972_7_The Synthetic Wild Life Act, 1972.txt")
    assert [s.number for s in act.sections] == ["1", "2", "3", "4"], (
        "a schedule's entries were appended as sections")
    assert not any("Animal 5" in line for s in act.sections for line in s.lines)
    assert any("after the last section (4)" in note for note in act.notes)


def test_an_annexure_inside_the_act_is_its_section_s_and_the_act_resumes(tmp_path):
    """Central Motor Vehicles Rules, 1989: annexures printed inside rule 115, then
    rules 115B onwards."""
    text = "\n".join([
        *[line for n in range(1, 21) for line in (f"{n}.", f"Rule {n}.", f"- Text {n}.")],
        "ANNEXURE I", "1.", "Petrol.", "2.", "Diesel.", "3.", "Gas.",
        *[line for n in range(21, 24) for line in (f"{n}.", f"Rule {n}.", f"- Text {n}.")],
    ])
    act = _act(tmp_path, text, name="1989_6_Synthetic Motor Rules, 1989.txt")
    assert [s.number for s in act.sections] == [str(n) for n in range(1, 24)]
    assert "Diesel." in act.sections[19].lines, "the annexure left the rule it is printed in"
    assert any("ANNEXURE I" in note and "resumes at section 21" in note
               for note in act.notes)


def test_a_list_running_ahead_of_the_sections_loses_to_them(tmp_path):
    """Central Motor Vehicles Rules, 1989, rule 4: items "8." to "12." of a list of
    documents, printed as sections are, before rules 5 to 12."""
    text = "\n".join([
        "1.", "Short title.", "- These rules may be called the Synthetic Rules.",
        "2.", "Documents.", "- Any of the following:",
        "8.", "School certificate,", "9.", "Birth certificate,",
        *[line for n in range(3, 9) for line in (f"{n}.", f"Rule {n}.", f"- Text of rule {n}.")],
    ])
    act = _act(tmp_path, text, name="1989_5_Synthetic Rules, 1989.txt")
    assert [s.number for s in act.sections] == [str(n) for n in range(1, 9)]
    rule_eight = next(s for s in act.sections if s.number == "8")
    assert rule_eight.title == "Rule 8.", "a list item was kept as rule 8"


def test_an_arrangement_of_sections_printed_first_is_not_the_act(tmp_path):
    text = "\n".join([
        "ARRANGEMENT OF SECTIONS", "1. Short title.", "2. Definitions.", "3. Offences.",
        "1.", "Short title.", "- This Act may be called the Synthetic Act.",
        "2.", "Definitions.", "- In this Act, words mean what they say.",
        "3.", "Offences.", "- Whoever breaks this Act is punished.",
    ])
    act = _act(tmp_path, text, name="2001_3_The Synthetic Act, 2001.txt")
    assert [(s.number, s.lines[0]) for s in act.sections] == [
        ("1", "- This Act may be called the Synthetic Act."),
        ("2", "- In this Act, words mean what they say."),
        ("3", "- Whoever breaks this Act is punished.")]


def test_a_section_printed_again_continues_it_and_a_carried_letter_numbers_it(tmp_path):
    text = "\n".join([
        "1.", "Short title.", "- Called the Synthetic Act.",
        "2.", "Definitions.", "(a)", "\"x\" means x;",
        "2.", "[(aa) \"y\" means y;]",
        "3.", "Fees.", "- Fees are payable.",
        "3.", "-A. Waiver of fees.", "- Fees may be waived.",
    ])
    act = _act(tmp_path, text, name="2002_4_The Synthetic Act, 2002.txt")
    assert [s.number for s in act.sections] == ["1", "2", "3", "3A"]
    assert "[(aa) \"y\" means y;]" in act.sections[1].lines
    assert act.sections[3].title == "Waiver of fees."


def test_the_name_is_cased_as_the_store_cases_it(tmp_path):
    act = _act(tmp_path, name="1998_5_Andhra Pradesh Women's Commission Act, 1998.txt",
               jurisdiction="Telangana")
    assert act.act_name == "Telangana 1998 5 Andhra Pradesh Women'S Commission Act, 1998"
    assert act.act_id == "TELANGANA_1998_5_ANDHRA PRADESH WOMEN'S COMMISSION ACT, 1998"


# =================== 2. passages cut as the store cuts them ======================

def test_each_passage_carries_its_own_words_under_a_header_citing_it(tmp_path):
    act = _act(tmp_path)
    rows = _ids(job.passages_for(act))
    head = rows["3"]["blob"]["full_text"]
    assert head.startswith(f"{act.act_name},  — s.3: Eviction.\n3.\nEviction.\n(1)")
    assert "for bona fide need." in head, "a section head must carry the whole section"
    clause = rows["3_SUB_1_CLAUSE_b"]["blob"]["full_text"]
    assert clause == f"{act.act_name},  — s.3(1)(b): Eviction.\n(b)\nfor bona fide need."
    assert rows["3_SUB_1_CLAUSE_a"]["blob"]["full_text"].endswith("(a)\nfor default, where-"), (
        "a division carried its children's words")


def test_i_after_h_is_a_letter_and_i_before_ii_is_a_numeral(tmp_path):
    rows = _ids(job.passages_for(_act(tmp_path)))
    assert "2_CLAUSE_i" in rows and "2_CLAUSE_h_SUBCLAUSE_i" not in rows, (
        "a definitions clause (i) was cited as a sub-clause of (h)")
    assert {"3_SUB_1_CLAUSE_a_SUBCLAUSE_i", "3_SUB_1_CLAUSE_a_SUBCLAUSE_ii"} <= set(rows)


def test_provisos_belong_to_the_innermost_division_and_are_numbered_through_it(tmp_path):
    rows = _ids(job.passages_for(_act(tmp_path)))
    assert {"3_SUB_1_CLAUSE_b_PROVISO_1", "3_SUB_1_CLAUSE_b_PROVISO_2",
            "3_SUB_1_CLAUSE_b_EXPLANATION_1"} <= set(rows)
    proviso = rows["3_SUB_1_CLAUSE_b_PROVISO_2"]
    assert proviso["atom_type"] == "proviso"
    assert " — s.3(1)(b) [proviso]: Eviction." in proviso["blob"]["full_text"]
    assert proviso["blob"]["parent_chain"] == ["section_3", "sub_section_1", "clause_b",
                                               "proviso_2"]


def test_every_row_has_the_store_s_shape(tmp_path):
    rows = job.passages_for(_act(tmp_path))
    fields = ["chunk_id", "doc_type", "act_id", "act_name", "year", "chapter",
              "section_number", "section_title", "sub_section", "clause", "sub_clause",
              "atom_type", "parent_chunk_id", "parent_chain", "full_text", "keywords"]
    for row in rows:
        assert list(row["blob"]) == fields
        assert row["blob"]["doc_type"] == hybrid.DOC_TYPE
    heads = [r for r in rows if r["atom_type"] == "section_head"]
    assert all(r["parent_chunk_id"] is None and r["blob"]["parent_chunk_id"] == ""
               for r in heads)


# ================= 3 and 4. vector n is passage n; refusals change nothing ===========

def _vector(text: str):
    import numpy as np

    seed = sum(text.encode("utf8")) % (2 ** 32)
    v = np.random.default_rng(seed).standard_normal(hybrid.DIMENSIONS).astype("float32")
    return v / np.linalg.norm(v)


def _encode(texts):
    import numpy as np

    return np.stack([_vector(t) for t in texts])


class _BM25:
    def __init__(self, short=False):
        self.tokens, self.short = None, short

    def __call__(self, tokens, folder):
        self.tokens = tokens
        folder.mkdir()
        docs = len(tokens) - (1 if self.short else 0)
        (folder / "params.index.json").write_text(json.dumps({"num_docs": docs}))
        return docs


def _library(tmp_path):
    """A consistent set of three held passages, with its lineage record."""
    import faiss

    store = tmp_path / "store"
    store.mkdir()
    held = [f"held passage {n}" for n in range(3)]
    index = faiss.IndexFlatIP(hybrid.DIMENSIONS)
    index.add(_encode(held))
    faiss.write_index(index, str(store / "bare.index"))
    (store / "bm25").mkdir()
    params = store / "bm25" / "params.index.json"
    params.write_text(json.dumps({"num_docs": 3}))
    with sqlite3.connect(store / "chunks.db") as con:
        con.execute("create table chunks (doc_type TEXT NOT NULL, pos INTEGER NOT NULL, "
                    "chunk_id TEXT NOT NULL, act_id TEXT, case_id TEXT, parent_chunk_id TEXT, "
                    "atom_type TEXT, section_number TEXT, blob TEXT NOT NULL, "
                    "PRIMARY KEY (doc_type, pos))")
        for pos, text in enumerate(held):
            con.execute("insert into chunks values ('bare_act', ?, ?, 'HELD_ACT', null, null, "
                        "'section_head', '1', ?)", (pos, f"held{pos}",
                                                     json.dumps({"full_text": text})))
    con.close()
    record = {"schema": 1, "doc_type": "bare_act", "model": hybrid.EMBED_MODEL,
              "dimensions": hybrid.DIMENSIONS, "passages": 3,
              "vector_index": {"path": "bare.index", "vectors": 3,
                               "bytes": (store / "bare.index").stat().st_size},
              "bm25": {"path": "bm25", "num_docs": 3,
                       "params_sha256": hashlib.sha256(params.read_bytes()).hexdigest()},
              "passage_store": {"path": "chunks.db"}}
    lineage = tmp_path / "lineage.json"
    lineage.write_text(json.dumps(record))
    assert hybrid.check_lineage(record, store) == []
    return job.Store(store, lineage)


def _state(store):
    with sqlite3.connect(store.vector_store / "chunks.db") as con:
        rows = con.execute("select pos, chunk_id from chunks order by pos").fetchall()
    con.close()
    return (rows, (store.vector_store / "bare.index").read_bytes(),
            store.lineage.read_text(), sorted(p.name for p in store.vector_store.iterdir()))


def test_after_an_append_vector_n_is_still_passage_n(tmp_path):
    import faiss

    store = _library(tmp_path)
    rows = job.passages_for(_act(tmp_path))
    bm25 = _BM25()
    summary = job.append(rows, store, encode=_encode, build_bm25=bm25)
    assert summary["appended"] == len(rows) and summary["passages"] == 3 + len(rows)

    with sqlite3.connect(store.vector_store / "chunks.db") as con:
        held = con.execute("select pos, chunk_id, blob from chunks order by pos").fetchall()
    con.close()
    assert [pos for pos, _, _ in held] == list(range(3 + len(rows))), "positions have a gap"
    assert [cid for _, cid, _ in held[3:]] == [r["chunk_id"] for r in rows]
    index = faiss.read_index(str(store.vector_store / "bare.index"))
    for pos, _, blob in held:
        text = json.loads(blob)["full_text"]
        assert float(index.reconstruct(pos) @ _vector(text)) > 0.999, (
            f"vector {pos} is not the vector of passage {pos}")
    assert bm25.tokens == [hybrid.bm25_tokens(json.loads(b)["full_text"]) for _, _, b in held], (
        "BM25 was not rebuilt over every passage in position order")

    record = json.loads(store.lineage.read_text())
    assert record["passages"] == 3 + len(rows) and record["appended"][-1]["acts"] == [
        rows[0]["blob"]["act_id"]]
    assert record["bm25"]["params_sha256"] == hashlib.sha256(
        (store.vector_store / "bm25" / "params.index.json").read_bytes()).hexdigest()
    assert hybrid.check_lineage(record, store.vector_store) == [], "the new set does not agree"
    assert any(p.name.startswith("bare.index.before-") for p in store.vector_store.iterdir())
    assert any(p.name.startswith("bm25.before-") for p in store.vector_store.iterdir())


def test_an_act_already_held_is_refused_and_nothing_changes(tmp_path):
    store = _library(tmp_path)
    rows = job.passages_for(_act(tmp_path))
    for row in rows:
        row["blob"]["act_id"] = "HELD_ACT"
    before = _state(store)
    with pytest.raises(RuntimeError, match="already in the store"):
        job.append(rows, store, encode=_encode, build_bm25=_BM25())
    assert _state(store) == before


def test_repeated_new_passage_identity_is_refused_before_any_write(tmp_path):
    store = _library(tmp_path)
    rows = job.passages_for(_act(tmp_path))
    rows[1]["chunk_id"] = rows[0]["chunk_id"]
    before = _state(store)
    with pytest.raises(RuntimeError, match="repeat a chunk identifier"):
        job.append(rows, store, encode=_encode, build_bm25=_BM25())
    assert _state(store) == before


def test_a_set_that_does_not_agree_is_refused_and_nothing_changes(tmp_path):
    store = _library(tmp_path)
    (store.vector_store / "bm25" / "params.index.json").write_text(json.dumps({"num_docs": 4}))
    before = _state(store)
    with pytest.raises(RuntimeError, match="not consistent"):
        job.append(job.passages_for(_act(tmp_path)), store, encode=_encode,
                   build_bm25=_BM25())
    assert _state(store) == before


def test_a_short_bm25_rebuild_is_refused_and_nothing_changes(tmp_path):
    store = _library(tmp_path)
    before = _state(store)
    with pytest.raises(RuntimeError, match="does not hold every passage"):
        job.append(job.passages_for(_act(tmp_path)), store, encode=_encode,
                   build_bm25=_BM25(short=True))
    assert _state(store) == before, "a refused append left a passage, a file or a record"


def test_a_failed_passage_transaction_removes_both_staged_indexes(tmp_path):
    store = _library(tmp_path)
    with sqlite3.connect(store.vector_store / "chunks.db") as con:
        con.execute("create trigger refuse_append before insert on chunks "
                    "when NEW.doc_type='bare_act' and NEW.pos>=3 "
                    "begin select raise(abort, 'insert refused'); end")
    before = _state(store)
    with pytest.raises(sqlite3.IntegrityError, match="insert refused"):
        job.append(job.passages_for(_act(tmp_path)), store, encode=_encode,
                   build_bm25=_BM25())
    assert _state(store) == before, "a failed transaction left staged indexes or passages"


def test_a_dry_run_changes_nothing(tmp_path):
    store = _library(tmp_path)
    before = _state(store)
    summary = job.append(job.passages_for(_act(tmp_path)), store, encode=_encode,
                         build_bm25=_BM25(), dry_run=True)
    assert summary["dry_run"] and _state(store) == before
