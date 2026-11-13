"""A follow-up starts from NM's last understanding of the matter (plan AN.48, owner decision D175, 10 Nov 2026: "Yes, build it").

A message sent step by step after an answer is saved is read by NM's follow-up reader against the matter as that answer understood
it. On the same matter, facts and papers the turn keeps that understanding and the papers' reading and weighing in it, adds the
follow-up's own legal questions, and researches only the disputes they belong to - every other dispute's research is kept,
renumbered for this turn and checked as saved research is checked; every analysis is written again. Papers sent with the message,
any other judgement, a reader that cannot be reached, or an understanding that cannot be kept exactly as it was read the whole
matter again, as before. The stop says which. Offline: scripted models and search; the words are invented."""
import json
from copy import deepcopy

import pytest

from nm.core_engine import follow_up, message_reader, research, steps, turn
from nm.core_engine.conversation import TurnContext, chat_matter_id, shown_of
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage
from tests.test_a_message_while_a_matter_waits import CHAT, SENT, judged
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - pytest fixture
from tests.test_research_only_what_is_new import NEW, phrased, searched

FOLLOW = {"message": "Could the client also say the notice was sent only by email?", "turn_id": "turn-2", "chat_id": CHAT,
          "steps": "interactive"}
SAME = {"kind": "same_matter", "new_questions": [NEW], "said": "Taken as a new question on Dispute 1."}
READ = ("core_research_understand", "core_research_chronology", "core_research_transfers", "core_research_connections",
        "core_research_weigh")


def _result(data, tier):
    return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def answered_first(served):
    """The first message worked step by step and finished end to end: the saved answer a follow-up starts from."""
    scripted = Scripted()
    scripted_answers(served, scripted)
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    reply = served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": "end_to_end"})
    assert reply.status_code == 200, reply.text
    return scripted


def reader_says(served, *judgements):
    """The follow-up reader answers with each judgement given in turn (an exception is raised); returns what it was asked."""
    asked, queue, first = [], list(judgements), served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == follow_up.OPERATION:
            asked.append(json.loads(prompt.user))
            out = queue.pop(0)
            if isinstance(out, Exception):
                raise out
            return _result(out, tier)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    return asked


def followed(served, **changes):
    return served.client.post("/api/turn", json={**FOLLOW, **changes})


def go(served, choice):
    return served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-2", "choice": choice})


def held(served):
    return shown_of(served.store.load(chat_matter_id(OWNER, CHAT)))


def card(served):
    return served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]["waiting"]


def made_since(served, count):
    return [name for name, _ in served.model.calls[count:]]


def test_a_follow_up_on_the_same_matter_keeps_the_understanding_and_researches_only_what_it_adds(served, monkeypatch):
    scripted = answered_first(served)
    phrased(served)
    searches = searched(monkeypatch)
    asked = reader_says(served, SAME)
    before, written_before = len(served.model.calls), len(scripted.payloads("core_response_writer", "D2"))
    reply = followed(served)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"
    made = made_since(served, before)
    assert not set(READ) & set(made), "the papers are not read again nor the matter understood again"
    assert made.count("core_understanding") == 1, "the follow-up's own words are read, once"
    record = held(served)
    work = record["steps"]["understood"]["plan"]["work"]
    assert all(item["id"].startswith("turn-2:w") for item in work), "this turn's own numbering"
    new, = [item for item in work if item["question"] == NEW["question"]]
    assert new["dispute"]["id"] == "D1" and new["sources"][-1]["source_id"] == "turn-2:advocate"
    assert set(record["steps"]["parts"]) == {"D2"}, "the other dispute's research is kept; the one asked about is researched again"
    assert record["go"]["taken"]["route"] == "kept"
    shown = card(served)
    assert shown["done_said"] == steps.KEPT_SAID
    # Plan AN.51 (51b, D196): code's own sentence for the kind stands first; the reader's wording comes last, marked.
    assert shown["taken"].startswith(follow_up.SAID["same_matter"] + " NM kept its understanding of the matter")
    assert shown["taken"].endswith("NM's reading: Taken as a new question on Dispute 1.")
    assert NEW["question"] in shown["taken"] and "The law found before for Dispute 2 is kept." in shown["taken"]
    seen, = asked
    assert seen["new_message"] == FOLLOW["message"] and seen["earlier_messages"] == [SENT["message"]]
    assert [dispute["id"] for dispute in seen["the_matter_as_we_understood_it"]["disputes"]] == ["D1", "D2"]

    searches.clear()
    final = go(served, "end_to_end")
    assert final.status_code == 200, final.text
    assert any(query.startswith(new["id"] + ":q") for query in searches), "the new question is searched"
    kept = [item["id"] for item in work if item["dispute"]["id"] == "D2"]
    assert not any(query.startswith(identity + ":q") for identity in kept for query in searches), "D2 is not searched again"
    assert len(scripted.payloads("core_response_writer", "D2")) > written_before, "every analysis is written again"
    rows = turn.saved_rows(served.store.load(chat_matter_id(OWNER, CHAT)), OWNER)
    saved = rows[-1]["activities"]["research"]
    assert rows[-1]["turn_id"] == "turn-2" and saved["contract"] == research.ADDED_CONTRACT
    assert NEW["question"] in json.dumps(saved["plan"]["proposal"]["understanding"], ensure_ascii=False)


def test_a_follow_up_adding_no_question_keeps_every_dispute_s_research(served, monkeypatch):
    answered_first(served)
    searches = searched(monkeypatch)
    reader_says(served, {"kind": "same_matter", "new_questions": [], "said": "Taken as a request to say it more simply."})
    assert followed(served).json()["detail"]["code"] == "waiting"
    assert set(held(served)["steps"]["parts"]) == {"D1", "D2"}
    assert "The law found before for Dispute 1, Dispute 2 is kept." in card(served)["taken"]
    searches.clear()
    assert go(served, "end_to_end").status_code == 200
    assert searches == [], "nothing is searched again"


@pytest.mark.parametrize("kind", ["changes_matter", "another_matter", "unclear"])
def test_a_follow_up_that_changes_the_matter_reads_it_all_again_and_says_so(served, kind):
    answered_first(served)
    reader_says(served, {"kind": kind, "new_questions": [], "said": "Your message adds when the notice was served."})
    before = len(served.model.calls)
    assert followed(served).json()["detail"]["code"] == "waiting"
    made = made_since(served, before)
    assert "core_research_understand" in made and made.count("core_understanding") == 1, "read again; the message read once"
    record = held(served)
    assert record["go"]["taken"] == {"route": "afresh",
                                     "said": f"NM read the whole matter again from the start. {follow_up.SAID[kind]} NM's reading: "
                                             "Your message adds when the notice was served."}
    assert record["steps"]["parts"] == {}
    assert card(served)["done_said"].startswith("NM has read your papers and understood the matter")


def test_a_reader_that_cannot_be_reached_reads_it_all_again(served):
    answered_first(served)
    reader_says(served, ProviderUnavailable("Synthetic provider outage"))
    before = len(served.model.calls)
    assert followed(served).json()["detail"]["code"] == "waiting"
    assert "core_research_understand" in made_since(served, before)
    assert held(served)["go"]["taken"] == {"route": "afresh", "said": follow_up.AGAIN_SAID["unread"]}


def test_a_question_that_cannot_be_added_reads_it_all_again(served):
    """The phrase step for the follow-up's question fails: the grown plan would carry a new issue."""
    answered_first(served)
    reader_says(served, SAME)
    first = served.model.structured

    def failing(prompt, schema, tier, **kwargs):
        if prompt.operation in ("core_research_phrases", "core_research_judgment_phrases") and NEW["question"] in prompt.user:
            raise ProviderUnavailable("Synthetic provider outage")
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = failing
    before = len(served.model.calls)
    assert followed(served).json()["detail"]["code"] == "waiting"
    assert "core_research_understand" in made_since(served, before)
    assert held(served)["go"]["taken"] == {"route": "afresh", "said": follow_up.AGAIN_SAID["not_added"]}


def test_a_question_whose_phrasing_fails_outright_reads_it_all_again(served, monkeypatch):
    answered_first(served)
    reader_says(served, SAME)

    def failing(*args, **kwargs):
        raise ProviderUnavailable("Synthetic provider outage")
    monkeypatch.setattr(research, "with_questions", failing)
    assert followed(served).json()["detail"]["code"] == "waiting"
    assert held(served)["go"]["taken"] == {"route": "afresh", "said": follow_up.AGAIN_SAID["not_added"]}


def test_an_understanding_that_does_not_admit_again_as_it_was_reads_it_all_again(served, monkeypatch):
    answered_first(served)
    reader_says(served, SAME)
    phrased(served)
    real = follow_up.earlier

    def changed(rows):
        before = deepcopy(real(rows))
        before["plan"]["issues"].append({"work_id": None, "mismatch": "An issue it never had", "proposal": {}})
        return before
    monkeypatch.setattr(follow_up, "earlier", changed)
    assert followed(served).json()["detail"]["code"] == "waiting"
    assert held(served)["go"]["taken"] == {"route": "afresh", "said": follow_up.AGAIN_SAID["not_added"]}


def test_a_dispute_s_research_that_fails_its_check_is_researched_again(served, monkeypatch):
    answered_first(served)
    reader_says(served, {"kind": "same_matter", "new_questions": [], "said": "Taken as a question on the matter."})
    real = follow_up.earlier

    def damaged(rows):
        before = deepcopy(real(rows))
        searches = before["parts"]["D2"]["searches"]
        searches.pop(next(iter(searches)))
        return before
    monkeypatch.setattr(follow_up, "earlier", damaged)
    assert followed(served).json()["detail"]["code"] == "waiting"
    record = held(served)
    assert record["go"]["taken"]["route"] == "kept" and set(record["steps"]["parts"]) == {"D1"}


def test_a_first_message_and_a_message_sent_without_steps_are_read_as_before(served):
    asked = reader_says(served)
    scripted_answers(served, Scripted())
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    assert "taken" not in held(served)["go"] and asked == []
    assert served.client.post("/api/turn/go", json={"chat_id": CHAT, "turn_id": "turn-1", "choice": "end_to_end"}).status_code == 200
    before = len(served.model.calls)
    reply = followed(served, steps=None)
    assert reply.status_code == 200, reply.text
    assert asked == [] and "core_research_understand" in made_since(served, before), "end to end exactly as before"


def test_read_everything_again_at_the_stop_understands_the_matter_again(served):
    answered_first(served)
    phrased(served)
    reader_says(served, SAME)
    assert followed(served).json()["detail"]["code"] == "waiting"
    assert held(served)["go"]["taken"]["route"] == "kept"
    first = served.model.structured

    def rethinking(prompt, schema, tier, **kwargs):
        if prompt.operation == message_reader.OPERATION:
            return _result(judged(kind="rethink", said="Taken as a request to read the whole matter again."), tier)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = rethinking
    before = len(served.model.calls)
    reply = served.client.post("/api/turn/message", json={"chat_id": CHAT, "turn_id": "turn-2",
                                                          "message": "Read everything again from the start."})
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting"
    assert "core_research_understand" in made_since(served, before)
    record = held(served)
    assert "taken" not in record["go"], "the whole matter was read again"
    assert card(served)["done_said"].startswith("NM has read your papers and understood the matter")


# --- code's rules ----------------------------------------------------------------------------------------------------------


def later_context(served, message="And now?"):
    matter = served.store.load(chat_matter_id(OWNER, CHAT))
    rows = tuple(turn.saved_rows(matter, OWNER))
    return rows, TurnContext(matter, CHAT, "turn-2", message, rows).payload()


def test_kept_research_is_renumbered_for_this_turn_and_passes_research_s_own_check(served):
    answered_first(served)
    rows, context = later_context(served)
    before = follow_up.earlier(rows)
    assert before["turn_id"] == "turn-1" and set(before["parts"]) == {"D1", "D2"}
    plan = research.accept(before["plan"]["proposal"], context)
    moved = follow_up.carried(before["parts"]["D2"], before["plan"], plan)
    research.validate(moved, plan, context)
    assert "turn-1:w" not in json.dumps({key: value for key, value in moved.items() if key != "plan"})
    with pytest.raises(ValueError):
        research.validate(research.rebased(before["parts"]["D2"], plan), plan, context)  # not renumbered: refused
    other = deepcopy(before["plan"])
    for item in other["work"]:
        if item["dispute"]["id"] == "D2":
            item["question"] += " Asked otherwise."
    with pytest.raises(ValueError):
        follow_up.carried(before["parts"]["D2"], other, plan)


def test_only_the_last_answer_with_a_matter_to_research_is_kept():
    assert follow_up.earlier(()) is None
    assert follow_up.earlier(({"turn_id": "t1", "activities": {"contract": "core_turn_unanswered_v1"}},)) is None
    assert follow_up.earlier(({"turn_id": "t1", "activities": {"research": {"contract": "core_research_v17", "plan": {}}}},)) is None


def test_papers_sent_with_a_follow_up_read_it_all_again_without_asking_the_reader():
    class Untouched:
        def __getattr__(self, name):
            raise AssertionError("no call is made")
    context = {"latest": {"turn_id": "t2", "source_id": "t2:advocate", "text": "See these."}, "conversation": [],
               "documents": [{"turn_id": "t2", "source_id": "t2:d1p1", "text": "A page."}]}
    taken = follow_up.continued(Untouched(), context, {"plan": {}, "parts": {}}, lambda stage, **detail: None)
    assert taken == {"route": "afresh", "said": follow_up.AGAIN_SAID["papers"], "interpretation": None}
    unread = {**context, "documents": [], "unread_document_pages": [{"turn_id": "t2", "name": "scan.pdf", "page": 1}]}
    assert follow_up.continued(Untouched(), unread, {"plan": {}, "parts": {}}, lambda stage, **detail: None)["route"] == "afresh"


PLAN = {"proposal": {"understanding": {"disputes": [
    {"id": "D1", "name": "Lease", "between": ["client", "landlord"],
     "legal_questions": [{"id": "D1Q1", "question": "Whether the lease was valid?"}]},
    {"id": "D2", "name": "Notice", "between": ["client", "landlord"],
     "legal_questions": [{"id": "D2Q1", "question": "Whether notice was given?"}]}]}},
    "work": [{"id": "w1", "dispute": {"id": "D1"}}, {"id": "w2", "dispute": {"id": "D2"}}]}


def test_the_reader_s_judgement_is_admitted_only_for_the_matter_s_own_disputes():
    before = {"plan": PLAN, "parts": {}}
    judgement, why = follow_up.admitted({"kind": "same_matter", "new_questions": [NEW], "said": " Taken  as asked. "}, before)
    assert why is None and judgement == {"kind": "same_matter", "new_questions": [NEW], "said": follow_up.SAID["same_matter"],
                                         "reading": "Taken as asked."}
    assert follow_up.admitted({"kind": "same_matter", "new_questions": [{**NEW, "dispute": "D9"}], "said": ""}, before)[0] is None
    assert follow_up.admitted({"kind": "same_matter", "new_questions": [{**NEW, "question": " "}], "said": ""}, before)[0] is None
    assert follow_up.admitted({"kind": "same_matter", "new_questions": [NEW] * 21, "said": ""}, before)[0] is None
    assert follow_up.admitted({"kind": "guess", "new_questions": [], "said": ""}, before)[0] is None
    other, _ = follow_up.admitted({"kind": "changes_matter", "new_questions": [NEW], "said": ""}, before)
    assert other == {"kind": "changes_matter", "new_questions": [], "said": follow_up.SAID["changes_matter"], "reading": ""}


def test_a_judgement_that_cannot_be_admitted_is_asked_once_more_then_taken_as_unclear():
    class Reader:
        def __init__(self):
            self.users = []

        def structured(self, prompt, schema, tier, **kwargs):
            self.users.append(json.loads(prompt.user))
            return _result({"kind": "same_matter", "new_questions": [{**NEW, "dispute": "D9"}], "said": "x"}, tier)

        def context_budget(self, tier):
            return 100_000
    reader = Reader()
    context = {"latest": {"turn_id": "t2", "source_id": "t2:advocate", "text": "And the rent?"},
               "conversation": [{"source_id": "t1:advocate", "record_role": "original_account", "text": "The lease."},
                                {"source_id": "t1:nm", "record_role": "nm_interpretation", "text": "Our answer."}]}
    judgement = follow_up.read(reader, {"plan": PLAN, "parts": {}}, context)
    assert judgement == {"kind": "unclear", "new_questions": [], "said": follow_up.SAID["unclear"], "reading": ""}
    assert len(reader.users) == 2 and "why_it_cannot_be_taken" in reader.users[1]
    assert reader.users[0]["earlier_messages"] == ["The lease."], "the advocate's own messages, not NM's"


def test_how_a_follow_up_started_is_kept_carried_and_dropped_by_a_rethink():
    go = steps.taking(steps.first(), "kept", "NM kept its understanding.")
    assert steps.valid(go) and steps._carried(go)["taken"] == {"route": "kept", "said": "NM kept its understanding."}
    assert "taken" not in steps.rethink(steps.waited(go, "understood"))
    assert not steps.valid(steps.taking(steps.first(), "guessed", "x"))
    assert not steps.valid(steps.taking(steps.first(), "kept", " "))
    assert steps.valid(steps.first()), "a record without it reads as before"
