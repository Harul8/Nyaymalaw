"""Authority retrieval against the real index. Class C — runs on ingest.

WHAT THIS PINS THAT THE UNIT TESTS CANNOT
------------------------------------------
The unit tests prove the Finding contract refuses a submission, an unassessed
binding status and an unchecked treatment. They prove it against Findings a
test constructed.

These prove it against 451,548 paragraphs the corpus actually holds — which is
where the interesting failures live, because the corpus is where the labels are
noisy, the court strings are unnormalised and the citator is mostly silent.

They skip cleanly when the index has not been built. A skip is visible in the
run; a test that quietly passes with nothing behind it is not.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter, default_authority_index
from nm.bootstrap.composition import ROOT
from nm.knowledge.manifest import Manifest
from nm.ports.evidence import (
    Binding,
    Coverage,
    EvidenceNeed,
    ParaKind,
    SourceKind,
    TreatmentState,
)

pytestmark = pytest.mark.class_c

CORPUS = ROOT / "legal_database" / "vector_store"
INDEX = default_authority_index(ROOT)


@pytest.fixture(scope="module")
def adapter():
    manifest = Manifest.load(ROOT / "spec" / "manifest.yaml")
    a = CorpusEvidenceAdapter(CORPUS, manifest, authority_index=INDEX)
    if not a.available:
        pytest.skip("the corpus is not attached")
    if not a.authority_available:
        pytest.skip("the authority index is not built — "
                    "run python tools/build_authority_index.py")
    return a


def need(question: str, **kw) -> EvidenceNeed:
    return EvidenceNeed(question=question, governing_date=date(2026, 8, 30),
                        want_authority=True, **kw)


# ================================================= the index itself ========

def test_the_index_records_what_it_was_built_from():
    """Defect shape S11. A derived artefact with no identity cannot be refused
    when it goes stale — it just serves old law, fluently.

    The precedent is not hypothetical: the previous build's 437MB dense index
    is only KNOWABLE as unusable because it shipped an identity record.
    """
    if not INDEX.exists():
        pytest.skip("the authority index is not built")
    con = sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)
    try:
        identity = dict(con.execute("select key, value from identity").fetchall())
    finally:
        con.close()

    assert identity["corpus_version"], "an index that cannot name its source is refused"
    assert int(identity["indexed_paragraphs"]) > 0
    assert identity["attributable_kinds"] == "ratio,reasoning,order"
    # The exclusions are recorded, not merely performed. A count nobody kept is
    # a filter nobody can audit.
    assert int(identity["excluded_not_attributable"]) > 0
    assert identity["partial"] == "no", "a partial index must not be served as whole"


def test_nothing_but_ratio_reasoning_and_order_is_indexed():
    """Counsel's submission is 14.8% of the corpus and reads exactly like a
    holding. It is excluded at BUILD time as well as at use — two independent
    exclusions, because a filter at use can be bypassed by a new call site and
    a filter at build cannot."""
    if not INDEX.exists():
        pytest.skip("the authority index is not built")
    con = sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)
    try:
        kinds = {r[0] for r in con.execute(
            "select distinct para_type from paras").fetchall()}
    finally:
        con.close()
    assert kinds <= {"ratio", "reasoning", "order"}, (
        f"the index holds non-attributable paragraphs: {kinds - {'ratio', 'reasoning', 'order'}}")


# ================================================= retrieval ===============

def test_an_authority_need_returns_attributable_paragraphs_with_locators(adapter):
    result = adapter.fetch(need("adverse possession of immovable property title"))
    assert result.coverage is Coverage.ANSWERED, result.missing
    assert result.searched_stores == ("authority_index",)

    for f in result.findings:
        assert f.source_kind is SourceKind.AUTHORITY
        assert f.para_kind.attributable, f"{f.ref} is {f.para_kind.value}"
        assert f.span.strip()
        assert f.locator.count("::") == 2, "a locator must read back to one paragraph"


def test_every_authority_carries_a_computed_binding_status_and_its_rule(adapter):
    """Binding status is COMPUTED from court and date, never asserted. The rule
    travels with it because an advocate who cannot see why an authority was
    called binding has to take it on trust."""
    result = adapter.fetch(need("adverse possession of immovable property title"))
    assert result.findings
    for f in result.findings:
        assert f.binding in (Binding.BINDING, Binding.PERSUASIVE, Binding.NOT_ASSESSED)
        assert f.binding_reason.strip()
        assert f.binding_for == "Telangana"
        if f.binding is Binding.BINDING:
            # Only two routes to binding on a Telangana matter today.
            assert ("art-141" in f.binding_reason or "bind-1" in f.binding_reason
                    or "hc-own" in f.binding_reason), f.binding_reason


def test_treatment_is_three_state_and_a_miss_is_never_clean(adapter):
    """The citator holds 4,894 entries against 33,791 judgments. Most lookups
    MISS, and a miss means the index is silent — not that the judgment is
    undoubted."""
    result = adapter.fetch(need("adverse possession of immovable property title"))
    assert result.findings
    states = {f.treatment.state for f in result.findings}
    assert states <= {TreatmentState.CLEAN, TreatmentState.NEGATIVE,
                      TreatmentState.NOT_CHECKED}
    for f in result.findings:
        assert f.treatment.scope.strip(), "a bare state is a claim about the whole judgment"
        if f.treatment.state is TreatmentState.NOT_CHECKED:
            # Unusable alone, and still QUOTABLE with its status disclosed.
            # Unusable is not unmentionable — that distinction is what stops
            # the gate from silently deleting most of the corpus.
            assert not f.usable
            assert f.quotable


def test_an_unusable_authority_says_which_gate_blocked_it(adapter):
    """`usable=False` with no explanation is an absent input reading as a quiet
    decision. The advocate is entitled to know which of five things went wrong."""
    result = adapter.fetch(need("adverse possession of immovable property title"))
    for f in result.blocked:
        assert f.blocking_reason
        assert f.blocking_reason.split(":", 1)[0].startswith("G-")


def test_a_query_matching_nothing_names_the_index_it_searched(adapter):
    """S3. A zero result that cannot name its index is indistinguishable from
    absence, and that shape has produced four false gaps in this project."""
    result = adapter.fetch(need("zzzqxwv qwertyuiop plindraxu vworbleth"))
    assert result.coverage is not Coverage.ANSWERED
    assert result.searched_stores == ("authority_index",)
    assert "authority index" in (result.missing or "")


def test_an_incidental_one_word_match_is_not_served_as_authority(adapter):
    """FTS ORs the terms, so a question containing one common legal word
    matches tens of thousands of paragraphs.

    My first version of the test above assumed nonsense returns nothing. It
    returned EIGHT judgments, because "doctrine" and "nonexistent" are real
    words. The test was wrong; the behaviour it exposed was not — an advocate
    shown eight authorities for one incidental word has been given noise
    wearing the shape of research.

    The floor is LEXICAL COVERAGE, not a similarity score. H4 forbids an
    absolute cut on a score because a score cut leaves no trace; this one
    counts what it rejected and says so.
    """
    result = adapter.fetch(need("zzzqxwv nonexistent doctrine of qwertyuiop"))
    for f in result.findings:
        assert f.confidence >= 0.5, (
            f"{f.ref} matched {f.confidence:.0%} of the question and was served "
            f"as authority")


def test_confidence_reports_lexical_coverage_and_the_best_answer_leads(adapter):
    """`confidence` says how much of the QUESTION a paragraph contains. It says
    nothing about whether the paragraph answers it, and it is not a relevance
    score — naming it honestly is what stops it being read as one."""
    result = adapter.fetch(need("adverse possession of immovable property based on title"))
    assert result.coverage is Coverage.ANSWERED
    scores = [f.confidence for f in result.findings]
    assert scores == sorted(scores, reverse=True), "the fullest match must lead"
    assert scores[0] == 1.0


def test_the_provision_route_is_unaffected_by_the_authority_route(adapter):
    """Two different needs, two different stores, and neither silently answers
    for the other."""
    provision = adapter.fetch(EvidenceNeed(
        question="section 6 of the specific relief act",
        governing_date=date(2026, 8, 30)))
    assert provision.coverage is Coverage.ANSWERED
    assert provision.findings[0].source_kind is SourceKind.PROVISION
    assert provision.findings[0].para_kind is ParaKind.UNKNOWN
    assert "authority_index" not in provision.searched_stores


# ============================================ the identity index ===========

IDENTITY = ROOT / ".nm" / "identity.db"


@pytest.fixture(scope="module")
def identity():
    from nm.knowledge.identity import IdentityIndex
    ix = IdentityIndex(IDENTITY)
    if not ix.available:
        pytest.skip("the identity index is not built — "
                    "run python tools/build_identity_index.py")
    return ix


def test_the_identity_index_recovers_what_the_derived_store_dropped(identity):
    """The measurement that reversed a design decision.

    `vector_store/` put bench coverage at 7.5% and a hierarchy rule was
    declined on it. The source files carry `Bench:` on 90.2%.
    """
    s = identity.stats()
    cases, bench = int(s["cases"]), int(s["with_bench"])
    assert cases > 30_000
    assert bench / cases > 0.85, (
        f"bench coverage fell to {bench / cases:.1%} — the parse has regressed, "
        f"and a wrong bench size silently changes which authority governs")
    assert int(s["citation_keys"]) > 250_000


def test_the_bench_distribution_stays_plausible(identity):
    """A REGRESSION GUARD ON THE PARSE ITSELF.

    The first parse scanned to a stop keyword. Only 40% of files carry a
    `PETITIONER:` header, so on the rest it ran into the judgment body and
    counted "IN THE SUPREME COURT OF INDIA" and the case number as judges —
    producing 1,556 nine-judge benches, roughly a hundred times the number in
    the Supreme Court's history. Every count looked fine; only the shape gave
    it away.
    """
    import sqlite3
    con = sqlite3.connect(f"file:{IDENTITY}?mode=ro", uri=True)
    try:
        rows = dict(con.execute(
            "select bench_size, count(*) from cases where bench_size is not null "
            "group by 1").fetchall())
    finally:
        con.close()
    total = sum(rows.values())
    small = sum(v for k, v in rows.items() if k <= 3)
    huge = sum(v for k, v in rows.items() if k >= 8)
    assert small / total > 0.85, (
        f"only {small / total:.1%} of benches are 1-3 judges; real practice is "
        f"overwhelmingly single judge and Division Bench")
    assert huge / total < 0.005, (
        f"{huge:,} benches of 8+ judges is not plausible — the parse is "
        f"swallowing non-judge lines again")


def test_treatment_is_answerable_for_the_great_majority(identity):
    """THE POINT OF THE WHOLE EXERCISE.

    The shipped citator reaches 0.83% of held judgments. What changed is not
    that more cases have treatment — most judgments are never doubted — but
    that the QUESTION is now answerable: *does anything in the 34,037 held
    treat this adversely?* That is a check with a scope, not a silence.
    """
    import sqlite3
    con = sqlite3.connect(f"file:{IDENTITY}?mode=ro", uri=True)
    try:
        cases = [r[0] for r in con.execute(
            "select case_id from cases order by random() limit 200")]
    finally:
        con.close()
    answered = sum(1 for c in cases
                   if identity.treatment(c).state.value != "not_checked")
    assert answered / len(cases) > 0.70, (
        f"only {answered / len(cases):.1%} of judgments got a treatment answer; "
        f"82.2% carry a reporter citation and should be addressable")


def test_a_clean_answer_states_the_scope_it_was_checked_against(identity):
    """`clean` is a statement about 34,037 judgments, NOT about Indian law.
    An advocate not told the boundary will read it as the wider claim."""
    import sqlite3
    con = sqlite3.connect(f"file:{IDENTITY}?mode=ro", uri=True)
    try:
        cid = con.execute(
            "select case_id from citations join cases using (case_id) limit 1"
        ).fetchone()[0]
    finally:
        con.close()
    t = identity.treatment(cid)
    assert "34,037" in t.scope
    assert "outside this corpus" in t.scope


def test_an_adverse_record_is_offered_as_a_passage_to_read_not_a_holding(identity):
    """Extraction from prose gets direction wrong some of the time — "overruled
    by X" and "overruled X" are one word apart. So an adverse record says a
    passage EXISTS and hands it over; it never asserts that the judgment is
    overruled."""
    import sqlite3
    con = sqlite3.connect(f"file:{IDENTITY}?mode=ro", uri=True)
    try:
        row = con.execute("select target_case_id from treatment "
                          "where grade='adverse' limit 1").fetchone()
    finally:
        con.close()
    if row is None:
        pytest.skip("no adverse records in this build")
    t = identity.treatment(row[0])
    assert t.state.value == "negative"
    assert "appear to treat" in t.scope
    assert "not a holding" in t.scope


def test_what_could_not_be_established_is_enumerable_not_null(identity):
    """THE REJECTS TABLE.

    These files span 1955 to 2026 and one header format does not fit them. An
    undifferentiated NULL conflates *this judgment states no bench* with *this
    era writes it differently*, and neither can be worked.

    Enumerated, the drift is obvious and runs in OPPOSITE DIRECTIONS by field:
    bench parsing fails in the old era and is clean in the 2010s, while
    citations and parties fail in the modern one. That is what found the
    neutral-citation format — `2025 INSC 407` — which lifted citation coverage
    from 82.2% to 90.9% on the next build.
    """
    rows = identity.rejects()
    assert rows, "a corpus spanning seventy years with no rejects is a parser that lies"

    fields = {f for f, _, _ in rows}
    assert {"bench", "citations", "parties"} <= fields

    # Every reject carries a REASON, not just a count.
    import sqlite3
    con = sqlite3.connect(f"file:{IDENTITY}?mode=ro", uri=True)
    try:
        blank = con.execute(
            "select count(*) from rejects where reason is null or trim(reason) = ''"
        ).fetchone()[0]
    finally:
        con.close()
    assert blank == 0, f"{blank} rejects recorded with no reason"


def test_the_authoring_judge_is_never_counted_as_the_bench(identity):
    """67% of the missing-bench files carry an inline `Name, J.` — the judge who
    WROTE the judgment, not the bench that heard it.

    Counting it as a single-judge bench would raise coverage from 90.5% to 97%
    and silently demote every Division Bench whose author signed alone. Bench
    size decides which authority governs, so the gap is left open and named.
    """
    import sqlite3
    con = sqlite3.connect(f"file:{IDENTITY}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select count(*) from rejects where field='bench' "
            "and reason like '%names who wrote it%'").fetchone()[0]
        sources = dict(con.execute(
            "select bench_source, count(*) from cases group by 1").fetchall())
    finally:
        con.close()
    assert rows > 1000, "the author-only rejects have stopped being recorded"
    assert "author_inline" not in sources, (
        "an authoring judge is being counted as a bench")
