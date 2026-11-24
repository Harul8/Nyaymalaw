"""Plan AN.67, piece 23d4 (owner decision D331): a draft changed as the advocate asks. The change begins from the latest version as
saved and writes again only the parts the advocate's message asked to change, the writer told which message asks it; code's checks
and the independent review of the whole draft follow, with an allowance of rewrites of the change's own; the result is the draft's
next version, the earlier kept as it was. Read again, a changed version is checked from the version before it, and each version
against the conversation as it was written from it, so that a later message cannot unsettle what code found of an earlier one.
The template and the matter are invented (tests/test_drafting.py); no paid call."""
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, drafting
from nm.core_engine import rounds as runner
from nm.core_engine.conversation import added_messages
from nm.core_engine.research import accept, retrieve
from nm.core_engine.retrieval import HybridSearcher
from nm.shared.model_port import ModelError
from tests.test_core_answer_sources import AdjacentJudgment
from tests.test_core_research import Model as ResearchModel
from tests.test_core_research import proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection
from tests.test_drafting import HELD, MESSAGE, NOTHING, TEMPLATE, Writer, demand, facts, found, kinds, requested

ADDRESS = "Send it to 4 Park Street, Pune."


@pytest.fixture(scope="module")
def matter():
    ctx = context(MESSAGE)
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    record = retrieve(accept(proposal(1), ctx), HybridSearcher({"provision": statute, "judgment": AdjacentJudgment()}), ctx,
                      model=ResearchModel())
    return ctx, record


def added(ctx, *texts):
    """The conversation with the advocate's messages added while the matter waited, after the latest (48h)."""
    turn_id = ctx["latest"]["turn_id"]
    return {**ctx, "added": added_messages(turn_id, [{"text": text} for text in texts])}


def addressed(source="M2"):
    """The demand written again with the address the advocate gave in their later message."""
    return {"part_id": "demand", "paragraphs": [{
        "text": "Asha Verma is called upon to pay the amount within the time the Act allows, at 4 Park Street, Pune.",
        "source_ids": ["M1", source],
        "particulars": [{"particular_id": "drawer", "words": "Asha Verma", "source_id": "M1"},
                        {"particular_id": "address", "words": "4 Park Street, Pune", "source_id": source}],
        "missing": []}]}


def first(ctx, record):
    sources = answer_sources.build(ctx, record)
    return drafting.write(Writer({"parts": [facts(), demand()]}, NOTHING), TEMPLATE, ctx, sources)


def test_a_change_writes_again_only_the_parts_asked_and_is_reviewed_and_kept_as_the_next_version(matter):
    ctx, record = matter
    v1 = first(ctx, record)
    assert v1["added"] == 0 and "change" not in v1
    later = added(ctx, ADDRESS)
    sources = answer_sources.build(later, record)
    asked_in = later["added"][0]["source_id"]
    writer = Writer({"parts": [addressed()]}, NOTHING)
    v2 = drafting.change(writer, v1, later, sources, parts=["demand"], asked_in=asked_in)
    assert kinds(v2) == [drafting.WRITING, drafting.REVIEW] and v2["rounds"][0]["asked"] == ["demand"]
    assert v2["stopped"] == {"why": runner.COMPLETE, "reason": None} and v2["reviewed"] is True
    assert v2["change"] == {"parts": ["demand"], "asked_in": asked_in} and v2["added"] == 1
    # The parts not asked stand as they were; the part asked is as written again.
    assert v2["parts"][0] == v1["parts"][0]
    assert v2["parts"][1]["paragraphs"] == addressed()["paragraphs"] and v2["parts"][1]["faults"] == []
    # The writer is told which message asks the change, by the ID it sees it under, with the part as it stood.
    sent = requested(writer.calls[0])
    assert sent["change_asked"] == {"in_message": "M2", "parts": ["demand"]}
    assert [part["part_id"] for part in sent["document"]["parts"]] == ["demand"]
    assert sent["earlier_draft"] == [{"part_id": "demand", "paragraphs": v1["parts"][1]["paragraphs"], "faults": []}]
    assert writer.calls[0][0].effort == drafting.reasoning.effort("repair")
    # The review reads the whole draft, told which message asked for the change.
    reviewed = requested(writer.calls[1])
    assert reviewed["change_asked"] == sent["change_asked"] and [part["part_id"] for part in reviewed["draft"]] == ["facts", "demand"]
    # Read again: from the version before it, against the conversation as each was written from.
    assert drafting.validate(v2, later, sources, templates=HELD, earlier=v1) is v2
    before = drafting.written_from(v1, later)
    assert "added" not in before and before == ctx
    assert drafting.validate(v1, before, answer_sources.build(before, record), templates=HELD) is v1
    # Shown: which parts differ from the version before.
    assert drafting.shown(v2, v1)["changed"] == ["Demand"] and drafting.shown(v1)["changed"] is None
    assert drafting.shown(v1, v1)["changed"] == []


def test_a_version_is_read_only_as_what_it_is(matter):
    ctx, record = matter
    v1 = first(ctx, record)
    later = added(ctx, ADDRESS)
    sources = answer_sources.build(later, record)
    asked_in = later["added"][0]["source_id"]
    v2 = drafting.change(Writer({"parts": [addressed()]}, NOTHING), v1, later, sources, parts=["demand"], asked_in=asked_in)

    def refused(version, conversation, given, earlier):
        with pytest.raises(ValueError):
            drafting.validate(version, conversation, given, templates=HELD, earlier=earlier)
    refused(v2, later, sources, None)  # a change is read from the version it changes
    refused(v1, ctx, answer_sources.build(ctx, record), v1)  # a first version changes none
    refused(v1, later, sources, None)  # read against more messages than it was written from
    for altered in ({**v2["change"], "parts": ["facts"]}, {**v2["change"], "parts": ["demand", "facts"]},
                    {**v2["change"], "asked_in": "turn:added9"}, {"parts": ["demand"]}):
        refused({**v2, "change": altered}, later, sources, v1)
    refused({key: value for key, value in v2.items() if key != "added"}, later, sources, v1)
    other = deepcopy(v1)
    other["parts"][0]["paragraphs"][0]["text"] = "Something else."
    refused(v2, later, sources, other)  # a change begins from the version as it was saved: what it kept is that version's
    # A conversation with fewer messages than the draft was written from cannot be read for it.
    with pytest.raises(ValueError):
        drafting.written_from(v2, ctx)


def test_a_later_message_cannot_unsettle_what_code_found_in_an_earlier_version(matter):
    ctx, record = matter
    sources = answer_sources.build(ctx, record)
    dated = facts(close=", and the notice is dated 12 January 2026")
    v1 = drafting.write(Writer({"parts": [dated, demand()]}, {"parts": [dated]}, NOTHING), TEMPLATE, ctx, sources)
    assert v1["parts"][0]["faults"], "a date nothing given gives is at code's fault"
    later = added(ctx, "The notice is dated 12 January 2026.")
    stale = {key: value for key, value in v1.items() if key != "added"}
    with pytest.raises(ValueError):
        # Read against the conversation as it now is, the date is given and the round no longer what code finds of it.
        drafting.validate(stale, later, answer_sources.build(later, record), templates=HELD)
    before = drafting.written_from(v1, later)
    assert drafting.validate(v1, before, answer_sources.build(before, record), templates=HELD) is v1


def test_a_change_has_its_own_allowance_of_rewrites(matter):
    ctx, record = matter
    v1 = first(ctx, record)
    later = added(ctx, ADDRESS)
    sources = answer_sources.build(later, record)
    wrong = [addressed(source="M9"), addressed(source="M8"), addressed(source="M7")]
    writer = Writer(*({"parts": [part]} for part in wrong), NOTHING)
    v2 = drafting.change(writer, v1, later, sources, parts=["demand"], asked_in=later["added"][0]["source_id"])
    assert kinds(v2) == [drafting.WRITING] * 3 + [drafting.REVIEW], "the change's writing, then two rewrites"
    assert v2["stopped"]["why"] == runner.BACKSTOP and v2["parts"][1]["faults"]
    # Each rewrite is told the change too.
    assert all(requested(call)["change_asked"]["parts"] == ["demand"] for call, _ in zip(writer.calls[:3], wrong))
    assert drafting.validate(v2, later, sources, templates=HELD, earlier=v1) is v2


def test_a_review_finding_in_a_part_not_asked_is_written_again_within_the_change(matter):
    ctx, record = matter
    v1 = first(ctx, record)
    later = added(ctx, ADDRESS)
    sources = answer_sources.build(later, record)
    writer = Writer({"parts": [addressed()]}, {"findings": [found("facts", why="It leaves out how the cheque was presented.")]},
                    {"parts": [facts(close=", marked funds insufficient by the bank")]}, NOTHING)
    v2 = drafting.change(writer, v1, later, sources, parts=["demand"], asked_in=later["added"][0]["source_id"])
    assert kinds(v2) == [drafting.WRITING, drafting.REVIEW, drafting.WRITING, drafting.REVIEW]
    assert v2["rounds"][2]["asked"] == ["facts"] and v2["stopped"]["why"] == runner.COMPLETE
    assert drafting.shown(v2, v1)["changed"] == ["Facts", "Demand"]
    assert drafting.validate(v2, later, sources, templates=HELD, earlier=v1) is v2


def test_a_change_names_parts_the_writer_writes_and_a_message_the_conversation_holds(matter):
    ctx, record = matter
    v1 = first(ctx, record)
    later = added(ctx, ADDRESS)
    sources = answer_sources.build(later, record)
    asked_in = later["added"][0]["source_id"]
    for parts, message in (([], asked_in), (["nope"], asked_in), (["demand", "demand"], asked_in), (["demand"], "elsewhere")):
        with pytest.raises(ValueError):
            drafting.change(Writer(), v1, later, sources, parts=parts, asked_in=message)
    # Named in any order, kept in the template's.
    v2 = drafting.change(Writer({"parts": [facts(), addressed()]}, NOTHING), v1, later, sources, parts=["demand", "facts"],
                         asked_in=asked_in)
    assert v2["change"]["parts"] == ["facts", "demand"]
    # A change whose writing cannot be made leaves the draft as it was: there is no new version.
    with pytest.raises(ModelError):
        drafting.change(Writer(ModelError("unavailable")), v1, later, sources, parts=["demand"], asked_in=asked_in)
    # Set wording is never the writer's: a change cannot name it.
    held = {"id": "x", "version": 1, "title": "T", "law": {"act": "A", "sections": ["1"]}, "parts": [
        TEMPLATE["parts"][0], {"id": "close", "title": "Close", "for": "The close.", "particulars": [], "wording": ["Yours."]}]}
    worded = {**v1, "template": drafting.check_template(held)}
    with pytest.raises(ValueError):
        drafting.change(Writer(), worded, later, sources, parts=["close"], asked_in=asked_in)
