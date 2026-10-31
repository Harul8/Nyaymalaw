"""Research: the v7 reasoning loop, its phrases, searches, the provision pick and (v8)
the judgment pick, and the replay of every earlier plan version. These prove handoffs and mechanical contracts,
not the model's legal judgment."""
from copy import deepcopy
import re
import threading

import pytest

from nm.core_engine import answer_sources
from nm.core_engine.calls import TurnCalls
from nm.core_engine.research import (
    CONTRACT, INSTRUMENTED_CONTRACT, JUDGMENT_PICKED_CONTRACT, MAX_REVISIONS, PICKED_CONTRACT, PROVISIONS_FOR_PICK, accept,
    picked_judgments, plan, retrieve, search_instruments, search_queries, validate,
)
from nm.core_engine.retrieval import HybridSearcher, SearchUnavailable
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, SchemaViolation, Usage
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection
import json

pytestmark = pytest.mark.class_a
V6 = INSTRUMENTED_CONTRACT


# --- v6 and earlier plan items (replay) ---------------------------------------------

def work(quote="Find the applicable law.", instruments=()):
    return {"sources": [{"source_id": "t2:advocate", "quote": quote}],
            "search_account": [{"source_id": "t2:advocate", "quote": quote}],
            "relationship": "parties to the reported position",
            "roles": ["claimant", "respondent"],
            "legal_questions": ["Which held law governs the reported position?"],
            "enquiries": [
                {"text": "legal prerequisites and exceptions", "purpose": "Locate elements",
                 "basis": "conditional"},
                {"text": "available relief and contrary positions", "purpose": "Test remedies",
                 "basis": "conditional"}],
            "rule_probe": "Where the stated conditions are met, the prescribed relief is available.",
            "instruments": list(instruments)}


def v5_work(quote="Find the applicable law."):
    """A plan item as research v5 (before named instruments) proposed it."""
    item = work(quote)
    for field in ("relationship", "roles", "legal_questions", "rule_probe", "instruments"):
        del item[field]
    return item


# --- v7 proposals ---------------------------------------------------------------------

def understanding(questions=1, disputes=1, *, needs_research=True, words="Find the applicable law",
                  why_it_matters=True):
    """A v9 understanding; why_it_matters=False gives the v7 and v8 shape."""
    return {"summary": "A reported position on which the advocate seeks the law.",
            "asked": ["Where the law stands on the reported position"], "ruled_out": [],
            "needs_research": needs_research, "no_research_reason": "" if needs_research else "A courtesy.",
            "parties": [{"who": "client", "role": "claimant"}],
            "facts": [{"id": "F1", "fact": "The advocate seeks the applicable law.", "advocate_words": words,
                       "certainty": "reported"}],
            "disputes": [{"id": f"D{d}", "name": f"Dispute {d}", "between": ["client", "other party"],
                          "fact_ids": ["F1"],
                          "legal_questions": [{"id": f"D{d}Q{n}", "question": f"Which rule governs point {n} of dispute {d}?",
                                               "why_needed": "It decides the advice.", "open_alternative": "",
                                               "law_to_check": ["Indian Contract Act, 1872"]}
                                              for n in range(1, questions + 1)] if needs_research else [],
                          "rights_at_stake": [], "relief_sought": [], "missing_facts": [],
                          **({"why_it_matters": f"Dispute {d} decides what the client can recover."}
                             if why_it_matters else {})}
                         for d in range(1, disputes + 1)],
            "related_points": []}


def statute_phrases(dispute, acts=("Indian Contract Act, 1872",)):
    return {"questions": [{"question_id": q["id"],
                           "phrases": [{"kind": "heading", "text": f"rule for {q['id']}"},
                                       {"kind": "rule", "text": "Where the stated conditions are met, relief is available."}],
                           "acts": list(acts)} for q in dispute["legal_questions"]]}


def judgment_phrases(subject):
    return {"questions": [{"question_id": q["id"], "phrases": [{"kind": "issue", "text": f"whether relief lies on {q['id']}"}]}
                          for d in subject["disputes"] for q in d["legal_questions"]]}


def proposal(questions=1, disputes=1, *, chronology=True, **kw):
    """A proposal as the current research contract keeps it; chronology=False gives the shape before v12."""
    subject = understanding(questions, disputes, **kw)
    return {"understanding": subject,
            "review_rounds": [{"code_problems": [], "verdict": "sound", "problems": []}],
            "statute_phrases": [{"dispute_id": d["id"], **statute_phrases(d)} for d in subject["disputes"]],
            "judgment_phrases": judgment_phrases(subject)["questions"], "failures": [],
            **({"chronology": [], "chronology_failures": []} if chronology else {})}


def _result(data, tier, completion=Completion.COMPLETE):
    return ModelResult(None, deepcopy(data), tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=completion)


class Model:
    """Answers each operation from a script; each pick chooses every shown candidate."""

    def __init__(self, subject=None, *, checks=None, revisions=None, fail=(), budget=100_000,
                 completion=Completion.COMPLETE, choose=None, choose_judgments=None):
        self.subject = subject or understanding()
        self.checks = list(checks or [{"verdict": "sound", "problems": []}])
        self.revisions = list(revisions or [])
        self.fail, self.budget, self.completion, self.choose = set(fail), budget, completion, choose
        self.choose_judgments = choose_judgments
        self.calls = []

    def context_budget(self, tier): return self.budget

    def structured(self, prompt, schema, tier, **kwargs):
        self.calls.append(prompt)
        operation = prompt.operation
        if (operation, prompt.user) in self.fail or operation in self.fail:
            raise SchemaViolation(f"Scripted failure for {operation}")
        if operation == "core_research_understand":
            data = self.subject
        elif operation == "core_research_check":
            data = self.checks.pop(0) if len(self.checks) > 1 else self.checks[0]
        elif operation == "core_research_revise":
            data = {"notes": "Corrected.", "understanding": self.revisions.pop(0)}
        elif operation == "core_research_phrases":
            dispute_id = re.search(r"^Dispute (\S+):", prompt.user, re.M).group(1)
            data = statute_phrases(next(d for d in self.subject["disputes"] if d["id"] == dispute_id))
        elif operation == "core_research_judgment_phrases":
            data = judgment_phrases(self.subject)
        elif operation in ("core_research_pick", "core_research_judgment_pick"):
            shown = {}
            for label, number in re.findall(r"^\s+(Q\d+)\.(\d+) ", prompt.user, re.M):
                shown.setdefault(label, []).append(f"{label}.{number}")
            choose = self.choose if operation == "core_research_pick" else self.choose_judgments
            data = {"questions": [{"question_id": q, "chosen": (choose or (lambda ids: ids))(ids), "note": "Chosen."}
                                  for q, ids in shown.items()]}
        else:
            raise AssertionError(operation)
        return _result(data, tier, self.completion)


def one_pick(record):
    """A v10 record of one dispute in the shape of v7-v9, which kept one pick of each kind
    for the whole matter (research v10, 21 Oct 2026, keeps each dispute's)."""
    return {**{key: value for key, value in record.items() if key not in ("part", "judgments")},
            "contract": "core_research_v9",
            "picks": record["picks"]["D1"], "judgment_picks": record["judgment_picks"]["D1"]}


def operations(model):
    return [prompt.operation for prompt in model.calls]


def searcher():
    many = Collection()
    many.rows = {p: {"chunk_id": f"s{p}", "full_text": f"Section {p}\nProvision {p} text.", "act_id": "act",
                     "act_name": "Act", "section_number": str(p)} for p in range(25)}
    many.lexical = many.semantic = lambda query, depth: list(many.rows)
    many.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    return HybridSearcher({"provision": many, "judgment": judgments()})


def judgments(count=8):
    """More paragraphs than the six the search returns, each with its court, year and standing."""
    held = Collection("judgment")
    held.rows = {p: {"chunk_id": f"j{p}", "full_text": f"Paragraph {p}:\n the court  holds rule {p}.",
                     "case_id": f"case{p}", "case_name": f"Case {p} v State", "paragraph_num": str(p + 1),
                     "court": "Supreme Court of India", "year": "2001", "cited_by_count": p * 10,
                     "paragraph_type": "reasoning"} for p in range(count)}
    held.lexical = held.semantic = lambda query, depth: list(held.rows)
    held.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    return held


# --- the v7 loop ----------------------------------------------------------------------

def test_the_loop_reviews_and_revises_before_phrasing_and_reads_the_whole_conversation():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account", "text": "The neighbour blocked the access."}
    note = {"source_id": "t1:nm", "turn_id": "t1", "speaker": "nm", "record_role": "nm_interpretation",
            "text": "An earlier note."}
    ctx = context("Find the applicable law.", [earlier, note])
    first, corrected = understanding(1), understanding(2)
    model = Model(first, checks=[{"verdict": "revise", "problems": [{"problem": "A point is missing.", "fix": "Add it."}]},
                                 {"verdict": "sound", "problems": []}], revisions=[corrected])
    model.subject = corrected  # phrase calls answer for the corrected questions
    admitted = plan(model, ctx)
    assert operations(model)[:4] == ["core_research_understand", "core_research_check",
                                     "core_research_revise", "core_research_check"]
    assert sorted(operations(model)[4:]) == ["core_research_judgment_phrases", "core_research_phrases"]
    seen = model.calls[0].user
    assert "[1] Advocate: The neighbour blocked the access." in seen
    assert "[2] Our research assistant (an earlier note, not the advocate's words): An earlier note." in seen
    assert seen.endswith("Latest message from the advocate (the one we act on now):\nFind the applicable law.")
    assert admitted["proposal"]["understanding"] == corrected and len(admitted["proposal"]["review_rounds"]) == 2
    assert [w["question_id"] for w in admitted["work"]] == ["D1Q1", "D1Q2"]
    assert admitted["issues"] == [] and admitted["semantic_review"] == "pending"
    item = admitted["work"][0]
    assert item["sources"] == [{**ctx["latest"], "start": 0, "end": len(ctx["latest"]["text"])}]
    assert [e["text"] for e in item["enquiries"]] == ["rule for D1Q1", "Where the stated conditions are met, relief is available.",
                                                      "whether relief lies on D1Q1"]


def test_the_loop_stops_after_its_revisions_and_records_the_open_problems():
    problem = {"verdict": "revise", "problems": [{"problem": "Still unclear.", "fix": "Clarify."}]}
    model = Model(checks=[problem], revisions=[understanding()] * MAX_REVISIONS)
    admitted = plan(model, context("Find the applicable law."))
    assert operations(model).count("core_research_check") == MAX_REVISIONS + 1
    assert operations(model).count("core_research_revise") == MAX_REVISIONS
    assert any("open problems" in issue["mismatch"] for issue in admitted["issues"])


def test_code_checks_reject_words_the_advocate_did_not_say_even_when_the_review_is_sound():
    invented = understanding(words="The neighbour admitted the debt")
    model = Model(invented, revisions=[understanding()])
    admitted = plan(model, context("Find the applicable law."))
    assert operations(model)[:3] == ["core_research_understand", "core_research_check", "core_research_revise"]
    assert "do not appear" in admitted["proposal"]["review_rounds"][0]["code_problems"][0]["problem"]


def test_a_message_needing_no_research_makes_no_phrase_calls_and_no_work():
    model = Model(understanding(needs_research=False, words="Thank you"))
    admitted = plan(model, context("Thank you."))
    assert operations(model) == ["core_research_understand", "core_research_check"]
    assert admitted["work"] == [] and admitted["issues"] == []


def test_the_last_check_runs_beside_the_search_phrases():
    """Owner, 18 Oct 2026, for speed: one check-and-fix round, and no revision can follow
    the last check, so the search phrases for that understanding are written beside it."""
    import threading
    problem = {"verdict": "revise", "problems": [{"problem": "Unclear.", "fix": "Clarify."}]}
    phrasing = threading.Event()

    class Beside(Model):
        def structured(self, prompt, schema, tier, **kwargs):
            if prompt.operation in ("core_research_phrases", "core_research_judgment_phrases"):
                phrasing.set()
            elif (prompt.operation == "core_research_check"
                  and [p.operation for p in self.calls].count("core_research_check") == MAX_REVISIONS):
                assert phrasing.wait(timeout=10), "the search phrases were not written beside the last check"
            return super().structured(prompt, schema, tier, **kwargs)

    model = Beside(checks=[problem, {"verdict": "sound", "problems": []}], revisions=[understanding()])
    admitted = plan(model, context("Find the applicable law."))
    assert MAX_REVISIONS == 1
    assert [operations(model).count(name) for name in ("core_research_check", "core_research_revise")] == [2, 1]
    assert admitted["proposal"]["statute_phrases"] and admitted["issues"] == []


def test_the_loop_stops_at_its_next_step_once_it_is_not_wanted():
    """18 Oct 2026: the matter's first understanding is written beside the message's
    interpretation; when that finds no matter, the loop stops before its next step."""
    model = Model()
    admitted = plan(model, context("Thank you."), wanted=lambda: False)
    assert operations(model) == ["core_research_understand"]
    assert admitted == plan(Model(), context("Thank you."), {"units": [{"kind": "courtesy"}]})
    assert admitted["proposal"]["understanding"]["needs_research"] is False


def test_statute_phrases_are_written_per_dispute_beside_one_judgment_call():
    model = Model(understanding(2, disputes=3))
    admitted = plan(model, context("Find the applicable law."))
    assert operations(model).count("core_research_phrases") == 3
    assert operations(model).count("core_research_judgment_phrases") == 1
    assert len(admitted["work"]) == 6 and [w["id"] for w in admitted["work"]] == [f"t2:w{n}" for n in range(1, 7)]


def test_one_disputes_failed_phrases_keep_the_other_disputes_and_the_judgment_phrases():
    model = Model(understanding(1, disputes=2))
    original = model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_phrases" and "Dispute D2:" in prompt.user:
            model.calls.append(prompt)
            raise SchemaViolation("Scripted failure for D2")
        return original(prompt, schema, tier, **kwargs)

    model.structured = structured
    admitted = plan(model, context("Find the applicable law."))
    assert {w["question_id"] for w in admitted["work"]} == {"D1Q1", "D2Q1"}
    d2 = next(w for w in admitted["work"] if w["question_id"] == "D2Q1")
    assert [e["purpose"] for e in d2["enquiries"]] == ["issue"]  # judgment phrases still search it
    assert any("statute_phrases unavailable for D2" in issue["mismatch"] for issue in admitted["issues"])


def test_an_unavailable_review_keeps_the_understanding_and_is_recorded():
    model = Model(fail={"core_research_check"})
    admitted = plan(model, context("Find the applicable law."))
    assert admitted["proposal"]["review_rounds"] == [{"code_problems": [], "verdict": "unavailable", "problems": []}]
    assert any("check unavailable" in issue["mismatch"] for issue in admitted["issues"])
    assert admitted["work"]


def test_context_overflow_never_trims_or_calls_provider():
    model = Model(budget=1)
    with pytest.raises(ContextOverflow): plan(TurnCalls(model), context())
    assert model.calls == []


def test_incomplete_output_is_never_salvaged():
    model = Model(completion=Completion.LENGTH_LIMITED)
    with pytest.raises(ModelError): plan(model, context("Find the applicable law."))


# --- v7 search, pick and replay -------------------------------------------------------

def test_every_phrase_is_searched_with_its_question_and_named_acts_once_each():
    ctx = context("Find the applicable law.")
    subject = proposal()
    subject["statute_phrases"][0]["questions"][0]["acts"] = ["Indian Contract Act, 1872", " Indian  Contract Act, 1872 "]
    admitted = accept(subject, ctx)
    queries = search_queries(admitted["work"][0])
    assert [q["query_id"] for q in queries] == ["t2:w1:q1", "t2:w1:q2", "t2:w1:q3"]
    assert {q["context"] for q in queries} == {admitted["work"][0]["question"]}
    assert search_instruments(admitted["work"][0]) == ["Indian Contract Act, 1872"]


def test_search_returns_twenty_provisions_and_the_pick_admits_only_its_choice():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    found, asked = searcher(), []
    search = found.search
    found.search = lambda queries, instruments=None, **kw: asked.append(kw) or search(queries, instruments, **kw)
    model = Model(choose=lambda ids: ids[:2])
    record = retrieve(admitted, found, ctx, model=model)
    assert asked == [{"results": {"provision": PROVISIONS_FOR_PICK}}]
    assert record["contract"] == CONTRACT == "core_research_v13" and record["state"] == "evaluated"
    provisions = [c for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "provision"]
    assert len(provisions) == PROVISIONS_FOR_PICK
    assert record["picks"]["D1"]["chosen"] == {"t2:w1": [provisions[0]["id"], provisions[1]["id"]]}
    assert validate(record, admitted, ctx) == record
    sources = answer_sources.build(ctx, record)
    assert sorted(r["id"] for r in sources.values() if r["kind"] == "provision") == sorted(
        {provisions[0]["id"], provisions[1]["id"]} | {seg for c in provisions[:2] for seg in []})
    assert any(r["kind"] == "judgment" for r in sources.values())


def test_the_judgment_pick_chooses_among_the_six_returned_and_records_its_choice():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    model = Model(choose_judgments=lambda ids: [ids[2], ids[0]])
    record = retrieve(admitted, searcher(), ctx, model=model)
    paragraphs = [c for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "judgment"]
    assert len(paragraphs) == 6
    shown = next(p.user for p in model.calls if p.operation == "core_research_judgment_pick")
    assert re.findall(r"^\s+Q1\.(\d+) ", shown, re.M) == ["1", "2", "3", "4", "5", "6"]
    first = paragraphs[0]["source"]
    assert (f"Q1.1 {first['case_name']} (Supreme Court of India, 2001, cited by {first['cited_by_count']}), "
            f"paragraph {first['paragraph_num']}: Paragraph") in shown
    assert "the court holds rule" in shown  # whole words, spacing collapsed
    assert record["judgment_picks"]["D1"]["chosen"] == {"t2:w1": [paragraphs[2]["id"], paragraphs[0]["id"]]}
    assert picked_judgments(record) == {paragraphs[2]["id"], paragraphs[0]["id"]}
    assert record["state"] == "evaluated" and validate(record, admitted, ctx) == record
    assert operations(model).count("core_research_judgment_pick") == 1


def test_an_unavailable_judgment_pick_keeps_the_six_and_marks_the_research_partial():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    record = retrieve(admitted, searcher(), ctx, model=Model(fail={"core_research_judgment_pick"}))
    paragraphs = [c["id"] for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "judgment"]
    assert record["judgment_picks"]["D1"]["state"] == "unavailable"
    assert record["judgment_picks"]["D1"]["chosen"] == {"t2:w1": paragraphs[:6]}
    assert record["picks"]["D1"]["state"] == "evaluated"  # the provision pick is independent
    assert record["state"] == "partial" and validate(record, admitted, ctx) == record


def test_a_changed_judgment_pick_cannot_replay():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    record = retrieve(admitted, searcher(), ctx, model=Model(choose_judgments=lambda ids: ids[:1]))
    other = next(c["id"] for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "judgment"
                 and c["id"] not in record["judgment_picks"]["D1"]["chosen"]["t2:w1"])
    forged = deepcopy(record)
    forged["judgment_picks"]["D1"]["chosen"]["t2:w1"].append(other)
    with pytest.raises(ValueError, match="judgment pick"): validate(forged, admitted, ctx)
    missing = deepcopy(record)
    del missing["judgment_picks"]
    with pytest.raises(ValueError): validate(missing, admitted, ctx)


def test_saved_v7_records_replay_unchanged_and_admit_every_returned_judgment():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(why_it_matters=False, chronology=False), ctx, contract=PICKED_CONTRACT)
    record = one_pick(retrieve(accept(proposal(), ctx), searcher(), ctx, model=Model(choose_judgments=lambda ids: ids[:1])))
    saved = {key: value for key, value in record.items() if key != "judgment_picks"}
    saved.update(contract=PICKED_CONTRACT, plan=admitted)
    assert validate(saved, admitted, ctx) == saved
    assert picked_judgments(saved) is None
    judged = {r["id"] for r in answer_sources.build(ctx, saved).values() if r["kind"] == "judgment"}
    assert {c["id"] for c in saved["searches"]["t2:w1"]["candidates"] if c["kind"] == "judgment"} <= judged
    with pytest.raises(ValueError):
        validate({**saved, "contract": CONTRACT}, admitted, ctx)


def test_saved_v8_records_replay_unchanged_with_their_judgment_picks_and_parts():
    # Research v9 (16 Oct 2026) adds why each dispute matters; a v8 record keeps its shape.
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(why_it_matters=False, chronology=False), ctx, contract=JUDGMENT_PICKED_CONTRACT)
    record = one_pick(retrieve(accept(proposal(), ctx), searcher(), ctx, model=Model(choose_judgments=lambda ids: ids[:1])))
    saved = {**record, "contract": JUDGMENT_PICKED_CONTRACT, "plan": admitted}
    assert validate(saved, admitted, ctx) == saved
    assert picked_judgments(saved) == picked_judgments(record)
    with pytest.raises(ValueError):
        validate({**saved, "contract": CONTRACT}, admitted, ctx)


def test_a_v9_dispute_says_why_it_matters():
    ctx = context("Find the applicable law.")
    assert accept(proposal(), ctx)["proposal"]["understanding"]["disputes"][0]["why_it_matters"]
    with pytest.raises(SchemaViolation, match="why_it_matters"):
        accept(proposal(why_it_matters=False), ctx)
    with pytest.raises(SchemaViolation, match="undeclared"):
        accept(proposal(chronology=False), ctx, contract=JUDGMENT_PICKED_CONTRACT)


def test_shown_ids_alone_count_and_an_unknown_id_marks_the_research_partial():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    record = retrieve(admitted, searcher(), ctx, model=Model(choose=lambda ids: [ids[0], "Q1.99", "Q7.1", "Q1.0"]))
    assert len(record["picks"]["D1"]["chosen"]["t2:w1"]) == 1
    assert record["picks"]["D1"]["unknown"] == ["Q1.99", "Q7.1", "Q1.0"] and record["state"] == "partial"
    assert validate(record, admitted, ctx) == record


def test_an_unavailable_pick_keeps_each_questions_first_six_provisions():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    record = retrieve(admitted, searcher(), ctx, model=Model(fail={"core_research_pick"}))
    provisions = [c["id"] for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "provision"]
    assert record["picks"]["D1"]["state"] == "unavailable" and record["picks"]["D1"]["chosen"] == {"t2:w1": provisions[:6]}
    assert record["state"] == "partial" and validate(record, admitted, ctx) == record


def test_a_changed_pick_cannot_replay():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    record = retrieve(admitted, searcher(), ctx, model=Model(choose=lambda ids: ids[:1]))
    other = next(c["id"] for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "provision"
                 and c["id"] not in record["picks"]["D1"]["chosen"]["t2:w1"])
    forged = deepcopy(record)
    forged["picks"]["D1"]["chosen"]["t2:w1"].append(other)
    with pytest.raises(ValueError, match="pick"): validate(forged, admitted, ctx)
    missing = deepcopy(record)
    del missing["picks"]
    with pytest.raises(ValueError): validate(missing, admitted, ctx)


@pytest.mark.parametrize("failure", [SearchUnavailable("Unread work"), RuntimeError("Adapter failed"),
                                   KeyError("missing snapshot field")])
def test_searches_bind_queries_and_preserve_independent_work_when_one_fails(failure):
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(2), ctx)
    found = searcher()
    original, seen = found.search, []

    def search(queries, instruments=None, **kw):
        seen.append(queries)
        # The questions run side by side, so the failing one is named, not taken by turn.
        if queries[0]["query_id"].startswith("t2:w1:"): raise failure
        return original(queries, instruments, **kw)

    found.search = search
    record = retrieve(admitted, found, ctx, model=Model())
    assert len(seen) == 2 and record["state"] == "partial"
    assert set(record["searches"]) == {"t2:w2"} and set(record["failures"]) == {"t2:w1"}
    assert set(record["picks"]["D1"]["chosen"]) == {"t2:w2"}
    assert validate(record, admitted, ctx) == record
    broken = deepcopy(record)
    broken["failures"] = {}
    with pytest.raises(ValueError, match="disposition"): validate(broken, admitted, ctx)
    broken = deepcopy(record)
    broken["searches"]["t2:w2"]["queries"][0]["context"] = "Qualification dropped"
    with pytest.raises(ValueError): validate(broken, admitted, ctx)


def test_unconfigured_search_is_a_gap_and_not_empty_success():
    ctx = context("Find the applicable law.")
    record = retrieve(accept(proposal(), ctx), None, ctx, model=Model())
    assert record["state"] == "partial" and record["failures"] and record["picks"]["D1"]["state"] == "not_needed"
    assert record["judgment_picks"]["D1"]["state"] == "not_needed"


def test_questions_are_searched_side_by_side_each_as_alone_and_reported_as_each_finishes():
    """Step 1 (owner, 20 Oct 2026): the matter's questions run at once, each finding exactly what
    it finds searched alone, kept in the plan's order, the count reported as each finishes."""
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(3), ctx)
    found, together = searcher(), threading.Barrier(3, timeout=10)
    original = found.search

    def search(queries, instruments=None, **kw):
        together.wait()  # all three in flight at once, or this fails
        return original(queries, instruments, **kw)

    found.search = search
    seen = []
    record = retrieve(admitted, found, ctx, model=Model(), progress=lambda stage, **detail: seen.append((stage, detail)))
    alone = searcher()
    assert record["searches"] == {work["id"]: alone.search(search_queries(work), search_instruments(work),
                                                           results={"provision": PROVISIONS_FOR_PICK})
                                  for work in admitted["work"]}
    assert list(record["searches"]) == [work["id"] for work in admitted["work"]] and not record["failures"]
    assert [detail for stage, detail in seen if stage == "searching"] == [
        {"done": 0, "total": 3}, {"done": 1, "total": 3}, {"done": 2, "total": 3}]
    assert validate(record, admitted, ctx) == record


def test_replay_rebinds_source_provenance_to_original_context():
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    record = retrieve(admitted, None, ctx, model=Model())
    for damage in ("text", "speaker", "start", "record_role"):
        changed = deepcopy(admitted)
        changed["work"][0]["sources"][0][damage] = "unowned alteration"
        forged = {**record, "plan": changed}
        with pytest.raises(ValueError, match="original sources"): validate(forged, changed, ctx)


@pytest.mark.parametrize("failure", [None, {"stage": "saved", "reason": "ok"},
                                   {"stage": "search", "reason": ""}])
def test_malformed_failed_work_receipt_cannot_pass_replay(failure):
    ctx = context("Find the applicable law.")
    admitted = accept(proposal(), ctx)
    record = retrieve(admitted, None, ctx, model=Model())
    record["failures"]["t2:w1"] = failure
    with pytest.raises(ValueError): validate(record, admitted, ctx)


def test_phrases_for_a_question_that_does_not_exist_are_held_as_an_issue():
    subject = proposal()
    subject["judgment_phrases"].append({"question_id": "D9Q9", "phrases": [{"kind": "issue", "text": "stray"}]})
    admitted = accept(subject, context("Find the applicable law."))
    assert [w["question_id"] for w in admitted["work"]] == ["D1Q1"]
    assert any("Judgment phrases name no question" in issue["mismatch"] for issue in admitted["issues"])


# --- earlier plan versions replay -----------------------------------------------------

def test_v6_plans_keep_their_source_selection_and_queries():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account",
               "text": "The other party alleges authorisation; our client denies it.\nThe original record is not supplied."}
    ctx = context("Examine the position conditionally. Keep the allegation disputed; do not contact anyone.", [earlier])
    item = work(None)
    item["sources"].append({"source_id": earlier["source_id"], "quote": None})
    item["search_account"] = [{"source_id": earlier["source_id"], "quote": None}]
    admitted = accept({"work": [item]}, ctx, contract=V6)
    assert admitted["issues"] == [] and admitted["proposal"]["work"][0]["sources"] == item["sources"]
    for selected, original in zip(admitted["work"][0]["sources"], [ctx["latest"], earlier], strict=True):
        assert selected == {**original, "start": 0, "end": len(original["text"])}
    queries = search_queries(admitted["work"][0], contract=V6)
    assert queries[0]["text"] == queries[0]["context"] == earlier["text"]
    assert [q["query_id"] for q in queries] == ["t2:w1:original", "t2:w1:q1", "t2:w1:q2", "t2:w1:rule"]
    assert search_instruments(admitted["work"][0], contract=V6) == []


def test_v6_explicit_changed_quote_is_held_while_complete_source_peer_survives():
    ctx = context("the requested review remains conditional; the allegation is disputed.")
    damaged = work("The requested review remains conditional")
    admitted = accept({"work": [damaged, work(None)]}, ctx, contract=V6)
    assert [item["id"] for item in admitted["work"]] == ["t2:w2"]
    assert "exact" in admitted["issues"][0]["mismatch"]


@pytest.mark.parametrize("role,speaker", [("nm_interpretation", "nm"), ("service", "service")])
def test_v6_nonoriginal_search_basis_cannot_hide_independent_valid_work(role, speaker):
    previous = {"source_id": "old", "turn_id": "t1", "speaker": speaker,
                "record_role": role, "text": "A prior derived explanation."}
    ctx = context("Review this explanation against my account.", [previous])
    bad, good = work(None), work(None)
    bad["search_account"] = [{"source_id": "old", "quote": None}]
    admitted = accept({"work": [bad, good]}, ctx, contract=V6)
    assert [w["id"] for w in admitted["work"]] == ["t2:w2"]
    assert "original advocate" in admitted["issues"][0]["mismatch"]


def test_saved_v6_records_replay_and_cannot_pass_as_v7():
    from nm.core_engine import retrieval
    ctx = context("Find the applicable law.")
    admitted = accept({"work": [work(instruments=["Indian Contract Act"])]}, ctx, contract=V6)
    queries = search_queries(admitted["work"][0], contract=V6)
    instruments = search_instruments(admitted["work"][0], contract=V6)
    searched = HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")}).search(queries, instruments)
    searched["contract"] = retrieval.NAMED_CONTRACT
    for field in ("connected", "connections", "links"):  # search v9 added them (P32)
        del searched[field]
    record = {"contract": V6, "plan": admitted, "searches": {"t2:w1": searched}, "failures": {}, "state": "evaluated"}
    assert validate(record, admitted, ctx) == record
    assert answer_sources.build(ctx, record)  # earlier records admit every returned provision
    with pytest.raises(ValueError):
        validate({**record, "contract": CONTRACT}, admitted, ctx)


def test_original_queries_preserve_order_boundaries_and_repeated_words_across_turns():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account", "text": "The account remains disputed."}
    ctx = context("The account remains disputed.", [earlier])
    item = work(None)
    item["search_account"] = [item["sources"][0],
        {"source_id": "t1:advocate", "quote": None}, item["sources"][0]]
    admitted = accept({"work": [item]}, ctx, contract=V6)
    account = admitted["work"][0]["search_account"]
    assert [s["turn_id"] for s in account] == ["t1", "t2"]
    query = search_queries(admitted["work"][0], contract=V6)[0]
    assert query["text"] == earlier["text"] + "\n\n" + ctx["latest"]["text"]
    assert "Advocate passage" not in query["text"] and query["text"] == query["context"]
    from nm.core_engine.research import WINDOWED_CONTRACT
    previous = search_queries(admitted["work"][0], contract=WINDOWED_CONTRACT)[0]
    assert "Advocate passage 1:" in previous["text"] and "Advocate passage 2:" in previous["text"]


def test_v6_concepts_are_not_silently_truncated():
    ctx = context("Explain the legal relationship in general.")
    item = work(None)
    item["search_account"] = []
    admitted = accept({"work": [item]}, ctx, contract=V6)
    queries = search_queries(admitted["work"][0], contract=V6)
    assert len(queries) == 3 and all(q["context"] == "" for q in queries)  # two enquiries and the rule probe
    item["enquiries"] *= 4
    rejected = accept({"work": [item]}, ctx, contract=V6)
    assert rejected["work"] == [] and rejected["issues"]


def test_offered_passage_id_resolves_original_spelling_offsets_and_ownership():
    from nm.core_engine.research import _source_windows
    ctx = context("Hello. Separately, the technician retains the drive. The client disputes a right to retain it.")
    _, _, offered = _source_windows(ctx)
    item = work(None)
    item["search_account"] = [{"source_id": p["source_id"], "quote": None} for p in offered[1:]]
    admitted = accept({"work": [item]}, ctx, contract=V6)
    assert admitted["issues"] == []
    for source in admitted["work"][0]["search_account"]:
        assert source["source_id"] == ctx["latest"]["source_id"]
        assert source["text"] == ctx["latest"]["text"][source["start"]:source["end"]]
    query = search_queries(admitted["work"][0], contract=V6)[0]["text"]
    assert "Hello." not in query and "Separately, the technician" in query


def test_saved_v5_plans_and_searches_replay_without_named_instruments():
    from nm.core_engine import retrieval
    from nm.core_engine.research import ACCOUNT_CONTRACT
    ctx = context("Find the applicable law.")
    admitted = accept({"work": [v5_work()]}, ctx, contract=ACCOUNT_CONTRACT)
    assert search_instruments(admitted["work"][0], contract=ACCOUNT_CONTRACT) is None
    queries = search_queries(admitted["work"][0], contract=ACCOUNT_CONTRACT)
    searched = HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")}).search(queries)
    searched["contract"] = retrieval.RERANK_ORDER_CONTRACT
    for field in ("instruments", "connected", "connections", "links"):
        del searched[field]
    record = {"contract": ACCOUNT_CONTRACT, "plan": admitted, "searches": {"t2:w1": searched},
              "failures": {}, "state": "evaluated"}
    assert validate(record, admitted, ctx) == record
    current = accept({"work": [v5_work()]}, ctx, contract=V6)  # a v6 plan must state its analysis and instruments
    assert current["work"] == [] and current["issues"]


@pytest.mark.parametrize("kinds,runs", [(["courtesy"], False), (["courtesy", "restriction"], False),
                                        (["courtesy", "information"], True), (["request"], True)])
def test_the_loop_is_spared_only_when_the_message_carries_no_information_or_request(kinds, runs):
    model = Model()
    interpretation = {"units": [{"kind": kind} for kind in kinds], "issues": []}
    admitted = plan(model, context("Find the applicable law."), interpretation)
    assert bool(model.calls) is runs
    if not runs:
        assert admitted["work"] == [] and admitted["proposal"]["understanding"]["needs_research"] is False


def test_an_interpretation_with_issues_never_spares_the_loop():
    model = Model()
    plan(model, context("Find the applicable law."), {"units": [{"kind": "courtesy"}], "issues": ["unchecked"]})
    assert model.calls


def test_served_v4_research_record_replays_with_its_labelled_queries():
    from pathlib import Path
    from nm.core_engine.research import WINDOWED_CONTRACT
    root = (Path(__file__).resolve().parents[1] / "outputs/core-engine-build-20261010"
            / "browser-gpt6-cache-v1-diagnostics/0842eaae89c44f4093705de0664dd9eb")
    saved = json.loads((root / "008-research-retrieve-input.json").read_text(encoding="utf-8"))["value"]
    record = json.loads((root / "009-research-retrieve-output.json").read_text(encoding="utf-8"))["value"]["result"]
    assert record["contract"] == WINDOWED_CONTRACT
    assert validate(record, record["plan"], saved["context"]) == record
    labelled = [q for s in record["searches"].values() for q in s["queries"] if "Advocate passage 1:" in q["text"]]
    assert labelled, "the served v4 serialisation is preserved, not rebuilt"


def test_real_frozen_v2_search_replays_without_new_query_construction():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "outputs/core-engine-build-20261010"
    captured = json.loads((root / "live-served-capacity-remeasurement-writer-1-input.json").read_text(encoding="utf-8"))
    record = captured["research"]
    assert record["contract"] == "core_research_v2"
    assert validate(record, record["plan"], captured["context"]) == record
    unknown = {**record, "contract": "unknown_research_version"}
    with pytest.raises(ValueError, match="Unknown"): validate(unknown, record["plan"], captured["context"])
    changed = deepcopy(record)
    first = next(iter(changed["searches"].values()))
    first["queries"][0]["text"] += " unowned addition"
    with pytest.raises(ValueError): validate(changed, changed["plan"], captured["context"])


