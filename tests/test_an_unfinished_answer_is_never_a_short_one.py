"""AN UNFINISHED ANSWER IS NEVER A SHORT ONE. BK-49-AC1, BK-29-AC1/AC2,
BK-41-AC1. P37.

WHAT THESE DEFEND
-------------------
A provider that stops at the token limit returns prose that ends mid-sentence,
or -- with a structured read -- JSON that happens to close its braces and
passes the schema check. Both parse. Both are wrong in a way no downstream
check can see, because what is missing left no trace.

    THE ADAPTER CHECKED EXACTLY ONE FINISH REASON. `content_filter` was
    handled and `length` was not handled anywhere, so a cut-off answer came
    back as an ordinary one and reached legal work.

And the budget half, which is the same shape one level out: six things an
operation can exhaust -- time, tokens, money, retries, delegated children, and
the advocate's cancellation -- with each bounded at a call site or not at all.

    A CHILD WITH A FRESH BUDGET MAKES THE PARENT'S BUDGET A SUGGESTION. Five
    children of one minute each under a one-minute cap is five minutes, and
    the delegation comparison is then measuring something that was never
    bounded -- which is BK-92-AC4's negative control exactly.
"""
from __future__ import annotations

import pytest
from nm.domain.budget import (
    STAGES,
    Budget,
    Completion,
    Exhausted,
    Spend,
    progress,
    refuse_partial,
)

pytestmark = pytest.mark.class_a


# ============== 1. BK-49-AC1 -- every completion mode is typed ==============

def test_only_complete_is_usable_and_it_is_written_once():
    """No consumer decides for itself what a finished answer is."""
    assert Completion.COMPLETE.usable_for_legal_work is True
    for other in (Completion.LENGTH_LIMITED, Completion.FILTERED,
                  Completion.CANCELLED, Completion.NOT_ESTABLISHED):
        assert other.usable_for_legal_work is False


def test_silence_about_how_it_stopped_is_not_a_claim_that_it_finished():
    """Section 9, at the point where the absent input is a sentence somebody
    reads out in court."""
    assert Completion.not_established() is Completion.NOT_ESTABLISHED
    assert Completion.NOT_ESTABLISHED.usable_for_legal_work is False
    assert "not known to be finished" in Completion.NOT_ESTABLISHED.said()


def test_a_model_result_defaults_to_not_established():
    """The DEFAULT is the honest one. An adapter that says nothing must not
    thereby say the answer finished."""
    from nm.ports.model import ModelResult, Tier, Usage

    got = ModelResult(text="something", data=None, tier=Tier.ROUTINE,
                      provider="p", model="m",
                      usage=Usage(tokens_in=1, tokens_out=1, cost_usd=0.0),
                      latency_ms=1)
    assert got.completion is Completion.NOT_ESTABLISHED
    assert got.usable is False


def test_a_length_stop_is_named_as_unfinished_rather_than_short():
    said = Completion.LENGTH_LIMITED.said()
    assert "ran out of room" in said
    assert "not a short answer" in said


@pytest.mark.parametrize("reason,expected", [
    ("stop", Completion.COMPLETE),
    ("length", Completion.LENGTH_LIMITED),
    ("max_tokens", Completion.LENGTH_LIMITED),
    ("content_filter", Completion.FILTERED),
    (None, Completion.NOT_ESTABLISHED),
    ("some_reason_invented_next_year", Completion.NOT_ESTABLISHED),
])
def test_the_finish_reason_table_covers_the_population_and_its_absence(
        reason, expected):
    """AN UNRECOGNISED REASON IS NOT ESTABLISHED, never complete. A provider
    that adds a stop reason tomorrow must not have it read as finished by a
    table written today."""
    from nm.adapters.model.openai_adapter import _completion_of

    assert _completion_of(reason) is expected


def test_the_adapter_refuses_a_length_limited_response_that_parses():
    """BK-49-AC1'S NEGATIVE CONTROL: *return a provider length-limited
    response that happens to parse correctly* -> *the adapter refuses
    complete-result status before a consumer uses it*.

    The JSON here is valid and satisfies the schema. Nothing downstream could
    tell; the finish reason is the only evidence there is.
    """
    from nm.adapters.model.openai_adapter import OpenAIModelAdapter
    from nm.ports.model import OutputTruncated, Prompt, Tier

    adapter = OpenAIModelAdapter(_config(), client=_Client("length"))
    with pytest.raises(OutputTruncated, match="unfinished, not short"):
        adapter.structured(Prompt(system="s", user="u"),
                           {"type": "object",
                            "properties": {"a": {"type": "string"}},
                            "required": ["a"], "additionalProperties": False},
                           Tier.ROUTINE)


def test_the_same_response_with_a_normal_stop_is_returned():
    """THE POSITIVE CONTROL. A check that refused every response would be
    turned off within a week."""
    from nm.adapters.model.openai_adapter import OpenAIModelAdapter
    from nm.ports.model import Prompt, Tier

    adapter = OpenAIModelAdapter(_config(), client=_Client("stop"))
    got = adapter.structured(Prompt(system="s", user="u"),
                             {"type": "object",
                              "properties": {"a": {"type": "string"}},
                              "required": ["a"],
                              "additionalProperties": False},
                             Tier.ROUTINE)
    assert got.completion is Completion.COMPLETE
    assert got.usable is True
    assert got.data == {"a": "whole"}


def test_a_text_read_is_covered_by_the_same_check():
    """*both text and structured reads*, in the criterion's own words. The
    text path is the one where truncation is most obvious to a human and
    least visible to a program."""
    from nm.adapters.model.openai_adapter import OpenAIModelAdapter
    from nm.ports.model import OutputTruncated, Prompt, Tier

    adapter = OpenAIModelAdapter(_config(), client=_Client("length"))
    with pytest.raises(OutputTruncated):
        adapter.complete(Prompt(system="s", user="u"), Tier.ROUTINE)


# ---- the double: a provider that answers, and says how it stopped --------

class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason):
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5
    prompt_tokens_details = None


class _Response:
    def __init__(self, content, finish_reason):
        self.choices = [_Choice(content, finish_reason)]
        self.usage = _Usage()


class _Completions:
    def __init__(self, finish_reason):
        self._finish_reason = finish_reason

    def create(self, **_kwargs):
        # VALID JSON THAT SATISFIES THE SCHEMA. That is the whole point of the
        # counterexample: nothing about the payload says it was cut off.
        return _Response('{"a": "whole"}', self._finish_reason)


class _Chat:
    def __init__(self, finish_reason):
        self.completions = _Completions(finish_reason)


class _Client:
    def __init__(self, finish_reason):
        self.chat = _Chat(finish_reason)


def _config():
    """The real config shape, so the adapter runs its real path."""
    from nm.adapters.model.config import ModelConfig, TierConfig
    from nm.ports.model import Tier

    return ModelConfig(tiers={
        t: TierConfig(t, "openai", "gpt-test", "not-a-real-key", None)
        for t in Tier})


# ============ 2. BK-29-AC2 -- refused before legal work accepts it ==========

def test_refuse_partial_is_silent_on_a_complete_answer():
    assert refuse_partial(Completion.COMPLETE, doing="the posture read") == ""


@pytest.mark.parametrize("state", [
    Completion.LENGTH_LIMITED, Completion.FILTERED, Completion.CANCELLED,
    Completion.NOT_ESTABLISHED])
def test_refuse_partial_names_the_work_and_the_reason(state):
    why = refuse_partial(state, doing="the posture read")
    assert "the posture read" in why
    assert "not accepted as a complete result" in why


def test_the_one_read_funnel_refuses_before_returning():
    """STRUCTURAL, over the compiled source. BK-29-AC2's words are *before
    dependent legal work is accepted*, and `TurnEngine._read` is the one place
    every structured read passes through -- so a read added next month is
    covered without its author knowing this rule exists."""
    import inspect

    from nm.core.turn import TurnEngine

    source = inspect.getsource(TurnEngine._read)
    assert "refuse_partial" in source
    assert "OutputTruncated" in source


# ============= 3. BK-29-AC1 -- one schema-aware budget mechanism ============

def test_the_ceiling_is_derived_for_an_echoing_read_and_stated_otherwise():
    """The mechanism BK-29-AC1 asks for already exists; this keeps it. A read
    that quotes gets room proportional to what it was shown, and a read whose
    answer is a fixed shape gets a number stated once, in one table."""
    from nm.core import ceiling
    from nm.ports.model import Prompt

    short = Prompt(system="s", user="a brief")
    long = Prompt(system="s", user="a brief " * 400)
    assert ceiling.for_echo(long) > ceiling.for_echo(short)
    assert ceiling.for_read("route", long, echoes=False) == ceiling.FIXED["route"]
    assert ceiling.for_read("route", long, echoes=True) == ceiling.for_echo(long)


def test_an_unlisted_read_gets_the_floor_and_not_an_invented_number():
    from nm.core import ceiling
    from nm.ports.model import Prompt

    assert ceiling.for_read("a_read_nobody_listed", Prompt(system="s", user="u"),
                            echoes=False) == ceiling.FLOOR


def test_the_derived_ceiling_is_bounded_at_both_ends():
    """The floor stops a one-line brief producing a ceiling too small for the
    JSON around an empty answer; the cap stops a pasted judgment producing a
    request the provider refuses."""
    from nm.core import ceiling
    from nm.ports.model import Prompt

    assert ceiling.for_echo(Prompt(system="", user="x")) == ceiling.FLOOR
    assert ceiling.for_echo(Prompt(system="", user="x " * 100000)) == ceiling.CAP


# ================ 4. BK-41-AC1 -- one budget, six exhaustions ===============

def test_a_fresh_budget_with_no_limits_says_so_rather_than_looking_bounded():
    """A limit of zero is "not bounded here", and `declared()` makes an
    unbounded operation VISIBLE rather than silently unlimited."""
    free = Budget()
    assert free.declared() == ()
    assert free.spent_out is False
    assert "No limit is recorded" in free.said()


@pytest.mark.parametrize("field,spend,expected", [
    ("max_ms", Spend(elapsed_ms=1000), Exhausted.TIME),
    ("max_tokens", Spend(tokens=1000), Exhausted.TOKENS),
    ("max_cost_usd", Spend(cost_usd=1000.0), Exhausted.COST),
    ("max_retries", Spend(retries=1000), Exhausted.RETRIES),
    ("max_children", Spend(children=1000), Exhausted.CHILDREN),
])
def test_each_of_the_five_limits_is_named_when_it_runs_out(field, spend,
                                                           expected):
    """A single `over_budget` boolean sends whoever reads it to look at the
    wrong one: more time will not help a token exhaustion."""
    budget = Budget(**{field: 1}).spend_on(spend)
    assert budget.exhausted() is expected
    assert budget.spent_out is True
    assert budget.said()


def test_cancellation_wins_over_every_other_limit():
    """An operation the advocate stopped is stopped whatever else is true."""
    budget = Budget(max_ms=1).spend_on(Spend(elapsed_ms=9999)).cancel("t1")
    assert budget.exhausted() is Exhausted.CANCELLED
    assert "You stopped this" in budget.said()


def test_cancelling_twice_keeps_the_first_time():
    once = Budget().cancel("t1")
    assert once.cancel("t2").cancelled_at == "t1"


def test_a_cancellation_records_when():
    with pytest.raises(ValueError, match="records when"):
        Budget().cancel("")


def test_spend_accumulates_rather_than_replacing():
    budget = Budget().spend_on(Spend(tokens=10)).spend_on(Spend(tokens=5))
    assert budget.spend.tokens == 15


def test_wasted_work_is_counted_and_not_dropped():
    """BK-92-AC4's negative control: *exclude failed or cancelled children and
    retry costs*. An approach that is fast when its failures are not counted
    is not fast."""
    spent = Spend(children=3, failed_children=2, retries=4,
                  discarded_results=1).as_dict()
    assert spent["failed_children"] == 2
    assert spent["retries"] == 4
    assert spent["discarded_results"] == 1


# ============== 5. a child gets what is LEFT, never a fresh copy ============

def test_a_child_inherits_the_remainder():
    parent = Budget(max_ms=1000, max_tokens=100).spend_on(
        Spend(elapsed_ms=400, tokens=30))
    child = parent.for_child()
    assert child.max_ms == 600
    assert child.max_tokens == 70


def test_a_child_of_an_exhausted_parent_has_nothing():
    parent = Budget(max_ms=100).spend_on(Spend(elapsed_ms=100))
    assert parent.for_child().max_ms == 0


def test_a_cancelled_parent_hands_the_cancellation_down():
    """A child that kept running after its parent was cancelled is the
    cancellation the advocate believes in and the queue does not."""
    child = Budget(max_ms=1000).cancel("t1").for_child()
    assert child.exhausted() is Exhausted.CANCELLED


def test_an_unbounded_parent_does_not_hand_down_a_bound_of_zero():
    """Zero means "not bounded here", so subtracting into it would turn an
    unbounded parent into a child that can do nothing."""
    child = Budget(max_tokens=0).spend_on(Spend(tokens=50)).for_child()
    assert child.max_tokens == 0
    assert child.spent_out is False


def test_the_child_ledger_starts_empty_so_nothing_is_counted_twice():
    parent = Budget(max_ms=1000).spend_on(Spend(elapsed_ms=400))
    assert parent.for_child().spend.elapsed_ms == 0


# ================= 6. progress is a stage, never a percentage ===============

def test_progress_reports_a_stage_that_was_actually_reached():
    got = progress("retrieving authority", saved=False)
    assert got["stage"] == "retrieving authority"
    assert got["saved"] is False
    assert "Nothing has been written" in got["said"]


def test_progress_carries_no_percentage_anywhere():
    """A number invented from a stage index is a claim about how much is left,
    and this product does not know that."""
    for reached in STAGES:
        for saved in (True, False):
            got = progress(reached, saved=saved)
            assert "%" not in repr(got)
            assert not any(isinstance(v, float) for v in got.values())


def test_an_unknown_stage_is_not_established_rather_than_zero():
    got = progress("somewhere", saved=False)
    assert got["stage"] == "not established"
    assert "not known" in got["said"]


def test_progress_says_what_is_safe_to_do_next():
    """BK-41-AC1: *what is happening, what remains reliable and what they can
    safely do next*. The third is the one a spinner never answers."""
    assert progress("saved", saved=True)["safe_next"]
    assert "nothing needs undoing" in progress("reasoning", saved=False)["safe_next"]


def test_reaching_the_saved_stage_is_not_the_same_as_having_saved():
    """`saved` is read from the store by the caller, never inferred from the
    stage -- and a progress bar would happily report the second."""
    got = progress("saved", saved=False)
    assert got["saved"] is False
    assert "Nothing has been written to the file yet" in got["said"]
