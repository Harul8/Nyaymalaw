"""A message sent while a matter waits for the advocate (plan AN.48, piece 48c; owner decisions D146, D158, D161): the message reader
judges what it is - a go-ahead, information, a correction, a rethink, a new question, or unclear - and code admits a go-ahead only as
one the stop offers, for the matter's disputes. A go-ahead runs its step; information, a correction or a rethink joins the matter as
the advocate's words and the matter is understood again with them; a new question waits as the next message; an unclear one is asked
about; a reader that cannot be reached loses no message. NM says how it took each. Offline: scripted models; the words are invented."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.core_engine import message_reader, steps
from nm.core_engine.conversation import HEADER, chat_matter_id, checked_rows, digest, queued_of, shown_of, stored_chat
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from nm.shared.budget_contracts import Completion
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture

SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1", "steps": "interactive"}
CHAT = stored_chat(OWNER, None, "turn-1")


def judged(**out):
    base = {"kind": "unclear", "choice": None, "disputes": [], "critical": False, "corrects": "", "said": "", "ask": ""}
    return {**base, **out}


class Reader:
    """A stand-in reader: each call returns the next judgement given, and keeps what it was asked."""

    def __init__(self, *judgements):
        self.judgements, self.asked = list(judgements), []

    def answer(self, prompt, schema, tier):
        self.asked.append(json.loads(prompt.user))
        out = self.judgements.pop(0)
        if isinstance(out, Exception):
            raise out
        return ModelResult(None, out, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def reading(served, reader):
    """The served model answers the message reader's calls from reader; every other call as before."""
    first = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == message_reader.OPERATION:
            return reader.answer(prompt, schema, tier)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured


def waiting_matter(served):
    scripted_answers(served, Scripted())
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"


def say(served, words):
    return served.client.post("/api/turn/message", json={"chat_id": CHAT, "turn_id": "turn-1", "message": words})


def held(served):
    return shown_of(served.store.load(chat_matter_id(OWNER, CHAT)))


def test_a_go_ahead_in_words_runs_its_step_for_the_dispute_named(served):
    waiting_matter(served)
    reader = Reader(judged(kind="go", choice="research", disputes=["D1"], said="Taken as your go-ahead to research D1."))
    reading(served, reader)
    reply = say(served, "Go ahead with the first dispute.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"
    record = held(served)
    assert set(record["steps"]["parts"]) == {"D1"} and steps.waiting_of(record) == "researched"
    assert record["go"]["heard"][-1]["text"] == "Go ahead with the first dispute."
    card = served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]["waiting"]
    # Plan AN.51 (51b, D196): code's own sentence first; the reader's wording after it, marked.
    assert card["heard"][-1]["said"] == "Taken as your go-ahead. NM's reading: Taken as your go-ahead to research D1."
    seen = reader.asked[0]
    assert seen["new_message"] == "Go ahead with the first dispute."
    assert [d["id"] for d in seen["where_the_matter_stands"]["disputes"]] == ["D1", "D2"]


def test_a_go_ahead_the_stop_does_not_offer_is_asked_again_then_taken_as_unclear(served):
    waiting_matter(served)
    wrong = judged(kind="go", choice="write", disputes=["D1"], said="Writing D1.")  # not researched yet
    reader = Reader(wrong, wrong)
    reading(served, reader)
    reply = say(served, "Write it up.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard"
    assert reply.json()["detail"]["heard"]["taken"] == "unclear"
    assert "why_it_cannot_be_taken" in reader.asked[1], "told why, once"
    assert steps.waiting_of(held(served)) == "understood" and held(served)["steps"]["parts"] == {}


@pytest.mark.parametrize(('choice', 'disputes'), [('research', []), ('end_to_end', ['D1'])])
def test_a_reading_with_unresolved_scope_never_starts_whole_matter_work(served, choice, disputes):
    waiting_matter(served)
    proposal = judged(kind='go', choice=choice, disputes=disputes)
    reader = Reader(proposal, proposal)
    reading(served, reader)
    calls = list(served.model.calls)

    original = 'Take this dispute through, please.'
    reply = say(served, original)
    assert reply.status_code == 409 and reply.json()['detail']['heard']['taken'] == 'unclear'
    assert len(reader.asked) == 2 and 'why_it_cannot_be_taken' in reader.asked[1]
    record = held(served)
    assert steps.waiting_of(record) == 'understood' and record['steps']['parts'] == {}
    assert record['go']['heard'][-1]['text'] == original
    assert served.model.calls == calls


def test_an_explicit_batch_research_message_stops_before_any_analysis(served):
    waiting_matter(served)
    reader = Reader(judged(kind='go', choice='research_all'))
    reading(served, reader)

    reply = say(served, 'Research the law on every dispute in this matter.')
    assert reply.status_code == 409 and reply.json()['detail']['code'] == 'waiting'
    record = held(served)
    assert set(record['steps']['parts']) == {'D1', 'D2'} and record['steps']['answered'] is None
    assert steps.waiting_of(record) == 'researched' and len(reader.asked) == 1
    assert {'choice': 'research_all', 'disputes': None, 'said': 'Research all disputes'} in (
        reader.asked[0]['where_the_matter_stands']['can_be_asked_for'])


def test_information_joins_the_matter_as_the_advocates_own_message_and_nothing_is_redone(served):
    """48h (D159) refines 48c: information is kept as the advocate's message after the latest one; the matter is not understood
    again for it."""
    waiting_matter(served)
    reader = Reader(judged(kind="information", disputes=["D2"], critical=True,
                           said="Taken as new information: the notice was served on 3 March."))
    reading(served, reader)
    calls_before = len(served.model.calls)
    reply = say(served, "The notice was served on 3 March.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard"
    record = held(served)
    assert [entry["text"] for entry in record["added"]] == ["The notice was served on 3 March."] and record["steers"] == []
    assert steps.waiting_of(record) == "understood" and record["go"]["heard"][-1]["taken"] == "information"
    assert len(served.model.calls) == calls_before, "nothing written yet to check: nothing is redone"


def test_a_rethink_joins_the_matter_as_the_advocates_words_and_it_is_understood_again(served):
    waiting_matter(served)
    reading(served, Reader(judged(kind="rethink", said="Taken as a request to rethink the matter.")))
    calls_before = len(served.model.calls)
    reply = say(served, "Look at this as a tenancy matter, not a sale.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"
    record = held(served)
    assert [steer["text"] for steer in record["steers"]] == ["Look at this as a tenancy matter, not a sale."]
    assert steps.waiting_of(record) == "understood" and record["go"]["heard"][-1]["taken"] == "rethink"
    understood_again = [name for name, _ in served.model.calls[calls_before:] if name == "core_research_understand"]
    assert understood_again, "the matter is understood again with the advocate's words"


def test_a_new_question_waits_as_the_next_message_and_nothing_runs(served):
    waiting_matter(served)
    reading(served, Reader(judged(kind="question", said="Taken as a new question; it waits until you finish this matter.")))
    reply = say(served, "What is the stamp duty in Pune?")
    assert reply.status_code == 409 and reply.json()["detail"] == {
        **reply.json()["detail"], "code": "heard", "kept": True,
        "heard": {"taken": "question", "said": "Taken as a new question; it waits until you finish this matter."}}
    assert queued_of(served.store.load(chat_matter_id(OWNER, CHAT))) == [
        {"text": "What is the stamp duty in Pune?", "documents": []}]
    assert steps.waiting_of(held(served)) == "understood"


def test_an_unclear_message_is_asked_about(served):
    waiting_matter(served)
    reading(served, Reader(judged(kind="unclear", said="I could not tell how you meant this.",
                                  ask="Is this a new fact for the lease dispute?")))
    reply = say(served, "Also the lease.")
    assert reply.json()["detail"]["heard"]["said"] == (
        "NM could not tell how you meant this message. NM's reading: I could not tell how you meant this. "
        "Is this a new fact for the lease dispute?")


def test_a_waiting_reply_is_read_with_the_exact_exchange_it_answers(served):
    waiting_matter(served)
    original = 'That action first, please.\nThe other dispute can wait.'
    question = 'Do you mean research the first dispute?'
    reply_words = 'Yes, that one.'
    reader = Reader(judged(kind='unclear', ask=question), judged(kind='go', choice='research', disputes=['D1']))
    reading(served, reader)

    first = say(served, original)
    nm_words = first.json()['detail']['heard']['said']
    assert nm_words.endswith(question) and held(served)['steps']['parts'] == {}
    assert served.login().get(f'/api/chats/{CHAT}').status_code == 200

    second = say(served, reply_words)
    payload = reader.asked[1]
    assert payload['new_message'] == reply_words
    assert payload['waiting_exchanges'] == [{'advocate': original, 'nm': nm_words}]
    assert len(reader.asked) == 2
    assert second.json()['detail']['code'] == 'waiting'
    assert set(held(served)['steps']['parts']) == {'D1'} and held(served)['steps']['answered'] is None


def test_a_reader_that_cannot_be_reached_loses_no_message(served):
    waiting_matter(served)
    reading(served, Reader(ProviderUnavailable("Synthetic outage")))
    reply = say(served, "Go ahead.")
    assert reply.status_code == 409 and reply.json()["detail"]["heard"]["taken"] == "unread"
    assert held(served)["go"]["heard"][-1]["text"] == "Go ahead."
    assert steps.waiting_of(held(served)) == "understood"


def test_reopening_a_long_wait_keeps_every_heard_message_in_order(served):
    waiting_matter(served)
    messages = ['Please keep the deposit separate.\nThis applies throughout.']
    messages += [f'Update {index}: same scope.' for index in range(1, 30)]
    messages += ['Please keep the deposit separate.\nThis applies throughout.', 'Last update.']
    reader = Reader(*(judged(kind='unclear', ask='Which step would you like?') for _ in messages))
    reading(served, reader)
    calls_before = list(served.model.calls)

    for words in messages:
        reply = say(served, words)
        assert reply.status_code == 409 and reply.json()['detail']['heard']['taken'] == 'unclear'

    record = held(served)
    assert [entry['text'] for entry in record['go']['heard']] == messages
    assert record['steps']['parts'] == {} and served.model.calls == calls_before
    reopened = served.login().get(f'/api/chats/{CHAT}').json()
    heard_again = reopened['pending']['stopped']['waiting']['heard']
    assert [entry['text'] for entry in heard_again] == messages
    assert len(reader.asked) == len(messages)


@pytest.mark.parametrize('finish', ['done', 'end_to_end'])
def test_finishing_keeps_the_waiting_words_and_replays_the_saved_response(served, finish):
    waiting_matter(served)
    reader = Reader(judged(kind='unclear', ask='Which step would you like?'),
                    judged(kind='go', choice=finish))
    reading(served, reader)
    first = 'Please leave the deposit for later.\nI will review it separately.'
    assert say(served, first).json()['detail']['heard']['taken'] == 'unclear'
    terminal = 'Save what we have.' if finish == 'done' else 'Finish the remaining work end to end.'
    result = say(served, terminal)
    assert result.status_code == 200 and result.json()['committed'] == 'committed'

    def saved():
        return served.store.load(chat_matter_id(OWNER, CHAT))

    assert shown_of(saved()) is None
    row, = checked_rows(saved(), OWNER)
    assert [entry['text'] for entry in row['waiting_messages']] == [first, terminal]
    assert [entry['taken'] for entry in row['waiting_messages']] == ['unclear', 'go']
    assert row['response']['elements'] == result.json()['elements']

    calls_before = list(served.model.calls)
    replay = served.login().post('/api/turn', json=SENT)
    assert replay.status_code == 200 and replay.json()['replayed'] is True
    assert replay.json()['elements'] == result.json()['elements']
    assert checked_rows(saved(), OWNER) == (row,)
    assert served.model.calls == calls_before and len(reader.asked) == 2

    # A matching digest cannot make a receipt with out-of-contract transcript fields readable.
    matter = saved()
    metadata = deepcopy(matter.intake_answers)
    row['waiting_messages'][0]['text'] = ''
    row['digest'] = digest({key: value for key, value in row.items() if key != 'digest'})
    metadata[HEADER]['tail_digest'] = row['digest']
    served.store.commit(replace(matter, brain_chat=(row,), intake_answers=metadata, version=matter.version + 1),
                        expected_version=matter.version)
    assert served.login().get(f'/api/chats/{CHAT}').status_code == 409


def test_a_message_is_taken_only_while_the_matter_waits(served):
    reply = say(served, "Go ahead.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "not_waiting"


def test_code_admits_only_the_matters_disputes_and_says_something_where_the_reader_did_not():
    plan = {"proposal": {"understanding": {"disputes": [{"id": "D1", "name": "Lease"}, {"id": "D2", "name": "Notice"}]}},
            "work": [{"id": "w1", "dispute": {"id": "D1"}}, {"id": "w2", "dispute": {"id": "D2"}}]}
    record = {"steps": {"understood": {"interpretation": {}, "plan": plan}, "limits": None, "parts": {}, "cases": {},
                        "answered": None},
              "go": steps.waited(steps.first(), "understood"), "stopped": {"code": "waiting", "at": "now"}}
    judgement, why = message_reader.admitted(judged(kind="information", disputes=["D9"]), record)
    assert judgement is None and "D9" in why
    judgement, _ = message_reader.admitted(judged(kind="information", disputes=["D2"], said=""), record)
    assert judgement["disputes"] == ["D2"] and judgement["said"] == message_reader.SAID["information"]
    judgement, _ = message_reader.admitted(judged(kind="go", choice="research", disputes=["D2"]), record)
    assert judgement["go"]["allowed"] == ["research"] and judgement["go"]["disputes"] == ["D2"]
    assert message_reader.admitted({"kind": "dance"}, record)[0] is None
