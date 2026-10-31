"""The plan records the chronology of the documents (plan AN.27, P8c; research v12; invariants I4 and I5).

The papers an advocate sends are read for what they record (P8), and that reading now travels with the plan: it is made beside the
understanding, as soon as the message is known to carry a matter, so it adds no time; the plan keeps it with the stretches that could
not be read; and a plan is refused if what it keeps is not what the papers show - the numbering, the order of the dates, the document,
the date as code reads it, and the pages the words are on. A plan made before v12 is kept as it was. The papers are synthetic.
"""
import re
import threading
from copy import deepcopy
from functools import cache

import pytest

from nm.core_engine import research
from nm.core_engine.conversation import chat_matter_id
from nm.core_engine.research import CHRONICLED, CONTRACT, JUDGMENTS_READ_CONTRACT, accept, plan, retrieve, validate
from nm.core_engine.turn import saved_rows
from nm.shared.model_port import SchemaViolation, UsageLimitReached
from tests.test_core_research import Model, _result, operations, proposal, searcher
from tests.test_core_turn import run, store  # noqa: F401 - pytest fixture
from tests.test_core_turn_documents import DocumentModel, material
from tests.test_core_understanding import context as typed
from tests.test_the_chronology_of_each_document import DEED, ORDER, SCRIPT, Reading, event, row

pytestmark = pytest.mark.class_a


class Beside(Model):
    """The research double that also reads papers from a script. With `meet`, its understanding and its reading of the papers each
    wait for the other to be in flight, so a plan that does one after the other fails here."""

    def __init__(self, script=SCRIPT, *, unreadable=(), usage_limit=(), meet=None, transfers=None, transfers_unreadable=(),
                 transfers_usage_limit=(), **kw):
        super().__init__(**kw)
        self.papers, self.meet = Reading(script, fail=unreadable, usage_limit=usage_limit, meet=meet), meet
        self.transfers, self.transfers_fail = transfers or {}, (set(transfers_unreadable), set(transfers_usage_limit))

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_chronology":
            self.calls.append(prompt)
            return self.papers.structured(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_research_transfers":
            self.calls.append(prompt)
            name = re.search(r'^Document: "(.*)"', prompt.user, re.M).group(1)
            if name in self.transfers_fail[1]:
                raise UsageLimitReached("the account has no credit")
            if name in self.transfers_fail[0]:
                raise SchemaViolation(f"scripted failure for {name}")
            return _result({"transfers": self.transfers.get(name, [])}, tier)
        if prompt.operation == "core_research_understand" and self.meet is not None:
            self.meet.wait(timeout=10)
        return super().structured(prompt, schema, tier, **kwargs)


def sent(*rows):
    """The context of a turn that carries the documents the advocate sent."""
    return {**typed("Find the applicable law."), "documents": list(rows), "unread_document_pages": []}


def bundle():
    return sent(*[row("t1", 1, "deed.pdf", n, text) for n, text in DEED], *[row("t1", 2, "order.pdf", n, text) for n, text in ORDER])


@cache
def _made():
    return plan(Beside(), bundle())


def made():
    return deepcopy(_made())


def test_the_papers_are_read_beside_the_understanding_and_kept_with_the_plan():
    ctx = sent(*[row("t1", 1, "deed.pdf", n, text) for n, text in DEED])
    script = {"deed.pdf": SCRIPT["deed.pdf"]}
    model = Beside(script, meet=threading.Barrier(2))
    kept = plan(model, ctx)
    expected, _ = research.chronology_of(Reading(script), ctx)
    assert kept["proposal"]["chronology"] == expected and [e["id"] for e in expected] == ["E1", "E2"]
    assert kept["proposal"]["chronology_failures"] == [] and kept["issues"] == []
    assert operations(model).count("core_research_chronology") == 1


def test_a_plan_keeps_every_event_of_every_document_and_marks_the_one_whose_words_are_not_found():
    kept = made()
    events = kept["proposal"]["chronology"]
    assert [(e["id"], e["document"], e["anchored"]) for e in events] == [
        ("E1", "deed.pdf", True), ("E2", "deed.pdf", True), ("E3", "order.pdf", True), ("E4", "order.pdf", False),
        ("E5", "order.pdf", True), ("E6", "order.pdf", True)]
    assert kept["issues"] == [], "an event that is not anchored is marked, not an issue"


def test_a_plan_replays_from_its_own_proposal_and_a_record_made_from_it_validates():
    ctx = bundle()
    kept = made()
    assert accept(kept["proposal"], ctx) == kept
    record = retrieve(kept, searcher(), ctx, model=Model())
    assert record["contract"] == CONTRACT and record["state"] == "evaluated" and validate(record, kept, ctx) == record


def _renumber(events):
    for number, found in enumerate(events, 1):
        found["id"] = f"E{number}"


CASES = [
    ("a number out of turn", lambda p: p["chronology"][0].update(id="E2"), "numbered"),
    ("an event of no document of this turn", lambda p: p["chronology"][0].update(source="t9:d9"), "no document of this turn"),
    ("an event under another document's name", lambda p: p["chronology"][0].update(document="order.pdf"), "no document of this turn"),
    ("a sort date its date does not give", lambda p: p["chronology"][0].update(sort="1999-01-01"), "dated otherwise"),
    ("a later date before an earlier", lambda p: (p["chronology"].insert(0, p["chronology"].pop(1)), _renumber(p["chronology"])),
     "out of the order"),
    ("a dated event after an undated one", lambda p: (p["chronology"].insert(0, p["chronology"].pop()), _renumber(p["chronology"])),
     "out of the order"),
    ("words said to be found that are not", lambda p: p["chronology"][3].update(anchored=True, pages=[1]), "not anchored as"),
    ("words found that are said not to be", lambda p: p["chronology"][0].update(anchored=False, pages=[]), "not anchored as"),
    ("pages that are not the words' pages", lambda p: p["chronology"][0].update(pages=[2]), "not anchored as"),
    ("words found only in another document",
     lambda p: p["chronology"][0].update(words="Suits O.S. 891 of 2014 and 892 of 2014 are pending", anchored=True, pages=[2]),
     "not anchored as"),
    ("a stretch that failed in a document not sent",
     lambda p: p.update(chronology_failures=[{"document": "nope.pdf", "pages": "1", "reason": "x"}]), "names no document"),
    ("a kind outside the vocabulary", lambda p: p["chronology"][0].update(kind="gossip"), "vocabulary"),
    ("the chronology left out", lambda p: p.pop("chronology"), "missing"),
    ("the stretches that failed left out", lambda p: p.pop("chronology_failures"), "missing"),
]


@pytest.mark.parametrize("label,change,message", CASES, ids=[case[0] for case in CASES])
def test_a_plan_that_is_not_what_the_papers_show_is_refused(label, change, message):
    proposed = made()["proposal"]
    change(proposed)
    with pytest.raises(SchemaViolation, match=message):
        accept(proposed, bundle())


def test_a_stretch_that_could_not_be_read_is_an_issue_and_makes_the_research_partial():
    ctx = bundle()
    kept = plan(Beside(SCRIPT, unreadable=["order.pdf"]), ctx)
    assert kept["proposal"]["chronology_failures"] == [{"document": "order.pdf", "pages": "1-2", "reason": "SchemaViolation"}]
    assert [issue["mismatch"] for issue in kept["issues"]] == ["chronology unavailable for order.pdf (pages 1-2): SchemaViolation"]
    assert {e["document"] for e in kept["proposal"]["chronology"]} == {"deed.pdf"}
    assert retrieve(kept, searcher(), ctx, model=Model())["state"] == "partial"


def test_no_documents_make_an_empty_chronology_without_a_call():
    model = Beside()
    kept = plan(model, typed("Find the applicable law."))
    assert kept["proposal"]["chronology"] == [] and kept["proposal"]["chronology_failures"] == []
    assert "core_research_chronology" not in operations(model)


def test_a_message_with_no_matter_reads_no_papers():
    courtesy = {"issues": [], "units": [{"kind": "courtesy", "source": {"text": "Thanks."}}]}
    model = Beside()
    kept = plan(model, bundle(), courtesy)
    assert kept["proposal"]["chronology"] == [] and operations(model) == []
    model = Beside()
    stopped = plan(model, bundle(), wanted=lambda: False)
    assert stopped["proposal"]["chronology"] == [] and operations(model) == ["core_research_understand"]


def test_a_usage_limit_in_the_reading_stops_the_plan():
    with pytest.raises(UsageLimitReached):
        plan(Beside(SCRIPT, usage_limit=["deed.pdf"]), bundle())


def test_the_contracts_before_v12_keep_their_shape_and_v12_needs_the_chronology():
    ctx = bundle()
    before = accept(proposal(chronology=False), ctx, contract=JUDGMENTS_READ_CONTRACT)
    # v13 (AN.28) keeps the chronology as v12 did, read with the whole file in view and its dates checked.
    assert "chronology" not in before["proposal"] and CHRONICLED == ("core_research_v12", CONTRACT)
    assert CONTRACT == "core_research_v13"
    with pytest.raises(SchemaViolation, match="undeclared"):
        accept(proposal(), ctx, contract=JUDGMENTS_READ_CONTRACT)
    with pytest.raises(SchemaViolation, match="missing"):
        accept(proposal(chronology=False), ctx)


def test_a_record_saved_under_v11_still_validates_as_it_was_saved():
    ctx = bundle()
    before = accept(proposal(chronology=False), ctx, contract=JUDGMENTS_READ_CONTRACT)
    record = retrieve(accept(proposal(), ctx), searcher(), ctx, model=Model())
    saved = {**record, "contract": JUDGMENTS_READ_CONTRACT, "plan": before}
    assert validate(saved, before, ctx) == saved
    with pytest.raises(ValueError):
        validate({**saved, "contract": CONTRACT}, before, ctx)


class Reads(DocumentModel):
    """The scripted turn, with its papers read: the notice on the memo's second page is an event."""

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_chronology":
            self.calls.append((prompt.operation, prompt.user))
            return _result({"events": [event("25-09-2026", "other", "A notice was given.", "Notice dated 25-09-2026")]}, tier)
        return super().structured(prompt, schema, tier, **kwargs)


def test_a_saved_turn_keeps_the_chronology_and_a_later_turn_reads_the_carried_papers_again(store):
    first = run(store, Reads(), message="Please look at the memo.", documents=material())
    assert first["committed"] == "committed"
    run(store, Reads(), chat_id=first["chat_id"], turn_id="t2", message="And what next?")
    rows = saved_rows(store.load(chat_matter_id("owner", first["chat_id"])), "owner")
    assert len(rows) == 2
    for saved in rows:
        record = saved["activities"]["research"]
        (found,) = record["plan"]["proposal"]["chronology"]
        assert record["contract"] == CONTRACT and record["plan"]["proposal"]["chronology_failures"] == []
        assert (found["id"], found["sort"], found["document"], found["source"], found["pages"], found["anchored"]) == (
            "E1", "2026-09-25", "memo.pdf", "t1:d1", [2], True)
