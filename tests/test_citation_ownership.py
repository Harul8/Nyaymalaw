"""Collision visibility and owned readback; legacy coverage is never invented."""
import sqlite3

import pytest

from nm.core_engine.citations import TextUnavailable, check_citations
from tests.test_citation_check import _build, _only

pytestmark = pytest.mark.class_a


def make_pairs(index, *, marked=True):
    with sqlite3.connect(index.database) as db:
        db.executescript("""
            alter table citations rename to old_citations;
            create table citations (citation_key text, case_id text,
                                    primary key(citation_key,case_id));
            insert into citations select * from old_citations;
            drop table old_citations;
        """)
        if marked:
            db.execute("insert into identity values ('citation_ownership','all_pairs_v2')")


def test_every_owner_of_one_exact_key_is_preserved(tmp_path):
    index = _build(tmp_path)
    make_pairs(index)
    with sqlite3.connect(index.database) as db:
        db.execute("insert into citations values ('19734SCC225','SYN_1980_BETA')")
    result = check_citations("(1973) 4 SCC 225", index)
    row = _only(result)
    assert row["lookup"] == "ambiguous" and row["status"] == "check"
    assert {j["case_id"] for j in row["judgments"]} == {"SYN_1973_ALPHA", "SYN_1980_BETA"}
    assert all(j["matched_keys"] == ["19734SCC225"] for j in row["judgments"])
    assert result["index"]["scope"]["collision_coverage"] == "all_indexed_owners"


@pytest.mark.parametrize("shape", ["legacy", "unmarked_pairs", "false_marked_legacy"])
def test_legacy_or_unestablished_coverage_stays_explicit_without_losing_found_text(tmp_path, shape):
    index = _build(tmp_path)
    if shape == "unmarked_pairs": make_pairs(index, marked=False)
    if shape == "false_marked_legacy":
        with sqlite3.connect(index.database) as db:
            db.execute("insert into identity values ('citation_ownership','all_pairs_v2')")
    result = check_citations("(1973) 4 SCC 225", index)
    assert _only(result)["lookup"] == "found"
    assert result["index"]["scope"]["collision_coverage"] == "unassessed"
    assert "does not establish" in result["index"]["statement"]


def test_dangling_owner_is_unavailable_not_not_held_and_peer_survives(tmp_path):
    index = _build(tmp_path)
    with sqlite3.connect(index.database) as db:
        db.execute("insert into citations values ('19992SCC123','MISSING_CASE')")
    result = check_citations("(1999) 2 SCC 123; (1973) 4 SCC 225", index)
    assert [r["status"] for r in result["citations"]] == ["could_not_check", "found"]


def test_source_text_cannot_escape_held_corpus(tmp_path):
    index = _build(tmp_path)
    (tmp_path / "outside.txt").write_text("Outside held corpus", encoding="utf8")
    with pytest.raises(TextUnavailable, match="outside"):
        index.text({"source_file": "../outside.txt"})
    row = next(iter(index.judgments_for(("19734SCC225",)).values()))
    assert "Header" in index.text(row)


def test_missing_lookup_table_cannot_be_reported_as_no_matches(tmp_path):
    index = _build(tmp_path)
    with sqlite3.connect(index.database) as db:
        db.execute("drop table citations")
    assert _only(check_citations("(1973) 4 SCC 225", index))["status"] == "could_not_check"
