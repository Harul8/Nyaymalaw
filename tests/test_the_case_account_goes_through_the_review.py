"""Plan AN.51 (D290, 17 Nov 2026; D202 decided as Claude recommended): the case account goes through the independent review, once,
and what it faults is left out.

After the account is made and checked, one call on the review tier (6.1 Terra, D289) reads it against the same material and names
each item it finds wrong. Code leaves out of what is shown each item the review names, each requirement whose law is not in a held
passage offered for the dispute (never shown to the review), and each thing to get left serving only what was left out; the record
keeps them all, nothing is rewritten after the review, and the line on the account and the research note say what was left out and
why. 'checked' is the view's state only where the second look and the review were both made (F-03). Offline: scripted answers on an
invented matter; whether the review finds what is wrong in a real account is for the bounded live run, not these tests.
"""
import json
from copy import deepcopy

import pytest

from nm.core_engine import case_gathered, research_note
from nm.shared.model_port import ModelError, SchemaViolation, Tier, UsageLimitReached
from tests.test_the_case_is_gathered_under_headings import account, element, kept
from tests.test_what_makes_a_disputes_case_stronger_is_set_out import Scripted, setting

pytestmark = pytest.mark.class_a


class Tiered(Scripted):
    """Scripted, keeping the tier each call was sent on; the review raising what it is given to raise."""

    def __init__(self, first, checked, reviewed=None, raises=None):
        super().__init__(first, checked, reviewed)
        self.tiers, self.raises = [], raises

    def structured(self, prompt, schema, tier, **kwargs):
        self.tiers.append((prompt.operation, tier))
        if prompt.operation == "core_case_review" and self.raises is not None:
            self.seen.append(prompt)
            raise self.raises
        return super().structured(prompt, schema, tier, **kwargs)


def reviewed(faults=(), first=None, checked=None, raises=None):
    ctx, record, sources, dispute, alias, words, located = setting()
    first = first or account(alias, words, located)
    model = Tiered(first, kept(first) if checked is None else checked, {"faults": list(faults)}, raises)
    case = case_gathered.assess(model, ctx, record, sources, dispute)
    return case, model, (ctx, record, sources, dispute)


def fault(item, number, why="It is wrong by the papers."):
    return {"item": item, "number": number, "why": why}


def test_the_review_is_one_call_on_the_review_tier_shown_the_account_as_it_would_be_shown():
    case, model, _ = reviewed()
    assert model.tiers == [("core_case", Tier.ROUTINE), ("core_case_check", Tier.ROUTINE), ("core_case_review", Tier.JUDGE)]
    asked, _, review = model.seen
    assert review.system == case_gathered.CASE_REVIEW and review.user.startswith(asked.user), "the same material, then the account"
    shown_to = json.loads(review.user[review.user.index("The account NM has prepared:\n") + len("The account NM has prepared:\n"):])
    assert shown_to == case_gathered.for_review(case)
    # The requirement whose law is not in a held passage is never shown to the review; every other item is, with its number in the
    # account and each requirement with its heading's name.
    assert [(item["number"], item["heading"]) for item in shown_to["elements"]] == [
        (1, "Possession"), (2, case_gathered.OTHER), (3, case_gathered.OTHER), (4, "Possession")]
    assert [(ask["number"], ask["for"]) for ask in shown_to["to_get"]] == [(1, [3]), (2, [3, 4])]
    assert [(item["number"], item["attacks"]) for item in shown_to["other_side"]] == [(1, [1, 4]), (2, []), (3, []), (4, [2])]
    assert [item["number"] for item in shown_to["decides"]] == [1]
    assert case["review"] == {"faults": []} and case["checked"] == "checked" and case["failures"] == []
    assert case["left_out"] == [{"item": "element", "number": 5, "by": "law", "why": ""}]


def test_what_the_review_names_is_left_out_of_what_is_shown_and_said_with_its_reason():
    case, _, (ctx, record, sources, _) = reviewed([
        fault("element", 3, "The law sets no notice before such a suit."), fault("other_side", 1, "Their entry is not in the papers."),
        fault("decides", 1, "It is not what decides it."), fault("element", 3, "Said twice."), fault("to_get", 9, "Nothing.")])
    # The record keeps every item; what was left out is named by its number in the account, in the account's order.
    assert len(case["elements"]) == 5 and len(case["other_side"]) == 4 and len(case["decides"]) == 1
    assert case["left_out"] == [
        {"item": "element", "number": 3, "by": "review", "why": "The law sets no notice before such a suit."},
        {"item": "element", "number": 5, "by": "law", "why": ""},
        {"item": "to_get", "number": 1, "by": "with", "why": ""},
        {"item": "other_side", "number": 1, "by": "review", "why": "Their entry is not in the papers."},
        {"item": "decides", "number": 1, "by": "review", "why": "It is not what decides it."}]
    assert "The review names to_get 9, which it was not shown: nothing is left out for it" in case["notes"]
    view = case_gathered.shown(case, ctx, record, sources)
    assert [item["element"] for item in view["elements"]] == [
        "Possession for twelve years", "Possession that was open", "Possession without the owner's leave"]
    # The ask for the requirement left out alone goes with it; the one that serves another keeps that one.
    assert [(ask["what"], ask["serves"]) for ask in view["to_get"]] == [
        ("The client's statement", ["Possession without the owner's leave"])]
    assert [item["relies_on"] for item in view["other_side"]] == [
        "Their notice of an earlier year", "Their tax receipts", "Their sale deed"]
    assert view["other_side"][2]["against"] == ["Possession that was open"] and view["decides"] == []
    assert view["state"] == "checked"
    assert view["said"] == (
        "This is NM's working list: a second look checked it, code looked for each quotation of law in the passage it names, and "
        "the independent review read it against the papers and the law. Left out of it: 3 items the independent review found "
        "wrong, 1 requirement whose law NM could not find in the law it read and 1 thing to get that was only for what was left "
        "out; the research note says which and why.")
    # The note says the same line and, item by item, what was left out and why.
    said = [block["text"] for block in research_note._case_blocks({"text": "The boundary dispute", "case": view})]
    assert view["said"] in said and "Left out of this list:" in said
    for line in ("• A requirement: Notice before the suit. The independent review found it wrong: The law sets no notice before "
                 "such a suit.",
                 "• A requirement: Title of the predecessor. NM could not find the words of the law it names in the law it read.",
                 "• A thing to get: A certified copy of the revenue record. It was to get only for what was left out.",
                 "• A point of the other side: Their own entry in the record. The independent review found it wrong: Their entry "
                 "is not in the papers.",
                 "• A thing said to decide the dispute: Whether possession was open. The independent review found it wrong: It is "
                 "not what decides it."):
        assert line in said, line


def test_checked_is_said_only_where_the_second_look_and_the_review_were_both_made():
    ctx, record, sources, dispute, alias, words, located = setting()
    unreviewed, model, _ = reviewed(raises=ModelError("The review did not complete"))
    assert unreviewed["review"] is None and unreviewed["failures"] == [{"step": "case_review", "reason": "ModelError"}]
    assert unreviewed["left_out"] == [{"item": "element", "number": 5, "by": "law", "why": ""}], "code's own still left out"
    view = case_gathered.shown(unreviewed, ctx, record, sources)
    assert view["state"] == "unreviewed" and view["said"] == (
        "This is NM's working list: a second look checked it and code looked for each quotation of law in the passage it names. "
        "It has not been through the independent review. Left out of it: 1 requirement whose law NM could not find in the law it "
        "read; the research note says which and why.")
    assert case_gathered.validate(json.loads(json.dumps(unreviewed)), ctx, record, sources, dispute) == unreviewed
    # The second look failed and the review was made: unchecked, the review claimed.
    first = account(alias, words, located)
    unchecked, _, _ = reviewed(first=first, checked="fail")
    assert unchecked["failures"] == [{"step": "case_check", "reason": "SchemaViolation"}] and unchecked["review"] == {"faults": []}
    view = case_gathered.shown(unchecked, ctx, record, sources)
    assert view["state"] == "unchecked" and "a second look" not in view["said"] and "the independent review read it" in view["said"]
    both, _, _ = reviewed(first=first, checked="fail", raises=SchemaViolation("scripted"))
    assert [failure["step"] for failure in both["failures"]] == ["case_check", "case_review"]
    assert case_gathered.shown(both, ctx, record, sources)["state"] == "unchecked"
    assert case_gathered.validate(json.loads(json.dumps(both)), ctx, record, sources, dispute) == both
    # A usage limit at the review stops the turn, as at every step.
    with pytest.raises(UsageLimitReached):
        reviewed(raises=UsageLimitReached("limit"))


def test_nothing_left_to_show_is_not_reviewed():
    ctx, record, sources, dispute, alias, words, located = setting()
    unfound = element(alias, "words no passage holds", 1, "missing", [], "Title of the predecessor")
    first = {"headings": ["Title"], "elements": [unfound], "to_get": [{"what": "The deed", "from_whom": "the client",
             "elements": [1], "why": "It shows title.", "helps": "It proves it."}], "other_side": [], "decides": []}
    case, model, _ = reviewed(first=first)
    assert [operation for operation, _ in model.tiers] == ["core_case", "core_case_check"], "no review of an empty account"
    assert case["review"] is None and case["failures"] == []
    assert [(entry["item"], entry["by"]) for entry in case["left_out"]] == [("element", "law"), ("to_get", "with")]
    view = case_gathered.shown(case, ctx, record, sources)
    assert view["elements"] == [] and view["to_get"] == [] and view["state"] == "checked"
    said = [block["text"] for block in research_note._case_blocks({"text": "The title dispute", "case": view})]
    assert "NM left out every requirement it set out for this dispute." in said
    assert not any(text.startswith("NM set out no element") for text in said)
    assert case_gathered.validate(json.loads(json.dumps(case)), ctx, record, sources, dispute) == case


def test_a_saved_reviewed_case_replays_exactly_and_one_changed_is_refused():
    case, _, (ctx, record, sources, dispute) = reviewed([fault("element", 1), fault("to_get", 2)])
    saved = json.loads(json.dumps(case, ensure_ascii=False))
    assert case_gathered.validate(saved, ctx, record, sources, dispute) == case
    for change in (lambda kept: kept["review"]["faults"].pop(), lambda kept: kept["left_out"].pop(),
                   lambda kept: kept["review"]["faults"][0].update(why="Another reason."),
                   lambda kept: kept.update(review=None), lambda kept: kept["failures"].append(
                       {"step": "case_review", "reason": "ModelError"}),
                   lambda kept: kept.update(review=None, failures=[{"step": "case_review", "reason": "ModelError"}])):
        changed = deepcopy(saved)
        change(changed)
        with pytest.raises(ValueError, match="what code makes"):
            case_gathered.validate(changed, ctx, record, sources, dispute)
    with pytest.raises(ValueError, match="not of its contract's shape"):
        case_gathered.validate({**saved, "review": {"faults": [{"item": "law", "number": 1, "why": ""}]}}, ctx, record, sources,
                               dispute)
    without = {key: value for key, value in saved.items() if key != "review"}
    with pytest.raises(ValueError, match="what code makes"):
        case_gathered.validate(without, ctx, record, sources, dispute)


def test_the_review_is_asked_in_plain_words_and_in_a_loop():
    words = " ".join(case_gathered.CASE_REVIEW.split())
    for part in ("Message:", "Purpose:", "Outcome:", "Work in a loop", "You are the independent review of this account",
                 "a requirement the law it quotes does not set", "a burden put on the wrong side",
                 "an ask for what the papers already show", "An item that is right stands",
                 "NM leaves out each item you name, tells the advocate so with your reason, and changes nothing else",
                 "keep only those you can stand behind"):
        assert part in words, part
    assert set(case_gathered.REVIEW_SCHEMA["properties"]) == {"faults"}
    assert case_gathered.REVIEW_FAULT["properties"]["item"]["enum"] == list(case_gathered.ITEMS)
