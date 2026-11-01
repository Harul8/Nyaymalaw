"""After a paper's reading, a second pass over it, shown what was read from it, gives only what that leaves out; what it gives is
placed, checked and settled with the rest (plan AN.33, D17 and D25; research v14; piece 33g).

The owner, 1 Nov 2026: "how do we ensure all these and in principle all the legally important details are extracted and considered by
NM?" Two readings of the same papers made blind (AN.31) each found points the other missed: one pass is not the whole of what a model
can find. So each stretch of a paper whose reading did not fail is read once more, by the reading's own call - its prompt and the same
file before the pages - shown the points read from the paper and asked only what they leave out. Code places what it gives as it places
the reading's, marks it as the second pass's, adds none the list holds word for word, and settles it with the rest; a pass that fails
adds nothing and is recorded with why. The plan lists each pass and what it added. The papers are invented.
"""
import re

import pytest

from nm.core_engine import reasoning, research
from nm.core_engine.research import CHRONOLOGY_V14, SECOND_PASS, chronology_of
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import _result
from tests.test_failed_checks_are_settled_by_the_model import DEED, NOTE, RIGHT, Settling, sent, settled, shown
from tests.test_the_chronology_of_each_document import event

pytestmark = pytest.mark.class_a

ASKED = "What the reading already set out from this paper"
SURVEY = event("11-2-2016", "order", "A survey ordered in file K/58/2014.", "A survey was ordered on 11-2-2016 in file K/58/2014")
REGISTERED = event("undated", "document", "The agreement was registered at the office.", "Registered at the office")


class Passing(Settling):
    """As Settling, and answers each second pass from `second`, keyed by the paper's name (a failure where it names "fail")."""

    def __init__(self, reading, second=None, settling=None, fail=()):
        super().__init__(reading, settling, fail)
        self.second = second or {}

    def structured(self, prompt, schema, tier, **kwargs):
        if ASKED in prompt.user:
            with self.lock:
                self.calls.append(prompt)
            name = re.search(r'^Document: "(.*)"', prompt.user[prompt.user.index("The pages you read for:"):], re.M).group(1)
            if self.second.get(name) == "fail":
                raise SchemaViolation("scripted failure")
            return _result({"events": self.second.get(name, [])}, tier)
        return super().structured(prompt, schema, tier, **kwargs)

    def passes(self):
        return [call for call in self.calls if ASKED in call.user]

    def readings(self):
        return [call for call in self.calls if call.system == CHRONOLOGY_V14 and ASKED not in call.user]


def test_the_second_pass_is_the_readings_own_call_shown_what_was_read_and_only_what_it_leaves_out_is_added():
    model = Passing({"deed.pdf": [RIGHT]}, {"deed.pdf": [RIGHT, SURVEY]})
    passes = []
    events, failures = chronology_of(model, sent(("deed.pdf", DEED)), passes=passes)
    [reading], [second] = model.readings(), model.passes()
    assert (second.operation, second.system) == (reading.operation, reading.system) == ("core_research_chronology", CHRONOLOGY_V14)
    assert second.user.startswith(reading.user), "the same file before the pages, so that it reads as the reading did"
    asked = second.user[len(reading.user):]
    assert '"what": "A sale of 42 kg."' in asked and "now only for what that list leaves out" in asked
    assert [(e["what"], e["second_pass"]) for e in events] == [("A sale of 42 kg.", False), (SURVEY["what"], True)], (
        "the point the list holds is not added twice")
    survey = events[1]
    assert survey["anchored"] and survey["pages"] == [2] and survey["date_found"] == "words"
    assert passes == [{"document": "deed.pdf", "pages": "1-2", "added": 1, "reason": ""}] and failures == []


def test_what_the_second_pass_gives_is_settled_with_the_rest():
    slip = event("undated", "document", "The agreement was registered at the office.", "Registerd at the office")
    model = Passing({"deed.pdf": [RIGHT]}, {"deed.pdf": [slip]},
                    {"deed.pdf": {"settled": [settled(0, "clerical", REGISTERED)], "added": []}})
    events, _ = chronology_of(model, sent(("deed.pdf", DEED)))
    [settle] = model.settles()
    [check] = shown(settle)["to_check"]
    assert check["words"] == "Registerd at the office" and "not found" in check["why"]
    [kept] = [e for e in events if e["kind"] == "document"]
    assert kept["anchored"] and kept["words"] == "Registered at the office" and kept["settled"] == "clerical" and kept["second_pass"]
    assert model.calls.index(settle) > model.calls.index(model.passes()[0]), "the second pass comes before the settling"


def test_a_second_pass_that_fails_adds_nothing_and_is_recorded_with_why():
    model = Passing({"deed.pdf": [RIGHT], "note.pdf": []}, {"deed.pdf": "fail", "note.pdf": [
        event("21 March 2017", "statement", "The supplier's agent signed for the stores.",
              "The supplier's agent signed for the stores on 21 March 2017", "the buyer")]})
    passes = []
    events, failures = chronology_of(model, sent(("deed.pdf", DEED), ("note.pdf", NOTE)), passes=passes)
    assert [(e["document"], e["second_pass"]) for e in events] == [("deed.pdf", False), ("note.pdf", True)]
    assert sorted(passes, key=lambda item: item["document"]) == [
        {"document": "deed.pdf", "pages": "1-2", "added": 0, "reason": "SchemaViolation"},
        {"document": "note.pdf", "pages": "1", "added": 1, "reason": ""}]
    assert failures == [], "the reading stands: a failed second pass leaves no page unread"


def test_a_stretch_whose_reading_failed_is_given_no_second_pass():
    class Failing(Passing):
        def structured(self, prompt, schema, tier, **kwargs):
            if prompt.system == CHRONOLOGY_V14 and ASKED not in prompt.user and 'Document: "deed.pdf"' in prompt.user.split(
                    "The pages you read for:")[-1]:
                raise SchemaViolation("scripted failure")
            return super().structured(prompt, schema, tier, **kwargs)
    model = Failing({"note.pdf": []}, {"note.pdf": []})
    passes = []
    events, failures = chronology_of(model, sent(("deed.pdf", DEED), ("note.pdf", NOTE)), passes=passes)
    assert [failure["document"] for failure in failures] == ["deed.pdf"]
    assert [item["document"] for item in passes] == ["note.pdf"] and len(model.passes()) == 1


def test_the_plan_lists_each_second_pass_and_refuses_one_that_says_otherwise_than_its_events():
    from tests.test_the_plan_records_the_chronology import bundle, made
    ctx, record = bundle(), made()
    second = record["proposal"]["chronology_second_pass"]
    assert [(item["document"], item["added"], item["reason"]) for item in second] == [("deed.pdf", 0, ""), ("order.pdf", 0, "")], (
        "a second pass for each paper; this double gives again only what its reading gave")
    assert research.accept(record["proposal"], ctx)["issues"] == []
    wrong = {**record["proposal"], "chronology_second_pass": [{**second[0], "document": "elsewhere.pdf"}, second[1]]}
    with pytest.raises(SchemaViolation, match="second pass"):
        research.accept(wrong, ctx)


def test_the_plan_refuses_more_events_marked_as_the_second_passs_than_it_added():
    events = [{"id": "E1", "document": "deed.pdf", "second_pass": True}, {"id": "E2", "document": "deed.pdf", "second_pass": True}]
    ctx = sent(("deed.pdf", DEED))
    assert research._second_pass_issues([{"document": "deed.pdf", "pages": "1-2", "added": 2, "reason": ""}], events, ctx) == []
    with pytest.raises(SchemaViolation, match="E2 is marked as the second pass's"):
        research._second_pass_issues([{"document": "deed.pdf", "pages": "1-2", "added": 1, "reason": ""}], events, ctx)
    with pytest.raises(SchemaViolation, match="says otherwise"):
        research._second_pass_issues([{"document": "deed.pdf", "pages": "1-2", "added": 1, "reason": "SchemaViolation"}], [], ctx)


def test_the_second_pass_reads_with_care_and_asks_in_plain_words():
    assert reasoning.STEPS["chronology_second"] == ("high", True) and research.MAX_OUTPUT["chronology_second"] == 32000
    words = " ".join(SECOND_PASS.split())
    for part in ("What the reading already set out from this paper, point by point (date, kind, what, said_by)",
                 "Read the pages you read for again, now only for what that list leaves out",
                 "any point there that a careful lawyer would need", "Give each as an event, as the reading would have",
                 "give none where the list holds them all", "Do not give again a point the list holds, in whatever words it is put"):
        assert part in words, part
