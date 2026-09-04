"""A4 — E-116 and E-117.

E-116  A zero names the index it came from and that index's identity. An index
       that cannot be opened yields NOT_ASSESSED, never an empty hit list.
       Every hit carries SEARCHED and a confidence; none carries RESOLVED.

E-117  An Act is identified by EXACT TITLE only. The search surface cannot
       identify one at all, which is the structural half of that rule.

WHY THESE ARE INVARIANTS AND NOT SCENARIOS
-------------------------------------------
Each states a RULE about any query, and each is written so that the mechanism
being removed turns it red — not so that today's behaviour is recorded. The
zero-result rule is tested by making the index absent, not by finding a query
that happens to return nothing.
"""
from __future__ import annotations

import inspect
import sqlite3

import pytest

from nm.adapters.search import authority
from nm.adapters.search.authority import AuthorityIndexSearch
from nm.domain.traceability import refuses
from nm.ports.evidence import Coverage, Origin
from nm.ports.search import CorpusSearch, IndexIdentity, SearchHit

pytestmark = pytest.mark.class_a


def _identity() -> IndexIdentity:
    return IndexIdentity(name="probe", built_at="2026-09-04", source="probe.db",
                         corpus_version="test", held=10, of_source=100,
                         scope="Telangana and the Union of India")


# ============================ E-116: the zero ==============================

@refuses("A4", 1)
@pytest.mark.eval_id("E-116")
def test_an_index_that_cannot_be_opened_is_not_assessed_never_empty(tmp_path):
    """THE MOST REPEATED DEFECT IN THIS PROJECT, at the search box.

    A screen that could not run returning the shape of a clean result. An
    advocate handed `hits: []` reads "the law is not in the corpus", and the
    truth was that nothing was searched at all.
    """
    result = AuthorityIndexSearch(tmp_path / "not-built.db").search("possession")

    assert result.coverage is Coverage.NOT_ASSESSED, (
        f"an absent index reported {result.coverage.value} — the advocate is "
        f"being told something about the corpus when nothing was searched")
    assert result.hits == ()
    assert result.why and "not present" in result.why
    assert "build_authority_index" in result.why, (
        "the reason must name what would fix it")


@pytest.mark.eval_id("E-116")
def test_an_index_with_no_identity_is_not_searched_at_all(tmp_path):
    """S11. The only reason the previous build's 437MB dense index was KNOWABLY
    unusable is that it shipped an identity. An index that cannot say what it
    is gets used on trust."""
    path = tmp_path / "anonymous.db"
    con = sqlite3.connect(path)
    con.execute("create virtual table paras using fts5(case_id, case_name, "
                "court, year, para_type, chunk_id, text)")
    con.execute("insert into paras values ('c1','A vs B','SC','2001','ratio',"
                "'k1','the possession was adverse')")
    con.commit()
    con.close()

    result = AuthorityIndexSearch(path).search("possession")
    assert result.coverage is Coverage.NOT_ASSESSED, (
        "an index with no identity answered a query. There is no way to know "
        "what corpus it was built from, so its hits cannot be read.")
    assert result.hits == ()


@pytest.mark.eval_id("E-116")
def test_a_result_with_no_index_named_cannot_be_constructed():
    """B-163: a zero result must name the index it came from. Enforced by the
    type, so no adapter can omit it — a zero from an unnamed index reads
    exactly like an empty corpus."""
    with pytest.raises(ValueError, match="names the index"):
        CorpusSearch(query="x", index="   ", coverage=Coverage.ANSWERED,
                     identity=_identity())


@pytest.mark.eval_id("E-116")
def test_a_search_that_ran_must_carry_what_it_searched():
    """A zero is only readable against what the index HOLDS. 451,548 paragraphs
    sounds like the corpus until it is set beside the 1,015,780 it came from."""
    with pytest.raises(ValueError, match="identity"):
        CorpusSearch(query="x", index="probe", coverage=Coverage.ANSWERED)


@pytest.mark.eval_id("E-116")
def test_not_assessed_without_a_reason_is_refused():
    """§9's third state must be visible in the OUTPUT, not only in the type.
    `NOT_ASSESSED` with no reason tells the advocate nothing was found rather
    than that nothing was looked at."""
    with pytest.raises(ValueError, match="reason"):
        CorpusSearch(query="x", index="probe", coverage=Coverage.NOT_ASSESSED)

    with pytest.raises(ValueError, match="returned hits"):
        CorpusSearch(query="x", index="probe", coverage=Coverage.NOT_ASSESSED,
                     why="nothing was searched",
                     hits=(SearchHit(case_id="c1", case_name="A vs B",
                                     court="SC", year=2001, para_type="ratio",
                                     snippet="…", rank=-1.0, confidence=0.5),))


@pytest.mark.eval_id("E-116")
def test_an_unknown_source_size_is_none_and_never_a_ratio_of_zero():
    """A ratio of zero says the index is empty. Not knowing is a third state
    and it is a VALUE."""
    unknown = IndexIdentity(name="p", built_at="x", source="y",
                            corpus_version="z", held=10, of_source=0,
                            scope="Telangana and the Union of India")
    assert unknown.fraction_of_source is None


@refuses("A4", 2)
@pytest.mark.eval_id("E-116")
def test_no_hit_may_claim_resolved_provenance():
    """E-051's counterexample: a governing authority arrived at by RANKING,
    presented as one arrived at by an exact key. A search box has no key."""
    with pytest.raises(ValueError, match="RESOLVED"):
        SearchHit(case_id="c1", case_name="A vs B", court="SC", year=2001,
                  para_type="ratio", snippet="…", rank=-1.0, confidence=0.9,
                  origin=Origin.RESOLVED)


@pytest.mark.eval_id("E-116")
def test_every_hit_carries_a_confidence_that_is_a_probability():
    with pytest.raises(ValueError, match="probability"):
        SearchHit(case_id="c1", case_name="A vs B", court="SC", year=2001,
                  para_type="ratio", snippet="…", rank=-1.0, confidence=4.2)


@pytest.mark.eval_id("E-116")
def test_a_filtered_zero_names_the_filter_that_narrowed_it(tmp_path):
    """An advocate who set a court and got nothing is owed the difference
    between `not in this court` and `not in the corpus`."""
    said = authority._why_empty({"court": "High Court for Telangana"})
    assert "High Court for Telangana" in said
    assert "Clearing them" in said
    unfiltered = authority._why_empty({})
    assert "party names" in unfiltered, (
        "an unfiltered zero must say what the index does NOT hold — searching "
        "case names against a paragraph index returns zero and reads as absence")


@pytest.mark.eval_id("E-116")
def test_a_query_of_pure_operators_is_not_assessed_rather_than_crashing(tmp_path):
    """An advocate typing `"part performance"` is not writing a query language.
    An unescaped quote raises inside FTS5, arrives as a 500, and reads as
    absence — so the operators are stripped and an empty remainder is
    NOT_ASSESSED with its reason."""
    assert authority._fts_query('"" () * ^') is None
    assert authority._fts_query('s. 53A "part performance"') == (
        '"53A" "part" "performance"'), (
        "every term must be quoted, so nothing the advocate typed is read as "
        "an operator")


# ====================== E-117: fuzzy may never identify ====================

@refuses("A4", 0)
@pytest.mark.eval_id("E-117")
def test_the_search_surface_cannot_identify_an_act():
    """CLAUDE.md §5, structurally.

    Measured: `Indian Easements Act 1882` scored to the Indian Evidence Act,
    1872 on the shared word *Indian*, and to the Transfer of Property Act,
    1882 on the shared year. The defence is not a better scorer — it is that
    this surface has no way to return an Act at all, so the exact-match path
    is the only path an Act can come down.
    """
    from nm.ports.search import CorpusSearchPort

    methods = [n for n in dir(CorpusSearchPort) if not n.startswith("_")]
    assert methods == ["search"], (
        f"the search port grew {methods}. Every method here ranks, and a "
        f"ranked method whose name says `act` is one refactor away from "
        f"deciding WHICH statute is read.")

    act_shaped = [n for n in dir(AuthorityIndexSearch)
                  if not n.startswith("_") and
                  any(w in n.lower() for w in ("act", "statute", "provision",
                                               "section"))]
    assert not act_shaped, (
        f"the search adapter exposes {act_shaped}. An Act is identified by "
        f"exact title through the evidence adapter, never by ranking.")


@pytest.mark.eval_id("E-117")
def test_a_search_hit_carries_no_act_field_to_be_mistaken_for_one():
    """A hit describes a case PARAGRAPH. If it carried an `act` the renderer
    would eventually print it, and a ranked paragraph's incidental mention of
    a statute would read as the governing Act."""
    fields = set(SearchHit.__dataclass_fields__)
    assert not (fields & {"act", "act_id", "statute", "section", "provision"}), (
        f"SearchHit carries statute-shaped fields: {fields}")


@pytest.mark.eval_id("E-117")
def test_the_query_builder_never_scores_a_title_against_a_title():
    """The positive control for §5, on the code itself.

    A ranking function comparing two TITLES is the exact operation that
    produced all three measured wrong answers. This asserts the adapter holds
    no such comparison — no similarity, no ratio, no overlap.
    """
    src = inspect.getsource(authority)
    for banned in ("SequenceMatcher", "difflib", "fuzz.", "token_set_ratio",
                   "jaccard", "levenshtein"):
        assert banned not in src, (
            f"the search adapter uses {banned}. Ranking PARAGRAPHS is what "
            f"this module is for; a similarity score anywhere near a title is "
            f"how an Act gets identified by overlap.")


# ============ the two NEVERs that needed a mechanism, not a tag ============

@refuses("A4", 3)
@pytest.mark.eval_id("E-116")
def test_every_result_says_which_law_it_searched():
    """THE CORPUS IS TELANGANA AND THE UNION, and a result that does not say
    so is read as an answer about wherever the advocate is asking from.

    An empty result to a Kerala question is not a finding about Kerala law.
    Nothing downstream catches that, because a zero is indistinguishable from
    a zero — the only place it can be caught is here, on the way out.
    """
    result = AuthorityIndexSearch(".nm/authority.db").search(
        "adverse possession", limit=1)
    if result.identity is None:
        pytest.skip("NOT ASSESSED: the authority index is not built here, so "
                    "there is no identity to inspect. This is skipped rather "
                    "than passed, because a green result from an absent index "
                    "is exactly the shape this file exists to refuse.")

    assert result.identity.scope.strip(), (
        "the index answered without saying what law it covers")
    assert "Telangana" in result.identity.scope, result.identity.scope

    # AND IT HAS NO DEFAULT ON THE TYPE. A field that defaults quietly becomes
    # a field nobody sets, and a wrong scope then looks exactly like a right
    # one. Constructing without it must be a TypeError.
    with pytest.raises(TypeError):
        IndexIdentity(name="p", built_at="x", source="y", corpus_version="z",
                      held=1, of_source=2)


@refuses("A4", 4)
@pytest.mark.eval_id("E-116")
def test_no_route_turns_a_search_hit_into_a_fact_on_a_matter():
    """THE ADVOCATE PLACES IT; THE PRODUCT DOES NOT.

    A hit is a ranked paragraph. The moment a route exists that writes one
    onto a matter, the product has established a fact by ranking — and every
    downstream control that trusts an established fact inherits it.

    Asserted on the ROUTE TABLE rather than on the search module, because the
    danger is a convenience endpoint added next to it later.
    """
    from nm.edge import api

    search_writes = [
        r for r in api.app.routes
        if getattr(r, "path", "").startswith("/api/search")
        and set(getattr(r, "methods", ()) or ()) - {"GET", "HEAD", "OPTIONS"}
    ]
    assert not search_writes, (
        f"the search surface has a writing route: {search_writes}. A hit that "
        f"can be posted onto a matter is a fact the product established by "
        f"ranking.")

    # AND NO IMPORT PATH FROM THE SEARCH ADAPTER TO THE MATTER.
    #
    # Asserted on the IMPORTS rather than by scanning the source for words: a
    # word scan fails on the module's own explanatory prose, which has already
    # cost this project two rewritten tests. What is actually forbidden is a
    # dependency, and a dependency is a thing that can be enumerated.
    import ast
    tree = ast.parse(inspect.getsource(authority))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            reached.add(node.module)
        elif isinstance(node, ast.Import):
            reached.update(a.name for a in node.names)
    forbidden = sorted(m for m in reached
                       if m.startswith(("nm.domain.matter", "nm.ports.store",
                                        "nm.adapters.store")))
    assert not forbidden, (
        f"the search adapter imports {forbidden}. It reads an index and "
        f"returns paragraphs; a path from here to the matter is the one thing "
        f"this NEVER forbids.")
