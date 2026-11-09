"""Research only what is new (plan AN.48, piece 48i; owner decision D156). A message sent while a matter waits may raise a legal
question a dispute's research has not asked: the message reader proposes it, NM says so and offers to research it, and nothing runs
until the advocate goes ahead. On the go-ahead the question joins the plan after all its own questions, so that every other keeps
its identity (research v19); only the new question is searched, the dispute's earlier searches used as saved; the other disputes'
research is kept as it was; and the dispute's analysis, written from its earlier research, is written again when the advocate asks.
Offline: scripted models and search; the words are invented."""
import json

from nm.core_engine import message_reader, research, steps
from nm.core_engine.retrieval import HybridSearcher
from nm.shared.model_port import Completion, ModelResult, Usage
from tests.test_a_message_while_a_matter_waits import CHAT, SENT, Reader, held, judged, reading, say
from tests.test_additions_are_the_advocates_messages import go
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import served  # noqa: F401 - pytest fixture

NEW = {"dispute": "D1", "question": "Whether a notice sent only by email was valid notice?",
       "why_needed": "The claim rests on the notice.", "law_to_check": ["Indian Contract Act, 1872"]}
WORDS = "The notice was sent only by email."


def phrased(served):
    """The phrase steps answer for the new question as they would for any (the scripted research knows only its own)."""
    first = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation in ("core_research_phrases", "core_research_judgment_phrases") and NEW["question"] in prompt.user:
            data = ({"questions": [{"question_id": "D1Q2", "phrases": [{"kind": "rule", "text": "notice given by electronic mail"}],
                                    "acts": ["Indian Contract Act, 1872"], "sections": []}]}
                    if prompt.operation == "core_research_phrases" else
                    {"questions": [{"question_id": "D1Q2", "phrases": [{"kind": "issue", "text": "whether email is valid notice"}]}]})
            return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)
        return first(prompt, schema, tier, **kwargs)
    served.model.structured = structured


def searched(monkeypatch):
    """The query IDs every search is asked for."""
    asked, first = [], HybridSearcher.search_many

    def counting(self, searches, **kwargs):
        asked.extend(query["query_id"] for search in searches for query in search[0])
        return first(self, searches, **kwargs)
    monkeypatch.setattr(HybridSearcher, "search_many", counting)
    return asked


def test_what_is_new_is_researched_alone_on_the_go_ahead_and_its_analysis_written_again(served, monkeypatch):
    scripted = Scripted()
    scripted_answers(served, scripted)
    phrased(served)
    asked = searched(monkeypatch)
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    assert go(served, "research").json()["detail"]["code"] == "waiting"
    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"
    before = held(served)["steps"]
    ids_before = [work["id"] for work in before["understood"]["plan"]["work"]]

    reading(served, Reader(judged(kind="information", disputes=["D1"], new_questions=[NEW], said="Taken as new information.")))
    reply = say(served, WORDS)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard", "nothing runs until the advocate goes ahead"
    assert f"NM can research what is new for Dispute 1: {NEW['question']}" in reply.json()["detail"]["heard"]["said"]
    proposed, = held(served)["go"]["proposed"]
    assert proposed["source"] == "turn-1:added1" and proposed["dispute_id"] == "D1"
    card = served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]["waiting"]
    assert {"choice": "research", "disputes": ["D1"], "said": "Research what is new: Dispute 1"} in [
        {key: offered[key] for key in ("choice", "disputes", "said")} for offered in card["gos"]]

    asked.clear()
    assert go(served, "research", ["D1"]).json()["detail"]["code"] == "waiting"
    after = held(served)
    work = after["steps"]["understood"]["plan"]["work"]
    assert [item["id"] for item in work][:len(ids_before)] == ids_before, "every other question keeps its identity"
    new, = [item for item in work if item["id"] not in ids_before]
    assert new["dispute"]["id"] == "D1" and new["question"] == NEW["question"] and new["sources"][-1]["source_id"] == "turn-1:added1"
    assert any(query.startswith(new["id"] + ":q") for query in asked), "the new question is searched"
    assert not any(query.startswith(identity + ":q") for identity in ids_before for query in asked), "nothing else is searched again"
    parts = after["steps"]["parts"]
    assert parts["D2"]["searches"] == before["parts"]["D2"]["searches"] and parts["D2"]["contract"] == research.ADDED_CONTRACT
    assert set(parts["D1"]["searches"]) == {*before["parts"]["D1"]["searches"], new["id"]}, "added to the dispute's research"
    assert "proposed" not in after["go"]
    assert not [saved for saved in after["steps"]["answered"]["sections"] if saved["dispute_id"] == "D1"], "to be written again"

    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"
    assert NEW["question"] in json.dumps(scripted.payloads("core_response_writer", "D1")[-1], ensure_ascii=False)
    assert [saved["dispute_id"] for saved in held(served)["steps"]["answered"]["sections"]] == ["D1"]


def test_a_dispute_s_new_question_is_numbered_after_its_own_and_its_work_after_the_plans():
    from tests.test_core_research import understanding
    subject = understanding(disputes=2)
    subject["disputes"][0]["legal_questions"].append({**subject["disputes"][0]["legal_questions"][0], "id": "D1Q3"})
    plan = {"proposal": {"understanding": subject, "statute_phrases": [], "judgment_phrases": [], "failures": []}}

    class Phrases:
        def __init__(self):
            self.users = []

        def structured(self, prompt, schema, tier, **kwargs):
            self.users.append(prompt.user)
            return ModelResult(None, {"questions": []}, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                               completion=Completion.COMPLETE)

        def context_budget(self, tier):
            return 100_000
    proposal = research.with_questions(Phrases(), plan, [{"dispute_id": "D1", "question": "Q?", "why_needed": "", "law_to_check": [],
                                                           "source": "t1:added1"},
                                                          {"dispute_id": "D9", "question": "Q?", "why_needed": "", "law_to_check": [],
                                                           "source": "t1:added1"}])
    assert [question["id"] for question in proposal["understanding"]["disputes"][0]["legal_questions"]] == ["D1Q1", "D1Q3", "D1Q4"]
    assert proposal["added_questions"] == [{"question_id": "D1Q4", "dispute_id": "D1",
                                            "source": {"source_id": "t1:added1", "quote": None}}], "none for a dispute not held"
    assert research.plan_contract({"proposal": proposal}) == research.ADDED_CONTRACT
    assert research.plan_contract(plan) == research.CONTRACT
    assert research.with_questions(Phrases(), plan, []) is plan["proposal"], "nothing added: the proposal as it was"


def test_questions_proposed_wait_on_the_go_ahead_until_researched_and_a_rethink_drops_them():
    entry = {"dispute_id": "D1", "question": "Q?", "why_needed": "", "law_to_check": [], "source": "t1:added1"}
    go = steps.proposing(steps.waited(steps.first(), "researched"), [entry])
    assert steps.valid(go) and steps._carried(go)["proposed"] == [entry]
    assert "proposed" not in steps.rethink(go), "the matter is understood again with everything said"
    assert "proposed" not in steps.unproposed(go, {"D1"}) and steps.unproposed(go, {"D2"})["proposed"] == [entry]
    assert not steps.valid({**go, "proposed": [{**entry, "question": " "}]})


def test_the_reader_proposes_questions_only_for_the_matters_disputes():
    plan = {"proposal": {"understanding": {"disputes": [
        {"id": "D1", "name": "Lease", "legal_questions": [{"id": "D1Q1", "question": "Whether the lease was valid?"}]},
        {"id": "D2", "name": "Notice", "legal_questions": [{"id": "D2Q1", "question": "Whether notice was given?"}]}]}},
        "work": [{"id": "w1", "dispute": {"id": "D1"}}, {"id": "w2", "dispute": {"id": "D2"}}]}
    record = {"steps": {"understood": {"interpretation": {}, "plan": plan}, "limits": None, "parts": {}, "cases": {},
                        "answered": None},
              "go": steps.waited(steps.first(), "understood"), "stopped": {"code": "waiting", "at": "now"}}
    judgement, _ = message_reader.admitted(judged(kind="information", disputes=["D1"], new_questions=[
        NEW, {**NEW, "dispute": "D9"}, {**NEW, "question": "  "}]), record)
    assert judgement["new_questions"] == [NEW]
    assert message_reader.material(record, "x")["where_the_matter_stands"]["questions_each_dispute_asks"] == [
        {"dispute": "D1", "questions": ["Whether the lease was valid?"]}, {"dispute": "D2", "questions": ["Whether notice was given?"]}]
    assert message_reader.admitted(judged(kind="go", choice="research", disputes=["D2"], new_questions=[NEW]), record)[0][
        "new_questions"] == [], "only information or a correction raises questions"
