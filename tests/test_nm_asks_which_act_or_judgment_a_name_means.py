"""NM asks which Act or judgment a name means (plan AN.37, D87; owner, 5 Nov 2026: "do 3"). Where the research reads a section
named by an Act's name and the library holds more than one Act by that name, or finds a citation under which it holds more than
one judgment, code asks the advocate in the turn's window which is meant - each held Act or judgment a choice, NM's own judgement
(or going on without the judgment) the default - and the answer settles it: the pick keeps no reading of another Act for that
name, and the judgment meant is read as one held once. The question waits its own two minutes from when it was asked, and joins
whatever the window already asks. The Acts, the judgments and the citation are invented."""
from copy import deepcopy

import pytest

from nm.core_engine import questions, research, response_writer, retrieval
from nm.core_engine.retrieval import HybridSearcher
from tests.test_core_research import Model
from tests.test_current_brain_retrieval import Collection, row
from tests.test_the_law_a_question_names_is_read_by_its_number import ACT, KEY, Named, naming_plan

pytestmark = pytest.mark.class_a
TS = "TELANGANA_1907_2_IMAGINED RELIEF ACT, 1907"


class Twice(Named):
    """The test library holding the invented Act twice: centrally and in Telangana, each with its own section 6."""

    def __init__(self):
        super().__init__()
        self.rows[7]["act_id"] = "UNION OF INDIA_1907_1_IMAGINED RELIEF ACT, 1907"
        self.rows[7]["act_name"] = "Union Of India 1907 1 Imagined Relief Act, 1907"
        self.rows[8] = {**row(text="6. Recovery of a thing possessed in Telangana: within one year."), "chunk_id": "named-6-ts",
                        "act_id": TS, "act_name": "Telangana 1907 2 Imagined Relief Act, 1907", "section_number": "6"}

    def kept_acts(self, keys):
        return (self.rows[7]["act_id"], TS) if KEY in keys else ()

    def read_provision(self, act_id, reference):
        at = {self.rows[7]["act_id"]: 7, TS: 8}.get(act_id)
        if at is None or reference != "6":
            return {"state": "not_held", "sources": [], "reason": "No such provision"}
        context = {"scope": "indexed_section_segments", "bounded": False, "unread_positions": [],
                   "segments": [{"position": at, "row": deepcopy(self.rows[at])}]}
        return {"state": "found", "sources": [retrieval._candidate("provision", at, self.rows[at], self.revision(), None, [], context)],
                "reason": None}


def researched(settle):
    ctx, plan = naming_plan()
    model = Model()
    parts = research.retrieve_parts(plan, HybridSearcher({"provision": Twice(), "judgment": Collection("judgment")}), ctx,
                                    model=model, settle=settle)
    return ctx, plan, model, research.assemble(plan, [future.result() for future in parts.values()])


def provisions_kept(record):
    rows = {c["id"]: c for search in record["searches"].values() for c in retrieval.offered(search)}
    return {rows[identity]["source"]["act_id"] for ids in research.chosen(record).values() for identity in ids
            if identity in rows and rows[identity]["source"].get("section_number") == "6"}


def test_the_advocate_is_asked_which_act_a_name_means_and_the_pick_keeps_that_acts_section_alone():
    asked = []

    def settle(put):
        asked.extend(put)
        return [(question, {"chosen": [question["choices"][1]["label"]], "other": ""}) for question in put]
    ctx, plan, model, record = researched(settle)
    (question,) = asked
    assert question["asked_by"] == "code" and question["header"] == "Which Act is meant"
    assert ACT in question["question"] and question["default"] == [research.NM_JUDGES]
    assert [choice["label"] for choice in question["choices"]] == [
        "Imagined Relief Act, 1907", "Imagined Relief Act, 1907 (Telangana)", research.NM_JUDGES]
    assert question["depends"] == [plan["proposal"]["understanding"]["disputes"][0]["id"]]
    assert provisions_kept(record) == {TS}, "the pick keeps no reading of the Act the advocate did not mean"
    shown = next(p.user for p in model.calls if p.operation == "core_research_pick")
    assert "the advocate means Imagined Relief Act, 1907 (Telangana)" in shown
    (meant,) = next(iter(record["meant"].values()))
    assert meant["meant"] == TS
    assert research.validate(record, plan, ctx) == record, "the record replays with what the advocate said"
    forged = deepcopy(record)
    next(iter(forged["meant"].values()))[0]["meant"] = "AN ACT IT MAY NOT BE"
    with pytest.raises(ValueError):
        research.validate(forged, plan, ctx)
    told = response_writer._research_context(record, None)["searches"][0]["named"][0]
    assert told["state"] == "ambiguous" and told["the_advocate_means"] == "Imagined Relief Act, 1907 (Telangana)"


def test_left_to_nm_every_reading_is_offered_and_kept_as_the_pick_judges():
    ctx, plan, model, record = researched(lambda put: [(question, None) for question in put])
    assert provisions_kept(record) == {"UNION OF INDIA_1907_1_IMAGINED RELIEF ACT, 1907", TS}
    assert next(iter(record["meant"].values()))[0]["meant"] is None
    assert research.validate(record, plan, ctx) == record


def test_nothing_is_asked_where_the_turn_asks_nothing_and_the_record_is_as_before():
    ctx, plan, model, record = researched(None)
    assert "meant" not in record and research.validate(record, plan, ctx) == record


def test_a_citation_held_more_than_once_is_asked_of_and_the_judgment_meant_is_read():
    cited = [{"id": "CJ1", "citation": "(1990) 1 ABC 1", "keys": ["abc:1990:1:1"], "where": ["t1:advocate"], "state": "ambiguous",
              "judgment": None, "reason": None,
              "held": [{"case_id": "c1", "title": "A v B", "court": "High Court", "year": 1990},
                       {"case_id": "c2", "title": "C v D", "court": "Supreme Court", "year": 1990}], "meant": None}]
    put = []

    def settle(asked):
        put.extend(asked)
        return [(question, {"chosen": ["C v D (Supreme Court, 1990)"], "other": ""}) for question in asked]
    now = research._cited_meant(cited, settle, ["d1", "d2"])
    (question,) = put
    assert question["header"] == "Which judgment is meant" and question["default"] == [research.WITHOUT_IT]
    assert question["depends"] == ["d1", "d2"] and now[0]["meant"] == "c2" and cited[0]["meant"] is None
    asked = {"questions": [{"question_id": "Q1", "cited": ["CJ1"]}]}
    assert research._cited_cases(asked, {"w1": "Q1"}, now, set()) == ["c2"]
    assert research._cited_cases(asked, {"w1": "Q1"}, cited, set()) == [], "not said: not read, as before"
    assert research._cited_unsure_kept(now[0]) and not research._cited_unsure_kept({**now[0], "meant": "c9"})
    assert research._cited_meant(cited, None, ["d1"]) is cited


def test_code_adds_a_question_to_the_window_and_each_waits_its_own_time():
    now = [0.0]
    asking = questions.Asking([], clock=lambda: now[0], wait=120, open_for=600)
    first = research.named_question({"act": ACT, "work_ids": ["w1"], "acts": ["UNION OF INDIA_1_ONE", "UNION OF INDIA_2_TWO"],
                                     "titles": ["One", "Two"]}, {"id": "d1", "name": "Possession"})
    admitted, refused = questions.admit([first], disputes={"d1"})
    assert not refused and asking.add(admitted) == ["q1"] and asking.open()
    assert asking.add(admitted) == ["q1"], "the same question is not asked twice"
    now[0] = 100.0
    model = questions.admit([{**first, "question": "Whom do you act for?", "asked_by": "model"}], disputes={"d1"})[0]
    assert asking.add(model) == ["q2"]
    asking.receive({"q2": {"chosen": ["One"], "other": ""}})
    now[0] = 130.0
    answers = asking.wait_for(["q1"])
    assert answers["q1"]["how"] == "assumed" and answers["q2"]["how"] == "answered", "q1's time was up; q2 was answered"
    assert asking.receive({"q1": {"chosen": ["Two"], "other": ""}}) == "taken" and asking.answers()["q1"]["how"] == "late"
    now[0] = 701.0
    assert not asking.open(), "open OPEN seconds from the last question asked"
    full = questions.Asking([], clock=lambda: 0.0)
    many = questions.admit([{**first, "question": f"Which Act is meant by name {n}?"} for n in range(5)], disputes={"d1"})[0]
    assert full.add(many) == ["q1", "q2", "q3", "q4"], "admit asks at most four"
    assert full.add(questions.admit([{**first, "question": "One more?"}], disputes={"d1"})[0]) == [None]


def test_a_question_code_asks_while_the_research_runs_opens_the_window_and_is_saved_with_the_turn(tmp_path, monkeypatch):
    """Through the real turn: the research asks (settle), the window opens with the question, the page's answer comes back to
    the research, and the question and its answer are saved with the turn as code's."""
    from nm.core_engine import turn
    from nm.core_engine.conversation import chat_matter_id
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_core_turn import ScriptedModel, run
    from tests.test_nm_asks_in_the_middle_of_a_turn import Desk

    store = FileMatterStore(tmp_path, key="k" * 64)
    question = research.named_question({"act": ACT, "work_ids": ["w1"], "acts": ["UNION OF INDIA_1_ONE", "TELANGANA_2_TWO"],
                                        "titles": ["One", "Two"]}, {"id": "d1", "name": "Possession"})
    real, got = research.retrieve_parts, []

    def retrieve_parts(*args, settle=None, **kwargs):
        got.extend(settle([question]))
        return real(*args, settle=settle, **kwargs)
    monkeypatch.setattr(research, "retrieve_parts", retrieve_parts)
    desk = Desk({"q1": {"chosen": ["Two (Telangana)"]}})
    response = run(store, ScriptedModel(legal=True), propose=lambda *args: [], desk=desk)
    assert desk.opened == ["t1"] and got[0][1]["chosen"] == ["Two (Telangana)"]
    row = turn.saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")[0]
    assert [(q["question"], q["asked_by"]) for q in row["asked"]["questions"]] == [(question["question"], "code")]
    assert [(a["chosen"], a["how"]) for a in row["asked"]["answers"]] == [(["Two (Telangana)"], "answered")]
