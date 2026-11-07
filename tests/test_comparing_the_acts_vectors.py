"""The comparison of the Acts' earlier vectors with vectors made from their wording (plan AN.45, D107; operations/compare_retrieval.py).

It is a measurement for the owner to read before the swap, so what it reports must be what it measured: the questions are what the
comparison needs; a sample library is the same passages in the same positions under each label's vectors, with a lineage record the
search accepts; a rank counts each section once and says none where the provision is not there; a question that names its Act is searched
with the Act named and one in plain words is not; and the summary counts what it says. Invented Acts and vectors prove the arithmetic and
the shapes; the measurement itself is a bounded run on the live Act store."""
import json
import re
import sqlite3

import numpy as np
import pytest

from nm.Archives.legal_brain.retrieve import hybrid_sections as hybrid
from operations import compare_retrieval as tool
from tests.test_appending_bare_acts_never_mismaps import _encode, _vector

pytestmark = pytest.mark.class_a


def question(number, style, expect, asked="a question"):
    return {"id": number, "style": style, "asked": asked, "expect": [{"act": a, "section": s} for a, s in expect]}


def test_the_questions_are_each_one_that_has_an_answer_and_the_plain_ones_name_no_act():
    questions = tool.load_questions()
    assert len(questions) == 80 and len({q["id"] for q in questions}) == 80
    assert sum(q["style"] == "plain" for q in questions) == sum(q["style"] == "named" for q in questions) == 40
    for q in questions:
        assert q["expect"] and all(item["act"] and str(item["section"]) for item in q["expect"])
        if q["style"] == "named":
            assert len({item["act"] for item in q["expect"]}) == 1, f"{q['id']} names one Act"
        else:
            assert not re.search(r"\b(Act|Code|Sanhita)\b", q["asked"]), f"{q['id']} is in plain words: {q['asked']}"
    twins = {q["id"][:-1] for q in questions}
    assert all({f"{n}p", f"{n}n"} <= {q["id"] for q in questions} for n in twins), "each question is asked both ways"


def test_a_question_list_with_a_repeated_id_or_no_answer_is_refused(tmp_path):
    def listing(*items):
        path = tmp_path / "q.json"
        path.write_text(json.dumps({"questions": list(items)}), encoding="utf-8")
        return path
    ok = question("Q1p", "plain", [("An Act", "5")])
    assert len(tool.load_questions(listing(ok))) == 1
    with pytest.raises(ValueError, match="twice"):
        tool.load_questions(listing(ok, ok))
    with pytest.raises(ValueError, match="not a question with an answer"):
        tool.load_questions(listing(question("Q2p", "plain", [])))
    with pytest.raises(ValueError, match="no Act or no section"):
        tool.load_questions(listing(question("Q3p", "plain", [("An Act", "")])))


def test_a_rank_counts_each_section_once_and_is_none_where_the_provision_is_not_there():
    ordered = [("A", "1"), ("A", "1"), ("B", "7"), ("A", "1"), ("C", "2"), ("B", "7")]
    assert tool.first_rank(ordered, {("C", "2")}) == 3, "the section A1 counts once, though it fills three places"
    assert tool.first_rank(ordered, {("B", "7"), ("C", "2")}) == 2, "the best of several answers"
    assert tool.first_rank(ordered, {("D", "9")}) is None and tool.first_rank([], {("A", "1")}) is None


def result(number, style, **ranks):
    return {"id": number, "style": style, "asked": number,
            "ranks": {mode: {"earlier": pair[0], "wording": pair[1]} for mode, pair in ranks.items()}}


def test_the_summary_counts_what_it_says_and_compares_label_against_label():
    results = [result("1", "plain", a=(1, 1)), result("2", "plain", a=(1, 4)), result("3", "named", a=(2, 1)),
               result("4", "named", a=(None, 3)), result("5", "named", a=(12, None))]
    entry = tool.summarise(results)["a"]
    assert entry["earlier"] == {"questions": 5, "in the first 1": 2, "in the first 3": 3, "in the first 5": 3, "in the first 10": 3,
                                "found at all": 4, "mean of 1/rank": round((1 + 1 + .5 + 0 + 1 / 12) / 5, 4)}
    assert entry["wording"]["in the first 1"] == 2 and entry["wording"]["found at all"] == 4
    assert entry["wording against earlier"] == {"better": 2, "same": 1, "worse": 2}, "a rank of none is the worst"
    by_style = tool.by_style(results)
    assert by_style["plain"]["a"]["earlier"]["questions"] == 2 and by_style["named"]["a"]["earlier"]["questions"] == 3


class Collection:
    """A collection that ranks the sample's positions as told, whatever the question."""

    def __init__(self, semantic, lexical):
        self._semantic, self._lexical = semantic, lexical

    def semantic(self, query, depth):
        assert depth == tool.DEPTH
        return self._semantic

    def lexical(self, query, depth):
        return self._lexical


def test_every_question_is_put_to_both_labels_three_ways_and_only_a_named_question_names_its_act():
    places_of = {0: ("A_ID", "1"), 1: ("A_ID", "2"), 2: ("B_ID", "9")}
    collections = {"earlier": Collection([2, 1, 0], [0, 1, 2]), "wording": Collection([0, 1, 2], [0, 1, 2])}
    questions = [{**question("Q1p", "plain", [("An Act", "1")]), "_ids": {"An Act": "A_ID"}},
                 {**question("Q1n", "named", [("An Act", "2")]), "_ids": {"An Act": "A_ID"}}]
    told = []

    def searcher(label, text, acts):
        told.append((label, acts))
        return [("B_ID", "9"), ("A_ID", "2"), ("A_ID", "1")] if label == "earlier" else [("A_ID", "1"), ("A_ID", "2")]
    results = tool.search_all(questions, collections, places_of, searcher)
    assert [(r["id"], r["ranks"]["vectors alone"]) for r in results] == [
        ("Q1p", {"earlier": 3, "wording": 1}), ("Q1n", {"earlier": 2, "wording": 2})]
    assert results[0]["ranks"]["words alone"] == {"earlier": 1, "wording": 1}
    assert results[0]["ranks"]["the product's search"] == {"earlier": 3, "wording": 1}
    assert results[1]["ranks"]["the product's search"] == {"earlier": 2, "wording": 2}
    assert told == [("earlier", None), ("wording", None), ("earlier", ["An Act"]), ("wording", ["An Act"])]
    report = tool.text_report(results, {"passages": 3, "acts": 2, "expected_acts": 1, "distractors": 1, "seed": 5,
                                        "named Acts the search did not match to a held Act": []})
    assert "3 passages of 2 Acts" in report and "Q1p" in report and "Named Acts the search did not match to a held Act: none" in report


def store_with_acts(tmp_path, titles):
    path = tmp_path / "acts.db"
    con = sqlite3.connect(path)
    con.execute("create table acts (act_id text primary key, record text)")
    con.executemany("insert into acts values (?,?)", [(act_id, json.dumps({"title": title})) for act_id, title in titles])
    con.commit()
    con.close()
    return path


def test_an_act_the_questions_name_is_found_by_its_exact_title_once_or_the_comparison_stops_and_says_which(tmp_path):
    store = store_with_acts(tmp_path, [("A1", "The Imagined Relief Act, 1907"), ("A2", "The  Invented   Penal Code, 1860"),
                                       ("A3", "The Twin Act, 1950"), ("A4", "The Twin Act, 1950")])
    wanted = [question("Q1p", "plain", [("the imagined relief act, 1907", "1"), ("The Invented Penal Code, 1860", "2")])]
    assert tool.resolve_acts(store, wanted) == {"the imagined relief act, 1907": "A1", "The Invented Penal Code, 1860": "A2"}
    with pytest.raises(SystemExit) as stopped:
        tool.resolve_acts(store, [question("Q2p", "plain", [("The Twin Act, 1950", "1"), ("The Missing Act, 1900", "2")])])
    assert "'The Twin Act, 1950': held 2 times" in str(stopped.value) and "'The Missing Act, 1900': not held" in str(stopped.value)


def test_the_other_acts_looked_through_are_chosen_the_same_for_a_seed_and_never_those_the_questions_name(tmp_path):
    store = store_with_acts(tmp_path, [(f"ACT{n:02d}", f"Act {n}") for n in range(30)])
    one = tool.distractor_acts(store, {"ACT03", "ACT04"}, 8, seed=5)
    assert one == tool.distractor_acts(store, {"ACT03", "ACT04"}, 8, seed=5) and len(one) == 8
    assert not {"ACT03", "ACT04"} & set(one) and one != tool.distractor_acts(store, {"ACT03", "ACT04"}, 8, seed=6)
    assert len(tool.distractor_acts(store, set(), 99, seed=1)) == 30, "no more than there are"


def rows_of_passages():
    rows = []
    for pos, (act, section, text) in enumerate([
            ("A1", "1", "Act A,  — s.1: Short title\n1. Short title.\nThis Act may be called A."),
            ("A1", "2", "Act A,  — s.2: Relief\n2. Relief.\nThe court may grant relief."),
            ("B1", "5", "Act B,  — s.5: Costs\n5. Costs.\nCosts follow the event."),
            ("B1", "5", "Act B,  — s.5(a): Costs\n(a) where the party is a minor.")]):
        rows.append((pos * 10, f"{act}_S{section}_{pos}", act, None if pos < 3 else f"{act}_S{section}_2", "section_head" if pos < 3 else "clause",
                     section, json.dumps({"chunk_id": f"{act}_S{section}_{pos}", "act_id": act, "full_text": text})))
    return rows


def test_a_sample_library_is_the_same_passages_in_the_same_positions_under_each_labels_vectors(tmp_path):
    import faiss

    rows = rows_of_passages()
    vectors = {"earlier": _encode([json.loads(r[6])["full_text"] for r in rows]),
               "wording": _encode([tool.wording(json.loads(r[6])["full_text"]) for r in rows])}
    verified = {label: tool.verify(matrix, [json.loads(r[6])["full_text"] for r in rows], _encode, count=3) for label, matrix in
                {"earlier": vectors["earlier"]}.items()}
    verified["wording"] = tool.verify(vectors["wording"], [tool.wording(json.loads(r[6])["full_text"]) for r in rows], _encode, count=3)
    assert all(v["sampled"] == v["same_vector"] == 3 and v["mean_similarity"] >= 0.99 for v in verified.values())
    folder = tmp_path / "out" / "sample"
    records = tool.write_sample(folder, rows, vectors, verified)
    assert set(records) == {"earlier", "wording"}
    con = sqlite3.connect(folder / "sample.db")
    stored = con.execute("select pos, chunk_id, act_id, parent_chunk_id, atom_type, section_number from chunks order by pos").fetchall()
    assert [s[0] for s in stored] == [0, 1, 2, 3], "the sample's positions are its own, in the store's order"
    assert [s[1] for s in stored] == [r[1] for r in rows] and stored[3][3] == rows[3][3] and stored[3][4] == "clause"
    for label, path in records.items():
        record = json.loads(path.read_text(encoding="utf-8"))
        assert hybrid.check_lineage(record, folder.parent, doc_type="bare_act") == [], label
        assert record["verified"] == verified[label]
        index = faiss.read_index(str(folder / f"{label}.index"))
        for pos in range(4):
            assert float(index.reconstruct(pos) @ vectors[label][pos]) > 0.999
    assert not np.allclose(vectors["earlier"], vectors["wording"]), "the two labels differ in their vectors"
    with pytest.raises(SystemExit, match="exists"):
        tool.write_sample(folder, rows, vectors, verified)
    with pytest.raises(ValueError, match="3 vectors for 4 passages"):
        tool.write_sample(tmp_path / "other", rows, {"earlier": vectors["earlier"][:3]}, verified)


def test_a_vector_made_again_that_is_not_the_one_held_is_not_verified():
    texts = [f"passage {n} says something else" for n in range(10)]
    held = _encode(texts)
    assert tool.verify(held, texts, _encode, count=5)["same_vector"] == 5
    other = tool.verify(_encode([t + " altered" for t in texts]), texts, _encode, count=5)
    assert other["same_vector"] == 0 and other["mean_similarity"] < 0.5
