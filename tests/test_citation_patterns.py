"""One copy of "how an advocate writes a provision reference", and only one.

WHAT HAPPENED, AND WHY THE TEST IS SHAPED LIKE THIS
----------------------------------------------------
The grounding gate and the evidence adapter each had their own pattern for
reading a provision reference out of text. The gate's was hardened against a
false positive — `O.S. 442/2023` parsing as "section 442", because `O.S. 442`
contains `S. 442`. The adapter's was not, because nothing connected them.

One realistic brief then did this:

    "We act for the plaintiff in O.S. 442/2023 ... what is the step under
     section 6 of the Specific Relief Act?"

    -> retrieval looked up Specific Relief Act s.442
    -> found nothing, reported NOT_HELD
    -> the model answered about s.6
    -> the grounding gate correctly withheld the turn, because s.6 had never
       been retrieved

Two components each behaving correctly, one useless answer, and the defect
living in the gap between them. It was invisible to unit tests and obvious the
first time seven realistic turns ran end to end.

CLAUDE.md rule 4 is the fix, and it is why the last test here exists: the
question is not *where is the other copy* but **what makes a second copy
impossible**. A grep is a weak enforcement mechanism, and it is a great deal
stronger than a memo.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from nm.shared.citation_contracts import cases_named, provisions_cited, wanted_section
from nm.shared.traceability_contracts import refuses

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


@refuses("H2", 0)
def test_a_case_number_is_not_a_section_number():
    """THE COUNTEREXAMPLE, in both directions.

    `O.S. 442/2023` is an Original Suit. Reading it as section 442 sends
    retrieval after a provision that does not exist and then reports the
    absence as a corpus gap.
    """
    brief = ("We act for the plaintiff in O.S. 442/2023 before the City Civil "
             "Court. What is the step under section 6 of the Specific Relief Act?")
    assert wanted_section(brief) == "6"
    assert provisions_cited(brief) == {"6"}

    for number in ("O.S. 442/2023", "R.S.A. 12 of 2019", "C.C. 77/2025",
                   "W.P. 8891/2024", "Crl.M.P. 1234/2021"):
        assert not provisions_cited(number), (
            f"{number} is a number of record, not a provision")


def test_ordinary_provision_references_still_match():
    """The other half of the flag-calibration rule. A gate that stops matching
    real citations protects nothing."""
    assert provisions_cited("under section 138 of the NI Act") == {"138"}
    assert provisions_cited("see s. 53A and sec 65") == {"53A", "65"}
    assert provisions_cited("Article 65 governs") == {"65"}
    assert provisions_cited("an injunction under Order XXXIX") == {"XXXIX"}


def test_a_schedule_article_resolves_to_the_key_the_corpus_uses():
    """All 137 Limitation Act Articles are `schedule_article` atoms keyed
    `Article_65`, and they are absent from the parents layer entirely — so a
    section-shaped lookup finds none of them and returns a confident zero."""
    assert wanted_section("limitation under article 65 for possession") == "Article_65"


def test_case_names_are_found_and_prose_is_not():
    assert cases_named("settled by Ramesh Kumar v State of Telangana")
    assert not cases_named("the landlord has issued a quit notice to the tenant")
    assert not cases_named("we act for the plaintiff in a possession suit")


#: The canonical module, and the population every ownership scan draws from:
#: the product AND the pipeline, because the index builds are the other reader
#: of the same text (CLAUDE.md section 1, step 4).
_CANONICAL = ROOT / "nm/shared/citation_contracts.py"
_POPULATION = ("nm", "pipeline")

#: What a reader of each kind finds, and the same shape with the decisive word
#: replaced -- a pattern that finds the second as well is a catch-all, not a
#: reader. `shape` is what the match itself must contain to count.
_READS = {
    "provision": (("under section 138 of the Act", "see Article 65 of the Schedule",
                   "Order XXXIX Rule 1 CPC", "s. 6 of the Act"),
                  ("under station 138 of the Act", "see Particle 65 of the Schedule",
                   "Border XXXIX Mule 1 CPC", "x. 6 of the Act"),
                  r"(?i)(?:section|article|order|s\.).*(?:\d|[ivxl]{2,})"),
    "case citation": (("(2018) 5 SCC 379", "AIR 1973 SC 1461", "2023 INSC 123", "[1950] SCR 88"),
                      ("(2018) 5 XYZ 379", "QRS 1973 XY 1461", "2023 QRST 123", "[1950] XYZ 88"),
                      r"(?i)SCC|AIR|INSC|SCR"),
}


def _readers(source: str) -> set[str]:
    """Which kinds of legal reference the literal `re.compile` calls here READ.

    Judged by what each pattern MATCHES, not how it is spelt. The spelling scan
    this replaced flagged a word list that merely contains "section" (a filter
    for wordings that name the law) and missed a citation pattern whose
    reporter sat after a parenthesis.
    """
    import ast

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return literal(node.left) + literal(node.right)
        raise ValueError

    kinds = set()
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "compile" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re" and node.args):
            continue
        try:
            text = literal(node.args[0])
        except ValueError:
            continue
        flags = " ".join(ast.unparse(a) for a in [*node.args[1:], *(k.value for k in node.keywords)])
        try:
            compiled = re.compile(text, re.I if ("re.I" in flags or "IGNORECASE" in flags) else 0)
        except re.error:
            continue
        for kind, (real, lookalike, shape) in _READS.items():
            reads = any((m := compiled.search(r)) and re.search(shape, m.group(0)) for r in real)
            if reads and not any(compiled.search(x) for x in lookalike):
                kinds.add(kind)
    return kinds


def _offenders(kind: str) -> list[str]:
    return [str(path.relative_to(ROOT))
            for folder in _POPULATION for path in sorted((ROOT / folder).rglob("*.py"))
            if path != _CANONICAL and "__pycache__" not in path.parts
            and kind in _readers(path.read_text(encoding="utf8"))]


def test_no_module_defines_its_own_provision_pattern():
    """WHAT MAKES THE SECOND COPY IMPOSSIBLE.

    If nothing structurally refuses the duplicate, THAT is the defect — not the
    duplicate. A pattern anywhere in the product or the pipeline that reads a
    provision reference, outside the canonical module, fails the build, and
    whoever writes it is pointed at the one to import.
    """
    offenders = _offenders("provision")
    assert not offenders, (
        "a second provision-reference pattern exists in "
        + ", ".join(offenders)
        + " — import from nm.shared.citation_contracts instead. The last time there were "
          "two, one was hardened and the other was not, and a realistic brief "
          "retrieved the wrong section and reported a corpus gap.")


def test_no_module_defines_its_own_case_citation_pattern():
    """The SAME rule for case citations.

    The identity build reads judgment bodies for citations and the citation
    engine reads an advocate's text for them. If the two read differently, a
    citation the index linked is one the advocate's check cannot find, and the
    check reports it as not held -- a zero that reads exactly like absence.
    """
    offenders = _offenders("case citation")
    assert not offenders, (
        "a second case-citation pattern exists in " + ", ".join(offenders)
        + " -- use nm.shared.citation_contracts, so the build, the search and the "
          "check read citations the same way.")


def test_the_ownership_scan_sees_a_planted_reader_and_ignores_a_catch_all():
    """THE POSITIVE CONTROL, and the negative one. The scans finding nothing is
    only evidence if they can find something; and a pattern that matches any
    text, or a word list that names the law, is not a second reader."""
    assert _readers('import re\nS = re.compile(r"\\b(?:sections?|sec)\\s*(\\d+)", re.I)\n') == {"provision"}
    assert _readers('import re\nR = re.compile(r"\\(\\d{4}\\)\\s*\\d+\\s*scc\\s*\\d+", re.I)\n') == {"case citation"}
    assert _readers('import re\nR = re.compile(r"AIR\\s*" + r"\\d{4}\\s*SC\\s*\\d+")\n') == {"case citation"}
    assert _readers('import re\nR = re.compile(r"[^\\n]+")\n') == set()
    assert _readers('import re\nW = re.compile(r"\\b(?:act|section|article|rule|order)\\b|\\d", re.I)\n') == set()


def test_every_format_shown_to_the_advocate_is_read():
    """The formats listed when nothing is recognised are a promise; each is read whole."""
    from nm.shared.citation_contracts import READ_FORMATS, find_reporter_citations
    for example in READ_FORMATS:
        found = find_reporter_citations(example)
        assert [c.text for c in found] == [example], example


def test_a_citation_is_looked_up_exactly_as_written_first():
    from nm.shared.citation_contracts import find_reporter_citations, reporter_key
    for written in ("(2018) 5 SCC 379", "AIR 1973 SC 1461", "2005 (3) ALT 456", "2023 INSC 123"):
        (citation,) = find_reporter_citations(f"see {written}, at para 4")
        assert citation.keys[0] == reporter_key(written)


def test_an_equivalent_reporter_name_is_listed_only_where_measured():
    """AIR `SC` reads the `Supreme Court` form and AIR `AP` the `Andhra Pradesh`
    form; ALT/`Andh LT` and ALD/`Andh LD` were measured to be different series
    and must never be merged, or a High Court citation resolves to a Supreme
    Court judgment at the same page."""
    from nm.shared.citation_contracts import find_reporter_citations
    (sc,) = find_reporter_citations("AIR 1973 SC 1461")
    assert "AIR1973SUPREMECOURT1461" in sc.keys
    (ap,) = find_reporter_citations("AIR 1990 AP 123")
    assert "AIR1990ANDHRAPRADESH123" in ap.keys
    for written, other in (("1990 (3) ALT 605", "ANDHLT"), ("(1998) 3 ALD 273", "ANDHLD"),
                           ("(1990) 3 Andh LT 605", "ALT605"), ("2006 (1) ALD (Cri) 580", "ALDCRL")):
        (citation,) = find_reporter_citations(written)
        assert not any(other in key for key in citation.keys[1:]), (written, citation.keys)


def test_the_identity_build_links_a_citation_the_way_the_check_reads_it():
    """A judgment that cites `AIR 1973 SC 1461` treats the case held only as
    `AIR 1973 SUPREME COURT 1461`; and a citation leading to two judgments
    gives neither a treatment it may not have had."""
    from pipeline.build_identity_index import extract_treatment
    text = "The decision in Somebody v. State, AIR 1973 SC 1461 was overruled by a larger bench."
    held = {"AIR1973SUPREMECOURT1461": ("TARGET", 1973)}
    (record,) = extract_treatment(text, "TREATING", 1990, held.get)
    assert record[:2] == ("TARGET", "TREATING") and record[4] == "adverse"
    two = {"AIR1973SC1461": ("ONE", 1973), "AIR1973SUPREMECOURT1461": ("OTHER", 1973)}
    assert extract_treatment(text, "TREATING", 1990, two.get) == []


def test_a_case_number_is_not_a_case_citation():
    from nm.shared.citation_contracts import find_reporter_citations
    assert find_reporter_citations("We act in O.S. 442/2023 and W.P. 1234 of 2019 under section 6.") == ()
