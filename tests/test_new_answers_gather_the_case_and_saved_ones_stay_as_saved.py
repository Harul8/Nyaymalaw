"""Plan AN.49 (D291, 17 Nov 2026; AN.48's register item 15): 49d is wired. Every new answer's case step makes the account gathered
under headings (case_gathered, v3) in place of v2; a case saved before as v2 is checked and shown exactly as it was saved (P46),
by case_strength as before - the same answer reopened draws it without headings, as the page has always drawn it. Offline: the
two-dispute scripted matter of tests/test_core_answer_sections.py through the real loop; not browser QA and no claim about the
model's legal reading (the paid check of AN.49's column 7 measured that)."""
from nm.core_engine import answer_sections, case_gathered, case_strength, turn
from tests.test_core_answer_sections import Scripted, answered, refused


def cases_shown(ctx, activity):
    """Each section's case as the answer and the board show it (answer_sections.case_shown, which both read)."""
    return [answer_sections.case_shown(section, ctx, activity["research"], activity["sources"]) for section in activity["sections"]]


def test_a_new_answer_sets_out_the_gathered_account_and_draws_it_with_its_headings():
    ctx, elements, activity, calls = answered(Scripted())
    assert {section["case"]["contract"] for section in activity["sections"]} == {case_gathered.CONTRACT}
    shown = cases_shown(ctx, activity)
    assert len(shown) == 2 and all(view["state"] == "checked" and "headings" in view and "decides" in view for view in shown)
    made = sorted(call["operation"] for call in calls.calls if call["operation"].startswith("core_case"))
    assert made == ["core_case", "core_case", "core_case_check", "core_case_check"], "the same two calls for each dispute"
    assert turn.validate_activity(activity, ctx, elements) == activity
    # A gathered case changed after saving is refused, as any saved case is.
    refused(activity, ctx, elements, lambda forged: forged["sections"][0]["case"].update(headings=["Another heading"]))


def test_a_case_saved_before_as_v2_is_checked_and_drawn_as_it_was_saved(monkeypatch):
    monkeypatch.setattr(case_gathered, "assess", case_strength.assess)  # the case step as it was before D291
    ctx, elements, activity, _ = answered(Scripted())
    monkeypatch.undo()
    assert {section["case"]["contract"] for section in activity["sections"]} == {case_strength.CONTRACT}
    shown = cases_shown(ctx, activity)
    assert len(shown) == 2 and all(view["state"] == "checked" and "headings" not in view and "decides" not in view for view in shown)
    # Reopened under this build: checked by v2's own check and drawn as before.
    assert turn.validate_activity(activity, ctx, elements) == activity
    refused(activity, ctx, elements, lambda forged: forged["sections"][0]["case"].update(checked="unchecked"))
