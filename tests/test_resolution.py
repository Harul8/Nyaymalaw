"""S5 — resolution before search. H2, H3, H4 and D3B.

WHAT THE SLICE IS FOR, IN ONE MEASURED NUMBER
-----------------------------------------------
Five golden scenarios, twenty-three served turns, and the limitation position
was NOT_COMPUTED on every one of them because no Article was ever retrieved
(B-065). The sharpest instance: the advocate asks *"is the claim still in
time"* and the product answers *"no Act in the curated manifest governs this
question"* about an Act it holds in full.

Every test here is written against the counterexample its eval names, not
against the implementation. E-051's counterexample is *a governing Article
arrived at by ranking*, so that is what these construct and refuse.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.adapters.evidence.corpus import EXAMINED_CEILING
from nm.core.cause import interpret
from nm.domain.matter import CauseOfAction
from nm.domain.quotable import Quotable
from nm.domain.traceability import refuses
from nm.knowledge.resolution import (
    CODE_TITLES,
    CORRESPONDS,
    LIMITATION_ARTICLE,
    Correspondence,
    Edge,
    article_for,
    corresponding,
    governs,
)
from nm.ports.evidence import (
    Binding,
    EvidenceNeed,
    Finding,
    Origin,
    ParaKind,
    SourceKind,
    Treatment,
)

pytestmark = pytest.mark.class_a

TODAY = date(2026, 8, 31)


def _finding(**kw) -> Finding:
    base = dict(
        proposition="Limitation Act, 1963 Article 14",
        source_kind=SourceKind.PROVISION,
        ref="Limitation Act, 1963 Article 14",
        span="For the price of goods sold and delivered... three years.",
        locator="the_limitation_act_1963::Article_14::schedule_article",
        store="the_limitation_act_1963",
        binding=Binding.BINDING, binding_for="Telangana",
        binding_reason="an Act of Parliament in force",
        supports=True, para_kind=ParaKind.UNKNOWN,
        treatment=Treatment.statutory(), valid_from=date(1964, 1, 1),
        origin=Origin.RESOLVED,
    )
    base.update(kw)
    return Finding(**base)


# ================ H2 / E-050 — the query carries a date, always =============


@pytest.mark.eval_id("E-050")
def test_a_query_without_a_governing_date_is_rejected_not_defaulted_to_today():
    """H2: *A need without a governing date is REJECTED, not defaulted to
    today.*

    Defaulting is the whole defect. Every provision has a validity window, the
    2024 codes make that window decisive, and a need silently dated today would
    retrieve the current text for conduct in 2023 — confidently, with a real
    citation, and with nothing downstream able to notice.
    """
    with pytest.raises(TypeError):
        EvidenceNeed(question="what is the limitation")

    with pytest.raises(ValueError) as exc:
        EvidenceNeed(question="what is the limitation", governing_date=None)
    assert "not defaulted to today" in str(exc.value)

    # WITH a date it constructs, so this is not a blanket refusal.
    ok = EvidenceNeed(question="what is the limitation", governing_date=TODAY)
    assert ok.governing_date == TODAY


# ============ H3 / E-051 — a resolved Finding carries no score ==============


@refuses("D4", 0)
@pytest.mark.eval_id("E-051")
def test_a_resolved_finding_cannot_carry_a_similarity_score():
    """E-051's counterexample, exactly: A GOVERNING ARTICLE ARRIVED AT BY
    RANKING.

    H3: *where the graph resolves, the answer is exact and carries a citation,
    and no similarity score appears in its derivation.*

    Two defaults used to make that undecidable from the Finding's own data.
    `origin` defaulted to `"resolved"` — the strongest claim the product can
    make — so anything that forgot to say asserted it. And `confidence`
    defaulted to `1.0`, a score of exactly the shape a ranker produces. A
    ranked guess and an exact lookup were indistinguishable by construction.
    """
    with pytest.raises(ValueError) as exc:
        _finding(origin=Origin.RESOLVED, confidence=0.83)
    assert "arrived at by ranking" in str(exc.value)

    # AND THE OTHER DIRECTION. A searched Finding that drops its confidence is
    # a candidate presented as an answer, which is the search-first design H3
    # replaces.
    with pytest.raises(ValueError):
        _finding(origin=Origin.SEARCHED, confidence=None)

    # BOTH VALID SHAPES CONSTRUCT, so the type is not refusing everything.
    assert _finding(origin=Origin.RESOLVED, confidence=None).confidence is None
    assert _finding(origin=Origin.SEARCHED, confidence=0.5).confidence == 0.5


@pytest.mark.eval_id("E-051")
def test_provenance_nobody_recorded_is_not_reported_as_resolved():
    """THE DEFAULT IS THE WEAKEST CLAIM, NOT THE STRONGEST.

    A caller that forgets gets a Finding admitting nobody recorded how it was
    derived. It used to get one asserting an exact graph lookup.
    """
    assert _finding(origin=Origin.NOT_ESTABLISHED).origin \
        is Origin.NOT_ESTABLISHED
    # The escape is a VALUE and it is in the enum, not a null.
    assert Origin.NOT_ESTABLISHED in list(Origin)


@pytest.mark.eval_id("E-051")
def test_the_graph_resolves_by_exact_lookup_and_never_by_similarity():
    """CLAUDE.md §5: fuzzy may RANK, never IDENTIFY.

    Measured there, and the numbers are not close — matching case names reached
    0.83% of held judgments, matching reporter citations reached 90.9%. A cause
    this graph does not hold returns NOTHING rather than a near neighbour,
    because a near neighbour is a wrong Article nothing downstream catches.
    """
    edge = article_for(CauseOfAction.GOODS_SOLD_PRICE)
    assert edge is not None
    assert edge.provision == "Article_14"
    assert edge.act == "Limitation Act, 1963"

    # THE ESCAPE MEMBER RESOLVES TO NOTHING. "We did not work out the cause"
    # must never route anywhere.
    assert article_for(CauseOfAction.NOT_ESTABLISHED) is None

    # A CAUSE THE GRAPH DOES NOT HOLD returns nothing rather than the closest
    # edge. `CHEQUE_DISHONOUR` is in the vocabulary and deliberately carries no
    # limitation edge -- the NI Act's own s.142 window governs it, not a
    # Schedule Article, and guessing one would be a confident wrong answer.
    assert article_for(CauseOfAction.CHEQUE_DISHONOUR) is None


@pytest.mark.eval_id("E-051")
def test_every_edge_names_what_it_was_curated_from():
    """A routing decision that cannot say where it came from is one somebody
    remembered — the rule `Factor.finding` and `Period.read_from` already
    apply, in the file where remembering would be least visible."""
    for cause, edge in LIMITATION_ARTICLE.items():
        assert edge.cause is cause, f"{cause} is filed under the wrong key"
        assert edge.curated_from.strip(), f"{cause}: no curation source"
        assert edge.provision.startswith(("Article_", "s.")) or \
            edge.provision.isdigit(), (
            f"{cause}: {edge.provision!r} is not the corpus's own key form. "
            f"`Article 14` with a space looks up nothing and reports a gap.")

    with pytest.raises(ValueError):
        Edge(cause=CauseOfAction.MONEY_LENT, act="Limitation Act, 1963",
             provision="Article_19", curated_from="   ")


# ============= H3 — the cause read, and what its guards refuse ==============


@pytest.mark.eval_id("E-051")
def test_the_cause_read_refuses_a_span_the_advocate_never_wrote():
    """The posture reader's guard, applied to routing.

    The model is shown this product's own questions alongside the advocate's
    words. A guard checking the span against everything the model SAW let the
    extractor quote us back to ourselves and settle a posture nobody stated;
    the same hole here would settle a cause nobody described and send an exact
    lookup into an Article about a different suit.
    """
    said = "the goods were supplied against invoices and nothing was paid"

    good = interpret(Quotable(turn=said), {"cause": "goods_sold_price",
                            "quoted": "the goods were supplied", "why": "x"})
    assert good.cause is CauseOfAction.GOODS_SOLD_PRICE
    assert good.refused is None

    invented = interpret(Quotable(turn=said), {"cause": "money_lent",
                                "quoted": "we lent him the money", "why": "x"})
    assert invented.cause is CauseOfAction.NOT_ESTABLISHED
    assert "nothing the advocate wrote" in (invented.refused or "")

    # OUT OF VOCABULARY IS BLANKED, never accepted (B-042, B-055).
    out = interpret(Quotable(turn=said), {"cause": "wibble", "quoted": "the goods", "why": "x"})
    assert out.cause is CauseOfAction.NOT_ESTABLISHED
    assert "closed" in (out.refused or "")

    # `cannot_tell` IS AN ORDINARY ANSWER and not a refusal: nothing was
    # established, nothing was declined, and the two are different facts.
    unsure = interpret(Quotable(turn=said), {"cause": "cannot_tell", "quoted": "", "why": "x"})
    assert unsure.cause is CauseOfAction.NOT_ESTABLISHED
    assert unsure.refused is None

    # A CAUSE WITH NOTHING QUOTED settles nothing.
    bare = interpret(Quotable(turn=said), {"cause": "money_lent", "quoted": "", "why": "x"})
    assert bare.cause is CauseOfAction.NOT_ESTABLISHED
    assert "nothing quoted" in (bare.refused or "")


# ================ D3B / E-054 — across the 2024 codes =======================


@pytest.mark.eval_id("E-054")
def test_authority_under_the_corresponding_old_provision_is_reachable():
    """E-054's counterexample: *a BNS charge that retrieves nothing because the
    case law cites the IPC.*

    T-051: case law is overwhelmingly pre-2024 and cites the old numbering, so
    a system searching only the new number retrieves almost nothing.
    """
    both_ways = corresponding("Bharatiya Nyaya Sanhita, 2023", "329")
    assert both_ways is not None
    assert both_ways.old_provision == "447"
    assert "trespass" in both_ways.subject

    # AND OLD TO NEW. Conduct in 2023 is governed by the IPC and the advocate
    # still has to file under the new code today.
    assert corresponding("Indian Penal Code, 1860", "447") is both_ways

    # EXACT ON THE PAIR, never on the number alone. `s.447` means different
    # things in different codes, and matching digits is the wrong-Act defect.
    assert corresponding("Limitation Act, 1963", "447") is None
    assert corresponding("Bharatiya Nyaya Sanhita, 2023", "447") is None


@pytest.mark.eval_id("E-054")
def test_the_code_titles_are_derived_from_the_pairs_and_never_retyped():
    """A second list would go stale the first time a pair was added, and the
    failure would be silent — the new pair simply never consulted."""
    assert set(CODE_TITLES) == (
        {c.old_act for c in CORRESPONDS} | {c.new_act for c in CORRESPONDS})
    for c in CORRESPONDS:
        assert c.curated_from.strip(), f"{c.subject}: unverified pair"

    with pytest.raises(ValueError):
        Correspondence(old_act="  ", old_provision="1", new_act="X",
                       new_provision="2", subject="s", curated_from="c")


@pytest.mark.eval_id("E-054")
def test_the_governing_date_is_the_date_of_the_conduct():
    """GS-16, and the reason H2 refuses a dateless need.

    Two trespasses on one file, one in March 2024 and one last week: one thread
    is governed by the IPC throughout and the other by the BNS. The advice is
    given on the same day for both.
    """
    assert governs(date(2024, 3, 1)) != governs(date(2024, 8, 1))
    assert "1860" in governs(date(2024, 6, 30))
    assert "2023" in governs(date(2024, 7, 1)), "the transition day itself"


# ================= H4 / E-052 — structure may exclude =======================


@pytest.mark.eval_id("E-052")
def test_a_ceiling_that_binds_is_reported_and_never_silent(tmp_path):
    """H4: *No top-k or absolute-threshold cut. Any similarity exclusion is an
    outlier rejection with a recorded, measured gap, and it names what it
    rejected.*

    The query was `order by rank limit 40`. Forty is a top-k cut on a
    SIMILARITY ORDER — precisely what H4 names — and the forty-first paragraph
    was discarded with no count and no trace, so a miss caused by the cut was
    indistinguishable from an absence in the corpus.

    The ceiling stays: an unbounded scan of 451,553 attributable paragraphs on
    every turn is not a retrieval strategy. What it may not be is SILENT.

    Asserted on BEHAVIOUR, against a real index. The first version of this test
    scanned the source for `limit 40` and failed on the comment explaining the
    fix, which is what a source scan is worth.
    """
    import sqlite3

    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import Manifest

    db = tmp_path / "authority.db"
    con = sqlite3.connect(db)
    con.executescript(
        "create virtual table paras using fts5("
        "  case_id, case_name, court, year UNINDEXED, para_type UNINDEXED,"
        "  chunk_id UNINDEXED, text, tokenize = 'porter unicode61');")
    body = ("the doctrine of adverse possession requires animus possidendi "
            "against the true owner throughout the statutory period")
    con.executemany(
        "insert into paras values (?,?,?,?,?,?,?)",
        [(f"case_{i}", f"Case {i} vs State", "Supreme Court of India", 2015,
          "ratio", f"chunk_{i}", body) for i in range(EXAMINED_CEILING + 12)])
    con.commit()
    con.close()

    # The corpus dir need not hold chunks.db: this exercises the authority
    # path, which reads its own index.
    (tmp_path / "chunks.db").write_bytes(b"")
    adapter = CorpusEvidenceAdapter(
        tmp_path, Manifest.load("spec/manifest.yaml"), authority_index=db)

    need = EvidenceNeed(
        question="adverse possession animus possidendi against the true owner",
        governing_date=TODAY, want_authority=True)
    result = adapter.fetch(need)

    assert result.findings, "the fixture index returned nothing at all"
    assert result.assumption, (
        "more paragraphs matched than were examined and the answer said "
        "nothing about it — a miss caused by the ceiling is then "
        "indistinguishable from an absence in the corpus")
    assert "did not reach" in result.assumption
    assert "not a statement about the corpus" in result.assumption
    assert str(EXAMINED_CEILING) in result.assumption


@pytest.mark.eval_id("E-052")
def test_a_ceiling_that_does_not_bind_claims_nothing(tmp_path):
    """THE POSITIVE CONTROL. A disclosure that fires on every answer teaches
    the advocate to ignore it, which costs more than it buys."""
    import sqlite3

    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import Manifest

    db = tmp_path / "authority.db"
    con = sqlite3.connect(db)
    con.executescript(
        "create virtual table paras using fts5("
        "  case_id, case_name, court, year UNINDEXED, para_type UNINDEXED,"
        "  chunk_id UNINDEXED, text, tokenize = 'porter unicode61');")
    body = ("the doctrine of adverse possession requires animus possidendi "
            "against the true owner throughout the statutory period")
    con.executemany(
        "insert into paras values (?,?,?,?,?,?,?)",
        [(f"case_{i}", f"Case {i} vs State", "Supreme Court of India", 2015,
          "ratio", f"chunk_{i}", body) for i in range(3)])
    con.commit()
    con.close()
    (tmp_path / "chunks.db").write_bytes(b"")

    adapter = CorpusEvidenceAdapter(
        tmp_path, Manifest.load("spec/manifest.yaml"), authority_index=db)
    result = adapter.fetch(EvidenceNeed(
        question="adverse possession animus possidendi against the true owner",
        governing_date=TODAY, want_authority=True))

    assert result.findings
    assert "did not reach" not in (result.assumption or ""), (
        "the ceiling reported binding on three rows")


# ================== H3 ON THE SERVED PATH ===================================


@pytest.mark.eval_id("E-051")
def test_the_turn_routes_a_determinate_question_without_a_named_provision(
        tmp_path):
    """B-065, CLOSED, and asserted where it actually failed.

    The four defects S4's scenario run exposed all lived between a correct
    module and the served path. `article_for` and `_route` can both be right
    while the engine never sets `cause_of_action`, and the twenty-three turns
    that computed no limitation would look exactly the same.

    So this drives the REAL adapter — manifest, chunk store, routing — with a
    question that names no provision at all.
    """
    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import Manifest

    adapter = CorpusEvidenceAdapter(
        "legal_database/vector_store", Manifest.load("spec/manifest.yaml"))
    if not adapter.available:
        pytest.skip("the corpus is not attached")

    need = EvidenceNeed(question="is the claim still in time",
                        governing_date=TODAY,
                        cause_of_action="goods_sold_price")
    routed = adapter._route(need)
    assert routed is not None, (
        "the question names no Act and no section, which is the case the graph "
        "exists for, and nothing resolved")
    assert routed.entry.act_name == "Limitation Act, 1963"
    assert routed.provision == "Article_14"
    assert "I resolved one" in routed.note, "the route was not disclosed"
    assert "Also arguable" in routed.note, (
        "the alternatives are not named, so a wrong route is invisible until "
        "the advocate has acted on it")


@pytest.mark.eval_id("E-051")
def test_a_provision_the_advocate_named_outranks_the_graph(tmp_path):
    """THE ADVOCATE'S INSTRUCTION WINS.

    Routing past a section they named would substitute this product's view of
    the cause for their instruction — the one thing an exact lookup must never
    do, and the mirror of the defect where keyword scoring outvoted a named
    Act on `possession`.
    """
    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import Manifest

    adapter = CorpusEvidenceAdapter(
        "legal_database/vector_store", Manifest.load("spec/manifest.yaml"))
    if not adapter.available:
        pytest.skip("the corpus is not attached")

    named = EvidenceNeed(
        question="what does section 6 of the Specific Relief Act say",
        governing_date=TODAY, cause_of_action="goods_sold_price")
    assert adapter._route(named) is None, (
        "the graph routed to a Limitation Article over a section the advocate "
        "named in the same sentence")


@pytest.mark.eval_id("E-051")
def test_the_engine_sets_the_cause_so_the_graph_can_be_consulted(tmp_path):
    """`EvidenceNeed.cause_of_action` existed since slice 2 AND NOTHING SET IT.

    A field with no producer is a graph with no input. This asserts the engine
    fills it on a served turn, because every other test here would pass with
    the wiring absent.
    """
    from nm.core.turn import TurnInput
    from tests.test_turn_contract import build

    seen: list[str | None] = []

    class _Recording:
        def __init__(self):
            from tests.test_turn_contract import _Evidence
            self._inner = _Evidence()

        def fetch(self, need):
            seen.append(need.cause_of_action)
            return self._inner.fetch(need)

    engine, _ = build(tmp_path, evidence=_Recording())
    engine.run(TurnInput(
        advocate_id="adv", today=TODAY,
        message=("we act for the plaintiff. the goods were supplied against "
                 "invoices dated 14 March 2023 and nothing was paid.")))

    assert seen, "retrieval was never called"
    assert seen[0] == "goods_sold_price", (
        f"the engine did not put a cause on the need: {seen[0]!r}. The graph "
        f"cannot be consulted without one, which is how the field sat unused "
        f"for three slices.")
