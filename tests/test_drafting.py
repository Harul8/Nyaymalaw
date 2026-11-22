"""Plan AN.67, D323 (piece 23a): a document drafted part by part from a versioned template on the shared loop runner, code's checks
of every part, the rewrite of the parts at fault, the saved draft checked again from what it kept, and the draft as shown.

The template and the matter are invented for the test; no template is held until the owner agrees one (AN.67)."""
from copy import deepcopy
import json

import pytest

from nm.core_engine import answer_sources, drafting
from nm.core_engine import rounds as runner
from nm.core_engine.calls import StopRequested
from nm.core_engine.research import accept, retrieve
from nm.core_engine.retrieval import HybridSearcher
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelError, ModelResult, SchemaViolation, Tier, Usage
from tests.test_core_answer_sources import AdjacentJudgment
from tests.test_core_research import Model as ResearchModel, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

MESSAGE = ("Draft the notice. The cheque for Rs. 50,000 drawn by Asha Verma came back unpaid on 10 January 2026, "
           "marked funds insufficient.")

TEMPLATE = {
    "id": "invented_demand_notice", "version": 1, "title": "Notice of demand",
    "law": {"act": "An invented Act", "sections": ["4"]},
    "parts": [
        {"id": "facts", "title": "Facts", "for": "What happened to the cheque, as the papers give it.",
         "particulars": [{"id": "amount", "said": "the cheque's amount"},
                         {"id": "returned_on", "said": "the day the cheque came back unpaid"}]},
        {"id": "demand", "title": "Demand", "for": "The demand made of the drawer, and where it is sent.",
         "particulars": [{"id": "drawer", "said": "the drawer's name"},
                         {"id": "address", "said": "the drawer's address"}]},
    ]}
HELD = {(TEMPLATE["id"], TEMPLATE["version"]): TEMPLATE}


@pytest.fixture(scope="module")
def matter():
    ctx = context(MESSAGE)
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    record = retrieve(accept(proposal(1), ctx), HybridSearcher({"provision": statute, "judgment": AdjacentJudgment()}), ctx,
                      model=ResearchModel())
    return ctx, answer_sources.build(ctx, record)


def facts(*, amount="Rs. 50,000", returned="10 January 2026", source="M1", cited=("M1", "P1")):
    return {"part_id": "facts", "paragraphs": [{
        "text": f"The cheque for {amount} was returned unpaid on {returned}, marked funds insufficient.",
        "source_ids": list(cited),
        "particulars": [{"particular_id": "amount", "words": amount, "source_id": source},
                        {"particular_id": "returned_on", "words": returned, "source_id": "M1"}],
        "missing": []}]}


def demand(*, address_given=False):
    text = "Asha Verma is called upon to pay the amount within the time the Act allows, at [[address]]."
    return {"part_id": "demand", "paragraphs": [{
        "text": text, "source_ids": ["M1"],
        "particulars": [{"particular_id": "drawer", "words": "Asha Verma", "source_id": "M1"}],
        "missing": ["address"]}]}


class Writer:
    """Answers each drafting call from a script, in order; an exception in the script is raised for its call."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def context_budget(self, tier):
        return 400_000

    def structured(self, prompt, schema, tier, **kwargs):
        self.calls.append((prompt, tier))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return ModelResult(None, deepcopy(answer), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def requested(call):
    return json.loads(call[0].user)


def test_a_draft_whose_parts_stand_is_complete_in_one_round(matter):
    ctx, sources = matter
    writer = Writer({"parts": [facts(), demand()]})
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.COMPLETE, "reason": None}
    assert len(record["rounds"]) == 1 and record["rounds"][0]["asked"] == ["facts", "demand"]
    assert [part["part_id"] for part in record["parts"]] == ["facts", "demand"]
    assert all(part["faults"] == [] for part in record["parts"])
    assert record["state"] == drafting.FOR_REVIEW
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    prompt, tier = writer.calls[0]
    assert prompt.operation == drafting.OPERATION and prompt.system == drafting.WRITER and tier is Tier.HARD
    assert prompt.effort == "medium"
    sent = requested(writer.calls[0])
    assert list(sent)[:3] == ["original_context", "held_law", "time_limits"] and "earlier_draft" not in sent
    assert [part["part_id"] for part in sent["document"]["parts"]] == ["facts", "demand"]
    assert prompt.user[:prompt.cache_through] == json.dumps({key: sent[key] for key in list(sent)[:3]},
                                                            ensure_ascii=False)[:-1]
    shown = drafting.shown(record)
    assert shown["parts"][1]["paragraphs"] == [
        "Asha Verma is called upon to pay the amount within the time the Act allows, at "
        "[particular needed: the drawer's address]."]
    assert shown["parts"][0]["title"] == "Facts" and shown["state"] == drafting.FOR_REVIEW


def test_code_finds_what_does_not_stand_and_only_the_part_at_fault_is_written_again(matter):
    ctx, sources = matter
    wrong = facts(amount="Rs. 5,00,000", returned="12 February 2026", cited=("M1", "P9"))
    writer = Writer({"parts": [wrong, demand()]}, {"parts": [facts()]})
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    first = record["rounds"][0]["faults"]
    assert first["demand"] == []
    found = " | ".join(first["facts"])
    assert "not offered: P9" in found
    assert "do not stand in M1: 'Rs. 5,00,000'" in found and "do not stand in M1: '12 February 2026'" in found
    assert "12 February 2026" in found and "Do not work out a date yourself" in found
    assert "Neither stated nor marked as missing: amount, returned_on." in found
    # The rewrite asks for the part at fault alone, shows it with its faults, at a repair's level, on the same cached prefix.
    assert record["rounds"][1]["asked"] == ["facts"]
    again = requested(writer.calls[1])
    assert [part["part_id"] for part in again["document"]["parts"]] == ["facts"]
    assert again["earlier_draft"] == [{"part_id": "facts", "paragraphs": wrong["paragraphs"], "faults": first["facts"]}]
    assert writer.calls[1][0].effort == "high"
    shared = writer.calls[0][0].cache_through
    assert shared == writer.calls[1][0].cache_through and writer.calls[0][0].user[:shared] == writer.calls[1][0].user[:shared]
    assert record["stopped"] == {"why": runner.COMPLETE, "reason": None}
    assert record["parts"][0]["paragraphs"] == facts()["paragraphs"] and record["parts"][0]["faults"] == []
    assert record["parts"][1]["paragraphs"] == demand()["paragraphs"]
    assert drafting.validate(record, ctx, sources, templates=HELD) is record


def test_a_part_left_out_given_twice_or_marked_wrongly_is_at_fault(matter):
    ctx, sources = matter
    unmarked = demand()
    unmarked["paragraphs"][0]["missing"] = []
    found = drafting._faults({"parts": [facts(), facts()]}, TEMPLATE, ["facts", "demand"], ctx, sources, None)
    assert found == {"facts": ["This part was not given once."], "demand": ["This part was not given once."]}
    found = drafting._faults({"parts": [unmarked, facts()]}, TEMPLATE, ["demand"], ctx, sources, None)
    assert list(found) == ["demand"]
    assert "marks ['address'] as missing but lists nothing" in found["demand"][0]
    assert found["demand"][1] == "Neither stated nor marked as missing: address."
    stray = demand()
    stray["paragraphs"][0]["particulars"].append({"particular_id": "amount", "words": "Rs. 50,000", "source_id": "M1"})
    assert "which is not a particular of this part" in " ".join(
        drafting._faults({"parts": [stray]}, TEMPLATE, ["demand"], ctx, sources, None)["demand"])
    # Words that stand in the passage cited but not in the paragraph are not stated.
    unstated = facts()
    unstated["paragraphs"][0]["text"] = "The cheque was returned unpaid on 10 January 2026."
    assert "does not state amount in the words given for it" in " ".join(
        drafting._faults({"parts": [unstated]}, TEMPLATE, ["facts"], ctx, sources, None)["facts"])


def test_the_rewrites_end_at_the_allowance_and_the_faults_left_are_kept(matter):
    ctx, sources = matter
    tries = [facts(amount=f"Rs. {n},000") for n in (1, 2, 3)]
    writer = Writer({"parts": [tries[0], demand()]}, {"parts": [tries[1]]}, {"parts": [tries[2]]})
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert len(writer.calls) == 1 + drafting.REWRITES
    assert record["stopped"]["why"] == runner.BACKSTOP and record["stopped"]["reason"]
    assert record["parts"][0]["paragraphs"] == tries[2]["paragraphs"] and record["parts"][0]["faults"]
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    assert drafting.shown(record)["parts"][0]["faults"] == record["parts"][0]["faults"]


def test_a_rewrite_that_changes_nothing_ends_the_rounds(matter):
    ctx, sources = matter
    wrong = facts(amount="Rs. 9,000")
    writer = Writer({"parts": [wrong, demand()]}, {"parts": [wrong]})
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.NOTHING_NEW, "reason": None} and len(writer.calls) == 2
    assert drafting.validate(record, ctx, sources, templates=HELD) is record


def test_a_writer_that_cannot_be_asked(matter):
    ctx, sources = matter
    with pytest.raises(ModelError, match="could not be written"):
        drafting.write(Writer(SchemaViolation("scripted")), TEMPLATE, ctx, sources)
    record = drafting.write(Writer({"parts": [facts(amount="Rs. 9,000"), demand()]}, ModelError("scripted")),
                            TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.UNAVAILABLE, "reason": "ModelError"} and len(record["rounds"]) == 1
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    with pytest.raises(StopRequested):
        drafting.write(Writer({"parts": [facts(amount="Rs. 9,000"), demand()]}, StopRequested("stopped")),
                       TEMPLATE, ctx, sources)


def _tampered(record, change):
    copy = deepcopy(record)
    change(copy)
    return copy


def test_a_saved_draft_is_read_only_as_its_rounds_leave_it(matter):
    ctx, sources = matter
    wrong = facts(amount="Rs. 5,00,000")
    record = drafting.write(Writer({"parts": [wrong, demand()]}, {"parts": [facts()]}), TEMPLATE, ctx, sources)
    assert drafting.validate(record, ctx, sources, templates=HELD) is record

    def other_template(r): r["template"]["title"] = "Another notice"
    # A proposal changed so that code finds it otherwise, and one changed so that its findings stay but its words do not.
    def proposal_changed(r): r["rounds"][0]["proposal"]["parts"][0] = facts()
    def words_changed(r): r["rounds"][1]["proposal"]["parts"][0]["paragraphs"][0]["text"] += " Paid."
    def faults_dropped(r): r["rounds"][0]["faults"]["facts"] = []
    def stop_changed(r): r["stopped"] = {"why": runner.BACKSTOP, "reason": "said"}
    def part_changed(r): r["parts"][1]["paragraphs"][0]["text"] = "Pay now."
    def round_added(r): r["rounds"].append(deepcopy(r["rounds"][1]))
    def asked_changed(r): r["rounds"][1]["asked"] = ["facts", "demand"]
    def malformed(r): r["rounds"][0]["proposal"]["parts"][0]["paragraphs"][0]["missing"] = "address"
    def no_rounds(r): r["rounds"] = []
    def state_changed(r): r["state"] = "sent"
    cases = {other_template: "not one NM holds", proposal_changed: "differs from what code finds",
             words_changed: "not as its rounds leave them",
             faults_dropped: "differs from what code finds", stop_changed: "does not end as its rounds do",
             part_changed: "not as its rounds leave them", round_added: "rounds end when nothing is left",
             asked_changed: "differs from what code finds", malformed: "form does not hold",
             no_rounds: "does not say how its rounds ended", state_changed: "not one this code reads"}
    for change, said in cases.items():
        with pytest.raises(ValueError, match=said):
            drafting.validate(_tampered(record, change), ctx, sources, templates=HELD)
    with pytest.raises(ValueError, match="not one NM holds"):
        drafting.validate(record, ctx, sources)


def test_a_template_names_its_parts_and_particulars_once():
    drafting.check_template(TEMPLATE)
    twice = deepcopy(TEMPLATE)
    twice["parts"][1]["id"] = "facts"
    renamed = deepcopy(TEMPLATE)
    renamed["parts"][1]["particulars"][0]["id"] = "amount"
    spaced = deepcopy(TEMPLATE)
    spaced["parts"][0]["particulars"][0]["id"] = "the amount"
    unsaid = deepcopy(TEMPLATE)
    unsaid["parts"][0]["for"] = " "
    for bad in (twice, renamed, spaced, unsaid, {**TEMPLATE, "version": "1"}, {**TEMPLATE, "parts": []},
                {k: v for k, v in TEMPLATE.items() if k != "law"}):
        with pytest.raises(ValueError):
            drafting.check_template(bad)
    assert drafting.TEMPLATES == {}


def test_the_writer_is_told_the_purpose_and_works_in_a_loop():
    assert "Purpose:" in drafting.WRITER and "Outcome:" in drafting.WRITER and "Work in a loop" in drafting.WRITER
    assert "[[its id]]" in drafting.WRITER and "work none out" in drafting.WRITER
