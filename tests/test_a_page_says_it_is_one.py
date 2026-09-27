"""A PAGE SAYS IT IS ONE, AND PAGES READ THE SOURCE IN ITS OWN ORDER.

THE MEASURED DEFECTS, 27 September 2026, on the built authority index.

1. `expand(case_id)` read at most 200 paragraphs (500 at the ceiling) and
   nothing said it had stopped. 49 held judgments run past 200, eight past
   500; Kesavananda Bharati's 1,124 came back as its first 200, indistinguishable
   from the whole judgment. `document()` could only return every segment at
   once, so a tool had the choice of all of a long judgment or none of it.

2. `expand` ordered paragraphs by `chunk_id`, a string, so `P1001` sorted
   before `P101`: 13 of those 49 judgments came back out of source order.

THE RULES, each asserted below:

* paging an expansion reads every paragraph once, in the order the index
  stored them, and the last page -- and only the last -- says it is the end;
* a cursor from another build of the index, or one it never issued, is
  refused by name, never read as the start;
* a window of a stored document says where it sits and how much it left out,
  and one past the end is refused rather than returned empty;
* no reader in the product orders a source's paragraphs by a string key.
"""
from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path

import pytest

from nm.legal_brain.evidence_port import SourceDocument
from nm.legal_brain.search_authority import AuthorityIndexSearch
from nm.legal_brain.search_port import CaseExpansion, Coverage

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
BUILT = "2026-08-30T07:51:38"
#: Paragraph numbers whose string order is not their order: P1001 < P101.
NUMBERS = [99, 100, 101, 999, 1000, 1001, 1002]


def _index(tmp_path: Path) -> Path:
    path = tmp_path / "authority.db"
    with sqlite3.connect(path) as con:
        con.execute("create virtual table paras using fts5(case_id, case_name, court, "
                    "year UNINDEXED, para_type UNINDEXED, chunk_id UNINDEXED, text)")
        con.execute("create table identity(key text, value text)")
        con.executemany("insert into identity values (?, ?)", [
            ("built_at", BUILT), ("source", "test"), ("corpus_version", "t"),
            ("indexed_paragraphs", str(len(NUMBERS))), ("attributable_kinds", "ratio")])
        for n in NUMBERS:  # stored in source order
            con.execute("insert into paras values ('c1', 'A v B', 'Supreme Court of India', "
                        "'1973', 'ratio', ?, ?)",
                        (f"c1_P{n}_C01", f"paragraph {n} of the judgment"))
    return path


def _read_all(search, **kw) -> tuple[list[str], int]:
    out, after, pages = [], None, 0
    while True:
        page = search.expand("c1", after=after, **kw)
        assert page.coverage is Coverage.ANSWERED, page.why
        out += [p.locator for p in page.paragraphs]
        pages += 1
        after = page.next_after
        if after is None:
            return out, pages
        assert pages < 50, "the cursor never reached the end"


def test_paging_reads_every_paragraph_once_in_stored_order(tmp_path):
    search = AuthorityIndexSearch(_index(tmp_path))
    read, pages = _read_all(search, limit=3)
    assert read == [f"c1_P{n}_C01" for n in NUMBERS], read
    assert pages == 3


def test_a_page_that_is_the_whole_case_says_so(tmp_path):
    page = AuthorityIndexSearch(_index(tmp_path)).expand("c1", limit=len(NUMBERS))
    assert len(page.paragraphs) == len(NUMBERS) and page.next_after is None


def test_a_page_that_stopped_early_says_so(tmp_path):
    page = AuthorityIndexSearch(_index(tmp_path)).expand("c1", limit=2)
    assert len(page.paragraphs) == 2 and page.next_after is not None


@pytest.mark.parametrize("cursor", ["garbage", "1999-01-01T00:00:00#1", f"{BUILT}#x"])
def test_a_cursor_this_build_did_not_issue_is_refused_by_name(tmp_path, cursor):
    page = AuthorityIndexSearch(_index(tmp_path)).expand("c1", after=cursor)
    assert page.coverage is Coverage.NOT_ASSESSED and page.paragraphs == ()
    assert page.why and cursor.partition("#")[0] in page.why


def test_an_expansion_that_did_not_run_cannot_offer_a_next_page():
    with pytest.raises(ValueError):
        CaseExpansion(case_id="c1", index="i", coverage=Coverage.NOT_ASSESSED,
                      why="not built", next_after=f"{BUILT}#3")


# ============================================ stored documents ====
WHOLE = SourceDocument(state="read", label="Act", store="s",
                       segments=tuple((f"Section {n}", f"text {n}") for n in range(10)), target=7)


def test_a_document_read_without_a_window_is_whole():
    assert WHOLE.whole and WHOLE.total == 10 and WHOLE.first == 0


def test_a_window_says_where_it_sits_and_what_it_left_out():
    window = WHOLE.window(3, 4)
    assert window.segments == WHOLE.segments[3:7]
    assert (window.first, window.total, window.target) == (3, 10, 7)
    assert not window.whole


@pytest.mark.parametrize("start,count", [(-1, None), (0, 0), (10, None), (99, 2)])
def test_a_window_outside_the_document_is_refused_not_empty(start, count):
    with pytest.raises(ValueError):
        WHOLE.window(start, count)


def test_a_window_cannot_claim_more_than_the_document():
    with pytest.raises(ValueError):
        SourceDocument(state="read", segments=(("a", "b"),), first=3, total=2)


# ====================================== the order, product-wide ====

def test_no_reader_orders_a_source_by_a_string_key():
    """THE POPULATION IS EVERY SQL STRING IN nm. Paragraphs and
    provisions have a stored order (`rowid`, `pos`); a locator, chunk id or
    section number sorts as text, and text puts 1001 before 101."""
    string_keys = re.compile(r"order\s+by\s+[^;\"']*\b(chunk_id|locator|section_number)\b", re.I)
    offenders = []
    for path in (ROOT / "nm").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and string_keys.search(node.value):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert offenders == [], f"a source is ordered by a string key: {offenders}"


def test_the_order_scan_rejects_the_line_it_replaced():
    replaced = '"from paras where case_id = ? order by chunk_id limit ?"'
    assert re.search(r"order\s+by\s+[^;\"']*\b(chunk_id|locator|section_number)\b",
                     ast.literal_eval(replaced), re.I)
