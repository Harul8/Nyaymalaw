"""Exact presence, complete fragment checking and unresolved attribution differ."""
import pytest

from nm.core_engine.citations import check_citations
from tests.test_citation_check import _build

pytestmark = pytest.mark.class_a


def check(tmp_path, quote, source, citations="(1973) 4 SCC 225"):
    index = _build(tmp_path)
    (index.judgments / "Synthetic/SYN_1973_ALPHA.txt").write_text(source, encoding="utf8")
    return check_citations(f'{citations}: "{quote}"', index)["citations"]


@pytest.mark.parametrize("quote,source,result", [
    ("refused", "The request was refused.", "found"),
    ("The request has been ... not ... permitted in these circumstances",
     "The request has been permitted in these circumstances", "not_found"),
    ("first relevant clause ... not ... last relevant clause",
     "first relevant clause notice last relevant clause", "not_found"),
    ("The [original] request", "The [original] request was refused.", "found"),
    ("The [accepted] request", "The request was refused.", "not_assessed"),
    ("The request … was refused", "The request for the order was refused", "found"),
    ("‘The request’ was refused", "'The request'\nwas refused", "found"),
])
def test_no_substantive_fragment_is_silently_discarded(tmp_path, quote, source, result):
    (row,) = check(tmp_path, quote, source)
    assert row["quotes"][0]["result"] == result
    assert row["quotes"][0]["quote"] == quote
    assert row["quotes"][0]["attribution"] == "single_candidate"
    assert row["status"] == ("check" if result == "not_found" else "found")


@pytest.mark.parametrize("other", ["(2006) 3 SCC 1", "1999 (3) ALT 10", "(2000) 1 SCC 999",
                                  "AIR 1980 SC 100"])
def test_other_possible_source_never_disappears_or_gains_quote_ownership(tmp_path, other):
    rows = check(tmp_path, "Special exact words", "Special exact words",
                 f"(1973) 4 SCC 225; {other}")
    assert rows[0]["quotes"][0]["result"] == "found"
    assert all(row["quotes"][0]["attribution"] == "unresolved" for row in rows)
    assert rows[1]["quotes"][0]["result"] in {"not_found", "not_assessed"}
    assert rows[1]["lookup"] != "found" or rows[1]["status"] == "found"


def test_parallel_keys_to_same_case_preserve_single_candidate_check(tmp_path):
    rows = check(tmp_path, "missing words", "different words",
                 "(1973) 4 SCC 225 : AIR 1973 SC 1461")
    assert all(row["quotes"][0]["attribution"] == "single_candidate" for row in rows)
    assert all(row["status"] == "check" for row in rows)


def test_presence_in_both_cases_does_not_decide_intended_source(tmp_path):
    index = _build(tmp_path)
    for case_id in ("SYN_1973_ALPHA", "SYN_2006_ACRONYM"):
        (index.judgments / "Synthetic" / f"{case_id}.txt").write_text("Shared words", encoding="utf8")
    result = check_citations('(1973) 4 SCC 225; (2006) 3 SCC 1: "Shared words"', index)
    assert all(r["quotes"][0]["result"] == "found" for r in result["citations"])
    assert all(r["quotes"][0]["attribution"] == "unresolved" for r in result["citations"])
