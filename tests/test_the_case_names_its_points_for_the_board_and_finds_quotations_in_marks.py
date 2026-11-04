"""The case step's v2 (plan AN.39, D57-D58; owner, 4 Nov 2026): the board in short phrases with the detail in the reading pane, so each
element and each thing the other side relies on carries a short name for the board, given in the same call; and a law quotation the
step wrapped in quotation marks is still found in the passage it names (the saved one-paper answer of 4 Nov had 13 of its 15 element
laws refused for that alone). A case saved as v1 is checked and shown exactly as it was saved (P46). The matter is invented."""
from copy import deepcopy

import pytest

from nm.core_engine import case_strength
from tests.test_what_makes_a_disputes_case_stronger_is_set_out import Scripted, account, element, setting

pytestmark = pytest.mark.class_a


def test_each_element_and_each_thing_the_other_side_relies_on_keeps_its_short_name_for_the_board():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    case = case_strength.assess(Scripted(first, first), ctx, record, sources, dispute)
    assert case["contract"] == case_strength.CONTRACT == "core_case_v2"
    assert [item["label"] for item in case["elements"]] == ["Possession for the period"] * 3
    assert case["other_side"][0]["label"] == "Their own entry"
    shown = case_strength.shown(case, ctx, record, sources)
    assert [item["label"] for item in shown["elements"]] == ["Possession for the period"] * 3
    assert shown["other_side"][0]["label"] == "Their own entry"
    assert case_strength.validate(case, ctx, record, sources, dispute) == case


def test_the_step_is_asked_for_the_short_names_in_plain_words():
    words = " ".join(case_strength.CASE.split())
    assert "label (the element named in a few words, as the advocate's matter board lists it)" in words
    assert "label (what they will rely on, in a few words)" in words
    assert case_strength.SCHEMA["properties"]["elements"]["items"]["required"][:2] == ["element", "label"]


def test_a_law_quotation_wrapped_in_quotation_marks_is_found_and_shown_in_the_passages_own_words():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    first["elements"][2] = element(alias, f"\u201c{words}\u201d")
    case = case_strength.assess(Scripted(first, first), ctx, record, sources, dispute)
    assert [item["law_found"] for item in case["elements"]] == [True, False, True]
    assert case["elements"][2]["law"]["quote"] == f"\u201c{words}\u201d", "the step's own words are kept as given"
    shown = case_strength.shown(case, ctx, record, sources)
    given = shown["elements"][2]["law"]
    assert given["found"] and given["words"] in sources[given["source_id"]]["text"], "the passage's own words, line breaks and all"
    assert given["words"].split() == words.split()
    assert case_strength.validate(case, ctx, record, sources, dispute) == case


def test_a_case_saved_as_v1_is_checked_and_shown_exactly_as_it_was_saved():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    for item in [*first["elements"], *first["other_side"]]:
        item.pop("label")
    first["elements"][2] = {key: value for key, value in element(alias, f"\u201c{words}\u201d").items() if key != "label"}
    _, offered, points = case_strength.material(ctx, record, sources, dispute)
    saved = {"contract": case_strength.V1_CONTRACT, "dispute_id": dispute["id"], "proposal": first, "checked": "checked",
             "failures": [], **case_strength.admit(first, offered, points, sources, case_strength.V1_CONTRACT)}
    assert case_strength.validate(saved, ctx, record, sources, dispute) == saved
    assert [item["law_found"] for item in saved["elements"]] == [True, False, False], "v1 looked for a quotation only as given"
    assert all("label" not in item for item in [*saved["elements"], *saved["other_side"]])
    shown = case_strength.shown(saved, ctx, record, sources)
    assert all("label" not in item for item in [*shown["elements"], *shown["other_side"]])
    assert shown["elements"][0]["law"]["words"] == words and shown["elements"][2]["law"] == {
        "found": False, "words": f"\u201c{words}\u201d"}
    relabelled = deepcopy(saved)
    relabelled["elements"][0]["label"] = "Possession"
    with pytest.raises(ValueError, match="what code makes"):
        case_strength.validate(relabelled, ctx, record, sources, dispute)
