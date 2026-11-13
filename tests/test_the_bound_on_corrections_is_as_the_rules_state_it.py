"""The bound on corrections is as the rules state it (plan AN.53, 53f; D221 as refined by D243; the review's F-23).

The rules said 'one turn-owned ledger ... nested activities cannot reset its bound', and the ledger's own description said 'no
nested stage receives a fresh allowance'. The code's bound is finer, and two small calls sit outside it. The rule (AGENTS.md)
and the description (nm/core_engine/calls.py) now say what is true, and this file holds each fact they state, so that a change
to either the code or the words that parts them fails here:

- the turn's total is durable: the attempt store keeps what was used across a retry, a restart and Continue, and a run of the
  turn begins from it, never from nothing;
- within it each scope has its own allowance (the shared steps one between them, each section two, each edit one), which starts
  afresh with each run of the turn and after a steer - the total does not;
- the title and the reader of a message sent while a matter waits each ask once more on their own, outside it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nm.core_engine import calls as ledger
from nm.core_engine import titles
from nm.core_engine.calls import ALLOWANCE, EDIT_ALLOWANCE, SECTION_ALLOWANCE, SHARED_ALLOWANCE, CorrectionUnavailable, TurnCalls
from nm.shared.model_port import Completion, ModelResult, Usage
from nm.shared.turn_attempt_store import ALLOWANCE as DURABLE_ALLOWANCE
from nm.shared.turn_attempt_store import FileTurnAttempts

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


class _Model:
    def context_budget(self, tier):
        return 100_000


def _spend(turn, scope, allowance, times):
    spent = 0
    with turn.scope(scope, allowance):
        for _ in range(times):
            try:
                turn.spend("core_response_writer")
            except CorrectionUnavailable:
                break
            spent += 1
    return spent


def test_the_allowances_are_the_ones_the_rules_and_the_description_name():
    assert (SHARED_ALLOWANCE, SECTION_ALLOWANCE, EDIT_ALLOWANCE, ALLOWANCE) == (1, 2, 1, 32)
    assert DURABLE_ALLOWANCE == ALLOWANCE, "the store that keeps the total holds the same total"


def test_each_scope_has_its_own_allowance_and_every_correction_counts_towards_the_total():
    turn = TurnCalls(_Model(), corrections_used=3)
    assert _spend(turn, "section-D1", SECTION_ALLOWANCE, 5) == 2
    assert _spend(turn, "section-D2", SECTION_ALLOWANCE, 5) == 2, "another section's own allowance"
    assert turn.corrections_used == 7


def test_a_new_run_of_the_turn_starts_each_scope_afresh_and_the_total_where_it_was():
    first = TurnCalls(_Model(), corrections_used=0)
    _spend(first, "section-D1", SECTION_ALLOWANCE, 5)
    again = TurnCalls(_Model(), corrections_used=first.corrections_used)   # Continue, a restart, the next step
    assert _spend(again, "section-D1", SECTION_ALLOWANCE, 5) == 2, "the section's allowance starts afresh"
    assert again.corrections_used == 4, "the total goes on from where it was"


def test_a_steer_starts_each_scope_afresh_and_carries_the_total():
    turn = TurnCalls(_Model(), corrections_used=0)
    _spend(turn, "section-D1", SECTION_ALLOWANCE, 5)
    after = turn.successor()
    assert after.corrections_used == 2 and _spend(after, "section-D1", SECTION_ALLOWANCE, 5) == 2


def test_no_run_and_no_scope_passes_the_total():
    nearly = TurnCalls(_Model(), corrections_used=ALLOWANCE - 1)
    assert _spend(nearly, "section-D1", SECTION_ALLOWANCE, 5) == 1
    assert _spend(TurnCalls(_Model(), corrections_used=ALLOWANCE), "section-D2", SECTION_ALLOWANCE, 5) == 0


def test_the_attempt_store_keeps_the_total_across_a_retry(tmp_path):
    store = FileTurnAttempts(tmp_path / "attempts.sqlite")
    identity, digest = "a" * 64, "b" * 64
    claim = store.claim(identity, digest)
    for _ in range(3):
        store.consume_correction(identity, claim["token"])
    store.finish(identity, claim["token"], "retryable", "interrupted")
    assert store.claim(identity, digest)["corrections_used"] == 3, "a run after it begins from what was used"


class _Titling:
    """Answers every title it is asked for with one code cannot show, and counts the asks."""

    def __init__(self):
        self.asks = 0

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.asks += 1
        return ModelResult(text=None, data={"title": ""}, tier=tier, provider="stand-in", model="m", usage=Usage(1, 1, 0),
                           latency_ms=1, completion=Completion.COMPLETE)


def test_the_title_asks_once_more_on_its_own_and_no_more():
    model = _Titling()
    assert titles.entitle(model, {"message": "A question."}) is None and model.asks == 2


def test_the_rule_and_the_ledgers_description_say_all_of_it():
    rules = " ".join((ROOT / "AGENTS.md").read_text(encoding="utf8").split())
    for said in ("Its total is durable per turn", "starts afresh with each run of the turn",
                 "the conversation's title and the reader of a message sent while a matter waits",
                 "each ask once more on their own, outside the ledger"):
        assert said in rules, said
    described = " ".join((TurnCalls.__doc__ or "").split())
    assert "No nested stage receives a fresh allowance" not in described, "the description that was not true"
    for name in ("ALLOWANCE", "SHARED_ALLOWANCE", "SECTION_ALLOWANCE", "EDIT_ALLOWANCE", "successor", "titles.py",
                 "message_reader.py"):
        assert name in described, name
    assert re.search(r"no retry, restart, Continue, step or steer resets it", described)
    assert json.dumps(ledger.ALLOWANCE)  # the names it cites are the module's own
