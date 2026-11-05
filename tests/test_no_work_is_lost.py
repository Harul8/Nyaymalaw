"""No work is ever lost (plan AN.41, D66-D73; owner, 4 Nov 2026: "they should be saved to history first and then processed further,
so that no work is ever lost"), and an answer stopped or steered while it is worked on (plan AN.42, D78-D79).

The message and its files are saved with the conversation before any AI work; each step's result as it finishes; an answer that
stops keeps all it finished, with why, for Continue or Discard; the same message sent again continues where it stopped, each saved
step checked as a saved answer is checked. Offline: scripted models and a synthetic store; the words are invented."""
import threading

import pytest

from nm.core_engine import turn
from nm.core_engine.calls import StopRequested
from nm.core_engine.conversation import ConversationRefused, chat_matter_id, shown_of, stored_chat
from nm.shared.external_ai_contracts import ModelPermissionRefused
from tests.test_core_answer_sections import Scripted, through_turns
from tests.test_core_turn import FileMatterStore, run


@pytest.fixture
def store(tmp_path):
    return FileMatterStore(tmp_path, key="synthetic-turn-fixture")


def held(store, turn_id="t1", chat_id=None):
    return shown_of(store.load(chat_matter_id("owner", stored_chat("owner", chat_id, turn_id))))


def written(scripted, dispute):
    return len(scripted.payloads("core_response_writer", dispute))


def test_the_message_and_its_files_are_saved_before_any_ai_work(store):
    model = through_turns(Scripted())
    first, seen = model.structured, {}

    def structured(prompt, schema, tier, **kwargs):
        seen.setdefault("held", held(store))  # what is saved when the first call is made
        return first(prompt, schema, tier, **kwargs)
    model.structured = structured
    run(store, model)
    saved = seen["held"]
    assert saved["message"] == "Hello." and saved["turn_id"] == "t1" and saved["elements"] == []
    assert saved["steps"]["understood"] is None and saved["steps"]["parts"] == {} and saved["stopped"] is None


def test_an_answer_that_stopped_continues_where_it_stopped(store):
    """D70: sent again, the message continues from what it finished - its understanding, research and sections - and only the
    overview, where it stopped, is written."""
    stopping = Scripted(refuse={"core_response_overview"})
    with pytest.raises(ModelPermissionRefused) as refused:
        run(store, through_turns(stopping))
    assert refused.value.kept
    assert written(stopping, "D1") == 1 and written(stopping, "D2") == 1
    going_on = Scripted()
    model = through_turns(going_on)
    research_calls = len(model.calls)
    response = run(store, model)
    assert response["committed"] == "committed" and held(store) is None
    assert written(going_on, "D1") == 0 and written(going_on, "D2") == 0, "sections finished are not written again"
    assert len(going_on.payloads("core_response_overview")) == 1
    assert len(model.calls) == research_calls, "neither the understanding nor the research is made again"
    assert not any(e["text"].startswith("NM stopped before") for e in response["elements"])


def test_a_saved_step_that_no_longer_passes_its_check_is_done_again(store):
    scripted = Scripted(refuse={"core_response_overview"})
    model = through_turns(scripted)  # the same scripted research both times
    with pytest.raises(ModelPermissionRefused):
        run(store, model)
    scripted.refuse.clear()
    before = {dispute: written(scripted, dispute) for dispute in ("D1", "D2")}
    # One dispute's saved research is changed on disk: it no longer passes the check a saved answer passes.
    matter = store.load(chat_matter_id("owner", stored_chat("owner", None, "t1")))
    record = dict(matter.intake_answers)
    record["core_shown"] = {**record["core_shown"]}
    record["core_shown"]["steps"] = {**record["core_shown"]["steps"],
                                     "parts": {**record["core_shown"]["steps"]["parts"],
                                               "D2": {**record["core_shown"]["steps"]["parts"]["D2"], "state": "forged"}}}
    from dataclasses import replace
    store.commit(replace(matter, intake_answers=record, version=matter.version + 1), expected_version=matter.version)
    response = run(store, model)
    assert response["committed"] == "committed"
    # The dispute whose research failed its check is researched and written again; the other is kept as it was shown.
    assert written(scripted, "D1") == before["D1"] and written(scripted, "D2") == before["D2"] + 1


def test_a_stop_keeps_what_was_finished_and_discard_saves_it_as_it_stopped(store):
    """D78, D69, D71: the advocate stops the answer; no further call is sent, every piece finished is kept with why; Discard saves
    the answer as it stopped, and reopened it is read exactly as saved."""
    asked = threading.Event()
    scripted = Scripted()
    model = through_turns(scripted)
    first = model.structured

    def structured(prompt, schema, tier, **kwargs):
        out = first(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_response_cross_check":
            asked.set()  # the advocate presses Stop once the sections are checked across
        return out
    model.structured = structured
    with pytest.raises(ConversationRefused) as refused:
        run(store, model, stopping=asked.is_set)
    assert refused.value.code == "stopped" and refused.value.kept and refused.value.status == 409
    assert not scripted.payloads("core_response_overview"), "no call is sent after the stop"
    stopped = held(store)
    assert stopped["stopped"]["code"] == "stopped" and len(stopped["steps"]["answered"]["sections"]) == 2
    matter = store.load(chat_matter_id("owner", stopped["request"]["chat_id"]))
    response = turn.discard(store, matter, "owner", "t1", session_current=lambda: True)
    assert response["service_status"].startswith(turn.STOPS["stopped"])
    assert response["elements"][0]["text"].startswith("NM stopped before finishing this answer.")
    rows = turn.saved_rows(store.load(matter.id), "owner")
    assert [row["turn_id"] for row in rows] == ["t1"] and held(store) is None


def test_a_message_stopped_before_anything_finished_is_saved_with_why_and_nothing_else(store):
    model = through_turns(Scripted())
    first = model.structured

    def structured(prompt, schema, tier, **kwargs):
        raise ModelPermissionRefused("External model permission is required.")
    model.structured = structured
    with pytest.raises(ModelPermissionRefused):
        run(store, model)
    stopped = held(store)
    assert stopped["steps"]["understood"] is None and stopped["stopped"]["code"] == "model_permission_required"
    model.structured = first
    matter = store.load(chat_matter_id("owner", stopped["request"]["chat_id"]))
    response = turn.discard(store, matter, "owner", "t1", session_current=lambda: True)
    assert response["elements"] == [] and response["service_status"].startswith(turn.STOPS["model_permission_required"])
    assert "your message and files are saved" in response["service_status"]
    row, = turn.saved_rows(store.load(matter.id), "owner")
    assert row["message"] == "Hello." and row["activities"] == {"contract": turn.UNANSWERED_CONTRACT}
    # A later message reads it as part of the conversation.
    later = run(store, through_turns(Scripted()), chat_id=stopped["request"]["chat_id"], turn_id="t2", message="And now?")
    assert later["committed"] == "committed"


def test_a_new_message_waits_while_another_of_the_conversation_is_worked_on(store):
    with pytest.raises(ModelPermissionRefused):
        run(store, through_turns(Scripted(refuse={"core_response_overview"})))
    chat_id = held(store)["request"]["chat_id"]
    with pytest.raises(ConversationRefused) as refused:
        run(store, through_turns(Scripted()), chat_id=chat_id, turn_id="t2", message="And now?",
            running=lambda turn_id: turn_id == "t1")
    assert refused.value.code == "turn_in_progress"
    assert held(store)["turn_id"] == "t1", "the answer being worked on is untouched"


def test_a_steer_goes_into_the_answer_being_worked_on_and_is_saved_with_it(store):
    """D79: a steer stops the answer after the step in progress and the answer goes on with it - the understanding made again
    from it, the research kept where the plan still asks the same, each section shown reviewed again against it."""
    steer = {"text": "Take the second notice into account too.", "documents": [], "at": "2026-11-05T10:00:00+00:00"}
    pressed, waiting = threading.Event(), [steer]
    scripted = Scripted()
    model = through_turns(scripted)
    first = model.structured

    def structured(prompt, schema, tier, **kwargs):
        out = first(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_response_cross_check" and waiting:
            pressed.set()
        return out
    model.structured = structured

    def steers():
        taken = list(waiting)
        waiting.clear()
        pressed.clear()
        return taken
    response = run(store, model, stopping=pressed.is_set, steers=steers)
    assert response["committed"] == "committed"
    reviews = [payload for name, payload in scripted.calls if name == "core_response_review"]
    assert any(steer["text"] in str(payload) for payload in reviews), "the review checks the answer against the steer"
    rows = turn.saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")
    assert rows[0]["steers"] == [steer] and rows[0]["message"] == "Hello."
    # Reopened, the turn is read exactly as saved; sent again, it is the saved answer.
    assert run(store, through_turns(Scripted()))["replayed"]


def test_a_stop_is_not_a_model_failure(store):
    """A stop is never answered with a note in a section's place: it ends the turn, keeping what was finished."""
    from nm.core_engine import answer_sections
    from nm.shared.model_port import ModelError
    assert not issubclass(StopRequested, ModelError) and StopRequested in answer_sections._STOP


def test_an_answer_stopped_in_the_earlier_form_continues_with_what_it_had_shown(store):
    """An answer that stopped before plan AN.41 was kept as what it had shown and the activity it came from (P27). Continue keeps
    that work too - checked as any saved step is - instead of starting again and losing what was shown."""
    from dataclasses import replace
    from nm.core_engine.conversation import TurnContext
    scripted = Scripted(refuse={"core_response_overview"})
    model = through_turns(scripted)
    with pytest.raises(ModelPermissionRefused):
        run(store, model)
    matter = store.load(chat_matter_id("owner", stored_chat("owner", None, "t1")))
    now = shown_of(matter)
    context = TurnContext(matter, now["request"]["chat_id"], "t1", now["message"], ()).payload()
    earlier = {key: now[key] for key in ("turn_id", "request", "message", "documents", "elements", "metrics", "at", "base_version")}
    earlier["activity"] = {**turn.activity_of(now, context), "waiting": []}
    store.commit(replace(matter, intake_answers={**matter.intake_answers, "core_shown": earlier}, version=matter.version + 1),
                 expected_version=matter.version)
    assert "steps" not in held(store) and held(store)["elements"]
    scripted.refuse.clear()
    before = {dispute: written(scripted, dispute) for dispute in ("D1", "D2")}
    response = run(store, model)
    assert response["committed"] == "committed"
    assert {dispute: written(scripted, dispute) for dispute in ("D1", "D2")} == before, "its sections are not written again"
    assert len(scripted.payloads("core_response_overview")) == 2  # the one refused before, and the one written now


def test_after_a_steer_the_sections_shown_stay_until_each_is_replaced_and_only_those_replaced_are_finished(store):
    """D79: "a section already shown is replaced once its rewrite passes" - the page goes on showing it meanwhile; what is kept as
    finished is only what was reviewed against the steer, so a Continue after a stop never passes the steer over."""
    steer = {"text": "Weigh the later notice too.", "documents": [], "at": "2026-11-05T10:00:00+00:00"}
    pressed, waiting, seen = threading.Event(), [steer], []
    scripted = Scripted()
    model = through_turns(scripted)
    first = model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_review" and steer["text"] in prompt.user:
            now = held(store)
            seen.append((len((now["steps"]["answered"] or {}).get("sections", ())),
                         [e["text"] for e in now["elements"] if e["kind"] == "HEADING"]))
        out = first(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_response_cross_check" and waiting:
            pressed.set()
        return out
    model.structured = structured

    def steers():
        taken = list(waiting)
        waiting.clear()
        pressed.clear()
        return taken
    assert run(store, model, stopping=pressed.is_set, steers=steers)["committed"] == "committed"
    # At the first review against the steer: nothing finished since it, both sections still shown.
    assert seen[0] == (0, ["Dispute 1: In short for D1.", "Dispute 2: In short for D2."])
    # Both sections are reviewed side by side; by the overview's review both are replaced and count as finished.
    assert seen[-1] == (2, ["Dispute 1: In short for D1.", "Dispute 2: In short for D2."])
    assert all(len(headings) == 2 for _, headings in seen), "neither section left the page while it was reviewed again"
