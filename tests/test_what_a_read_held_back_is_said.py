"""WHAT A READ HELD BACK IS SAID.

THE MEASURED DEFECTS, 27 September 2026.

1. Four readers applied the corpus's contamination denylist with a bare
   `continue`: the provision lookup, the Act reader, the judgment reader and
   the authority search. A provision or judgment with a passage held back read
   exactly like one that never had it -- and a section whose every atom was
   held back was reported NOT HELD or as a retrieval defect, both untrue.

2. `/api/health` said "44 chunk(s) excluded". All 44 ids name a store
   `chunks.db` does not hold, so none was excluded. (The contamination they
   were written for -- fragments of the CrPC s.320 table stored as CrPC
   ss.485-508 -- is present under the store's own ids and is a corpus
   decision, recorded separately.)

THE RULES, each asserted below:

* the denylist is consulted in exactly one place, `_screen`, which returns
  what it held back -- the population is every reference in backend/nm;
* no caller discards that count;
* a provision, an Act document and a judgment document each say what they
  held back, and a provision held back entirely is NOT_HELD with the reason.
"""
from __future__ import annotations

import ast
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
from nm.knowledge.manifest import Manifest, ManifestEntry
from nm.ports.evidence import Coverage

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend" / "nm" / "adapters" / "evidence" / "corpus.py"


def _corpus(tmp_path: Path, denied: list[str]) -> CorpusEvidenceAdapter:
    with sqlite3.connect(tmp_path / "chunks.db") as con:
        con.execute("create table chunks(act_id text, atom_type text, chunk_id text, "
                    "blob text, doc_type text, section_number text, pos integer)")
        for pos, (section, chunk, words) in enumerate([
                ("5", "a_5_1", "(1) the first sub-section"),
                ("5", "a_5_2", "(2) a fragment of another table"),
                ("6", "a_6_1", "(1) nothing but a fragment")]):
            con.execute("insert into chunks values ('act_a', 'sub_section', ?, ?, 'bare_act', ?, ?)",
                        (chunk, json.dumps({"full_text": f"Act A . s.{section}: head\n{words}"}),
                         section, pos))
    (tmp_path / "contamination_denylist.json").write_text(json.dumps({"chunk_ids": denied}))
    manifest = Manifest(entries=(ManifestEntry("Act A, 2000", ("act_a",), ("5", "6"),
                                               in_force_from=date(2000, 1, 1)),))
    return CorpusEvidenceAdapter(tmp_path, manifest)


def test_a_provision_says_what_it_held_back(tmp_path):
    read = _corpus(tmp_path, ["a_5_2"]).read_provision("Act A, 2000", "5", date(2025, 1, 1))
    (finding,) = read.findings
    assert "first sub-section" in finding.span and "another table" not in finding.span
    assert read.search_note and "1 passage(s) were held back" in read.search_note


def test_a_provision_held_back_entirely_is_not_held_and_says_why(tmp_path):
    read = _corpus(tmp_path, ["a_6_1"]).read_provision("Act A, 2000", "6", date(2025, 1, 1))
    assert read.coverage is Coverage.NOT_HELD and read.findings == ()
    assert "denylist" in read.missing and read.search_note


def test_nothing_held_back_says_nothing(tmp_path):
    read = _corpus(tmp_path, []).read_provision("Act A, 2000", "5", date(2025, 1, 1))
    assert read.search_note is None


def test_an_act_document_counts_what_it_held_back(tmp_path):
    adapter = _corpus(tmp_path, ["a_5_2"])
    locator = adapter.read_provision("Act A, 2000", "6", date(2025, 1, 1)).findings[0].locator
    document = adapter.document(locator, "provision")
    assert document.state == "read" and document.excluded == 1


def test_a_judgment_document_counts_what_it_held_back(tmp_path):
    index = tmp_path / "authority.db"
    with sqlite3.connect(index) as con:
        con.execute("create table paras(case_id, case_name, court, year, para_type, chunk_id, text)")
        for chunk in ("p1", "p2", "p3"):
            con.execute("insert into paras values ('c1', 'A v B', 'Supreme Court of India', "
                        "'2020', 'ratio', ?, ?)", (chunk, f"paragraph {chunk}"))
    adapter = _corpus(tmp_path, ["p2"])
    adapter._authority_db = index
    document = adapter.document("c1::p1::ratio", "authority")
    assert document.state == "read" and len(document.segments) == 2 and document.excluded == 1
    assert document.label.startswith("A v B")


# ============================================ one owner, product-wide ====

def _functions_reaching(name: str) -> set[str]:
    reaching = set()
    for path in (ROOT / "backend" / "nm").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(isinstance(n, ast.Attribute) and n.attr == name for n in ast.walk(fn)):
                    reaching.add(f"{path.relative_to(ROOT).as_posix()}::{fn.name}")
    return reaching


def test_the_denylist_is_consulted_only_by_the_screen():
    """`readiness` reports how many ids are listed; nothing else may read it."""
    rel = ADAPTER.relative_to(ROOT).as_posix()
    assert _functions_reaching("_denylist") == {f"{rel}::_screen", f"{rel}::readiness"}


def test_no_caller_discards_what_the_screen_held_back():
    discarded, calls = [], 0
    for node in ast.walk(ast.parse(ADAPTER.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "_screen":
            calls += 1
            target = node.targets[0]
            names = [e.id for e in getattr(target, "elts", []) if isinstance(e, ast.Name)]
            if len(names) != 2 or names[1].startswith("_"):
                discarded.append(node.lineno)
    assert calls >= 4, f"the screen has {calls} callers; the scan is not seeing them"
    assert discarded == [], f"these reads drop what they held back: lines {discarded}"
