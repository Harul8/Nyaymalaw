"""A PROVISION IS READ WHOLE: every atom its store holds, in order, once.

THE MEASURED DEFECT, 26 September 2026. The provision reader took ONE atom
per section per store -- the section head where there was one, else the first
-- and the document reader kept the LONGEST atom. Where a store keeps the head
as a heading only, or has no head, one atom is part of the section: Limitation
Act s.18 came back as sub-section (1) alone, without (2) or the Explanation
the acknowledgment cases turn on, and it was marked resolved and supporting.
Of the 3,402 provisions the manifest intends, 760 came back part-read. After
the fix, 3,395 return every atom their store holds; 7 return nothing, as before.

THE RULES, each asserted below:

* the text is the union of the section's atoms, in the store's order;
* nothing is said twice, and a head that already holds the whole section reads
  exactly as it did;
* every word is the corpus's own -- nothing paraphrased or supplied;
* ONE function assembles a section, and every reader of provision atoms in the
  product calls it (a third reader taking one atom is refused by the scan);
* on the real corpus, every provision the manifest intends is read whole.
"""
from __future__ import annotations

import ast
import json
import re
import sqlite3
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
from nm.adapters.evidence.corpus import CorpusEvidenceAdapter, assemble_section

ROOT = Path(__file__).resolve().parents[1]
LABEL = "The Limitation Act, 1963 . s.18{part}: Effect of acknowledgment in writing."


def _atom(atom_type: str, part: str, words: str) -> tuple[str, str]:
    return atom_type, f"{LABEL.format(part=part)}\n{words}"


SPLIT = [  # a store with no head: s.18 as its sub-sections, explanation and clauses
    _atom("sub_section", "(1)", "(1)\nWhere, before the expiration of the prescribed period ..."),
    _atom("sub_section", "(2)", "(2)\nWhere the writing containing the acknowledgment is undated ..."),
    _atom("explanation", "(2) [explanation]", "Explanation.\nFor the purposes of this section,"),
    _atom("clause", "(2)(a)", "(a)\nan acknowledgment may be sufficient though it omits ..."),
]


def _words(text: str) -> str:
    return " ".join(text.split()).lower()


@pytest.mark.class_a
def test_every_atom_of_a_split_section_is_in_the_text_in_order():
    text = _words(assemble_section(SPLIT))
    bodies = [_words(t.partition("\n")[2]) for _, t in SPLIT]
    positions = [text.find(b) for b in bodies]
    assert -1 not in positions, f"an atom's words are missing: {positions}"
    assert positions == sorted(positions), "the atoms are not in the store's order"


@pytest.mark.class_a
def test_a_head_that_holds_the_whole_section_reads_exactly_as_it_did():
    head = ("section_head", "Union Of India 1963 1 The Specific Relief Act, 1963 . s.6: Suit.\n"
                            "6.\nSuit.\n(1)\nIf any person is dispossessed ...\n(2)\nNo suit ...")
    parts = [head, ("sub_section", "... s.6(1): Suit.\n(1)\nIf any person is dispossessed ..."),
             ("sub_section", "... s.6(2): Suit.\n(2)\nNo suit ...")]
    assert assemble_section(parts) == " ".join(head[1].split())


@pytest.mark.class_a
def test_nothing_is_said_twice_and_later_labels_are_dropped():
    text = assemble_section(SPLIT + [SPLIT[1]])
    assert _words(text).count("the writing containing the acknowledgment is undated") == 1
    assert text.count("Effect of acknowledgment in writing.") == 1, (
        "the first atom keeps its label; every later label is dropped")


@pytest.mark.class_a
def test_every_word_is_the_corpus_own():
    """Nothing supplied: the text is made of the atoms' own words, in order."""
    text = _words(assemble_section(SPLIT))
    source = " ".join(_words(t) for _, t in SPLIT)
    assert all(word in source.split() for word in text.split())


@pytest.mark.class_a
def test_every_reader_of_provision_atoms_assembles_through_the_one_function():
    """Drawn from every module under backend/nm. A function that queries the
    bare-Act atoms and does not assemble through `assemble_section` is a reader
    that can take one atom -- the defect this file exists for."""
    readers = []
    for path in (ROOT / "backend" / "nm").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            source = ast.get_source_segment(path.read_text(encoding="utf-8"), fn) or ""
            if re.search(r"doc_type\s*=\s*'bare_act'", source) and "select" in source.lower():
                if "blob" in source and "assemble_section(" not in source:
                    readers.append(f"{path.relative_to(ROOT).as_posix()}::{fn.name}")
    assert readers == [], f"these read provision text without assembling it: {readers}"


# ======================================================== on the corpus ====
CORPUS = ROOT / "legal_database" / "vector_store"


@pytest.fixture(scope="module")
def corpus():
    if not (CORPUS / "chunks.db").exists():
        pytest.skip("the corpus is not attached")
    return sqlite3.connect(f"file:{CORPUS / 'chunks.db'}?mode=ro", uri=True)


@pytest.mark.class_c
def test_every_intended_provision_is_read_whole_from_its_store(corpus):
    """The population is the manifest's whole intended coverage, not a sample."""
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from nm.knowledge.manifest import Manifest
    manifest = Manifest.load(ROOT / "pipeline" / "manifest.yaml")
    ids = [r[0] for r in corpus.execute("select distinct act_id from chunks where doc_type='bare_act'")]
    cache: dict[str, dict] = {}

    def rows(act_id):
        if act_id not in cache:
            by: dict[str, list] = {}
            for pos, section, atom, blob in corpus.execute(
                    "select pos, section_number, atom_type, blob from chunks "
                    "where doc_type='bare_act' and act_id=? order by pos", (act_id,)):
                by.setdefault(section, []).append((atom, json.loads(blob).get("full_text") or ""))
            cache[act_id] = by
        return cache[act_id]

    def last_line(text):
        lines = [line for line in text.splitlines() if line.strip()]
        return _words(lines[-1]) if lines else ""

    part_read = []
    for entry in manifest.entries:
        stores = [a for a in ids for p in entry.act_patterns
                  if fnmatchcase(a.lower(), p.lower().replace("%", "*").replace("_", "?"))]
        for section in entry.intended_sections:
            read = [(assemble_section(rows(s).get(section, [])), s) for s in stores if rows(s).get(section)]
            read = [r for r in read if r[0]]
            if not read:
                continue
            text, store = max(read, key=lambda r: len(r[0]))
            missing = [t for a, t in rows(store)[section] if a != "section_head"
                       and len(last_line(t)) >= 12 and last_line(t) not in _words(text)]
            if missing:
                part_read.append((entry.act_name, section, len(missing)))
    assert part_read == [], f"{len(part_read)} provisions are read in part: {part_read[:10]}"


@pytest.mark.class_c
@pytest.mark.parametrize("question,section,must_hold", [
    ("Limitation Act, 1963 section 18", "18", ("(2)", "Explanation", "(c)")),
    ("Negotiable Instruments Act, 1881 section 138", "138", ("Provided that", "(c)", "Explanation")),
    ("Specific Relief Act, 1963 section 6", "6", ("(2)", "against the Government", "(4)")),
])
def test_the_measured_sections_reach_the_turn_whole(corpus, question, section, must_hold):
    """Through the served adapter, not the helper alone."""
    from nm.knowledge.manifest import Manifest
    from nm.ports.evidence import EvidenceNeed
    adapter = CorpusEvidenceAdapter(CORPUS, Manifest.load(ROOT / "pipeline" / "manifest.yaml"))
    result = adapter.fetch(EvidenceNeed(question=question, governing_date=date(2025, 9, 1),
                                        provision_hint=section))
    assert result.findings, result.missing
    span = result.findings[0].span
    assert all(piece in span for piece in must_hold), (
        f"{question}: the text reaching the turn lacks {[p for p in must_hold if p not in span]}")
