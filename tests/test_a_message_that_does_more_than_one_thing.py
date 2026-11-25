"""Plan AN.61 (61c, D309): a message sent while a matter waits that does more than one thing keeps each. A go-ahead that also gives
facts or corrections runs with the message joined to the matter as the advocate's own, the analyses already written owed a check
against it at the next run that writes or finishes (D161-D162); a new question outside the matter, asked beside the rest, waits as
the next message in the advocate's exact words, which code finds in the message; at a guided stop the matter is read again with what
is added and the go-ahead in the same message is not taken (D310, D312). Code says each. Offline: scripted models; the words are
invented - no claim about how the real model reads real messages; not browser QA."""
from nm.core_engine import message_reader, steps
from nm.core_engine.conversation import chat_matter_id, queued_of
from tests.served_application import OWNER
from tests.test_a_message_while_a_matter_waits import CHAT, Reader, held, judged, reading, say
from tests.test_a_specific_request_at_a_stop import waiting

FACT = "The notice reached them on the fourth. Go ahead with the first dispute."
QUESTION = "Separately, what is the court fee on a suit for possession?"


def queued(served):
    return queued_of(served.store.load(chat_matter_id(OWNER, CHAT)))


def test_a_go_ahead_that_also_gives_a_fact_runs_with_the_message_joined_to_the_matter(served):
    waiting(served)
    reading(served, Reader(judged(kind="go", choice="research", disputes=["D1"], adds=True, also_asks="", said="")))
    reply = say(served, FACT)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    record = held(served)
    assert set(record["steps"]["parts"]) == {"D1"} and steps.waiting_of(record) == "researched"
    assert [entry["text"] for entry in record["added"]] == [FACT]
    assert "recheck" not in record["go"], "nothing was written for it to be checked against"
    # With an analysis written, a later go-ahead's facts owe it a check at the next run that writes or finishes.
    reading(served, Reader(judged(kind="go", choice="write", disputes=["D1"])))
    assert say(served, "Write it up.").json()["detail"]["code"] == "waiting"
    assert "recheck" not in held(served)["go"] and [entry["text"] for entry in held(served)["added"]] == [FACT]
    reading(served, Reader(judged(kind="go", choice="research", disputes=["D2"], adds=True)))
    assert say(served, "They paid half in cash. Research the second dispute.").json()["detail"]["code"] == "waiting"
    record = held(served)
    assert set(record["steps"]["parts"]) == {"D1", "D2"} and record["go"].get("recheck") is True
    assert [entry["text"] for entry in record["added"]] == [FACT, "They paid half in cash. Research the second dispute."]


def test_a_new_question_asked_beside_a_go_ahead_waits_as_the_next_message_in_the_advocate_s_words(served):
    waiting(served)
    reading(served, Reader(judged(kind="go", choice="research", disputes=["D1"], also_asks=f"  {QUESTION} ")))
    reply = say(served, f"Go ahead with the first dispute. {QUESTION}")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    assert set(held(served)["steps"]["parts"]) == {"D1"}
    assert queued(served) == [{"text": QUESTION, "documents": []}]
    assert message_reader.QUEUED_SAID in held(served)["go"]["heard"][-1]["said"]
    # Words that are not the advocate's are not kept: NM says it could not tell.
    reading(served, Reader(judged(kind="information", disputes=["D1"], also_asks="What is the fee for a possession suit?")))
    reply = say(served, f"The notice reached them on the fourth. {QUESTION}")
    assert reply.json()["detail"]["code"] == "heard"
    assert queued(served) == [{"text": QUESTION, "documents": []}]
    assert message_reader.UNQUEUED_SAID in reply.json()["detail"]["heard"]["said"]
    # Beside information, the advocate's own words wait too, and the information is kept.
    reading(served, Reader(judged(kind="information", disputes=["D1"], also_asks=QUESTION)))
    reply = say(served, f"They paid half in cash. {QUESTION}")
    assert reply.json()["detail"]["code"] == "heard"
    assert queued(served) == [{"text": QUESTION, "documents": []}] * 2
    assert [entry["text"] for entry in held(served)["added"]][-1] == f"They paid half in cash. {QUESTION}"


def test_at_a_guided_stop_the_matter_is_read_again_and_the_go_ahead_beside_the_facts_is_not_taken(served):
    waiting(served, guided=True)
    assert steps.waiting_of(held(served)) == steps.READ
    reading(served, Reader(judged(kind="go", choice="right", adds=True, said="")))
    reply = say(served, "That is right, but the notice reached them on the fourth.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", reply.text
    record = held(served)
    assert steps.waiting_of(record) == steps.READ and steps.READ not in record["go"]["guided"]["settled"]
    heard = record["go"]["heard"][-1]
    assert heard["taken"] == "information" and message_reader.GUIDED_GO_SAID in heard["said"]
