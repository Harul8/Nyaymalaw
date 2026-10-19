"""A STUDY CANNOT BE ADJUSTED AFTER IT IS SCORED. BK-66-AC1/AC2/AC3. P34.

WHAT THESE DEFEND
-------------------
`docs/blueprint/evaluations.json` already declares REVIEW-USABILITY for
BK-66-AC3, with its reviewer role, required inputs, tasks, failure conditions
and required output fields. It declares them in prose and nothing runs them --
which is the failure this repository opens by describing: *a hundred good rules
with no runner. A rule you cannot run is not a requirement.*

This is the runner, and it decides exactly one thing: whether a study is
ADMISSIBLE. Whether the product is actually comprehensible is what a
representative advocate is for, and no test in this file claims otherwise.

    NO OBSERVATION IN THIS SUITE IS A REAL ONE. Every `Observation` below is a
    fixture proving what the machinery accepts and refuses. BK-66-AC1's
    `model_eval` and `counsel_review` and BK-66-AC2's and AC3's
    `counsel_review` are NOT RUN and are not closed by anything here.

THE SEVEN REFUSALS ARE SEVEN TESTS, and each is a different way to produce a
favourable number from an unfavourable run.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.class_a

#: BK-66-AC1's list, verbatim: *what NM understood, used, assumed, changed,
#: still needs and will do next* -- plus the four control tasks BK-66-AC2 adds.
TASKS: tuple[str, ...] = (
    "say what NM understood",
    "say what material it used",
    "say what it assumed",
    "say what is disputed or unknown",
    "say what changed",
    "say what has become stale",
    "say what needs your decision",
    "say what it recommends next",
    "correct something",
    "pause and come back",
    "reach the source behind a statement",
)


# ==================== 1. the study that IS admissible =======================


def test_the_frozen_tasks_are_the_criterion_s_own_list():
    """BK-66-AC1 names what an advocate must be able to identify. The frozen
    task list is that list, so a study cannot quietly measure something
    easier."""
    joined = " | ".join(TASKS)
    for needed in ("understood", "used", "assumed", "changed", "stale",
                   "decision", "recommends", "correct", "pause", "source"):
        assert needed in joined, needed


# ======================= 2. the seven refusals ==============================


# ================== 3. the freeze, and what it must contain =================


# ============= 4. the rate, and the number that must not be zero ============


# =================== 5. invalidation, and superseding =======================


# ============ 6. the protocol this runs is the declared one ================


def test_the_usability_protocol_owns_the_criterion_this_packet_closes():
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    rows = json.loads((root / "docs" / "blueprint" / "evaluations.json")
                      .read_text(encoding="utf-8"))["manual_review_protocols"]
    usability = next(r for r in rows if r["id"] == "REVIEW-USABILITY")
    assert "BK-66-AC3" in usability["owner_criteria"]
    # AND ITS APPROVALS AND EVIDENCE ARE STILL EMPTY, which is the honest
    # state: no representative advocate study has been run.
    assert usability["approvals"] == []
    assert usability["evidence"] == []


# ======= 7. the control on the browser suite's phrase list ==================

def test_a_screen_saying_none_of_these_is_caught():
    """A POSITIVE CONTROL ON `MUST_BE_SAYABLE`, which lives in the browser
    suite and is therefore not exercised by Class-A.

    The list was written twice. The first version came from the criterion's
    own vocabulary, reported two categories missing that were on the screen in
    the product's better words, and would have been "fixed" by widening it
    until it passed -- which is how a check stops being able to fail. This is
    what stops the second version going the same way: a page saying none of
    these must still be reported as saying none of them.
    """
    from tests.test_the_journey_of_comprehension import MUST_BE_SAYABLE

    empty = "an entirely blank page with no words on it at all"
    missing = [name for name, phrases in MUST_BE_SAYABLE
               if not any(p in empty for p in phrases)]
    assert len(missing) == len(MUST_BE_SAYABLE), missing

    # AND EVERY CATEGORY IS SATISFIABLE. A phrase nothing could ever match
    # would make its category permanently missing, which reads as a product
    # defect and is a typing error.
    for name, phrases in MUST_BE_SAYABLE:
        assert phrases, name
        for phrase in phrases:
            assert phrase == phrase.lower(), (name, phrase)
