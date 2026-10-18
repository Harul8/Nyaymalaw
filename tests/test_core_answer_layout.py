"""The answer laid out as the readability design shows it (owner, 18 Oct 2026: "exactly the
way your artifact has presented"; rendering v14): each dispute's time limits close its own
part, a limit no part names follows "In short", and every question to the advocate is
gathered at the end under "What I need from you" - from each part that shows something
else of its own, so no part is left a bare heading. Scripted fixtures exercise the layout
and its exact replay; they do not show how a real writer divides its work."""
import pytest

from nm.core_engine import research_note, response_rendering, turn
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
        "SUMMARY", "WORKING", "WORKING", "LAW", "WORKING", "NEEDS", "QUESTION"]
    assert [elements[i]["text"] for i in (1, 2, 4)] == [
        "Last day to file the complaint", "A period misquoted", "Last day for the drawer to pay"]
    assert (elements[5]["text"], elements[6]["text"]) == ("What I need from you", ASK)
    # Each paragraph still names its own draft paragraph; the heading names none.
    saved, = rows(store, reply)
    draft = saved["activities"]["draft"]
    assert saved["activities"]["rendering_contract"] == response_rendering.CONTRACT == "core_response_rendering_v16"
    assert draft["units"][response_rendering.unit_index(elements, 6)]["text"] == ASK
    with pytest.raises(IndexError):
        response_rendering.unit_index(elements, 5)
    # The research note heads the questions as the answer does.
    note = research_note.note(saved, prepared_for="Owner")
    assert [block for block in note["blocks"] if block["kind"] == "heading"] == [
        {"kind": "heading", "text": "What I need from you"}]


def test_a_part_showing_nothing_else_keeps_its_question_and_unnamed_limits_follow_in_short(store):
    reply = calculated(store, Laid(names=(), law=False))
    assert [(element["kind"], element["text"]) for element in reply["elements"]] == [
        ("SUMMARY", SUMMARY), ("WORKING", "Last day for the drawer to pay"),
        ("WORKING", "Last day to file the complaint"), ("WORKING", "A period misquoted"), ("QUESTION", ASK)]


def test_an_earlier_rendering_replays_in_its_own_layout(store):
    reply = calculated(store, Laid())
    saved, = rows(store, reply)
    activity = saved["activities"]
    from nm.core_engine.turn import TurnContext
    matter = store.load(chat_matter_id("owner", reply["chat_id"]))
    context = TurnContext(matter, saved["chat_id"], saved["turn_id"], saved["message"], []).payload()
    earlier = response_rendering.render(context, activity["research"], activity["sources"], activity["draft"],
        activity["review"], execution=activity["execution"], authority_evidence=activity["authority_evidence"],
        contract=response_rendering.SECTIONS_CONTRACT, time_limits=activity["calculation"],
        held=activity["release"])
    # v13: the time limits after "In short", the question where it was written, no heading.
    assert [element["kind"] for element in earlier] == ["SUMMARY", "WORKING", "WORKING", "WORKING", "LAW", "QUESTION"]
    assert turn.validate_activity({**activity, "rendering_contract": response_rendering.SECTIONS_CONTRACT},
                                  context, earlier)["rendering_contract"] == response_rendering.SECTIONS_CONTRACT
