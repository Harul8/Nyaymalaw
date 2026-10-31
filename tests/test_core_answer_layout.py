"""The answer laid out as the readability design shows it (owner, 18 Oct 2026: "exactly the
way your artifact has presented"; rendering v14): each dispute's time limits close its own
part, a limit no part names follows "In short", and every question to the advocate is
gathered at the end under "What I need from you" - from each part that shows something
else of its own, so no part is left a bare heading. From turn v8 (owner decisions P39-P45,
24 Oct 2026) a live answer is laid out as rendering v18: "In short" first, each dispute's time
limits closing its section and those no section names after the sections. Scripted fixtures
exercise the layout and its exact replay; they do not show how a real writer divides its work."""
import pytest

from nm.core_engine import answer_sections, research_note, response_rendering, turn
from nm.core_engine.conversation import chat_matter_id
from tests.test_core_calculation import Calculating, chain, turn as calculated
from tests.test_core_turn import store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a
SUMMARY = "File the complaint in time; I need the cheque's date."
ASK = "When is the cheque dated?"


class Laid(Calculating):
    """The writer opens its part with a summary, keeps its law paragraph (unless told to
    write only the summary and the question), asks one question and names the time limits
    given (T1: paying, T2: the complaint, T3: the one not assessed)."""
    def __init__(self, names=("T1",), law=True):
        super().__init__(chain())
        self.names, self.law = list(names), law

    def structured(self, prompt, schema, tier, **kwargs):
        result = super().structured(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_response_writer":
            kept = result.data["units"] if self.law else []
            result.data["units"] = [{"kind": "summary", "text": SUMMARY, "uses": []}, *kept,
                                    {"kind": "question", "text": ASK, "uses": []}]
            result.data["time_limit_ids"] = list(self.names)
        return result


def rows(store, reply):
    return turn.saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")


def test_a_disputes_time_limits_close_its_part_and_the_questions_end_the_answer(store):
    reply = calculated(store, Laid())
    elements = reply["elements"]
    assert [element["kind"] for element in elements] == [
        "IN_SHORT", "ROW", "ROW_ACTION", "ADVICE", "WORKING", "WORKING", "WORKING", "NEEDS", "ASK"]
    assert elements[2]["text"] == SUMMARY
    # The limit the section names closes it; those it does not name stand outside the sections.
    assert [(elements[i]["text"], elements[i].get("outside")) for i in (4, 5, 6)] == [
        ("Last day for the drawer to pay", None), ("Last day to file the complaint", True),
        ("A period misquoted", True)]
    assert (elements[7]["text"], elements[8]["text"]) == ("What I need from you", ASK)
    # Each paragraph still names its own draft paragraph, in its own section from turn v6
    # (answered dispute by dispute, 19 Oct 2026); the heading names none.
    saved, = rows(store, reply)
    assert saved["activities"]["rendering_contract"] == response_rendering.REPAIRED_CONTRACT
    draft = answer_sections.piece_of(saved["activities"], elements[8]["section"])["draft"]
    assert draft["units"][response_rendering.unit_index(elements, 8)]["text"] == ASK
    with pytest.raises(IndexError):
        response_rendering.unit_index(elements, 7)
    # The research note heads the questions as the answer does.
    note = research_note.note(saved, prepared_for="Owner")
    assert [block for block in note["blocks"] if block["kind"] == "heading"] == [
        {"kind": "heading", "text": "In short"}, {"kind": "heading", "text": "What I need from you"}]


def test_a_section_showing_only_its_row_keeps_its_question_and_unnamed_limits_follow_the_sections(store):
    reply = calculated(store, Laid(names=(), law=False))
    assert [(element["kind"], element["text"]) for element in reply["elements"]] == [
        ("IN_SHORT", "In short"), ("ROW", "Dispute 1"), ("ROW_ACTION", SUMMARY),
        ("WORKING", "Last day for the drawer to pay"), ("WORKING", "Last day to file the complaint"),
        ("WORKING", "A period misquoted"), ("NEEDS", "What I need from you"), ("ASK", ASK)]


def test_an_earlier_rendering_replays_in_its_own_layout(store):
    # A turn as saved before 19 Oct 2026 (turn v5), shown under v13's layout.
    from nm.core_engine.conversation import open_turn
    from tests import core_whole_answer
    from tests.test_core_calculation import MESSAGE, Held
    from tests.test_core_turn import searcher
    context = open_turn(store, advocate_id="owner", message=MESSAGE, turn_id="t1").payload()
    _, activity, _ = core_whole_answer.prepare(Laid(), context, searcher(), held_acts=Held())
    earlier = response_rendering.render(context, activity["research"], activity["sources"], activity["draft"],
        activity["review"], execution=activity["execution"], authority_evidence=activity["authority_evidence"],
        contract=response_rendering.SECTIONS_CONTRACT, time_limits=activity["calculation"],
        held=activity["release"])
    # v13: the time limits after "In short", the question where it was written, no heading.
    assert [element["kind"] for element in earlier] == ["SUMMARY", "WORKING", "WORKING", "WORKING", "LAW", "QUESTION"]
    assert turn.validate_activity({**activity, "rendering_contract": response_rendering.SECTIONS_CONTRACT},
                                  context, earlier)["rendering_contract"] == response_rendering.SECTIONS_CONTRACT
