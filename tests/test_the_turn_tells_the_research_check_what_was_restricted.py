"""The turn tells the research check what the advocate restricted (plan AN.27, P5; invariant I2).

The interpretation step finds, in the advocate's latest message, the instructions that limit NM's work, with their exact words. The
turn hands those words to the matter understanding's check once the interpretation is decided - an empty list where nothing was
restricted, and None where the interpretation did not complete cleanly, because what was not established is never "none".
"""
import pytest

from nm.core_engine import turn
from nm.shared.model_port import ModelError

pytestmark = pytest.mark.class_a


class Calls:
    def checked(self, operation, activity):
        return activity()


def unit(kind, text):
    return {"id": f"u-{kind}", "kind": kind, "source": {"source_id": "t1:advocate", "text": text}, "meaning": "m"}


def interpreted(*units, issues=()):
    return {"contract": "core_understanding_v2", "units": list(units), "issues": list(issues), "status": "proposed",
            "semantic_review": "pending"}


def run(monkeypatch, result):
    seen = {}

    def plan(calls, context, interpretation=None, *, progress=None, wanted=None, restrictions=None):
        seen["restrictions"] = restrictions()      # asked first: it must wait for the interpretation, not run ahead of it
        seen["wanted"] = wanted()
        return "PLAN"

    def understand(calls, context):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(turn.research, "plan", plan)
    monkeypatch.setattr(turn.understanding, "understand", understand)
    return seen


def test_a_restriction_in_the_latest_message_reaches_the_check_in_the_advocates_exact_words(monkeypatch):
    seen = run(monkeypatch, interpreted(unit("request", "Understand the disputes."), unit("restriction", "Do not research yet."),
                                        unit("information", "The deed is dated 1980.")))
    out = turn._interpreted(Calls(), {}, lambda stage, **detail: None)
    assert seen["restrictions"] == ["Do not research yet."] and seen["wanted"] is True and out[1] == "PLAN"


def test_a_message_that_restricts_nothing_reaches_the_check_as_none_found(monkeypatch):
    seen = run(monkeypatch, interpreted(unit("request", "Understand the disputes.")))
    turn._interpreted(Calls(), {}, lambda stage, **detail: None)
    assert seen["restrictions"] == []


def test_an_interpretation_that_did_not_complete_cleanly_is_not_taken_to_say_nothing_was_restricted(monkeypatch):
    seen = run(monkeypatch, interpreted(unit("request", "Understand the disputes."), issues=["a quotation was not found"]))
    turn._interpreted(Calls(), {}, lambda stage, **detail: None)
    assert seen["restrictions"] is None


def test_an_interpretation_that_failed_leaves_it_not_known_and_the_loop_not_wanted(monkeypatch):
    seen = run(monkeypatch, ModelError("the provider was unavailable"))
    with pytest.raises(ModelError):
        turn._interpreted(Calls(), {}, lambda stage, **detail: None)
    assert seen["restrictions"] is None and seen["wanted"] is False


@pytest.mark.parametrize("bad", [None, {"units": "none"}, "interpretation"])
def test_what_is_not_an_interpretation_says_nothing(bad):
    assert turn._restrictions(bad) is None
