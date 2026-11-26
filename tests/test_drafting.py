"""Plan AN.67, D323 (pieces 23a to 23c): a document drafted part by part from a versioned template on the shared loop runner, code's
checks of every part, the independent review of the whole draft, the rewrite of the parts at fault and the review again, the saved
draft checked again from what it kept, and the draft as shown and as a Word file.

The first template and the matters are invented for the test. Piece 23d1 (D330): the held section 138 template, drafted from with
its set wording, its parts used only sometimes, the amount in words and its notes."""
import io
import json
import zipfile
from copy import deepcopy
from xml.etree import ElementTree

import pytest

from nm.core_engine import answer_sources, drafting
from nm.core_engine import rounds as runner
from nm.core_engine.calls import StopRequested
from nm.core_engine.research import accept, retrieve
from nm.core_engine.retrieval import HybridSearcher
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelError, ModelResult, SchemaViolation, Tier, Usage
from tests.test_core_answer_sources import AdjacentJudgment
from tests.test_core_research import Model as ResearchModel
from tests.test_core_research import proposal
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
#: A review that finds nothing.
NOTHING = {"findings": []}


@pytest.fixture(scope="module")
def matter():
    ctx = context(MESSAGE)
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    record = retrieve(accept(proposal(1), ctx), HybridSearcher({"provision": statute, "judgment": AdjacentJudgment()}), ctx,
                      model=ResearchModel())
    return ctx, answer_sources.build(ctx, record)


def facts(*, amount="Rs. 50,000", returned="10 January 2026", source="M1", cited=("M1", "P1"), close=", marked funds insufficient"):
    return {"part_id": "facts", "paragraphs": [{
        "text": f"The cheque for {amount} was returned unpaid on {returned}{close}.",
        "source_ids": list(cited),
        "particulars": [{"particular_id": "amount", "words": amount, "source_id": source},
                        {"particular_id": "returned_on", "words": returned, "source_id": "M1"}],
        "missing": []}]}


def demand(*, what="the amount"):
    text = f"Asha Verma is called upon to pay {what} within the time the Act allows, at [[address]]."
    return {"part_id": "demand", "paragraphs": [{
        "text": text, "source_ids": ["M1"],
        "particulars": [{"particular_id": "drawer", "words": "Asha Verma", "source_id": "M1"}],
        "missing": ["address"]}]}


def found(part_id, kind="leaves_out", said="", why="The demand does not say how much is demanded.", cited=("M1",)):
    return {"part_id": part_id, "kind": kind, "said": said, "why": why, "source_ids": list(cited)}


class Writer:
    """Answers each drafting call - writing or review - from a script, in order; an exception in the script is raised for its call."""

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


def kinds(record):
    return [entry["kind"] for entry in record["rounds"]]


def test_a_draft_whose_parts_stand_is_reviewed_whole_and_complete(matter):
    ctx, sources = matter
    writer = Writer({"parts": [facts(), demand()]}, NOTHING)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.COMPLETE, "reason": None}
    assert kinds(record) == [drafting.WRITING, drafting.REVIEW] and record["rounds"][0]["asked"] == ["facts", "demand"]
    assert [part["part_id"] for part in record["parts"]] == ["facts", "demand"]
    assert all(part["faults"] == [] and part["findings"] == [] for part in record["parts"])
    assert record["state"] == drafting.FOR_REVIEW and record["reviewed"] is True and record["beside"] == []
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    prompt, tier = writer.calls[0]
    assert prompt.operation == drafting.OPERATION and prompt.system == drafting.WRITER and tier is Tier.HARD
    assert prompt.effort == "medium"
    sent = requested(writer.calls[0])
    assert list(sent)[:3] == ["original_context", "held_law", "time_limits"] and "earlier_draft" not in sent
    assert [part["part_id"] for part in sent["document"]["parts"]] == ["facts", "demand"]
    assert prompt.user[:prompt.cache_through] == json.dumps({key: sent[key] for key in list(sent)[:3]},
                                                            ensure_ascii=False)[:-1]
    # The review reads the same conversation, held law and time limits first, then the whole document and the whole draft.
    looked, judged = writer.calls[1]
    assert looked.operation == drafting.REVIEW_OPERATION and looked.system == drafting.REVIEWER and judged is Tier.JUDGE
    assert looked.effort == "medium" and looked.user[:looked.cache_through] == prompt.user[:prompt.cache_through]
    reviewed = requested(writer.calls[1])
    assert list(reviewed) == ["original_context", "held_law", "time_limits", "document", "draft"]
    assert [part["part_id"] for part in reviewed["document"]["parts"]] == ["facts", "demand"]
    assert reviewed["draft"][1] == {"part_id": "demand", "paragraphs": [{
        "id": "demand.1", "text": "Asha Verma is called upon to pay the amount within the time the Act allows, at "
                                  "[particular needed: the drawer's address]."}]}
    shown = drafting.shown(record)
    assert shown["parts"][1]["paragraphs"] == [
        "Asha Verma is called upon to pay the amount within the time the Act allows, at "
        "[particular needed: the drawer's address]."]
    assert shown["parts"][0]["title"] == "Facts" and shown["state"] == drafting.FOR_REVIEW
    assert shown["parts"][0]["found"] == [] and shown["reviewed"] is None and shown["beside"] == []


def test_code_finds_what_does_not_stand_and_only_the_part_at_fault_is_written_again(matter):
    ctx, sources = matter
    wrong = facts(amount="Rs. 5,00,000", returned="12 February 2026", cited=("M1", "P9"))
    writer = Writer({"parts": [wrong, demand()]}, {"parts": [facts()]}, NOTHING)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    first = record["rounds"][0]["faults"]
    assert first["demand"] == []
    said = " | ".join(first["facts"])
    assert "not offered: P9" in said
    assert "do not stand in M1: 'Rs. 5,00,000'" in said and "do not stand in M1: '12 February 2026'" in said
    assert "12 February 2026" in said and "Do not work out a date yourself" in said
    assert "Neither stated nor marked as missing: amount, returned_on." in said
    # The rewrite asks for the part at fault alone, shows it with its faults, at a repair's level, on the same cached prefix; the
    # review comes only once code finds nothing.
    assert kinds(record) == [drafting.WRITING, drafting.WRITING, drafting.REVIEW] and record["rounds"][1]["asked"] == ["facts"]
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


def test_the_review_finds_what_code_cannot_and_the_parts_are_written_again_and_reviewed_again(matter):
    ctx, sources = matter
    framed = found("facts", kind="frames", said="was returned unpaid", why="The papers say the cheque came back unpaid.",
                   cited=("M1", "P9"))
    plain = facts(close="")
    asked = demand(what="the amount of the cheque, Rs. 50,000,")
    writer = Writer({"parts": [facts(), demand()]}, {"findings": [framed, found("demand")]},
                    {"parts": [plain, asked]}, NOTHING)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert kinds(record) == [drafting.WRITING, drafting.REVIEW, drafting.WRITING, drafting.REVIEW]
    admitted = record["rounds"][1]["findings"]
    # Code keeps the passages NM offered (P9 was not) and the words only where they stand in the part.
    assert admitted["facts"] == [{**framed, "source_ids": ["M1"]}] and admitted["demand"] == [found("demand")]
    # Both parts are written again, each told what the review found, at a repair's level.
    assert record["rounds"][2]["asked"] == ["facts", "demand"]
    again = requested(writer.calls[2])
    assert again["earlier_draft"][0]["faults"] == [
        "An independent review found that this part presents something otherwise than the papers or the advocate do "
        "(the words 'was returned unpaid'): The papers say the cheque came back unpaid. See M1."]
    assert again["earlier_draft"][1]["faults"][0].startswith("An independent review found that this part leaves out")
    assert writer.calls[2][0].effort == "high"
    # The rewritten draft is reviewed again, from the same cached prefix as the first review.
    first, second = writer.calls[1][0], writer.calls[3][0]
    assert second.operation == drafting.REVIEW_OPERATION and second.user[:second.cache_through] == first.user[:first.cache_through]
    assert [p["text"] for p in requested(writer.calls[3])["draft"][0]["paragraphs"]] == [plain["paragraphs"][0]["text"]]
    assert record["stopped"] == {"why": runner.COMPLETE, "reason": None}
    assert all(part["findings"] == [] for part in record["parts"]) and record["reviewed"] is True
    assert drafting.validate(record, ctx, sources, templates=HELD) is record


def test_what_code_admits_of_a_review():
    draft = {"facts": {"paragraphs": [{"text": "The cheque was returned unpaid."}], "faults": []},
             "demand": {"paragraphs": [{"text": "Pay the amount."}], "faults": []}}
    sources = {}
    returned = {"findings": [found("facts", said="was returned unpaid", cited=()),
                             found("facts", said="was dishonoured", cited=()),
                             found("elsewhere", cited=()), found("demand", why="  ", cited=())]}
    admitted, beside = drafting._admitted(returned, TEMPLATE, draft, sources)
    # Words that do not stand in the part are not taken as its words; the finding still stands, for the whole part.
    assert [item["said"] for item in admitted["facts"]] == ["was returned unpaid", ""]
    assert admitted["demand"] == []
    # A finding that names no part of the draft, or says no reason, is kept beside the draft and never acted on.
    assert [item["part_id"] for item in beside] == ["elsewhere", "demand"]


def test_findings_left_at_the_allowance_are_kept_for_the_advocate(matter):
    ctx, sources = matter
    tries = [facts(close=close) for close in (", marked funds insufficient", "", " for want of funds")]
    still = {"findings": [found("facts", kind="adds", why="The papers do not say why the cheque came back.")]}
    writer = Writer({"parts": [tries[0], demand()]}, still, {"parts": [tries[1]]}, still, {"parts": [tries[2]]}, still)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    # Code's checks and the review share the allowance; the last rewrite is reviewed too.
    assert kinds(record) == [drafting.WRITING, drafting.REVIEW] * (1 + drafting.REWRITES)
    assert record["stopped"]["why"] == runner.BACKSTOP and record["stopped"]["reason"]
    assert record["parts"][0]["paragraphs"] == tries[2]["paragraphs"] and record["parts"][0]["faults"] == []
    assert record["parts"][0]["findings"] and record["parts"][1]["findings"] == []
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    assert drafting.shown(record)["parts"][0]["found"] == [
        "An independent review found that this part states what nothing given bears out: The papers do not say why the cheque "
        "came back."]  # 23d3: on the page as in the Word file, without the IDs of passages


def test_the_rewrites_end_at_the_allowance_and_the_faults_left_are_kept(matter):
    ctx, sources = matter
    tries = [facts(amount=f"Rs. {n},000") for n in (1, 2, 3)]
    writer = Writer({"parts": [tries[0], demand()]}, {"parts": [tries[1]]}, {"parts": [tries[2]]}, NOTHING)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert len(writer.calls) == 1 + drafting.REWRITES + 1 and kinds(record)[-1] == drafting.REVIEW
    assert record["stopped"]["why"] == runner.BACKSTOP and record["stopped"]["reason"]
    assert record["parts"][0]["paragraphs"] == tries[2]["paragraphs"] and record["parts"][0]["faults"]
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    # 23d3: the page says a part is still at fault in the Word file's words; code's own words of each fault stay saved.
    assert drafting.shown(record)["parts"][0]["faults"] == [drafting.STILL_AT_FAULT]


def test_a_rewrite_that_changes_nothing_ends_the_rounds_once_the_draft_is_reviewed(matter):
    ctx, sources = matter
    wrong = facts(amount="Rs. 9,000")
    writer = Writer({"parts": [wrong, demand()]}, {"parts": [wrong]}, NOTHING)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.NOTHING_NEW, "reason": None} and len(writer.calls) == 3
    assert kinds(record) == [drafting.WRITING, drafting.WRITING, drafting.REVIEW]
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    # After a review, a rewrite that changes nothing ends the rounds with the review's findings kept.
    writer = Writer({"parts": [facts(), demand()]}, {"findings": [found("demand")]}, {"parts": [demand()]})
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.NOTHING_NEW, "reason": None} and record["parts"][1]["findings"]
    assert drafting.validate(record, ctx, sources, templates=HELD) is record


def test_a_writer_or_reviewer_that_cannot_be_asked(matter):
    ctx, sources = matter
    with pytest.raises(ModelError, match="could not be written"):
        drafting.write(Writer(SchemaViolation("scripted")), TEMPLATE, ctx, sources)
    record = drafting.write(Writer({"parts": [facts(amount="Rs. 9,000"), demand()]}, ModelError("scripted")),
                            TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.UNAVAILABLE, "reason": "ModelError"} and len(record["rounds"]) == 1
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    # A reviewer that cannot be asked leaves the draft as written, and the advocate is told it was not reviewed.
    record = drafting.write(Writer({"parts": [facts(), demand()]}, SchemaViolation("scripted")), TEMPLATE, ctx, sources)
    assert record["stopped"] == {"why": runner.UNAVAILABLE, "reason": "SchemaViolation"} and record["reviewed"] is False
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    assert drafting.shown(record)["reviewed"] == drafting.NOT_REVIEWED
    with pytest.raises(StopRequested):
        drafting.write(Writer({"parts": [facts(amount="Rs. 9,000"), demand()]}, StopRequested("stopped")),
                       TEMPLATE, ctx, sources)
    with pytest.raises(StopRequested):
        drafting.write(Writer({"parts": [facts(), demand()]}, StopRequested("stopped")), TEMPLATE, ctx, sources)


def _tampered(record, change):
    copy = deepcopy(record)
    change(copy)
    return copy


def test_a_saved_draft_is_read_only_as_its_rounds_leave_it(matter):
    ctx, sources = matter
    wrong = facts(amount="Rs. 5,00,000")
    record = drafting.write(Writer({"parts": [wrong, demand()]}, {"parts": [facts()]}, {"findings": [found("demand")]},
                                   {"parts": [demand(what="the amount of the cheque")]}, NOTHING), TEMPLATE, ctx, sources)
    assert kinds(record) == [drafting.WRITING, drafting.WRITING, drafting.REVIEW, drafting.WRITING, drafting.REVIEW]
    assert drafting.validate(record, ctx, sources, templates=HELD) is record

    def other_template(r): r["template"]["title"] = "Another notice"
    # A proposal changed so that code finds it otherwise, and one changed so that its findings stay but its words do not.
    def proposal_changed(r): r["rounds"][0]["proposal"]["parts"][0] = facts()
    def words_changed(r): r["rounds"][1]["proposal"]["parts"][0]["paragraphs"][0]["text"] += " Paid."
    def faults_dropped(r): r["rounds"][0]["faults"]["facts"] = []
    def findings_dropped(r): r["rounds"][2]["findings"]["demand"] = []
    def review_moved(r): r["rounds"][2]["returned"]["findings"][0]["part_id"] = "elsewhere"
    def kind_changed(r): r["rounds"][2]["kind"] = drafting.WRITING
    def stop_changed(r): r["stopped"] = {"why": runner.BACKSTOP, "reason": "said"}
    def part_changed(r): r["parts"][1]["paragraphs"][0]["text"] = "Pay now."
    def round_added(r): r["rounds"].append(deepcopy(r["rounds"][1]))
    def review_removed(r): del r["rounds"][4]
    def asked_changed(r): r["rounds"][1]["asked"] = ["facts", "demand"]
    def malformed(r): r["rounds"][0]["proposal"]["parts"][0]["paragraphs"][0]["missing"] = "address"
    def no_rounds(r): r["rounds"] = []
    def state_changed(r): r["state"] = "sent"
    def said_reviewed(r): r["reviewed"] = False
    cases = {other_template: "not one NM holds", proposal_changed: "differs from what code finds",
             words_changed: "not as its rounds leave them",
             faults_dropped: "differs from what code finds", findings_dropped: "differs from what code finds",
             review_moved: "differs from what code finds", kind_changed: "not the one its rounds before call for",
             stop_changed: "does not end as its rounds do",
             part_changed: "not as its rounds leave them", round_added: "go on after they ended",
             review_removed: "does not end as its rounds do",
             asked_changed: "differs from what code finds", malformed: "form does not hold",
             no_rounds: "does not say how its rounds ended", state_changed: "not one this code reads",
             said_reviewed: "not as its rounds leave them"}
    for change, said in cases.items():
        with pytest.raises(ValueError, match=said):
            drafting.validate(_tampered(record, change), ctx, sources, templates=HELD)
    with pytest.raises(ValueError, match="not one NM holds"):
        drafting.validate(record, ctx, sources)


def test_a_part_left_out_given_twice_or_marked_wrongly_is_at_fault(matter):
    ctx, sources = matter
    unmarked = demand()
    unmarked["paragraphs"][0]["missing"] = []
    faults = drafting._faults({"parts": [facts(), facts()]}, TEMPLATE, ["facts", "demand"], ctx, sources, None)
    assert faults == {"facts": ["This part was not given once."], "demand": ["This part was not given once."]}
    faults = drafting._faults({"parts": [unmarked, facts()]}, TEMPLATE, ["demand"], ctx, sources, None)
    assert list(faults) == ["demand"]
    assert "marks ['address'] as missing but lists nothing" in faults["demand"][0]
    assert faults["demand"][1] == "Neither stated nor marked as missing: address."
    stray = demand()
    stray["paragraphs"][0]["particulars"].append({"particular_id": "amount", "words": "Rs. 50,000", "source_id": "M1"})
    assert "which is not a particular of this part" in " ".join(
        drafting._faults({"parts": [stray]}, TEMPLATE, ["demand"], ctx, sources, None)["demand"])
    # Words that stand in the passage cited but not in the paragraph are not stated.
    unstated = facts()
    unstated["paragraphs"][0]["text"] = "The cheque was returned unpaid on 10 January 2026."
    assert "does not state amount in the words given for it" in " ".join(
        drafting._faults({"parts": [unstated]}, TEMPLATE, ["facts"], ctx, sources, None)["facts"])


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
    assert drafting.TEMPLATES[("ni_138_demand_notice", 1)] == drafting.NI_138_V1
    for key, template in drafting.TEMPLATES.items():
        assert key == (template["id"], template["version"])
        assert drafting.check_template(template) is template


def test_the_writer_and_the_reviewer_are_told_the_purpose_and_work_in_a_loop():
    for said in (drafting.WRITER, drafting.REVIEWER):
        assert "Purpose:" in said and "Outcome:" in said and "Work in a loop" in said
    assert "[[its id]]" in drafting.WRITER and "work none out" in drafting.WRITER
    assert all(kind in drafting.REVIEWER for kind in drafting.FINDS)


SAVED_AT = "2026-11-22T10:00:00+00:00"


def word_paragraphs(data):
    """Each paragraph of a Word file's document as (its text, whether any of it is highlighted)."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return [("".join(t.text or "" for t in p.iter(f"{w}t")), p.find(f".//{w}highlight") is not None)
            for p in root.iter(f"{w}p")]


def test_the_saved_draft_is_a_word_file_of_the_draft_with_what_is_left_for_the_advocate_apart(matter):
    ctx, sources = matter
    record = drafting.write(Writer({"parts": [facts(), demand()]}, NOTHING), TEMPLATE, ctx, sources)
    name, data = drafting.word(record, SAVED_AT)
    assert name == "Draft 2026-11-22 - Notice of demand"
    assert word_paragraphs(data) == [
        ("Notice of demand", False), ("Draft for your review · saved 22 November 2026", False),
        ("Facts", False), ("The cheque for Rs. 50,000 was returned unpaid on 10 January 2026, marked funds insufficient.", False),
        ("Demand", False),
        ("Asha Verma is called upon to pay the amount within the time the Act allows, at [particular needed: the drawer's address].",
         True),
        ("For your review", False), ("Not part of the document: remove these notes before it is sent.", False),
        ("• Demand: the papers do not give the drawer's address.", False), (drafting.DRAFTED, False)]
    # Saved and reopened, the draft gives the same file, byte for byte.
    again = drafting.validate(json.loads(json.dumps(record)), ctx, sources, templates=HELD)
    assert drafting.word(again, SAVED_AT) == (name, data)


def test_the_word_file_says_what_code_and_the_review_still_find_and_names_no_passage_by_its_id(matter):
    ctx, sources = matter
    tries = [facts(amount=f"Rs. {n},000") for n in (1, 2, 3)]
    record = drafting.write(Writer({"parts": [tries[0], demand()]}, {"parts": [tries[1]]}, {"parts": [tries[2]]},
                                   {"findings": [found("demand", why="The demand does not say how much."),
                                                 found("elsewhere", why="The notice has no date.")]}),
                            TEMPLATE, ctx, sources)
    notes = [text for text, _ in word_paragraphs(drafting.word(record, SAVED_AT)[1]) if text.startswith("• ")]
    assert notes == [f"• Facts: {drafting.STILL_AT_FAULT}", "• Demand: the papers do not give the drawer's address.",
                     "• Demand: An independent review found that this part leaves out what it needs and the conversation "
                     "gives: The demand does not say how much.", "• The review also said: The notice has no date."]
    unreviewed = drafting.write(Writer({"parts": [facts(), demand()]}, ModelError("scripted")), TEMPLATE, ctx, sources)
    assert [text for text, _ in word_paragraphs(drafting.word(unreviewed, SAVED_AT)[1])][-2] == f"• {drafting.NOT_REVIEWED}"
    # A title the file's XML or name cannot hold as it stands.
    odd = deepcopy(record)
    odd["template"]["title"] = "Notice & <demand>\x01"
    name, data = drafting.word(odd, SAVED_AT)
    assert name == "Draft 2026-11-22 - Notice demand" and word_paragraphs(data)[0] == ("Notice & <demand>", False)


# Piece 23d1 (D330): the held section 138 template. The matter is invented for the test.
NOTICE_MESSAGE = ("Draft the section 138 notice for my client Ravi Kumar of 12 Park Street, Pune. Cheque No. 004512 dated "
                  "2 January 2026 for Rs. 2,50,000/- drawn by Sunita Rao on Canara Bank, MG Road branch, given towards a hand "
                  "loan of Rs. 2,50,000, was presented through HDFC Bank, Camp branch on 5 January 2026 and returned by memo "
                  "dated 7 January 2026 with the reason \"Funds Insufficient\"; my client received the memo on 9 January 2026.")
NOTICE = drafting.NI_138_V1
WRITTEN = ["heading", "parties", "company", "debt", "cheque", "dishonour", "other_sums"]
DEMANDED = ("My client therefore calls upon you to pay the said amount of Rs. 2,50,000/- (Rupees Two Lakh Fifty Thousand only), "
            "the amount of the said cheque, to my client within fifteen days of the receipt of this notice.")


@pytest.fixture(scope="module")
def notice_matter():
    ctx = context(NOTICE_MESSAGE)
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    record = retrieve(accept(proposal(1), ctx), HybridSearcher({"provision": statute, "judgment": AdjacentJudgment()}), ctx,
                      model=ResearchModel())
    return ctx, answer_sources.build(ctx, record)


def part(part_id, text, stated=(), missing=()):
    return {"part_id": part_id, "paragraphs": [{
        "text": text, "source_ids": ["M1"],
        "particulars": [{"particular_id": name, "words": words, "source_id": "M1"} for name, words in stated],
        "missing": list(missing)}]}


def cheque(amount="Rs. 2,50,000/-"):
    return part("cheque", f"You drew Cheque No. 004512 dated 2 January 2026 for {amount} on Canara Bank, MG Road branch.",
                [("cheque_number", "004512"), ("cheque_date", "2 January 2026"), ("cheque_amount", amount),
                 ("drawee_bank", "Canara Bank, MG Road branch")])


def notice(*, amount="Rs. 2,50,000/-", company=None):
    """A writing of every written part of the held notice from the invented matter: the parts used only sometimes left out."""
    return {"parts": [
        part("heading", "Notice dated [[notice_date]], sent by [[modes]] from [[place]].",
             missing=("notice_date", "modes", "place")),
        part("parties", "From [[advocate_name]], Advocate, [[advocate_address]], for my client Ravi Kumar of 12 Park Street, "
                        "Pune, to Sunita Rao, [[drawer_address]].",
             [("client_name", "Ravi Kumar"), ("client_address", "12 Park Street, Pune"), ("drawer_name", "Sunita Rao")],
             ("advocate_name", "advocate_address", "drawer_address")),
        *([company] if company else []),
        part("debt", "The cheque was given towards a hand loan of Rs. 2,50,000 that my client made to you.",
             [("debt_nature", "a hand loan"), ("debt_amount", "Rs. 2,50,000")]),
        cheque(amount),
        part("dishonour", "My client presented the cheque through HDFC Bank, Camp branch on 5 January 2026; it was returned by "
                          "memo dated 7 January 2026 with the reason \"Funds Insufficient\", and my client received the memo on "
                          "9 January 2026.",
             [("presented_through", "HDFC Bank, Camp branch"), ("presented_on", "5 January 2026"),
              ("returned_on", "7 January 2026"), ("return_reason", "Funds Insufficient"),
              ("information_received", "9 January 2026")])]}


def saved_part(record, part_id):
    return next(item for item in record["parts"] if item["part_id"] == part_id)


def test_the_held_notice_is_drafted_with_its_set_wording_filled_in_and_its_notes(notice_matter):
    ctx, sources = notice_matter
    writer = Writer(notice(), NOTHING)
    record = drafting.write(writer, NOTICE, ctx, sources)
    assert kinds(record) == [drafting.WRITING, drafting.REVIEW] and record["stopped"]["why"] == runner.COMPLETE
    assert record["rounds"][0]["asked"] == WRITTEN and record["rounds"][0]["faults"] == {name: [] for name in WRITTEN}
    # The writer is asked for the written parts alone, shown the set wording and when the parts used only sometimes are used.
    document = {entry["part_id"]: entry for entry in requested(writer.calls[0])["document"]["parts"]}
    assert list(document) == [item["id"] for item in NOTICE["parts"]]
    assert document["demand"]["set_wording"] == NOTICE["parts"][7]["wording"] and "set_wording" not in document["cheque"]
    assert document["company"]["used_only_when"].startswith("the papers show that the drawer is a company")
    # Code writes the set wording from what the written parts state, the amount in words its own; what nothing gives stays marked.
    assert [paragraph["text"] for paragraph in saved_part(record, "demand")["paragraphs"]] == [DEMANDED]
    demand = saved_part(record, "demand")["paragraphs"][0]
    assert demand["particulars"] == [{"particular_id": "cheque_amount", "words": "Rs. 2,50,000/-", "source_id": "M1"}]
    assert demand["source_ids"] == ["M1"] and demand["missing"] == []
    close = saved_part(record, "close")["paragraphs"]
    assert [paragraph["text"] for paragraph in close][1:] == ["[[advocate_name]], Advocate", "Place: [[place]]",
                                                             "Date: [[notice_date]]"]
    assert close[1]["missing"] == ["advocate_name"] and saved_part(record, "close")["faults"] == []
    # The reviewer reads the draft whole, the set wording as code wrote it.
    reviewed = {entry["part_id"]: entry for entry in requested(writer.calls[1])["draft"]}
    assert reviewed["demand"]["paragraphs"] == [{"id": "demand.1", "text": DEMANDED}]
    assert reviewed["close"]["paragraphs"][1]["text"] == "[particular needed: the advocate's name], Advocate"
    # The notice as the advocate reads it: the parts used only sometimes left out, the notes with it.
    shown = drafting.shown(record)
    assert [item["part_id"] for item in shown["parts"]] == ["heading", "parties", "debt", "cheque", "dishonour", "demand",
                                                           "consequence", "close"]
    assert shown["notes"] == NOTICE["notes"] and shown["reviewed"] is None
    assert drafting.validate(json.loads(json.dumps(record)), ctx, sources) == record
    name, data = drafting.word(record, SAVED_AT)
    assert name.startswith("Draft 2026-11-22 - Demand notice under section 138")
    texts = [text for text, _ in word_paragraphs(data)]
    assert DEMANDED in texts and "Those in charge of the drawer" not in texts and "Other sums claimed" not in texts
    notes = [text[2:] for text in texts if text.startswith("• ")]
    assert notes[:4] == NOTICE["notes"]
    # A particular two parts need is asked for once, under the first.
    assert notes[4:] == [f"Notice: the papers do not give {said}." for said in (
        "the date of the notice", "how the notice is sent (registered post, speed post, courier, e-mail or another way)",
        "the place the notice is sent from")] + [f"From and to: the papers do not give {said}." for said in (
        "the advocate's name", "the advocate's office address", "the drawer's address")]
    # Set wording saved otherwise than code writes it, or a template saved otherwise than NM holds it, is not read.
    altered = deepcopy(record)
    saved_part(altered, "demand")["paragraphs"][0]["text"] = DEMANDED.replace("fifteen", "thirty")
    with pytest.raises(ValueError, match="not as its rounds leave them"):
        drafting.validate(altered, ctx, sources)
    reworded = deepcopy(record)
    reworded["template"]["parts"][7]["wording"] = ["Pay now."]
    with pytest.raises(ValueError, match="not one NM holds"):
        drafting.validate(reworded, ctx, sources)


def test_set_wording_fills_in_only_what_stands_and_follows_the_part_written_again(notice_matter):
    ctx, sources = notice_matter
    writer = Writer(notice(amount="Rs. 3,00,000/-"), {"parts": [cheque()]}, NOTHING)
    record = drafting.write(writer, NOTICE, ctx, sources)
    assert kinds(record) == [drafting.WRITING, drafting.WRITING, drafting.REVIEW] and record["rounds"][1]["asked"] == ["cheque"]
    assert "do not stand in M1" in " ".join(record["rounds"][0]["faults"]["cheque"])
    # The first writing's amount stood nowhere, so the set wording left it, and the amount in words, marked.
    first = drafting._state(NOTICE, record["rounds"][:1], sources)["draft"]["demand"]["paragraphs"][0]
    assert first["missing"] == ["cheque_amount", "amount_in_words"] and "[[cheque_amount]] ([[amount_in_words]])" in first["text"]
    assert [paragraph["text"] for paragraph in saved_part(record, "demand")["paragraphs"]] == [DEMANDED]
    assert drafting.validate(record, ctx, sources) is record


def test_what_the_review_finds_in_set_wording_is_kept_for_the_advocate_and_never_written_again(notice_matter):
    ctx, sources = notice_matter
    finding = found("consequence", kind="frames", why="The matter may call for a civil suit to be named as well.")
    record = drafting.write(Writer(notice(), {"findings": [finding]}), NOTICE, ctx, sources)
    assert kinds(record) == [drafting.WRITING, drafting.REVIEW] and record["stopped"]["why"] == runner.NOTHING_NEW
    assert saved_part(record, "consequence")["findings"] == [finding]
    assert drafting.shown(record)["parts"][6]["found"] == [drafting._told(finding, cited=False)]
    assert drafting.validate(record, ctx, sources) is record
    # A finding in a written part as well is written again; the set wording's stays with its unchanged words.
    debt = part("debt", "The cheque was given towards a hand loan of Rs. 2,50,000 that my client made to you, as the papers show.",
                [("debt_nature", "a hand loan"), ("debt_amount", "Rs. 2,50,000")])
    record = drafting.write(Writer(notice(), {"findings": [finding, found("debt")]}, {"parts": [debt]}, NOTHING), NOTICE, ctx, sources)
    assert kinds(record) == [drafting.WRITING, drafting.REVIEW, drafting.WRITING, drafting.REVIEW]
    assert record["rounds"][2]["asked"] == ["debt"] and drafting.validate(record, ctx, sources) is record
    assert record["stopped"]["why"] == runner.COMPLETE and saved_part(record, "consequence")["findings"] == []


def test_a_part_used_only_sometimes_may_be_left_out_but_not_given_twice(notice_matter):
    ctx, sources = notice_matter
    company = part("company", "This notice is also addressed to [[persons_in_charge]].", missing=("persons_in_charge",))
    empty = {"part_id": "company", "paragraphs": []}
    for given, faults in (([], []), ([empty], []), ([company], []), ([company, company], ["This part was not given once."])):
        assert drafting._faults({"parts": given}, NOTICE, ["company"], ctx, sources, None) == {"company": faults}
    assert drafting._faults({"parts": []}, NOTICE, ["debt"], ctx, sources, None) == {"debt": ["This part was not given once."]}
    # Given, it is shown and checked as any part; left out again when written again, it is no longer in the draft.
    record = drafting.write(Writer(notice(company=company), NOTHING), NOTICE, ctx, sources)
    assert "Those in charge of the drawer" in [item["title"] for item in drafting.shown(record)["parts"]]
    kept = [{"kind": drafting.WRITING, "asked": WRITTEN, "proposal": notice(company=company),
             "faults": {name: [] for name in WRITTEN}},
            {"kind": drafting.WRITING, "asked": ["company"], "proposal": {"parts": []}, "faults": {"company": []}}]
    assert drafting._state(NOTICE, kept[:1], sources)["draft"]["company"]["paragraphs"] == company["paragraphs"]
    assert drafting._state(NOTICE, kept, sources)["draft"]["company"]["paragraphs"] == []


@pytest.mark.parametrize("figures, words", [
    ("Rs. 2,50,000/-", "Rupees Two Lakh Fifty Thousand only"), ("Rs.50,000", "Rupees Fifty Thousand only"),
    ("INR 1,500.00", "Rupees One Thousand Five Hundred only"), ("1,00,00,000", "Rupees One Crore only"),
    ("Rs. 1,234,567", "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven only"),
    ("Rs. 10,001.5", "Rupees Ten Thousand One and Fifty Paise only"), ("₹ 7,15,019", "Rupees Seven Lakh Fifteen Thousand Nineteen only"),
    # Code writes no sum in words it would have to guess: words beside the figures, two sums, nought, figures grouped oddly.
    ("Rs. 2.5 lakh", None), ("Rs. 50,000/- (Rupees Fifty Thousand only)", None), ("Rs 18,00,000 and Rs 2,000", None),
    ("Rs. 0", None), ("Rs. 1,000,00", None), ("fifty thousand", None)])
def test_a_sum_in_figures_is_written_in_words_the_indian_way_or_not_at_all(figures, words):
    assert drafting.rupees_in_words(figures) == words


def test_a_template_holds_set_wording_parts_used_sometimes_computed_values_and_notes_only_in_their_form():
    drafting.check_template(NOTICE)

    def changed(change):
        copy = deepcopy(NOTICE)
        change(copy)
        return copy
    def states_own(t): t["parts"][7]["particulars"] = [{"id": "extra", "said": "an extra particular"}]
    def unknown_mark(t): t["parts"][7]["wording"] = ["Pay [[nothing_known]]."]
    def both(t): t["parts"][7]["when"] = "always"
    def blank_when(t): t["parts"][2]["when"] = " "
    def computed_from_nothing(t): t["computed"]["amount_in_words"]["from"] = "nothing_known"
    def computed_unknown_way(t): t["computed"]["amount_in_words"]["as"] = "guessed"
    def computed_clash(t): t["computed"] = {"cheque_amount": t["computed"]["amount_in_words"]}
    def bad_notes(t): t["notes"] = ["", "A note."]
    def no_written(t): t["parts"] = [item for item in t["parts"] if "wording" in item]
    def stray_key(t): t["parts"][0]["shown"] = True
    for change in (states_own, unknown_mark, both, blank_when, computed_from_nothing, computed_unknown_way, computed_clash,
                   bad_notes, no_written, stray_key):
        with pytest.raises(ValueError):
            drafting.check_template(changed(change))
