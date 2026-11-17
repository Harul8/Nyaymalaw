"""A requirement, or a point of the other side, may rest on several passages of law (plan AN.49, D293; the owner's "D293 - Ok",
17 Nov 2026).

The bounded live run of the finished build found 7 of 13 requirements set by several provisions or judgments read together, each
named in the gathered account's one law field: code could not place them, and D290 left all seven out although six were quoted word
for word. The gathered account (core_case_v3) now gives each item's law as a list of passages, each with its own exact words. Code
looks for each quotation in its own passage, as v2 looks for the one; a requirement is left out by law only where none is found, and
is shown with the quotations found and those not found said so. Offline: scripted answers on an invented matter.
"""
import pytest

from nm.core_engine import case_gathered, case_strength, research_note
from nm.shared.model_port import SchemaViolation, require_schema
from tests.test_the_case_is_gathered_under_headings import element, kept, other
from tests.test_what_makes_a_disputes_case_stronger_is_set_out import Scripted, setting

pytestmark = pytest.mark.class_a


def gathered():
    """Four requirements under one heading: two passages both found; two, the second's words named under the first's ID (the shape
    the live run showed); one quotation no passage holds; no law at all. Two points of the other side: one with a passage found and
    one not, one with no held law."""
    ctx, record, sources, dispute, _, _, located = setting()
    _, law, _ = case_strength.material(ctx, record, sources, dispute)
    first, second = list(law)[:2]
    words = {alias: " ".join(sources[law[alias]]["text"].split()[:6]) for alias in (first, second)}
    assert words[second] not in sources[law[first]]["text"], "the second passage's words are not the first's"
    one, two = {"source_id": first, "quote": words[first]}, {"source_id": second, "quote": words[second]}
    misnamed = {"source_id": first, "quote": words[second]}

    def needs(name, laws, status="missing", points=()):
        return {**element(first, "", 1, status, points, name), "law": laws}
    account = {"headings": ["Possession"],
               "elements": [needs("Possession for twelve years", [one, two], "shown", [located]),
                            needs("Possession that was open", [one, misnamed], "weak"),
                            needs("Notice before the suit", [{"source_id": first, "quote": "words no passage holds"}]),
                            needs("Title of the predecessor", [])],
               "to_get": [], "other_side": [{**other([1], "Their own entry in the record"), "law": [two, misnamed]},
                                            other([2], "Their tax receipts")],
               "decides": []}
    case = case_gathered.assess(Scripted(account, kept(account)), ctx, record, sources, dispute)
    return case, (ctx, record, sources, dispute), (first, second, words)


def test_each_passage_is_looked_for_in_its_own_passage_and_a_requirement_goes_only_where_none_is_found():
    case, _, (first, _, _) = gathered()
    assert [item["law_found"] for item in case["elements"]] == [[True, True], [True, False], [False], []]
    assert [item["law_found"] for item in case["other_side"]] == [[True, False], []]
    for note in (f"Element 2's law 2 ({first}) is not words of that held passage offered for this dispute",
                 f"Element 3's law 1 ({first}) is not words of that held passage offered for this dispute",
                 "Element 4 names no law"):
        assert note in case["notes"], note
    assert not [note for note in case["notes"] if note.startswith("Element 1's law")], "both of element 1's passages were found"
    # Left out by law: only the requirements none of whose quotations is found.
    assert case["left_out"] == [{"item": "element", "number": 3, "by": "law", "why": ""},
                                {"item": "element", "number": 4, "by": "law", "why": ""}]
    shown_to = case_gathered.for_review(case)
    assert [(item["number"], len(item["law"])) for item in shown_to["elements"]] == [(1, 2), (2, 2)], "the review sees each passage"


def test_the_view_gives_each_passage_as_v2_gives_the_one_and_the_note_says_each():
    case, (ctx, record, sources, _), (first, second, words) = gathered()
    view = case_gathered.shown(case, ctx, record, sources)
    assert [item["element"] for item in view["elements"]] == ["Possession for twelve years", "Possession that was open"]
    both, part = view["elements"][0]["law"], view["elements"][1]["law"]
    # The words shown are the passage's own, as they stand in it (v2), so spaced as it spaces them.
    assert [(law["found"], law["source_id"], " ".join(law["words"].split())) for law in both] == [
        (True, case_strength.answer_sources.aliases(sources)[first], words[first]),
        (True, case_strength.answer_sources.aliases(sources)[second], words[second])], "each passage's own words and identity"
    assert part[0]["found"] is True and part[1] == {"found": False, "words": words[second]}
    assert [len(item["law"]) for item in view["other_side"]] == [2, 0]
    assert view["other_side"][0]["law"][1] == {"found": False, "words": words[second]}
    assert [entry["by"] for entry in view["left_out"]] == ["law", "law"]
    said = [block["text"] for block in research_note._case_blocks({"text": "The boundary dispute", "case": view})]
    line = " ".join(next(text for text in said if "Possession that was open." in text).split())
    assert f'"{words[first]}".' in line and f'NM could not find these words in the law it read: "{words[second]}".' in line


def test_a_saved_account_is_checked_again_exactly_and_the_one_law_shape_is_not_v3():
    case, (ctx, record, sources, dispute), _ = gathered()
    assert case_gathered.validate(case, ctx, record, sources, dispute) == case
    require_schema(case["proposal"], case_gathered.SCHEMA_CHECKED)
    one_law = {**case["proposal"], "elements": [{**item, "law": item["law"][0] if item["law"] else {"source_id": "", "quote": ""}}
                                                for item in case["proposal"]["elements"]]}
    with pytest.raises(SchemaViolation):
        require_schema(one_law, case_gathered.SCHEMA_CHECKED)
    with pytest.raises(ValueError, match="shape"):
        case_gathered.validate({**case, "proposal": one_law}, ctx, record, sources, dispute)
