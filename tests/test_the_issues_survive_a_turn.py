"""PHASE 1 — an issue on the file does not vanish because a read forgot it.

THE MEASURED DEFECT
---------------------
GS-15, served, 6 September 2026. The issue count across five turns went

    1, 1, 1, 0, 2

On turn 4 the thread had NO ISSUES AT ALL, having carried one for the three
turns before it. Nothing disposed of it. The read simply did not mention it,
and the list was whatever the read returned.

THE TYPE ALREADY FORBADE THIS
-------------------------------
`DispositionState` says, in its own docstring: "THE COMPLETE SET, and there is
no fifth member meaning gone." `Disposition` refuses PARKED or CLOSED without a
reason, because "a stopped issue with no reason is indistinguishable from a
deleted one at the point it matters — when the advocate asks why they are not
running it."

So the data model had no delete path, and the pipeline deleted every issue on
every turn by rebuilding the list from one read. A RULE THE TYPE ENFORCES AND
THE ARCHITECTURE ROUTES AROUND IS NOT ENFORCED.

WHAT THIS DOES NOT YET DO, AND SAYS SO
----------------------------------------
Nothing can CLOSE an issue yet — the read has no disposition field, so the list
only grows. That is the honest state: an issue that stops being live must be
parked or closed WITH A REASON, and building that is the `decisions` section of
Phase 1. Accumulating is the correct failure direction in the meantime.
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput
from nm.domain import issue as issue_domain
from nm.domain.issue import Issue, IssueKind
from nm.domain.matter import Side
from nm.domain.quotable import Quotable
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 6)

#: Carries a needle the scripted issue reader recognises. A message it spots
#: nothing in would make every check below pass against an empty list.
OPENING = ("We act for the plaintiff at Hyderabad. The client was "
           "dispossessed of the land and we want possession back.")
FOLLOW_UPS = ("the agreement was never registered",
              "so where do we stand now",
              "what about the notice")


class _Forgetful(ScriptedModelAdapter):
    """Spots issues on the first read and NOTHING afterwards.

    GS-15 turn 4 exactly. Driven rather than waited for: the live read forgot
    on one turn of five and could not be made to do it on demand.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.reads = 0

    def structured(self, prompt, schema, tier, **kw):
        result = super().structured(prompt, schema, tier, **kw)
        if schema.get("x-nm-read") == "issues" and result.data is not None:
            self.reads += 1
            if self.reads > 1:
                return replace(result, data={"issues": []},
                               text=json.dumps({"issues": []}))
        return result


def _engine(tmp_path, inner=None):
    store = FileMatterStore(tmp_path, key=KEY)
    model = TracedModel(inner=inner or ScriptedModelAdapter(
        _model_config(), responses={"__default__": "Issue the notice."}))
    return TurnEngine(store=store, evidence=_Evidence(), model=model), store


def _live(store, matter_id):
    return issue_domain.from_stored(store.load(matter_id).threads[0].issues)


# ============================== on the wire ================================

def test_an_issue_survives_a_read_that_forgets_it(tmp_path):
    """THE DEFECT, AS A RULE.

    Not "issues are stored" — storing them and replacing the list from each
    read would pass that and change nothing. The count must NEVER FALL while
    nothing has disposed of anything.
    """
    engine, store = _engine(tmp_path, inner=_Forgetful(
        _model_config(), responses={"__default__": "Issue the notice."}))
    first = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                                 message=OPENING))
    counts = [len(_live(store, first.matter.id))]
    assert counts[0] > 0, (
        "the opening turn spotted no issues, so this test is not exercising "
        "the case it was written for")

    for message in FOLLOW_UPS:
        engine.run(TurnInput(advocate_id="adv_1", matter_id=first.matter.id,
                             today=TODAY, message=message))
        counts.append(len(_live(store, first.matter.id)))

    assert all(b >= a for a, b in zip(counts, counts[1:], strict=False)), (
        f"the issue count fell while nothing disposed of anything: {counts}. "
        f"GS-15 went 1, 1, 1, 0, 2 — the thread had no issues on turn 4 "
        f"having carried one for three turns.")


def test_they_come_back_from_the_store_typed(tmp_path):
    """`Thread.issues` is untyped because `nm.domain.issue` imports
    `nm.domain.matter`, so the store returns plain dicts. Left implicit, the
    next turn would merge dicts against Issues, match nothing, and every issue
    would look new every turn — this defect arriving through its own repair.
    """
    engine, store = _engine(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", today=TODAY,
                               message=OPENING))

    raw = store.load(out.matter.id).threads[0].issues
    assert raw, "nothing was persisted"
    live = issue_domain.from_stored(raw)
    assert live and all(isinstance(i, Issue) for i in live)
    assert all(i.statement.strip() for i in live)


# ================================ the merge ================================

def _issue(statement, kind=IssueKind.SUBSTANTIVE):
    return Issue(thread="thr_1", statement=statement, kind=kind,
                 runs_against=Side.MOVING, proof="quoted words")


def test_the_same_question_asked_twice_is_one_issue():
    """An `Issue` gets a fresh id from every read, so ids cannot match across
    turns. Two issues asking the court the same question are the same issue —
    which is also what a person would say."""
    a = _issue("Is the agreement enforceable?")
    b = _issue("is the AGREEMENT enforceable?   ")
    assert len(issue_domain.merge((a,), (b,))) == 1


def test_the_standing_issue_wins_a_match():
    """It carries a disposition a fresh read knows nothing about. Overwriting
    it would be the deletion again, wearing an update's clothes."""
    from nm.domain.issue import Disposition, DispositionState

    standing = replace(
        _issue("Was notice served?"),
        disposition=Disposition(state=DispositionState.PARKED,
                                reason="the client is getting the receipt"))
    merged = issue_domain.merge((standing,), (_issue("was notice served?"),))
    assert len(merged) == 1
    assert merged[0].disposition.state is DispositionState.PARKED, (
        "a fresh read overwrote a disposition it knew nothing about")


def test_a_new_question_is_added():
    """THE BOUND. A merge that only ever kept the standing list would freeze
    the thread on turn one — the opposite failure and just as bad."""
    merged = issue_domain.merge((_issue("Is it enforceable?"),),
                                (_issue("Was notice served?"),))
    assert len(merged) == 2


def test_an_empty_read_changes_nothing():
    assert len(issue_domain.merge((_issue("a"), _issue("b")), ())) == 2


def test_a_stored_row_that_cannot_be_rebuilt_is_dropped_and_the_rest_kept():
    """Losing one issue to a record written before a rule existed is bad.
    Losing the whole list to it is worse."""
    good = {"thread": "t", "statement": "Is it enforceable?",
            "kind": "substantive", "runs_against": "moving", "proof": "x"}
    rebuilt = issue_domain.from_stored(
        [good, {"statement": ""}, "not an issue", {"thread": "t"}])
    assert len(rebuilt) == 1
    assert rebuilt[0].statement == "Is it enforceable?"


# ================== the same question, asked differently ===================

def test_the_read_is_shown_what_is_already_on_the_thread():
    """Without this the read cannot restate anything — it does not know what
    is there, so every phrasing is a new issue."""
    from nm.core.issues import build_prompt

    standing = (Issue(thread="t", statement="What is the limitation period?",
                      kind=IssueKind.THRESHOLD, runs_against=Side.MOVING,
                      proof="x", id="iss_aaa"),)
    prompt = build_prompt(Quotable(turn="and is it time-barred?",
                                   file="the account"), standing)
    assert "iss_aaa" in prompt.user
    assert "What is the limitation period?" in prompt.user
    assert "restates" in prompt.user

    first = build_prompt(Quotable(turn="an opening message",
                                  file="the account"))
    assert "ISSUES ALREADY ON THIS THREAD" not in first.user, (
        "a thread with no issues must not be told to restate one")


def test_a_restated_question_does_not_become_a_second_issue():
    """THE DEFECT, AS A RULE.

    GS-15's issue count went 1, 2, 3, 4, 8 and three of the six were one
    question:

        What is the limitation period for the claim of specific performance?
        What is the limitation period that applies to the claim...?
        Is the plaintiff's claim for specific performance time-barred?

    Note what those three share: almost no words. "Is the claim time-barred"
    and "what is the limitation period" are the same question and would defeat
    any similarity test — which is why NOTHING HERE COMPARES SENTENCES. The
    read is shown the thread and names the id.
    """
    from nm.core.issues import read

    standing = (Issue(thread="t", statement="What is the limitation period?",
                      kind=IssueKind.THRESHOLD, runs_against=Side.MOVING,
                      proof="the account", id="iss_aaa"),)
    said = {"issues": [{"statement": "Is the claim time-barred?",
                        "kind": "threshold", "runs_against": "moving",
                        "quoted": "the account", "restates": "iss_aaa"}]}
    spotted = read(said, "t", Quotable(file="the account"), standing).issues
    assert [i.id for i in spotted] == ["iss_aaa"], (
        "the read named an id and it was not carried, so the merge has "
        "nothing to match on and falls back to comparing sentences")
    assert len(issue_domain.merge(standing, spotted)) == 1


def test_an_id_the_thread_does_not_hold_is_dropped():
    """A restatement pointing at nothing would silently become a new issue
    anyway; one pointing at ANOTHER thread's issue would merge two threads'
    work. Both are the silent direction, so the id is checked against what
    this thread actually holds."""
    from nm.core.issues import read

    standing = (Issue(thread="t", statement="What is the limitation period?",
                      kind=IssueKind.THRESHOLD, runs_against=Side.MOVING,
                      proof="the account", id="iss_aaa"),)
    said = {"issues": [{"statement": "A genuinely different question?",
                        "kind": "threshold", "runs_against": "moving",
                        "quoted": "the account", "restates": "iss_elsewhere"}]}
    spotted = read(said, "t", Quotable(file="the account"), standing).issues
    assert spotted and spotted[0].id != "iss_elsewhere"
    assert len(issue_domain.merge(standing, spotted)) == 2


def test_nothing_decides_two_sentences_are_one_issue_by_comparing_them():
    """CLAUDE.md 5, on the one axis where it is tempting to break it.

    Two issues about DIFFERENT provisions can read nearly identically, and two
    phrasings of one question can share no words. A similarity threshold gets
    both wrong, and the wrong direction — merging two real issues — loses one
    silently.
    """
    a = _issue("Is the claim under Article 54 time-barred?")
    b = _issue("Is the claim under Article 65 time-barred?")
    assert len(issue_domain.merge((a,), (b,))) == 2, (
        "two issues about different Articles were folded into one. The only "
        "thing that may decide they are the same is the READ naming an id")
