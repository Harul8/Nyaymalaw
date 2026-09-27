"""AN ACT THE ADVOCATE NAMES IS READ -- OR SAID TO BE OUT OF FORCE -- AND
NEVER REPLACED BY ONE THE PRODUCT INFERRED.

THE MEASURED DEFECTS, 26 September 2026, reviewing the capabilities the tool
layer will wrap.

1. `Manifest.resolve` skipped a NAMED Act that was not in force on the date and
   fell through to keyword scoring. Asked "can he get bail under section 437 of
   the Code of Criminal Procedure?" on a 2025 date, it read BNSS s.437 -- a
   different provision of a different code -- and told the advocate "You did
   not name an Act". Asked about cheating under section 420 of the Indian Penal
   Code, it read s.420 of the BNSS, the procedure code, not the penal one.

2. There was no way to read a provision of an Act already known. `fetch` takes
   a QUESTION and decides the Act from its words, so a caller that knew the
   Act had to write a sentence and hope it resolved back.

THE RULES, each asserted below with its population drawn from the manifest:

* a title or abbreviation in the question is never outvoted by keywords --
  whatever else the question says, the result is that Act or, where it was not
  in force on the date, NOT_RESOLVED naming it;
* `identify` never guesses and `infer` never identifies;
* `read_provision` reads the Act named, exactly -- an out-of-force Act's text
  is returned blocked by G-INFORCE, never a successor's; a title without its
  year is never resolved to one Act by date;
* every read on the corpus adapter says NOT_ASSESSED when the corpus cannot be
  read -- never a state claiming a search ran.
"""
from __future__ import annotations

import ast
import json
import sqlite3
import typing
from datetime import date, timedelta
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
from nm.knowledge.manifest import (
    ActBasis,
    Manifest,
    ManifestEntry,
    title_without_year,
)
from nm.ports.evidence import Coverage, EvidenceNeed, EvidenceResult

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Manifest.load(ROOT / "pipeline" / "manifest.yaml")
OUT_OF_FORCE = [e for e in MANIFEST.entries if e.in_force_to is not None]


def _after(entry: ManifestEntry) -> date:
    return entry.in_force_to + timedelta(days=1)


def _every_keyword_in_force_on(day: date) -> str:
    """The strongest keyword pull the manifest can put against a name."""
    return " ".join(k for e in MANIFEST.entries if e.in_force_on(day) for k in e.keywords)


def _named_forms(entry: ManifestEntry) -> list[str]:
    """How a question names this Act: its title, and each abbreviation in the
    one slot the manifest reads abbreviations in -- after a provision."""
    forms = [f"under section 1 of the {title_without_year(entry.act_name)}"]
    forms += [f"under section 1 {alias}" for alias in entry.aliases]
    return forms


# ============================================== the resolver: G5 =====

@pytest.mark.class_a
def test_the_population_is_live():
    """A POSITIVE CONTROL. Without out-of-force Acts, or with keywords too weak
    to outvote anything, the sweep below would pass while checking nothing."""
    assert len(OUT_OF_FORCE) >= 2, [e.act_name for e in OUT_OF_FORCE]
    outvoted = [e.act_name for e in OUT_OF_FORCE
                if MANIFEST.infer(f"{_named_forms(e)[0]} {_every_keyword_in_force_on(_after(e))}",
                                  _after(e)).entry is not None]
    assert outvoted, "no named Act faces a keyword candidate, so nothing is being refused"


@pytest.mark.class_a
@pytest.mark.parametrize("entry", OUT_OF_FORCE, ids=lambda e: e.act_name)
def test_a_named_act_is_never_outvoted_by_keywords(entry):
    day = _after(entry)
    for form in _named_forms(entry):
        question = f"{form}; {_every_keyword_in_force_on(day)}"
        result = MANIFEST.resolve(question, day)
        assert result.basis is not ActBasis.INFERRED, (
            f"{form!r} named an Act and was answered with an inference: "
            f"{result.entry and result.entry.act_name}")
        if result.entry is None:
            assert result.superseded is entry, (
                f"{form!r}: the Act named, out of force on {day}, was not reported")
        else:
            # A title shared by an Act IN FORCE on the date names that Act.
            assert title_without_year(result.entry.act_name) == title_without_year(entry.act_name) \
                or form != _named_forms(entry)[0], result.entry.act_name


@pytest.mark.class_a
def test_the_measured_question():
    day = date(2025, 1, 1)
    question = ("he was arrested today and produced before the magistrate; can he get "
                "bail under section 437 of the Code of Criminal Procedure?")
    assert MANIFEST.infer(question, day).entry is not None, "the keyword pull that won is gone"
    result = MANIFEST.resolve(question, day)
    assert result.entry is None and result.superseded.act_name.startswith("Code of Criminal")


@pytest.mark.class_a
@pytest.mark.parametrize("entry", MANIFEST.entries, ids=lambda e: e.act_name)
def test_identify_never_guesses_and_infer_never_identifies(entry):
    day = entry.in_force_from or date(2025, 1, 1)
    for question in [*_named_forms(entry), " ".join(entry.keywords)]:
        assert MANIFEST.identify(question, day).basis is not ActBasis.INFERRED
        assert MANIFEST.infer(question, day).basis is not ActBasis.NAMED


# ======================================== the exact reader: G4 =====

def _store(tmp_path: Path) -> tuple[Path, Manifest]:
    """Two codes with the same section number and different words, the
    earlier one repealed the day before the later one began, and a third
    pair sharing a title across their years."""
    db = tmp_path / "chunks.db"
    with sqlite3.connect(db) as con:
        con.execute("create table chunks(act_id text, atom_type text, chunk_id text, "
                    "blob text, doc_type text, section_number text, pos integer)")
        for pos, (act_id, words) in enumerate([
                ("old_code_1973", "OLD CODE WORDS for section ten"),
                ("new_sanhita_2023", "NEW SANHITA WORDS for section ten"),
                ("relief_act_1986", "RELIEF 1986 WORDS"),
                ("relief_act_2019", "RELIEF 2019 WORDS")]):
            con.execute("insert into chunks values (?, 'section_head', ?, ?, 'bare_act', '10', ?)",
                        (act_id, f"c{pos}", json.dumps({"full_text": f"{act_id} . s.10: head\n{words}"}), pos))
    manifest = Manifest(entries=(
        ManifestEntry("Old Code, 1973", ("old_code_1973",), ("10",),
                      in_force_from=date(1974, 4, 1), in_force_to=date(2024, 6, 30)),
        ManifestEntry("New Sanhita, 2023", ("new_sanhita_2023",), ("10",),
                      in_force_from=date(2024, 7, 1)),
        ManifestEntry("Relief Act, 1986", ("relief_act_1986",), ("10",),
                      in_force_from=date(1987, 1, 1), in_force_to=date(2020, 7, 19)),
        ManifestEntry("Relief Act, 2019", ("relief_act_2019",), ("10",),
                      in_force_from=date(2020, 7, 20)),
    ))
    return tmp_path, manifest


@pytest.mark.class_a
def test_an_out_of_force_act_is_read_as_itself_and_blocked(tmp_path):
    adapter = CorpusEvidenceAdapter(*_store(tmp_path))
    read = adapter.read_provision("Old Code, 1973", "10", date(2025, 1, 1))
    assert read.coverage is Coverage.ANSWERED
    (finding,) = read.findings
    assert "OLD CODE WORDS" in finding.span and "NEW SANHITA" not in finding.span
    assert not finding.usable and finding.blocking_reason.startswith("G-INFORCE")


@pytest.mark.class_a
def test_the_same_act_in_force_is_read_usable(tmp_path):
    adapter = CorpusEvidenceAdapter(*_store(tmp_path))
    (finding,) = adapter.read_provision("Old Code, 1973", "10", date(2020, 1, 1)).findings
    assert finding.usable and "OLD CODE WORDS" in finding.span


@pytest.mark.class_a
def test_a_title_without_its_year_is_never_resolved_by_date(tmp_path):
    adapter = CorpusEvidenceAdapter(*_store(tmp_path))
    read = adapter.read_provision("Relief Act", "10", date(2025, 1, 1))
    assert read.coverage is Coverage.NOT_HELD and read.findings == ()
    assert "Relief Act, 1986" in read.missing and "Relief Act, 2019" in read.missing


@pytest.mark.class_a
def test_an_unknown_act_is_named_as_unknown(tmp_path):
    read = CorpusEvidenceAdapter(*_store(tmp_path)).read_provision("Other Act, 1999", "10", date(2025, 1, 1))
    assert read.coverage is Coverage.NOT_HELD and "Other Act, 1999" in read.missing


_ARGUMENTS = {
    "need": EvidenceNeed(question="section 10 of the Old Code", governing_date=date(2025, 1, 1)),
    "act": "Old Code, 1973",
    "section": "10",
    "as_of": date(2025, 1, 1),
}


@pytest.mark.class_a
def test_every_read_says_not_assessed_when_the_corpus_cannot_be_read(tmp_path):
    """THE POPULATION IS EVERY PUBLIC METHOD returning `EvidenceResult`, read
    from the adapter's own annotations -- so a read added tomorrow is held to
    it, and one whose arguments this test cannot supply fails rather than
    being skipped."""
    _, manifest = _store(tmp_path)
    adapter = CorpusEvidenceAdapter(tmp_path / "never-attached", manifest)
    reads = [name for name, member in vars(CorpusEvidenceAdapter).items()
             if not name.startswith("_") and callable(member)
             and typing.get_type_hints(member).get("return") is EvidenceResult]
    assert {"fetch", "read_provision"} <= set(reads), reads
    for name in reads:
        params = [p for p in typing.get_type_hints(getattr(CorpusEvidenceAdapter, name)) if p != "return"]
        assert set(params) <= set(_ARGUMENTS), f"{name} takes {params}; supply them here"
        result = getattr(adapter, name)(**{p: _ARGUMENTS[p] for p in params})
        assert result.coverage is Coverage.NOT_ASSESSED, (name, result.coverage)
        assert "not readable" in result.missing


@pytest.mark.class_a
def test_an_unbuilt_authority_index_is_not_assessed(tmp_path):
    """The case-law read that never ran, by the same rule as the provision read."""
    adapter = _corpus_with_no_authority_index(tmp_path)
    result = adapter.fetch(EvidenceNeed(question="adverse possession against the true owner",
                                        governing_date=date(2025, 1, 1), want_authority=True))
    assert result.coverage is Coverage.NOT_ASSESSED, result.coverage
    assert "not built" in result.missing


def _corpus_with_no_authority_index(tmp_path: Path) -> CorpusEvidenceAdapter:
    path, manifest = _store(tmp_path)
    return CorpusEvidenceAdapter(path, manifest, authority_index=tmp_path / "never-built.db")


def _held_not_found_sites(tree: ast.AST) -> list[tuple[int, bool]]:
    """Every `Coverage.HELD_NOT_FOUND` a result is built with, and whether the
    `if` it sits under asks the manifest (`.intends(`)."""
    sites = []

    def visit(node, guards):
        if isinstance(node, ast.If):
            asks = "intends" in {n.attr for n in ast.walk(node.test) if isinstance(n, ast.Attribute)}
            for child in node.body:
                visit(child, guards + [asks])
            for child in node.orelse:
                visit(child, guards + [False])
            return
        if isinstance(node, ast.keyword) and node.arg == "coverage" \
                and isinstance(node.value, ast.Attribute) and node.value.attr == "HELD_NOT_FOUND":
            sites.append((node.value.lineno, any(guards)))
        for child in ast.iter_child_nodes(node):
            visit(child, guards)

    visit(tree, [])
    return sites


@pytest.mark.class_a
def test_held_not_found_is_only_ever_said_on_the_manifests_word():
    """G-HELDNOTFOUND's condition, as a rule over the product: 'the manifest
    declares the provision as intended coverage and retrieval did not return
    it'. A result built HELD_NOT_FOUND anywhere else claims a search ran and
    failed without the one fact that makes that claim. The population is
    every module in backend/nm."""
    offenders, seen = [], 0
    for path in (ROOT / "backend" / "nm").rglob("*.py"):
        for line, guarded in _held_not_found_sites(ast.parse(path.read_text(encoding="utf-8"))):
            seen += 1
            if not guarded:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert seen >= 1, "the scan found no HELD_NOT_FOUND at all, so it is checking nothing"
    assert offenders == [], f"HELD_NOT_FOUND said without the manifest: {offenders}"


@pytest.mark.class_a
def test_the_held_not_found_scan_rejects_the_branch_it_replaced():
    replaced = ("def _fetch_authority(self, need):\n"
                "    if not self.authority_available:\n"
                "        return EvidenceResult(coverage=Coverage.HELD_NOT_FOUND, missing='not built')\n")
    assert _held_not_found_sites(ast.parse(replaced)) == [(3, False)]


# ================================================= on the corpus =====
CORPUS = ROOT / "legal_database" / "vector_store"


@pytest.mark.class_c
@pytest.mark.parametrize("entry", OUT_OF_FORCE, ids=lambda e: e.act_name)
def test_every_out_of_force_act_reads_as_itself_on_the_corpus(entry):
    if not (CORPUS / "chunks.db").exists():
        pytest.skip("the corpus is not attached")
    adapter = CorpusEvidenceAdapter(CORPUS, MANIFEST)
    for section in entry.intended_sections[:25]:
        read = adapter.read_provision(entry.act_name, section, _after(entry))
        if not read.findings:
            continue
        (finding,) = read.findings
        assert any(fnmatchcase(finding.store.lower(), p.lower().replace("%", "*").replace("_", "?"))
                   for p in entry.act_patterns), f"{entry.act_name} s.{section} read from {finding.store}"
        assert finding.blocking_reason.startswith("G-INFORCE"), finding.blocking_reason
        return
    pytest.fail(f"no provision of {entry.act_name} was read, so nothing was checked")
