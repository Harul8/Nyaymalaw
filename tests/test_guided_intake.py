"""Plan AN.62-AN.64 (owner decisions D310-D312, D327, D328) through the HTTP API: a new matter worked step by step is taken through
guided intake before any research. NM reads back what it understood, with where each point is found, and shows no board yet; asks
whom the advocate acts for where no message of theirs says so, and takes it only in their own words; offers to set out the disputes;
proposes them on the board; and researches nothing until the advocate confirms them as they were shown. Moving between these stops
runs no step and calls no model. A message at a guided stop is read with the whole matter; End to end and Done stay open; a
follow-up is not taken through intake again. Offline: the scripted served application; the words are invented; not browser QA."""
from nm.core_engine import message_reader, steps
from nm.core_engine.conversation import chat_matter_id, shown_of, stored_chat
from tests.guided import ACTS_FOR, intake
from tests.served_application import OWNER
from tests.test_a_follow_up_starts_from_the_last_understanding import reader_says
from tests.test_a_message_while_a_matter_waits import Reader, judged, reading
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_research import understanding

CHAT = stored_chat(OWNER, None, "turn-1")
STATED = {"message": f"{ACTS_FOR} Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
UNSTATED = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
#: The advocate's words saying whom they act for, as code finds them in their message (research.acting_for).
THEIR_WORDS = ACTS_FOR.rstrip(".")


def sent(served, body=STATED):
    scripted_answers(served, Scripted())
    reply = served.client.post("/api/turn", json=body)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    return stop(served)


def stop(served):
    return served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]["waiting"]


def move(card):
    found, = [go for go in card["gos"] if go["choice"] in steps.MOVES]
    return found


def guide(served, card, **over):
    """The stop's own move pressed as the page presses it, bound to the stop shown (over: what a stale or altered page would send)."""
    go = move(card)
    body = {"chat_id": CHAT, "turn_id": "turn-1", "choice": go["choice"], "at": card["at"],
            **({"disputes": go["disputes"]} if go["disputes"] else {}), **over}
    return served.client.post("/api/turn/guide", json=body)


def go(served, choice, disputes=None):
    return served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": choice,
                                                    **({"disputes": disputes} if disputes else {})})


def say(served, words):
    return served.client.post("/api/turn/message", json={"chat_id": CHAT, "turn_id": "turn-1", "message": words})


def board(served):
    return served.client.get(f"/api/chats/{CHAT}/board").json()


def held(served):
    return shown_of(served.store.load(chat_matter_id(OWNER, CHAT)))


def counted(served):
    """Every model call the served application makes from now on, by operation."""
    calls, first = [], served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        calls.append(prompt.operation)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    return calls


def test_a_new_matter_first_reads_back_what_nm_understood_and_shows_no_board_yet(served):
    card = sent(served)
    assert card["after"] == steps.READ and card["done_said"] == steps.GUIDED_SAID[steps.READ][0]
    assert [option["choice"] for option in card["gos"]] == ["right", "end_to_end", "done"]
    assert move(card)["tentative"] is None, "a move runs no step: there is no time to estimate"
    read = card["read_back"]
    assert read["state"] == "ready" and read["summary"] == understanding()["summary"]
    assert [party["who"] for party in read["parties"]] == ["client"]
    fact, = read["facts"]
    assert fact["id"] == "F1" and fact["from"] == "advocate", "each fact with where its words are found"
    assert board(served)["state"] == "empty", "no board until NM proposes the disputes (D327)"
    assert held(served)["steps"]["parts"] == {}, "nothing researched"
    listed = served.client.get("/api/work").json()["chats"]
    assert [chat.get("waiting") for chat in listed] == [steps.WAITING_SAID[steps.READ]]


def test_moving_through_the_guided_stops_runs_no_step_and_calls_no_model(served):
    card = sent(served)
    calls = counted(served)
    seen = []
    while card["after"] in steps.GUIDED:
        seen.append(card["after"])
        reply = guide(served, card)
        assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
        assert reply.json()["detail"]["kept"] is True
        card = stop(served)
    assert seen == [steps.READ, steps.OFFER, steps.PROPOSED], "the advocate's message said whom they act for: no client stop"
    assert card["after"] == "understood" and calls == []
    assert held(served)["steps"]["parts"] == {}, "confirming the disputes researches nothing by itself"


def test_whom_the_advocate_acts_for_in_their_own_words_spares_the_question(served):
    guide(served, sent(served))
    card = stop(served)
    assert card["after"] == steps.OFFER and card["client"] == [{"who": "client", "words": THEIR_WORDS}]
    assert "read_back" in card and board(served)["state"] == "empty"


def test_nm_asks_whom_the_advocate_acts_for_where_no_message_says_so_and_takes_it_in_their_words(served):
    guide(served, sent(served, UNSTATED))
    card = stop(served)
    assert card["after"] == steps.CLIENT and card["parties"] == ["client"] and card["client"] == []
    assert [option["choice"] for option in card["gos"]] == ["end_to_end", "done"], "only the advocate's words settle it"
    assert board(served)["state"] == "empty"
    reading(served, Reader(judged(kind="information", said="Taken as whom you act for.")))
    reply = say(served, ACTS_FOR)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    card = stop(served)
    assert card["after"] == steps.OFFER and card["client"] == [{"who": "client", "words": THEIR_WORDS}]
    assert card["heard"][-1]["text"] == ACTS_FOR and card["heard"][-1]["said"].endswith("NM reads the matter again with it.")


def test_what_the_advocate_adds_at_the_read_back_is_read_with_the_whole_matter(served):
    sent(served)
    reading(served, Reader(judged(kind="correction", said="Taken as a correction.")))
    calls = counted(served)
    reply = say(served, "The account was opened in the other branch.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    assert "core_research_understand" in calls, "understood again with the advocate's words"
    card = stop(served)
    assert card["after"] == steps.READ, "the read-back again, of what NM now understands"
    assert board(served)["state"] == "empty"


def test_the_disputes_are_proposed_on_the_board_and_confirmed_only_as_shown(served):
    card = sent(served)
    guide(served, card)
    card = stop(served)
    assert card["after"] == steps.OFFER and board(served)["state"] == "empty"
    guide(served, card)
    card = stop(served)
    assert card["after"] == steps.PROPOSED and "read_back" not in card
    assert [dispute["id"] for dispute in board(served)["disputes"]] == ["D1", "D2"], "proposed on the board"
    assert card["disputes"] == [{"id": "D1", "name": "Dispute 1", "confirmed": False},
                                {"id": "D2", "name": "Dispute 2", "confirmed": False}]
    assert move(card)["disputes"] == ["D1", "D2"]
    stale = guide(served, card, at="2000-01-01T00:00:00+00:00")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "not_offered", "bound to the stop shown"
    assert guide(served, card, disputes=["D1"]).json()["detail"]["code"] == "not_offered", "bound to the disputes shown"
    assert go(served, "research").json()["detail"]["code"] == "not_offered", "nothing researched before they are confirmed"
    assert stop(served)["after"] == steps.PROPOSED
    assert guide(served, card).json()["detail"]["code"] == "waiting"
    card = stop(served)
    assert card["after"] == "understood" and [option["choice"] for option in card["gos"]][:2] == ["research", "research"]
    assert set(held(served)["go"]["guided"]["confirmed"]) == {"D1", "D2"}


def test_a_guided_go_ahead_its_stop_does_not_offer_is_refused(served):
    card = sent(served)
    for choice in ("identify", "confirm"):
        reply = served.client.post("/api/turn/guide",
                                   json={"chat_id": CHAT, "turn_id": "turn-1", "choice": choice, "at": card["at"]})
        assert reply.status_code == 409 and reply.json()["detail"]["code"] == "not_offered", choice
    assert go(served, "research").json()["detail"]["code"] == "not_offered"
    other = served.client.post("/api/turn/guide", json={"chat_id": CHAT, "turn_id": "turn-9", "choice": "right", "at": card["at"]})
    assert other.json()["detail"]["code"] == "not_waiting"
    assert stop(served)["after"] == steps.READ


def test_a_go_ahead_in_words_at_a_guided_stop_moves_it_without_a_step(served):
    sent(served)
    reading(served, Reader(judged(kind="go", choice="right", said="Taken as: that is right.")))
    calls = counted(served)
    reply = say(served, "Yes, that is the matter.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    assert calls == [message_reader.OPERATION], "the reader alone: the move runs no step"
    card = stop(served)
    assert card["after"] == steps.OFFER and card["heard"][-1]["text"] == "Yes, that is the matter."


def test_end_to_end_at_a_guided_stop_works_the_matter_through_on_nms_own_understanding(served):
    card = sent(served)
    end, = [option for option in card["gos"] if option["choice"] == "end_to_end"]
    assert end["said"] == steps.GUIDED_END_SAID
    reply = go(served, "end_to_end")
    assert reply.status_code == 200, reply.text
    assert reply.json()["committed"] == "committed"


def test_a_follow_up_is_not_taken_through_guided_intake_again(served):
    sent(served)
    assert go(served, "done").status_code == 200, "Done at the read-back saves the matter as it stands"
    reader_says(served, {"kind": "changes_matter", "new_questions": [], "said": "Your message adds a second account."})
    reply = served.client.post("/api/turn", json={"message": "Look at the second account too.", "chat_id": CHAT,
                                                  "turn_id": "turn-2", "steps": "interactive"})
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    record = held(served)
    assert record["turn_id"] == "turn-2" and steps.waiting_of(record) == "understood" and "guided" not in record["go"]


def test_a_message_that_asks_to_be_worked_straight_through_is_not_guided(served):
    scripted_answers(served, Scripted())
    served.model.way, served.model.way_reading = "end_to_end", "Work the whole matter through."
    reply = served.client.post("/api/turn", json=STATED)
    assert reply.status_code == 200, reply.text


def test_after_intake_one_chosen_dispute_is_researched_then_analysed_and_the_next_is_offered(served):
    """Plan AN.65-AN.66 (D313, D314) after guided intake: the advocate's chosen dispute is researched alone, then its analysis -
    with the account of what the client must prove, what to get and what the other side relies on (the case step) - is written
    for it alone; the stop after it offers the other dispute and the finish, and calls no model."""
    sent(served)
    assert intake(served.client, CHAT)["after"] == "understood"
    calls = counted(served)
    assert go(served, "research", ["D1"]).json()["detail"]["code"] == "waiting"
    assert set(held(served)["steps"]["parts"]) == {"D1"} and stop(served)["after"] == "researched"
    assert not [operation for operation in calls if operation.startswith("core_case")], "no analysis before its go-ahead"
    researched = len(calls)
    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"
    assert "core_response_writer" in calls[researched:], "the analysis written"
    card = stop(served)
    assert card["after"] == "written"
    assert card["disputes"] == [{"id": "D1", "name": "Dispute 1", "researched": True, "written": True},
                                {"id": "D2", "name": "Dispute 2", "researched": False, "written": False}]
    offered = [(option["choice"], option["disputes"]) for option in card["gos"]]
    assert ("research", ["D2"]) in offered and ("done", None) in offered, "the next dispute offered, or the finish"
    shown = len(calls)
    stop(served)
    assert len(calls) == shown, "the stop and its offer call no model"
    answered = held(served)["steps"]["answered"]["sections"]
    assert [section.get("dispute_id") for section in answered] == ["D1"], "the other dispute untouched"
    # The case step (AN.35, D290, D291) is kept with the analysis: its account of what the client must prove, what to get and what
    # the other side relies on, for the chosen dispute alone.
    case, = [section["case"] for section in answered]
    assert case["dispute_id"] == "D1" and case["contract"].startswith("core_case")


def test_a_confirmation_stands_for_each_dispute_left_exactly_as_it_was_confirmed():
    """D312: a correction that changes one dispute leaves the others confirmed; the changed one waits to be confirmed again."""
    proposed = {"understood": {"plan": {"proposal": {"understanding": understanding(disputes=2)}}}}
    record = {"settled": [steps.READ, steps.OFFER], "client": [{"who": "client", "words": THEIR_WORDS}], "confirmed": {}}
    waiting = steps.waited({**steps.guided(steps.first()), "guided": record}, steps.PROPOSED)
    went = steps.given(waiting, "confirm", held={"go": waiting, "steps": proposed}, disputes=["D2", "D1"],
                       at=waiting["waiting"]["at"])
    assert steps.waiting_of({"go": went, "stopped": {"code": "waiting"}}) == "understood"
    corrected = understanding(disputes=2)
    corrected["disputes"][1]["name"] = "Dispute 2 as corrected"
    matter = {"understood": {"plan": {"proposal": {"understanding": corrected}}}}
    assert steps.unconfirmed(went, matter) == ["D2"] and steps.guided_stop(went, matter) == steps.PROPOSED
    held_again = {"go": steps.waited(went, steps.PROPOSED), "steps": matter, "stopped": {"code": "waiting"}}
    card = steps.card(held_again)
    assert card["disputes"] == [{"id": "D1", "name": "Dispute 1", "confirmed": True},
                                {"id": "D2", "name": "Dispute 2 as corrected", "confirmed": False}]
    assert "Those marked as confirmed stand as you confirmed them" in card["next_said"]


def test_the_board_is_withheld_only_before_the_disputes_are_proposed():
    """D327: while the matter waits at the read-back, whom the advocate acts for or the offer - or is worked on before the offer is
    settled - there is no board; once NM proposes the disputes there is, and a matter outside guided intake always has one."""
    base = steps.guided(steps.first())
    working = {"go": {**base, "guided": {**base["guided"], "settled": [steps.READ]}}}
    assert steps.board_withheld(working)
    offered = {"go": {**base, "guided": {**base["guided"], "settled": [steps.READ, steps.OFFER]}}}
    assert not steps.board_withheld(offered)
    for after, withheld in ((steps.READ, True), (steps.CLIENT, True), (steps.OFFER, True), (steps.PROPOSED, False),
                            ("understood", False)):
        assert steps.board_withheld({"go": steps.waited(base, after), "stopped": {"code": "waiting"}}) is withheld, after
    assert not steps.board_withheld({"go": steps.first()})
