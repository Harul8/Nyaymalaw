"""The points read are weighed for the advice as a step of their own, checked by a second call, and the weighing reaches the answer
(plan AN.33, D19 and D21 (3); research v14; piece 33h).

The owner, 1 Nov 2026: "how do we ensure all these and in principle all the legally important details are extracted and considered
by NM?" Once the papers are read and the matter understood, one call weighs every point that matters - the dispute it bears on,
whether it helps or hurts the client, how much (critical or material; a point not weighed is background) and why, the legal question
a critical point raises that no question covers, or that it is a fact for the advocate - and a second call checks the weighing; code
keeps only what names a point and a dispute of the plan. The writer and the review are given each point's weight; the rounds of
repair count the points weighed and the facts; the table of what the papers record and the board mark them. The papers are invented.
"""
import json
import re

import pytest

from nm.core_engine import answer_sections, research, response_rendering, response_review, response_writer
from nm.core_engine.research import WEIGH, WEIGH_CHECK, weigh
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import _result, understanding
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import items_of, matter

pytestmark = pytest.mark.class_a


class Weighing:
    """Answers the weighing and its check from `weights` and `corrections` (a failure where either is "fail"); keeps what it was
    shown."""

    def __init__(self, weights, corrections=()):
        self.weights, self.corrections, self.seen = weights, corrections, []

    def context_budget(self, tier):
        return 10 ** 9

    def structured(self, prompt, schema, tier, **kwargs):
        self.seen.append(prompt)
        given = self.weights if prompt.operation == "core_research_weigh" else self.corrections
        if given == "fail":
            raise SchemaViolation("scripted failure")
        key = "weights" if prompt.operation == "core_research_weigh" else "corrections"
        return _result({key: list(given)}, tier)


def weight(identity, dispute="D1", effect="hurts", level="critical", why="It decides the claim.", question="", for_advocate=False):
    return {"id": identity, "dispute": dispute, "effect": effect, "weight": level, "why": why, "question": question,
            "for_advocate": for_advocate}


def points():
    ctx, record, sources = matter()
    proposal = record["plan"]["proposal"]
    return ctx, proposal, proposal["chronology"], proposal.get("connections", [])


def test_one_call_weighs_the_points_shown_by_id_with_the_disputes_and_a_second_checks_it():
    ctx, proposal, events, together = points()
    first, second = events[0]["id"], events[1]["id"]
    model = Weighing([weight(first), weight("E99"), weight(second, dispute="D9"), weight(first, level="material")],
                     [weight(second, level="material", effect="helps", why="It supports the client.")])
    weights, failures = weigh(model, ctx, proposal["understanding"], events, together)
    asked, checked = model.seen
    assert (asked.operation, asked.system, checked.operation, checked.system) == (
        "core_research_weigh", WEIGH, "core_research_weigh_check", WEIGH_CHECK)
    assert all(f'"id": "{event["id"]}"' in asked.user for event in events) and "Dispute D1:" in asked.user
    assert checked.user.startswith(asked.user) and json.loads(checked.user[checked.user.rindex("\n\n{") + 2:])["weights"] == [
        {**weight(first)}], "the check is shown the weighing code kept"
    assert [(w["id"], w["weight"], w["effect"], w["checked"]) for w in weights] == [
        (first, "critical", "hurts", "kept"), (second, "material", "helps", "added")]
    assert [failure["reason"] for failure in failures] == ["entry 2 names no point or no dispute of the plan",
                                                         "entry 3 names no point or no dispute of the plan"]


def test_the_check_may_change_a_weight_or_take_a_point_out_and_a_failure_says_so():
    ctx, proposal, events, together = points()
    first, second = events[0]["id"], events[1]["id"]
    changed, _ = weigh(Weighing([weight(first), weight(second)], [weight(first, level="background"),
                                                                    weight(second, effect="both")]),
                       ctx, proposal["understanding"], events, together)
    assert [(w["id"], w["effect"], w["checked"]) for w in changed] == [(second, "both", "changed")], "background leaves the weighing"
    unchecked, failures = weigh(Weighing([weight(first)], "fail"), ctx, proposal["understanding"], events, together)
    assert [(w["id"], w["checked"]) for w in unchecked] == [(first, "unchecked")] and failures == [
        {"step": "weigh_check", "reason": "SchemaViolation"}]
    none, failures = weigh(Weighing("fail"), ctx, proposal["understanding"], events, together)
    assert none == [] and failures == [{"step": "weigh", "reason": "SchemaViolation"}], "every point is then unweighed, and said so"


def test_the_plan_keeps_the_weighing_and_refuses_a_weight_that_names_no_point():
    from tests.test_the_plan_records_the_chronology import Beside, bundle

    class Weighed(Beside):
        def structured(self, prompt, schema, tier, **kwargs):
            if prompt.operation == "core_research_weigh":
                self.calls.append(prompt)
                return _result({"weights": [weight("E1")]}, tier)
            if prompt.operation == "core_research_weigh_check":
                self.calls.append(prompt)
                return _result({"corrections": []}, tier)
            return super().structured(prompt, schema, tier, **kwargs)
    ctx = bundle()
    record = research.plan(Weighed(), ctx)
    proposal = record["proposal"]
    assert [(w["id"], w["checked"]) for w in proposal["weights"]] == [("E1", "kept")] and proposal["weighing_failures"] == []
    assert research.accept(proposal, ctx)["issues"] == record["issues"]
    with pytest.raises(SchemaViolation, match="names no point"):
        research.accept({**proposal, "weights": [{**proposal["weights"][0], "id": "E99"}]}, ctx)
    unweighed = research.accept({**proposal, "weights": [], "weighing_failures": [{"step": "weigh", "reason": "SchemaViolation"}]},
                                ctx)
    assert "the weighing of the points unavailable: weigh SchemaViolation" in [issue["mismatch"] for issue in unweighed["issues"]]


def test_the_writer_and_the_review_are_given_each_points_weight_and_told_what_it_means():
    ctx, record, sources = matter()
    proposal = record["plan"]["proposal"]
    first = proposal["chronology"][0]["id"]
    proposal["weights"] = [{**weight(first, for_advocate=True), "checked": "kept"}]
    items = {item["id"]: item for item in items_of(record, ctx, sources)}
    assert {key: items[first][key] for key in ("weight", "effect", "dispute", "for_advocate")} == {
        "weight": "critical", "effect": "hurts", "dispute": "D1", "for_advocate": True}
    assert all("weight" not in item for key, item in items.items() if key != first)
    offered = {tag: alias for alias, tag in __import__("nm.core_engine.answer_sources", fromlist=["x"]).aliases(sources).items()}
    shown = {item["id"]: item for item in response_writer._coverage_shown(record, offered, ctx, compact=True)}
    assert shown[first] == {"id": first, "kind": proposal["chronology"][0]["kind"], "weight": "critical", "effect": "hurts",
                            "dispute": "D1", "for_advocate": True}
    writer = " ".join(response_writer.SYSTEM_V14.split())
    assert ("An item with a weight is one the weighing of the points found critical or material to the dispute it names, helping or "
            "hurting the client (effect); take up each critical one that bears on your part, and one marked for_advocate as a fact for "
            "the advocate to act on") in writer
    review = " ".join(response_review.SYSTEM_V12.split())
    assert "An item the weighing of the points marks critical (weight) for the dispute the piece is about is one whose absence weakens it" in review


def test_once_the_points_are_weighed_the_rounds_count_those_weighed_and_the_facts(monkeypatch):
    ctx, record, sources = matter()
    proposal = record["plan"]["proposal"]
    layout = response_writer.parts(record)
    monkeypatch.setattr(answer_sections, "ROUND_ITEMS", 1)
    everything = answer_sections.rounds(record, layout, ctx)
    proposal["weights"] = [{**weight(proposal["chronology"][0]["id"]), "checked": "kept"}]
    counted = len([item for item in items_of(record, ctx, sources) if "weight" in item or item["kind"] == "fact"])
    assert counted < len(items_of(record, ctx, sources))
    assert answer_sections.rounds(record, layout, ctx) == min(answer_sections.MAX_ROUNDS, 1 + max(0, counted - 1)) < everything


def test_the_table_and_the_board_mark_a_point_weighed_with_its_disputes_name():
    from nm.core_engine import matter_board
    ctx, record, sources = matter()
    proposal = record["plan"]["proposal"]
    first = proposal["chronology"][0]["id"]
    proposal["weights"] = [{**weight(first), "checked": "kept"}]
    name = proposal["understanding"]["disputes"][0]["name"]
    rows = {row["id"]: row for row in response_rendering.papers_record(record, ctx)["events"]}
    assert (rows[first]["weight"], rows[first]["effect"], rows[first]["dispute"]) == ("critical", "hurts", name)
    assert all("weight" not in row for key, row in rows.items() if key != first)
    papers = {}
    for row in ctx["documents"]:
        papers.setdefault(row["source_id"].rsplit("p", 1)[0], {"name": row["document"]["name"], "pages": []})["pages"].append(
            {"number": row["document"]["page"], "read_by": "local", "text": row["text"]})
    saved = [{"turn_id": "t1", "documents": list(papers.values())}]
    board = {event["id"]: event for event in matter_board._timeline(record, saved)["events"]}
    assert (board[first]["weight"], board[first]["dispute"]) == ("critical", name)
    page = (__import__("pathlib").Path(__file__).resolve().parents[1] / "nm" / "app" / "app.js").read_text(encoding="utf-8")
    assert "'Critical' : 'Material'" in page, "the page says the weight beside the point"


def test_a_critical_point_no_question_covers_raises_one_that_is_researched_and_one_for_the_advocate_raises_none():
    from tests.test_the_plan_records_the_chronology import Beside, bundle

    class Raising(Beside):
        def structured(self, prompt, schema, tier, **kwargs):
            if prompt.operation in ("core_research_weigh", "core_research_weigh_check"):
                self.calls.append(prompt)
                return _result({"weights": [weight("E1", question="Whether the sale after the death binds the heirs?"),
                                            weight("E2", level="critical", question="Not a question of law.", for_advocate=True)]}
                               if prompt.operation == "core_research_weigh" else {"corrections": []}, tier)
            if prompt.operation in ("core_research_phrases", "core_research_judgment_phrases") and "D1Q2" in prompt.user:
                self.calls.append(prompt)
                asked = re.findall(r"^- (\S+): ", prompt.user, re.M)
                kind = "rule" if prompt.operation == "core_research_phrases" else "issue"
                return _result({"questions": [{"question_id": q, "phrases": [{"kind": kind, "text": f"law on {q}"}],
                                               **({"acts": []} if kind == "rule" else {})} for q in asked]}, tier)
            return super().structured(prompt, schema, tier, **kwargs)
    ctx = bundle()
    model = Raising()
    record = research.plan(model, ctx)
    proposal = record["proposal"]
    [dispute] = proposal["understanding"]["disputes"]
    assert [q["id"] for q in dispute["legal_questions"]] == ["D1Q1", "D1Q2"]
    raised = dispute["legal_questions"][1]
    assert (raised["question"], raised["why_needed"]) == ("Whether the sale after the death binds the heirs?", "It decides the claim.")
    by_point = {w["id"]: w for w in proposal["weights"]}
    assert (by_point["E1"]["question_id"], by_point["E2"]["question_id"]) == ("D1Q2", ""), "a fact for the advocate raises no question"
    phrased = [p for p in model.calls if p.operation in ("core_research_phrases", "core_research_judgment_phrases") and "D1Q2" in p.user]
    assert len(phrased) == 2 and all("D1Q1" not in p.user for p in phrased), "only the new question is phrased again"
    assert [w["question_id"] for w in record["work"]] == ["D1Q1", "D1Q2"], "and it is researched with the rest"
    assert not [issue for issue in record["issues"] if "D1Q2" in issue["mismatch"]], "the new question has its search phrases"
    with pytest.raises(SchemaViolation, match="names a question its dispute does not hold"):
        research.accept({**proposal, "weights": [{**proposal["weights"][0], "question_id": "D9Q1"}, proposal["weights"][1]]}, ctx)


def test_the_check_of_the_weighing_may_write_as_much_as_a_papers_reading():
    # The measuring run of 1 Nov 2026 weighed 105 points; its check, reasoning at high, ran out of its 16,000 tokens (OutputTruncated)
    # and the weighing was kept unchecked, as designed. It may now write as much as a paper's reading.
    assert research.MAX_OUTPUT["weigh_check"] == research.MAX_OUTPUT["chronology"] == 32000
    assert research.MAX_OUTPUT["weigh"] == 24000
