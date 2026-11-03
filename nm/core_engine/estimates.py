"""What a model call, and a turn, is expected to cost before the work is done (plan AN.37, D41 and D45; owner, 3 Nov 2026: "I also
want to calculate approximate cost before every model call and then put a counter against that estimate ... so that we avoid any
loops which spiral the costs" and, on the counter, "may just record them for diagnostics and no impact on the live coversation").

DIAGNOSTICS ONLY. Nothing here holds a call back, cuts one short or tells the advocate anything: the turn keeps each call's estimate
beside what it cost, and the turn's estimates beside what it spent (calls.TurnCalls), and says in the log where spending passed them.
Only the allowance stops a turn (D42).

WHERE THE NUMBERS COME FROM. A call's input is counted as it is sent (model_port.estimate_tokens, which errs high) and priced as fresh
input, so a cached read makes the call cost less than its estimate, never more. Its output is the usual output of its step, measured
from the calls kept in the usage records up to 31 Oct 2026 (the median of the answered calls of each step, on 6 Luna, at each step's
own level), moved by how far the level the call is sent at stands from the step's own (OUTPUT_FACTOR: a first measure, from the
first paid run of 1 Nov 2026 - writing about three times the output at high, reviewing about twice). A turn's estimates are the
paid runs of 3 Nov 2026 on 6 Luna at medium (research v18): one paper 10 cents; two papers and two disputes 21 cents. Each call now
records its level and its estimate, so these are measured again from the calls themselves and not from belief.
"""
from __future__ import annotations

from nm.shared.model_config import token_pricing
from nm.shared.model_port import ConfigurationError

#: The usual output of a step, in tokens, at the step's own level: the median of its answered calls in the usage records to
#: 31 Oct 2026 (6 Luna). A step not measured there takes USUAL_DEFAULT.
USUAL_OUTPUT = {
    "core_understanding": 173, "core_research_understand": 7_348, "core_research_check": 901, "core_research_revise": 6_067,
    "core_research_chronology": 2_215, "core_research_transfers": 73, "core_research_phrases": 716,
    "core_research_judgment_phrases": 1_476, "core_research_pick": 827, "core_research_judgment_pick": 596,
    "core_response_writer": 2_269, "core_response_review": 756, "core_response_overview": 2_527,
    "core_response_cross_check": 267, "core_calculation": 335, "core_page_reading": 1_147,
}
USUAL_DEFAULT = 2_000
#: Output against a step at medium, by the level a call is sent at; None is the release's own setting, low for these models.
OUTPUT_FACTOR = {None: 0.6, "low": 0.6, "medium": 1.0, "high": 2.5, "max": 4.0}
#: Output is about a quarter of what a turn costs (plan AN.30): a turn moves with its level by a quarter of its output's move.
OUTPUT_SHARE = 0.25
#: A turn's usual cost on 6 Luna at medium (3 Nov 2026): for each paper sent, before its plan is known; once it is, what is spent
#: then and, for each dispute, its research, section and review, with the overview where there are two or more.
PER_PAPER_USD = 0.10
PER_DISPUTE_USD = 0.08
OVERVIEW_USD = 0.02
BASE_MODEL = "gpt-6-luna"
#: Where what was spent passes an estimate this many times, the log says so (D45: recorded; nothing else follows).
OVER_CALL = 3.0
OVER_TURN = 1.5


def _factor(level):
    return OUTPUT_FACTOR.get(level, 1.0)


def call_usd(model, tokens_in, operation, *, own=None, sent=None):
    """A call's expected cost in dollars before it is sent: tokens_in, its input as counted, at the price of fresh input, and the
    usual output of its step (operation), moved from the step's own level (own) to the level it is sent at (sent). None where the
    model's price is not established."""
    try:
        pricing = token_pricing(model)
    except ConfigurationError:
        return None
    if type(tokens_in) is not int or tokens_in < 0:
        return None
    output = round(USUAL_OUTPUT.get(operation, USUAL_DEFAULT) * _factor(sent) / _factor(own))
    return pricing.cost_usd(tokens_in, output)


def _scale(model, choice):
    """How many times a turn on model at the effort chosen (choice) costs one on 6 Luna at medium; None where a price is not
    established."""
    try:
        ratio = token_pricing(model).output_rate / token_pricing(BASE_MODEL).output_rate
    except ConfigurationError:
        return None
    return float(ratio) * ((1 - OUTPUT_SHARE) + OUTPUT_SHARE * _factor(choice))


def turn_start_usd(model, papers, choice):
    """A turn's rough estimate before its plan is known: the papers sent with the conversation (at least one turn's worth), on
    model at the effort chosen for the turn (choice)."""
    scale = _scale(model, choice)
    return None if scale is None else round(PER_PAPER_USD * max(1, papers) * scale, 6)


def turn_planned_usd(model, spent, disputes, choice):
    """A turn's estimate once its plan is known: what it has spent (spent, dollars) and, for each of its disputes, the usual."""
    scale = _scale(model, choice)
    if scale is None:
        return None
    rest = PER_DISPUTE_USD * max(1, disputes) + (OVERVIEW_USD if disputes > 1 else 0)
    return round(spent + rest * scale, 6)


def passed(spent, estimate, times):
    """Whether spent passes estimate by the given times; never where either is not known."""
    return (isinstance(spent, (int, float)) and isinstance(estimate, (int, float)) and estimate > 0
            and spent > estimate * times)
