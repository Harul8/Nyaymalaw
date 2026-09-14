"""Finding is not verifying -- the rules, without an index or a route. P21.

BK-84-AC3's domain half, BK-45-AC1's rule, and the vocabulary every other P21
test reads. Nothing here touches SQLite: these are the verdict functions over
their inputs, and each planted negative is the criterion's own.
"""
from __future__ import annotations

import pytest
from nm.core import research as rs
from nm.ports.evidence import Binding, Coverage

pytestmark = pytest.mark.class_a


# ================================================= the four outcomes ========

def test_an_unavailable_index_outranks_everything():
    """Nothing was searched, so nothing is said about coverage or results."""
    out = rs.classify(Coverage.NOT_ASSESSED, hits=0, court="Supreme Court",
                     court_read_as="court: 'Supreme Court' read as 'Supreme Court of India'")
    assert out is rs.Outcome.UNAVAILABLE_INDEX


def test_a_court_the_corpus_does_not_hold_is_unsupported_coverage_not_zero():
    """BK-38-AC2's planted negative: an unknown court alias. The old `1 = 0`
    filter made this read as zero results; zero results says the law is not
    there, and that is false."""
    out = rs.classify(Coverage.ANSWERED, hits=0, court="Kerala High Court",
                     court_read_as="court: 'Kerala High Court' matches no court this "
                                   "index holds. It holds ...")
    assert out is rs.Outcome.UNSUPPORTED_COVERAGE


def test_a_search_that_ran_and_found_nothing_says_so():
    out = rs.classify(Coverage.ANSWERED, hits=0, court=None, court_read_as="")
    assert out is rs.Outcome.SEARCHED_NO_RESULTS


def test_results_are_results():
    out = rs.classify(Coverage.ANSWERED, hits=3, court="Supreme Court",
                     court_read_as="court: 'Supreme Court' read as 'Supreme Court of India'")
    assert out is rs.Outcome.RESULTS


def test_an_out_of_scope_jurisdiction_is_unsupported_even_with_hits():
    """Scope is applied BEFORE retrieval. Hits that came back for a forum this
    corpus does not cover are not results the advocate may act on."""
    out = rs.classify(Coverage.ANSWERED, hits=7, court=None, court_read_as="",
                     in_scope=False)
    assert out is rs.Outcome.UNSUPPORTED_COVERAGE


# ============================================ identity and quotation ========

def test_a_verbatim_quote_is_verbatim_after_whitespace_only():
    source = "The test is whether the marker\n  was blue when the goods left."
    assert rs.quote_fidelity("the marker was blue when the goods left", source) \
        is rs.QuoteState.VERBATIM


def test_a_quote_that_differs_by_one_word_differs():
    """NO THRESHOLD. A near-quote is how a source is made to say what it did
    not (CLAUDE.md §5)."""
    source = "The test is whether the marker was blue when the goods left."
    assert rs.quote_fidelity("the marker was green when the goods left", source) \
        is rs.QuoteState.DIFFERS


def test_a_quote_with_no_source_text_is_not_checked_not_verbatim():
    assert rs.quote_fidelity("anything", None) is rs.QuoteState.NOT_CHECKED
    assert rs.quote_fidelity("   ", "anything") is rs.QuoteState.NOT_CHECKED


@pytest.mark.parametrize("identity,quote", [
    (rs.IdentityState.UNRESOLVED, rs.QuoteState.VERBATIM),
    (rs.IdentityState.INDEX_UNAVAILABLE, rs.QuoteState.VERBATIM),
    (rs.IdentityState.RESOLVED, rs.QuoteState.DIFFERS),
    (rs.IdentityState.RESOLVED, rs.QuoteState.NOT_CHECKED),
    (rs.IdentityState.UNRESOLVED, rs.QuoteState.NOT_CHECKED),
])
def test_a_ranked_snippet_cannot_be_attached_as_a_verified_source(identity, quote):
    """BK-38-AC1's negative control: *attach a ranked snippet as if it were an
    exact verified source.* A snippet has no resolved locator and windowed
    text; every combination short of RESOLVED + VERBATIM is refused, with the
    dimension that failed named."""
    ok, why = rs.may_attach(identity, quote)
    assert ok is False
    assert why
    assert (identity.value in why) or (quote.value in why)


def test_only_a_resolved_verbatim_source_may_be_attached():
    ok, why = rs.may_attach(rs.IdentityState.RESOLVED, rs.QuoteState.VERBATIM)
    assert ok is True and why == ""


def test_a_verified_citation_means_identity_and_words_and_nothing_more():
    """BK-84-AC3: *a verified citation does not establish all those
    dimensions.* The property is deliberately narrow."""
    a = rs.Reliance(issue="i", case_id="c", locator="c_P1", quote="q",
                     identity=rs.IdentityState.RESOLVED,
                     quote_fidelity=rs.QuoteState.VERBATIM,
                     treatment_state="negative")
    assert a.verified_citation is True
    assert a.support is rs.SupportState.NOT_ASSESSED
    assert a.applicability is rs.Applicability.NOT_ASSESSED
    assert a.treatment_state == "negative"
    d = a.as_dict()
    assert d["verified_citation"] is True and d["support"] == "not_assessed"


# ================================================ the adverse search ========

def _record(**kw) -> rs.Research:
    return rs.Research(id="res_x", objective="o", issue="i", **kw)


def test_no_adverse_search_is_not_a_clean_bill():
    """EVAL-014's planted negative: *replace the unavailable adverse result
    with an empty successful list without a completed search event.* A record
    with no adverse search, and one whose search could not run, both read
    `not_assessed` -- never `clean`."""
    assert rs.clean_bill(_record()) == "not_assessed"
    unavailable = _record(adverse=(rs.AdverseSearch(
        target="SYN_1", state=rs.AdverseState.UNAVAILABLE, why="index not built"),))
    assert rs.clean_bill(unavailable) == "not_assessed"
    not_run = _record(adverse=(rs.AdverseSearch(target="SYN_1", state=rs.AdverseState.NOT_RUN),))
    assert rs.clean_bill(not_run) == "not_assessed"


def test_an_adverse_search_that_ran_and_found_nothing_is_clean():
    ran = _record(adverse=(rs.AdverseSearch(
        target="SYN_1", state=rs.AdverseState.RAN, query="treatment of SYN_1",
        outcome=rs.Outcome.SEARCHED_NO_RESULTS),))
    assert rs.clean_bill(ran) == "clean"


def test_an_adverse_search_that_found_something_is_adverse_found():
    ran = _record(adverse=(rs.AdverseSearch(
        target="SYN_2001", state=rs.AdverseState.RAN, query="treatment",
        outcome=rs.Outcome.RESULTS, found=("SYN_2001",)),))
    assert rs.clean_bill(ran) == "adverse_found"
    assert ran.as_dict()["clean_bill"] == "adverse_found"


# ============================================ the record and its bound ======

def test_a_round_is_counted_once_and_the_bound_leaves_a_reason():
    r = _record()
    c = rs.Consulted(query="q", index="idx", outcome=rs.Outcome.SEARCHED_NO_RESULTS)
    r = rs.with_round(r, c)
    assert r.rounds == 1 and r.budget_left == 1 and not r.stopped_because
    r = rs.with_round(r, c)
    assert r.rounds == 2 and r.budget_left == 0
    assert "round limit" in r.stopped_because
    assert r.rounds_exceeded is False, "reaching the bound is not exceeding it"


def test_the_record_survives_a_round_trip_with_every_field():
    r = _record(created_at="2026-09-12", created_by="adv")
    r = rs.with_round(r, rs.Consulted(
        query="q", index="idx", outcome=rs.Outcome.RESULTS, built_at="t",
        corpus_version="v", held=7, of_source=12, court="SC",
        court_read_as="read as SC", from_year=1990, to_year=2010,
        case_ids=("A", "B"), why=""),
        rs.AdverseSearch(target="A, B", state=rs.AdverseState.RAN, query="t",
                        outcome=rs.Outcome.RESULTS, found=("B",)))
    r = rs.with_reliance(r, rs.Reliance(
        issue="i", case_id="A", locator="A_P1", quote="words",
        identity=rs.IdentityState.RESOLVED, quote_fidelity=rs.QuoteState.VERBATIM,
        treatment_state="clean", treatment_scope="s",
        applicability=rs.Applicability.BINDING, applicability_because="b",
        attached_by="adv", at="2026-09-12", source_version="snap-1",
        text_digest="d"))
    back = rs.Research.from_stored(r.as_dict())
    assert back == r, "a field did not survive as_dict -> from_stored"


def test_an_unreadable_stored_record_is_none_not_a_blank_record():
    assert rs.Research.from_stored({"objective": "no id"}) is None
    assert rs.Research.from_stored("garbage") is None
    assert rs.all_from_stored([{"id": "a", "objective": "o", "issue": "i"}, "x"])[0].id == "a"


# ==================================================== applicability =========

def test_applicability_follows_the_binding_relationship_and_names_the_third_state():
    binding, _ = rs.applicability_of(Binding.BINDING, forum_said="SC binds")
    assert binding is rs.Applicability.BINDING
    assert rs.applicability_of(Binding.PERSUASIVE, forum_said="x")[0] is rs.Applicability.PERSUASIVE
    state, why = rs.applicability_of(None, forum_said="")
    assert state is rs.Applicability.NOT_ASSESSED and why
    assert rs.applicability_of(Binding.NOT_ASSESSED, forum_said="unknown court")[0] \
        is rs.Applicability.NOT_ASSESSED
