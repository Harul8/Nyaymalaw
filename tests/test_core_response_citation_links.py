"""Rendering v4: sources link at the words that cite them, never a whole paragraph."""
import pytest

from nm.core_engine import response_authorities, response_rendering, response_review
from tests.test_core_response_rendering import Model
from tests.test_core_response_authorities import Reader
from tests.test_core_response_rendering import ready

pytestmark = pytest.mark.class_a


def rendered(text=None):
    legacy = ready(text) if text else ready()
    ctx, record, sources, draft, legacy_review, execution = legacy
    authorities = response_authorities.check(ctx, record, sources, draft, provision_reader=Reader(record))
    review = response_review.review(Model(legacy_review["proposal"]), ctx, record,
        sources, draft, execution=execution, authority_evidence=authorities)
    fresh = (ctx, record, sources, draft, review, execution)
    # Unnamed sources follow the paragraph as markers from v4 to v10, the versions a saved
    # answer is still replayed in; from v11 each source sits on its own words instead
    # (tests/test_core_linked_words.py).
    return (response_rendering.render(*fresh, authority_evidence=authorities,
                                      contract=response_rendering.HELD_CONTRACT)[0],
            response_rendering.render(*fresh, authority_evidence=authorities,
                                      contract=response_rendering.SHOWN_NAME_CONTRACT)[0])


def reachable(element):
    linked = {a["source_index"] for a in element["inline_citations"]}
    marked = {m["source_index"] for m in element["citation_markers"]}
    return linked, marked


def test_unnamed_sources_follow_the_paragraph_instead_of_linking_all_of_it():
    v4, v3 = rendered()
    assert v3["inline_citations"] == [{"text": v3["text"], "source_id": v3["source"]["id"], "source_index": 0}]
    assert v4["inline_citations"] == []
    linked, marked = reachable(v4)
    assert marked == set(range(len(v4["sources"]))) and not linked
    assert [m["source_id"] for m in v4["citation_markers"]] == [s["id"] for s in v4["sources"]]


def test_names_and_locators_link_ignoring_case_with_exact_offsets():
    text = "judgment 12 records a submission; JUDGMENT 13 rejects it. act article 64 includes an exception."
    v4, _ = rendered(text)
    # The checked provision reference outranks the name match for the same source.
    assert [a["text"] for a in v4["inline_citations"]] == ["judgment 12", "JUDGMENT 13", "article 64"]
    for anchor in v4["inline_citations"]:
        assert v4["text"][anchor["start"]:anchor["end"]] == anchor["text"]
        assert anchor["source_id"] == v4["sources"][anchor["source_index"]]["id"]
    linked, marked = reachable(v4)
    assert linked | marked == set(range(len(v4["sources"]))) and not linked & marked


def test_a_paragraph_that_is_only_a_name_is_never_one_link():
    v4, _ = rendered("Act Article 64")
    assert all((a["start"], a["end"]) != (0, len(v4["text"])) for a in v4["inline_citations"])
    assert [a["text"] for a in v4["inline_citations"]] == ["Article 64"]
    linked, marked = reachable(v4)
    assert linked | marked == set(range(len(v4["sources"]))) and not linked & marked


def source(identity, title, locator):
    return {"id": identity, "title": title, "locator": locator}


def authority(cases=(), provisions=()):
    return {"case_associations": list(cases), "prose_provisions": list(provisions)}


def provision_row(text, mention, candidates, key_match="one_used_identity"):
    start = text.index(mention)
    return {"text": mention, "start": start, "end": start + len(mention),
            "key_match": key_match, "candidate_source_ids": candidates}


def test_a_section_reference_links_only_when_its_act_is_named_in_the_same_sentence():
    sources = [source("p1", "The Consumer Protection Act, 1986", "14"),
               source("p2", "Consumer Protection Act, 2019", "2")]
    text = ("Section 14 of the Consumer Protection Act, 1986 lists remedies. "
            "Section 2 of the 2019 Act defines a consumer.")
    rows = [provision_row(text, "Section 14", ["p1"]), provision_row(text, "Section 2", ["p2"])]
    anchors, markers = response_rendering._cited_words(text, sources, authority(provisions=rows))
    assert [(a["text"], a["source_id"]) for a in anchors] == [("Section 14", "p1")]
    assert [m["source_id"] for m in markers] == ["p2"]


def test_an_unbound_or_shared_reference_never_selects_a_source():
    sources = [source("p1", "Act A", "5"), source("p2", "Act A", "5")]
    text = "Under Act A, section 5 applies."
    rows = [provision_row(text, "section 5", ["p1", "p2"], key_match="multiple_used_identities")]
    anchors, markers = response_rendering._cited_words(text, sources, authority(provisions=rows))
    assert anchors == [] and [m["source_id"] for m in markers] == ["p1", "p2"]


def test_a_case_citation_links_only_when_matched_to_one_used_judgment():
    sources = [source("j1", "Asha v Ravi", "4"), source("j2", "Mohan v State", "9")]
    text = "Asha v Ravi, (2003) 5 SCC 100, was followed; (2004) 1 SCC 7 was not."
    matched = {"start": text.index("(2003)"), "end": text.index("(2003)") + len("(2003) 5 SCC 100"),
               "association": "matched", "matching_source_ids": ["j1"]}
    unresolved = {"start": text.index("(2004)"), "end": text.index("(2004)") + len("(2004) 1 SCC 7"),
                  "association": "unresolved_association", "matching_source_ids": ["j2"]}
    anchors, markers = response_rendering._cited_words(text, sources, authority(cases=[matched, unresolved]))
    assert [(a["text"], a["source_id"]) for a in anchors] == [("(2003) 5 SCC 100", "j1")]
    assert [m["source_id"] for m in markers] == ["j2"]


def test_bare_numbers_and_repeated_names_stay_unlinked():
    sources = [source("p1", "Act A", "12"), source("p2", "Act B", "13")]
    text = "It mentions 12 and 13. Act A and Act A again; Act B once."
    anchors, markers = response_rendering._cited_words(text, sources, authority())
    assert [(a["text"], a["source_id"]) for a in anchors] == [("Act B", "p2")]
    assert [m["source_id"] for m in markers] == ["p1"]
