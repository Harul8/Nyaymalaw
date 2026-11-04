"""What makes a dispute's case stronger is set out from its held law and the papers (plan AN.35, D31-D32; piece 35c1).

The owner, 2 Nov 2026: the retrieved passages of the Acts and judgments "will tell us what will make the case stronger, and thereby
we should try to get those materials and evidences from the client accordingly". One step per dispute sets out what the law
requires - each element in the law's own words, who must prove it, and whether the papers show it, show it weakly or not at all -
what to get for each element weak or missing, and what the other side will rely on; a second call checks it, shown what code could
not check. Code keeps only the mechanical rules: law words exactly in a held passage offered for the dispute; points that are the
papers' points; "shown" only with a point found on its page; no ask for what the papers show. The matter is invented.
"""
import json
from copy import deepcopy

import pytest

from nm.core_engine import case_strength
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import _result
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import matter

pytestmark = pytest.mark.class_a


class Scripted:
    """Answers the case call and its check from scripts (a failure where a script is "fail"), keeping what it was shown."""

    def __init__(self, first, checked):
        self.first, self.checked, self.seen = first, checked, []

    def context_budget(self, tier):
        return 10 ** 9

    def structured(self, prompt, schema, tier, **kwargs):
        self.seen.append(prompt)
        given = self.first if prompt.operation == "core_case" else self.checked
        if given == "fail":
            raise SchemaViolation("scripted failure")
        return _result(given, tier)


def setting():
    ctx, record, sources = matter()
    dispute = record["plan"]["proposal"]["understanding"]["disputes"][0]
    _, law, points = case_strength.material(ctx, record, sources, dispute)
    alias = next(iter(law))
    words = " ".join(sources[law[alias]]["text"].split()[:6])
    located = next(point for point, found in points.items() if found)
    return ctx, record, sources, dispute, alias, words, located


def element(alias, words, status="missing", points=(), proves="client"):
    return {"element": "Possession for the period the law requires", "label": "Possession for the period",
            "law": {"source_id": alias, "quote": words}, "proves": proves, "status": status, "points": list(points),
            "why": "The papers say little of it."}


def ask(number, what="A certified copy of the revenue record"):
    return {"what": what, "from_whom": "the client", "element": number, "why": "The law requires it.", "helps": "It proves it."}


def account(alias, words, located):
    return {"elements": [element(alias, words, "shown", [located]), element(alias, "words no passage holds", "shown", ["E99"]),
                         element(alias, words)],
            "to_get": [ask(1), ask(3), ask(9)],
            "other_side": [{"relies_on": "Their own entry in the record", "label": "Their own entry",
                            "law": {"source_id": "", "quote": ""}, "answer": "It was made later.", "points": [located]}]}


def test_the_step_reads_the_dispute_its_law_and_every_point_and_its_check_is_told_what_code_could_not_check():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    model = Scripted(first, first)
    case = case_strength.assess(model, ctx, record, sources, dispute)
    asked, checked = model.seen
    assert (asked.operation, asked.system, checked.operation, checked.system) == (
        "core_case", case_strength.CASE, "core_case_check", case_strength.CASE_CHECK)
    shown = json.loads(asked.user)
    assert shown["dispute"]["id"] == dispute["id"] and shown["held_law"] and shown["points"]
    assert checked.user.startswith(asked.user) and "Your colleague's account:" in checked.user
    told = checked.user[checked.user.index("What code could not check:"):]
    assert "'E99', which is not a point of the papers' list" in told and "it stands as weak" in told
    assert [(e["status"], e["law_found"], e["points"]) for e in case["elements"]] == [
        ("shown", True, [located]), ("weak", False, []), ("missing", True, [])]
    assert [entry["element"] for entry in case["to_get"]] == [3], "the ask for what the papers show, and one for no element, go"
    assert [entry["why_set_aside"] for entry in case["set_aside"]] == ["The papers already show the element it is for",
                                                                       "It names no element of the list"]
    assert case["other_side"][0]["law"] == {"source_id": "", "quote": ""} and case["checked"] == "checked"


def test_a_failed_check_keeps_the_first_account_and_a_failed_first_call_leaves_the_case_unassessed():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    unchecked = case_strength.assess(Scripted(first, "fail"), ctx, record, sources, dispute)
    assert unchecked["checked"] == "unchecked" and unchecked["proposal"] == first and len(unchecked["elements"]) == 3
    assert unchecked["failures"] == [{"step": "case_check", "reason": "SchemaViolation"}]
    none = case_strength.assess(Scripted("fail", "fail"), ctx, record, sources, dispute)
    assert none["proposal"] is None and none["elements"] == [] and none["failures"] == [{"step": "case", "reason": "SchemaViolation"}]


def test_a_saved_case_replays_exactly_and_one_changed_is_refused():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    case = case_strength.assess(Scripted(first, first), ctx, record, sources, dispute)
    assert case_strength.validate(case, ctx, record, sources, dispute) == case
    changed = deepcopy(case)
    changed["elements"][1]["status"] = "shown"
    with pytest.raises(ValueError, match="what code makes"):
        case_strength.validate(changed, ctx, record, sources, dispute)
    with pytest.raises(ValueError, match="names no dispute"):
        case_strength.validate({**case, "dispute_id": "D9"}, ctx, record, sources, dispute)


def test_the_step_is_asked_for_the_case_in_plain_words_and_in_a_loop():
    words = " ".join(case_strength.CASE.split())
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "Work in a loop",
                 "what must still be gathered from the client or elsewhere before the matter is argued",
                 "Ask only for what the papers do not already show"):
        assert part in words, part
    assert "nothing may be asked of the client that the papers already prove" in " ".join(case_strength.CASE_CHECK.split())


def test_each_disputes_section_keeps_its_case_set_out_beside_it_and_a_changed_one_is_refused():
    """Piece 35c2: from research v15 each dispute's case is set out beside the writing of its section, from the same research,
    and kept with the section; the saved answer replays exactly, and a case changed, dropped or put under another dispute is
    refused (P46)."""
    from nm.core_engine import turn
    from tests.test_core_answer_sections import Scripted, answered, refused
    ctx, elements, activity, calls = answered(Scripted())
    sections = activity["sections"]
    assert [(section["case"]["contract"], section["case"]["dispute_id"], section["case"]["checked"]) for section in sections] == [
        (case_strength.CONTRACT, section["dispute_id"], "checked") for section in sections]
    made = sorted(call["operation"] for call in calls.calls if call["operation"].startswith("core_case"))
    assert made == ["core_case", "core_case", "core_case_check", "core_case_check"], "two calls for each dispute"
    assert turn.validate_activity(activity, ctx, elements) == activity
    refused(activity, ctx, elements, lambda forged: forged["sections"][0]["case"].update(checked="unchecked"))
    refused(activity, ctx, elements, lambda forged: forged["sections"][0].pop("case"))
    refused(activity, ctx, elements, lambda forged: forged["sections"][0].update(case=deepcopy(forged["sections"][1]["case"])))


def test_the_research_note_keeps_what_makes_the_case_stronger_as_the_page_shows_it():
    """Piece 35c3b: the note the advocate keeps or sends sets out the case as the page shows it - each element with how it stands
    and the law's words, or that NM could not find them in the law it read; what to get; what the other side will rely on."""
    from nm.core_engine import research_note
    view = {"state": "unchecked", "elements": [
        {"element": "Possession for the period the law requires", "proves": "client", "status": "weak", "why": "Only one entry shows it.",
         "law": {"found": True, "kind": "provision", "title": "Imagined Relief Act, 1907", "locator": "Section 4",
                 "words": "possession for twelve years", "source_id": "P:abc"}, "points": []},
        {"element": "Notice before the suit", "proves": "client", "status": "missing", "why": "Nothing shows it.",
         "law": {"found": False, "words": "notice in writing"}, "points": []}],
        "to_get": [{"what": "The postal receipt", "from_whom": "the client", "why": "It proves the date of posting.", "helps": "",
                    "for": "Notice before the suit"}],
        "other_side": [{"relies_on": "Their later entry", "answer": "It was made after the suit.", "law": None, "points": []}]}
    blocks = research_note._case_blocks({"kind": "CASE", "text": "What makes the case stronger", "case": view})
    assert [block["text"] for block in blocks] == [
        "What makes the case stronger",
        "NM's second look at this list could not be made, so it stands as first set out.",
        "Shown only weakly, for the client to prove: Possession for the period the law requires. Only one entry shows it. "
        'Imagined Relief Act, 1907, Section 4: "possession for twelve years".',
        "Not yet shown, for the client to prove: Notice before the suit. Nothing shows it. NM could not find these words in the law "
        'it read: "notice in writing".',
        "• To get, from the client: The postal receipt. It proves the date of posting.",
        "The other side will rely on: Their later entry. What answers it: It was made after the suit."]
    assert blocks[0]["kind"] == "subheading" and all(block["kind"] == "paragraph" for block in blocks[1:])
