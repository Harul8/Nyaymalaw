"""Plan AN.58 (D287, 17 Nov 2026; the owner's D269): every message is worked step by step unless it asks otherwise. A message sent
step by step is read once by the model, as its work begins and after it is saved, for how it asks to be worked. One read as asking
for the work end to end, or for one specific thing, is worked straight through, and code says so on the turn's record - its own
words first, the model's reading after them, marked; one read as step by step, or whose reading fails or cannot be admitted, stops
after the understanding as before. A go-ahead and a message sent without steps are never read for it. Offline: the scripted served
application and scripted readers - no claim about how the real model reads real messages; not browser QA."""
import pytest

from nm.core_engine import message_reader, shown_words, steps as stepwise
from nm.core_engine.conversation import chat_matter_id, shown_of, stored_chat
from nm.shared.model_port import Completion, ModelResult, ProviderUnavailable, Usage
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
CHAT = stored_chat(OWNER, None, "turn-1")
READING = "You want the account examined in one go."


def _records(monkeypatch):
    """Each go-ahead record the turn saves beside its conversation, in order."""
    from nm.core_engine import turn
    kept, real = [], turn.hold_shown

    def hold(store, context, held, **kwargs):
        kept.append(held.get("go"))
        return real(store, context, held, **kwargs)
    monkeypatch.setattr(turn, "hold_shown", hold)
    return kept


def test_a_message_read_as_step_by_step_stops_after_the_understanding_and_is_read_once(served):
    scripted = Scripted()
    scripted_answers(served, scripted)
    sent = served.client.post("/api/turn", json=SENT)
    assert sent.status_code == 409 and sent.json()["detail"]["code"] == "waiting"
    assert [asked["new_message"] for asked in served.model.ways] == [SENT["message"]]
    assert "way" not in served.client.get(f"/api/chats/{CHAT}").json()["pending"]
    assert not scripted.payloads("core_response_writer")
    # A go-ahead runs its step without reading the message again.
    went = served.client.post("/api/turn/go", json={
        "chat_id": CHAT, "turn_id": "turn-1", "choice": "research",
    })
    assert went.status_code == 409 and len(served.model.ways) == 1


@pytest.mark.parametrize("how", stepwise.WAYS)
def test_a_message_that_asks_otherwise_is_worked_straight_through_and_code_says_so(served, monkeypatch, how):
    scripted = Scripted()
    scripted_answers(served, scripted)
    served.model.way, served.model.way_reading = how, READING
    kept = _records(monkeypatch)
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 200, reply.text
    assert reply.json()["committed"] == "committed" and scripted.payloads("core_response_writer")
    # The message was saved first, as its first step; then, read, as worked straight through - code's words, the reading after.
    assert kept[0] == stepwise.first()
    said = f"{message_reader.WAY_SAID[how]} {shown_words.MARK} {READING}"
    assert kept[1] == {**stepwise.first(), "allowed": list(stepwise.STEPS), "way": {"how": how, "said": said}}
    assert all(go == kept[1] for go in kept[1:])
    # The reading is one of the turn's own calls, metered with it; no step's time was said, so none is kept.
    assert [call["operation"] for call in reply.json()["metrics"]["calls"]].count(message_reader.WAY_OPERATION) == 1
    assert "steps_timed" not in reply.json()["metrics"]


def test_a_fresh_research_only_route_saves_every_dispute_and_pauses(served, monkeypatch):
    scripted = Scripted()
    scripted_answers(served, scripted)
    requested = {**SENT, 'message': 'Research the law on both disputes and show me the authorities before analysis.'}
    readings = []

    def way(_calls, message, **_context):
        readings.append(message)
        return {'how': 'research_all', 'said': ''}

    monkeypatch.setattr(message_reader, 'way', way)
    reply = served.client.post('/api/turn', json=requested)
    assert reply.status_code == 409 and reply.json()['detail']['code'] == 'waiting'
    assert readings == [requested['message']]
    held = shown_of(served.store.load(chat_matter_id(OWNER, CHAT)))
    assert held['go']['allowed'] == ['understand', 'research']
    assert set(held['steps']['parts']) == {'D1', 'D2'} and held['steps']['answered'] is None
    assert not scripted.payloads('core_response_writer')

    reopened = served.login().get(f'/api/chats/{CHAT}').json()
    card = reopened['pending']['stopped']['waiting']
    assert card['after'] == 'researched'
    assert [(item['id'], item['researched'], item['written']) for item in card['disputes']] == [
        ('D1', True, False), ('D2', True, False),
    ]
    assert readings == [requested['message']]


def test_the_page_is_told_how_a_message_worked_straight_through_asked_for_it(served):
    # The review refused part-way: the turn stops with what it finished kept, and its record is what the page reads.
    scripted_answers(served, Scripted(refuse={"core_response_review"}))
    served.model.way, served.model.way_reading = "specific", "I have saved the account and will file it."
    stopped = served.client.post("/api/turn", json=SENT)
    assert stopped.status_code == 403, stopped.text
    pending = served.client.get(f"/api/chats/{CHAT}").json()["pending"]
    # A reading that claims something was or will be done is left out whole: code's words stand alone.
    assert pending["way"] == message_reader.WAY_SAID["specific"]


def test_a_reading_that_fails_leaves_the_message_step_by_step(served):
    scripted_answers(served, Scripted())
    inner = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == message_reader.WAY_OPERATION:
            raise ProviderUnavailable("Synthetic provider outage")
        return inner(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    sent = served.client.post("/api/turn", json=SENT)
    assert sent.status_code == 409 and sent.json()["detail"]["code"] == "waiting"


def test_the_way_reader_receives_the_complete_saved_conversation_in_order(served):
    from nm.core_engine import follow_up

    inner = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == follow_up.OPERATION:
            return ModelResult(None, {'kind': 'changes_matter', 'new_questions': [], 'said': ''},
                               tier, 'synthetic', 'fixture', Usage(1, 1, 0), 0,
                               completion=Completion.COMPLETE)
        return inner(prompt, schema, tier, **kwargs)

    served.model.structured = structured
    previous = [
        'Please keep any work on the deposit separate from the rent review.',
        'The client received the letter on Monday.',
        'There are two signatures on the agreement.',
        'The second letter came from the agent.',
        'The premises are still occupied.',
        'The lease remains in force.',
    ]
    chat_id = None
    for index, text in enumerate(previous, 1):
        sent = served.client.post('/api/turn', json={
            'chat_id': chat_id, 'turn_id': f'history-{index}', 'message': text,
        })
        assert sent.status_code == 200, sent.text
        chat_id = sent.json()['chat_id']
    saved = served.client.get(f'/api/chats/{chat_id}').json()['turns']
    latest = 'Now proceed within the limits I set at the beginning.'
    pending = served.client.post('/api/turn', json={
        'chat_id': chat_id, 'turn_id': 'read-full-scope', 'message': latest, 'steps': 'interactive',
    })
    assert pending.status_code == 409 and pending.json()['detail']['code'] == 'waiting'
    request, = served.model.ways
    assert request['new_message'] == latest
    expected = [entry for row in saved for entry in (
        f"advocate (original_account)\n{row['message']}",
        'nm (nm_interpretation)\n' + '\n\n'.join(item['text'] for item in row['elements']),
    )]
    assert request['earlier_messages_in_this_conversation'] == expected


def test_a_message_sent_without_steps_is_not_read_for_its_way(served):
    scripted_answers(served, Scripted())
    reply = served.client.post("/api/turn", json={"message": SENT["message"], "turn_id": "turn-1"})
    assert reply.status_code == 200 and not getattr(served.model, "ways", [])


class Reader:
    """A scripted reader of a message's way: its answers in order, and the prompts it was given."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        self.prompts.append(prompt)
        return ModelResult(None, self.answers.pop(0), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def test_a_way_that_cannot_be_admitted_is_asked_once_more_then_taken_as_step_by_step():
    import json
    reader = Reader({"way": "sideways", "said": ""}, {"way": "all of it", "said": ""})
    assert message_reader.way(reader, "Do it.", earlier=["Read the deed."], papers=1) == {"how": "steps", "said": ""}
    again = json.loads(reader.prompts[1].user)
    assert again["your_last_answer"] == {"way": "sideways", "said": ""} and "end_to_end" in again["why_it_cannot_be_taken"]
    assert json.loads(reader.prompts[0].user) == {"earlier_messages_in_this_conversation": ["Read the deed."],
                                                  "papers_sent_with_it": 1, "new_message": "Do it."}
    # Admitted at the second look.
    second = Reader({"way": "", "said": ""}, {"way": "end_to_end", "said": "You asked for it all at once."})
    assert message_reader.way(second, "Do it all.") == {
        "how": "end_to_end", "said": f"{message_reader.WAY_SAID['end_to_end']} {shown_words.MARK} You asked for it all at once."}


def test_only_a_messages_first_go_ahead_is_worked_straight_through():
    assert stepwise.opening(stepwise.first())
    through = stepwise.straight(stepwise.first(), "specific", "Code's words.")
    assert stepwise.valid(through) and not stepwise.opening(through)
    assert stepwise.attempt_part(through) == stepwise.attempt_part(stepwise.first()), "the same attempt as the first step"
    for go, how, said in ((through, "specific", "Words."), (stepwise.first(), "steps", "Words."), (stepwise.first(), "specific", " "),
                          ({**stepwise.first(), "n": 2}, "end_to_end", "Words.")):
        with pytest.raises(ValueError):
            stepwise.straight(go, how, said)
    assert not stepwise.valid({**through, "way": {"how": "steps", "said": "Words."}})
    gate = stepwise.Gate(stepwise.first())
    gate.through(through)
    assert gate.end_to_end and not gate.asks()
