"""The case account gathered where it is written (plan AN.49, piece 49d; D181, D233, D234).

The owner, 12 Nov 2026, of the matter board: "consolidate and bring logically connected aspects into one bullet". Version 3 of the case
step gives the account in a gathered shape from the same two calls: headings of the model's own choosing, each element under one,
each thing to get from one person or place with every element it serves, each point of the other side with the heading it attacks,
and what most decides the dispute. Code keeps only the mechanical rules, made again exactly on replay, and notes each element of the
first account that the account kept does not carry. The module is not wired in (D234), so these tests drive it directly. The matter
is invented.
"""
import json
from copy import deepcopy

import pytest

from nm.core_engine import case_gathered, case_strength, research_note
from nm.shared.model_port import SchemaViolation, require_schema
from tests.test_what_makes_a_disputes_case_stronger_is_set_out import Scripted, setting
from tests.test_what_makes_a_disputes_case_stronger_is_set_out import account as account_v2

pytestmark = pytest.mark.class_a

OTHER = "Other things the law requires"


def element(alias, words, heading, status, points, name):
    return {"element": name, "label": name.split(" ")[0], "heading": heading, "law": {"source_id": alias, "quote": words},
            "proves": "client", "status": status, "points": list(points), "why": "The papers say little of it."}


def ask(elements, what="A certified copy of the revenue record", from_whom="the revenue office"):
    return {"what": what, "from_whom": from_whom, "elements": list(elements), "why": "The law requires it.", "helps": "It proves it."}


def other(attacks, relies_on="Their own entry in the record"):
    return {"relies_on": relies_on, "label": relies_on.split(" ")[-1], "attacks": attacks, "law": {"source_id": "", "quote": ""},
            "answer": "It was made later.", "points": []}


def account(alias, words, located):
    """Headings: 1 holds two elements, 2 none, 3 has no name, 4 one; one element names a heading that is not in the list."""
    return {"headings": ["Possession", "Notice", "", "Title"],
            "elements": [element(alias, words, 1, "shown", [located], "Possession for twelve years"),
                         element(alias, words, 9, "weak", [], "Possession that was open"),
                         element(alias, words, 3, "missing", [], "Notice before the suit"),
                         element(alias, words, 1, "missing", [], "Possession without the owner's leave"),
                         element(alias, "words no passage holds", 4, "weak", [], "Title of the predecessor")],
            "to_get": [ask([1, 3, 9]), ask([1], what="The sale deed"), ask([], what="A photograph"),
                       ask([3, 4, 3], what="The client's statement", from_whom="the client")],
            "other_side": [other(1), other(2, "Their notice of an earlier year"), other(0, "Their tax receipts")],
            "decides": [{"what": "Whether possession was open", "why": "Everything turns on it.", "elements": [2, 7],
                         "other_side": [1, 5]},
                        {"what": "  ", "why": "No words.", "elements": [], "other_side": []}]}


def made(first=None, checked=None):
    ctx, record, sources, dispute, alias, words, located = setting()
    first = first or account(alias, words, located)
    model = Scripted(first, first if checked is None else checked)
    case = case_gathered.assess(model, ctx, record, sources, dispute)
    return case, model, (ctx, record, sources, dispute)


def test_the_same_two_calls_give_the_gathered_account_and_code_keeps_only_the_mechanical_rules():
    case, model, _ = made()
    asked, checked = model.seen
    assert (asked.operation, asked.system, checked.operation, checked.system) == (
        "core_case", case_gathered.CASE, "core_case_check", case_gathered.CASE_CHECK), "the same two steps, no call added"
    assert checked.user.startswith(asked.user) and "Your colleague's account:" in checked.user
    told = json.loads(checked.user[checked.user.index("What code could not check:\n") + len("What code could not check:\n"):])
    assert case["contract"] == "core_case_v3" and case["checked"] == "checked" and told == case["notes"]
    # Every element kept, each under one heading shown: the empty heading and the unnamed one are not shown; the elements that name
    # no named heading go under code's own, said so.
    assert case["headings"] == ["Possession", "Title", OTHER]
    assert [(item["element"], item["heading"], item["status"]) for item in case["elements"]] == [
        ("Possession for twelve years", 1, "shown"), ("Possession that was open", 3, "weak"), ("Notice before the suit", 3, "missing"),
        ("Possession without the owner's leave", 1, "missing"), ("Title of the predecessor", 2, "weak")]
    assert [item["law_found"] for item in case["elements"]] == [True, True, True, True, False], "v2's law check, unchanged"
    for note in ("Element 2 is under no named heading of the list: it is put under 'Other things the law requires'",
                 "Element 3 is under no named heading of the list: it is put under 'Other things the law requires'",
                 "Heading 2 ('Notice') has no element under it: it is not shown", "Heading 3 has no name: it is not shown",
                 "Element 5's law is not words of a held passage offered for this dispute"):
        assert note in case["notes"], note
    # Each ask serves every element it names that is in the list and not shown; one left serving none is set aside.
    assert [(entry["what"], entry["elements"]) for entry in case["to_get"]] == [
        ("A certified copy of the revenue record", [3]), ("The client's statement", [3, 4])]
    assert [(entry["what"], entry["elements"], entry["why_set_aside"]) for entry in case["set_aside"]] == [
        ("The sale deed", [1], "The papers already show every element it is for"), ("A photograph", [], "It names no element of the list")]
    for note in ("Ask 1 is for element 1, which the papers already show: it is taken off the ask",
                 "Ask 1 names element 9, which is not in the list: it is taken off the ask",
                 "Ask 2 is set aside: The papers already show every element it is for", "Ask 3 is set aside: It names no element of the list"):
        assert note in case["notes"], note
    # An attack on a heading not shown stands as attacking none; a deciding item keeps its words, losing the numbers that name nothing.
    assert [item["attacks"] for item in case["other_side"]] == [1, 0, 0]
    assert "The other side's point 2 attacks heading 2, which is not a heading shown: it stands as attacking none" in case["notes"]
    assert case["decides"] == [{"what": "Whether possession was open", "why": "Everything turns on it.", "elements": [2], "other_side": [1]}]
    assert "Deciding item 2 has no words: it is not shown" in case["notes"]
    assert case["first"] == case["proposal"] and case["not_carried"] == []


def test_an_element_of_the_first_account_the_checked_one_does_not_carry_is_noted_in_the_record_only():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    checked = deepcopy(first)
    checked["elements"][0]["element"] = "  possession FOR twelve   years "
    del checked["elements"][2]
    checked["elements"].append(element(alias, words, 1, "missing", [], "Possession that was peaceful"))
    case = case_gathered.assess(Scripted(first, checked), ctx, record, sources, dispute)
    assert case["first"] == first and case["proposal"] == checked
    assert case["not_carried"] == [{"number": 3, "element": "Notice before the suit"}], "the same words in other spacing or case carry"
    view = case_gathered.shown(case, ctx, record, sources)
    assert "not_carried" not in view and "Notice before the suit" not in json.dumps(view), "shown only once the paid check has measured it"


def test_a_failed_check_keeps_the_first_account_and_a_failed_first_call_leaves_the_case_unassessed():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    unchecked = case_gathered.assess(Scripted(first, "fail"), ctx, record, sources, dispute)
    assert (unchecked["checked"], unchecked["proposal"], unchecked["first"], unchecked["not_carried"]) == ("unchecked", first, first, [])
    assert unchecked["failures"] == [{"step": "case_check", "reason": "SchemaViolation"}] and len(unchecked["elements"]) == 5
    none = case_gathered.assess(Scripted("fail", "fail"), ctx, record, sources, dispute)
    assert (none["proposal"], none["first"], none["headings"], none["elements"], none["decides"]) == (None, None, [], [], [])
    assert none["failures"] == [{"step": "case", "reason": "SchemaViolation"}]
    assert case_gathered.shown(none, ctx, record, sources)["state"] == "unavailable"


def test_a_saved_gathered_case_replays_exactly_and_one_changed_is_refused():
    case, _, (ctx, record, sources, dispute) = made()
    saved = json.loads(json.dumps(case, ensure_ascii=False))
    assert case_gathered.validate(saved, ctx, record, sources, dispute) == case
    for change in (lambda kept: kept["elements"][1].update(heading=1), lambda kept: kept["to_get"][0]["elements"].append(1),
                   lambda kept: kept["not_carried"].append({"number": 1, "element": "Possession for twelve years"}),
                   lambda kept: kept.update(first=None), lambda kept: kept["headings"].reverse()):
        changed = deepcopy(saved)
        change(changed)
        with pytest.raises(ValueError, match="what code makes"):
            case_gathered.validate(changed, ctx, record, sources, dispute)
    with pytest.raises(ValueError, match="not of its contract's shape"):
        case_gathered.validate({**saved, "first": {"elements": []}}, ctx, record, sources, dispute)
    with pytest.raises(ValueError, match="names no dispute"):
        case_gathered.validate({**saved, "dispute_id": "D9"}, ctx, record, sources, dispute)
    with pytest.raises(ValueError, match="unknown contract"):
        case_strength.validate(saved, ctx, record, sources, dispute)  # why wiring it in is a register exception (D234)


def test_a_case_of_any_version_is_read_as_its_version_reads_it():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account_v2(alias, words, located)
    earlier = case_strength.assess(Scripted(first, first), ctx, record, sources, dispute)
    assert case_gathered.validate_saved(earlier, ctx, record, sources, dispute) == case_strength.validate(
        earlier, ctx, record, sources, dispute)
    assert case_gathered.shown_saved(earlier, ctx, record, sources) == case_strength.shown(earlier, ctx, record, sources)
    gathered, _, _ = made()
    assert case_gathered.validate_saved(gathered, ctx, record, sources, dispute) == gathered
    assert case_gathered.shown_saved(gathered, ctx, record, sources) == case_gathered.shown(gathered, ctx, record, sources)
    with pytest.raises(ValueError, match="unknown contract"):
        case_gathered.validate_saved({**gathered, "contract": "core_case_v9"}, ctx, record, sources, dispute)


def test_the_view_keeps_what_the_pages_read_today_and_adds_the_gathering():
    case, _, (ctx, record, sources, _) = made()
    view = case_gathered.shown(case, ctx, record, sources)
    assert list(view) == ["state", "headings", "elements", "to_get", "other_side", "decides"] and view["state"] == "checked"
    assert view["headings"] == ["Possession", "Title", OTHER] and [item["heading"] for item in view["elements"]] == [1, 3, 3, 1, 2]
    assert view["elements"][0]["law"]["found"] is True and view["elements"][0]["points"][0]["located"] is True
    assert view["elements"][4]["law"] == {"found": False, "words": "words no passage holds"}
    assert [(entry["for"], entry["serves"]) for entry in view["to_get"]] == [
        ("Notice before the suit", ["Notice before the suit"]),
        ("Notice before the suit", ["Notice before the suit", "Possession without the owner's leave"])]
    assert [item["attacks"] for item in view["other_side"]] == [1, 0, 0] and view["decides"] == case["decides"]
    # The note as it is drawn today reads the view as before: each ask said once, for the first element it serves.
    said = [block["text"] for block in research_note._case_blocks({"text": "The boundary dispute", "case": view})]
    assert "• To get, from the client: The client's statement (for: Notice before the suit). The law requires it. It proves it." in said


def test_the_gathered_shape_keeps_every_field_of_v2_and_differs_from_it():
    assert set(case_gathered.ELEMENT["properties"]) == set(case_strength.ELEMENT["properties"]) | {"heading"}
    assert set(case_gathered.OTHER_SIDE["properties"]) == set(case_strength.OTHER_SIDE["properties"]) | {"attacks"}
    ctx, record, sources, dispute, alias, words, located = setting()
    require_schema(account(alias, words, located), case_gathered.SCHEMA)
    with pytest.raises(SchemaViolation):
        require_schema(account_v2(alias, words, located), case_gathered.SCHEMA)


def test_the_step_is_asked_for_the_gathered_account_in_plain_words_and_in_a_loop():
    words = " ".join(case_gathered.CASE.split())
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "Work in a loop",
                 "what must still be gathered from the client or elsewhere before the matter is argued",
                 "as many as this dispute needs", "that is one thing to get, serving each of them", "what it attacks",
                 "the few things that most decide this dispute as the papers stand", "Ask only for what the papers do not already show"):
        assert part in words, part
    check = " ".join(case_gathered.CASE_CHECK.split())
    for part in ("Message:", "Purpose:", "Outcome:", "Work in a loop",
                 "nothing may be asked of the client that the papers already prove",
                 "no element of your colleague's account is lost in the gathering unless the law does not require it"):
        assert part in check, part
