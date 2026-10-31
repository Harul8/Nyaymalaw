"""How hard each step reasons is one policy (plan AN.30; owner, 1 Nov 2026: "review and update where and how more reasoning should be
used to optimize costs").

Input, not thought, drives what a turn costs: a big pass (a section written, a review, a take-up) carries 100,000 to 200,000 tokens and costs
about a cent and a half, while 4,000 more tokens of reasoning cost a fifth of a cent. So reasoning is given where it can prevent a
repeated pass or a wrong answer and costs little - every second look whose answer is small a level above its step, and the steps whose
miss reaches the advocate - and withheld where thought cannot change the result (the search steps stay at the release's own setting) or
costs more than it saves: the first paid run of the new build (1 Nov 2026) measured writing and reviewing at high at three times the
output and twice the time, so they stay at medium. reasoning.py holds the table; every call asks it. Fakes stand in for the models: this
pins what each call asks, not how a model reasons.
"""
import json
import re
from pathlib import Path

import pytest

from nm.core_engine import reasoning, research, response_review, response_writer, understanding
from nm.core_engine.research import plan
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage, estimate_tokens
from tests.test_a_total_the_model_worked_out_is_not_a_figure_the_papers_give import SAID, stating
from tests.test_core_calculation import Calculating, chain, fixed_bad, turn
from tests.test_core_research import Model, operations
from tests.test_core_turn import store  # noqa: F401 - pytest fixture
from tests.test_core_understanding import Model as Understood, context as typed, unit
from tests.test_only_the_failing_piece_is_looked_at_again_and_blocked import answered as answered_two
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import Opening, taking_up

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parent.parent

#: step -> (level, whether a large input raises it)
TABLE = {
    "message": ("medium", False),
    "understand": ("medium", True), "check": ("medium", True), "revise": ("high", True),
    "chronology": ("medium", True), "transfers": ("medium", True), "connections": ("medium", True),
    "chronology_check": ("high", True), "transfers_check": ("high", True), "connections_check": ("high", True),
    "phrases": (None, False), "judgment_phrases": (None, False), "pick": (None, False), "judgment_pick": (None, False),
    "write": ("medium", False), "overview": ("medium", False), "review": ("medium", False), "cross_check": ("medium", False),
    "repair": ("high", False), "take_up": ("high", False),
    "calculate": ("medium", False), "calculate_correct": ("high", False),
    "read_page": (None, False), "read_again": ("medium", False), "relook": ("medium", False),
}


def test_the_table_is_what_the_plan_decided():
    assert reasoning.STEPS == TABLE and reasoning.LEVELS == ("low", "medium", "high") and reasoning.LARGE_FILE_TOKENS == 60_000


@pytest.mark.parametrize("step", sorted(TABLE))
def test_a_step_asks_its_level_a_large_input_a_level_more_a_look_again_a_level_more_and_never_above_high(step):
    level, sized = TABLE[step]
    big = reasoning.LARGE_FILE_TOKENS + 1
    if level is None:
        assert reasoning.effort(step, tokens=big, again=True) is None, "the release's own setting stays its own"
        return
    assert reasoning.effort(step) == level
    assert reasoning.effort(step, tokens=reasoning.LARGE_FILE_TOKENS) == level, "more than the threshold, not the threshold"
    assert reasoning.effort(step, tokens=big) == (reasoning.raised(level) if sized else level)
    assert reasoning.effort(step, again=True) == reasoning.raised(level)
    assert reasoning.effort(step, tokens=big, again=True) in ("medium", "high") and reasoning.effort(step, tokens=10 ** 9, again=True) != "xhigh"
    assert reasoning.raised("high") == "high" and reasoning.raised(None) is None and reasoning.raised("low") == "medium"


def test_every_step_the_product_runs_has_a_level():
    assert set(research.MAX_OUTPUT) <= set(reasoning.STEPS), "each research step is a step of the table"
    for step in ("message", "write", "overview", "review", "cross_check", "repair", "take_up", "calculate", "calculate_correct",
                 "read_page", "read_again", "relook"):
        assert step in reasoning.STEPS


def test_no_call_sets_a_level_by_hand():
    """A second home for the rule is the defect (one rule, one owner): outside the table, no source sets effort to a level."""
    pattern = re.compile(r"""effort["']?\s*[=:]\s*["'](?:low|medium|high)["']""")
    found = []
    for path in sorted((ROOT / "nm").rglob("*.py")):
        if "Archives" in path.parts or "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and not line.lstrip().startswith("#"):
                found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:90]}")
    assert not found, found


def test_the_research_steps_ask_the_table_and_the_check_of_a_revision_looks_again():
    slip = stating("The invoices of 25 and 30 kg total 55 kg, not 110 kg.")
    fixed = stating("The invoices show 25 and 30 kg and the purchase agreement 110 kg.")
    model = Model(slip, revisions=[fixed])
    plan(model, typed(SAID))
    asked = [(prompt.operation, prompt.effort) for prompt in model.calls]
    assert asked[:4] == [("core_research_understand", "medium"), ("core_research_check", "medium"),
                         ("core_research_revise", "high"), ("core_research_check", "high")]
    assert all(effort is None for operation, effort in asked if operation in ("core_research_phrases", "core_research_pick")), \
        "the measured search steps stay at the release's own setting"
    assert operations(model)[:4] == [name for name, _ in asked[:4]]


class Spy:
    """A model that keeps the prompts it is asked and answers with what `data` says."""

    def __init__(self, data):
        self.data, self.prompts = data, []

    def context_budget(self, tier):
        return 10 ** 9

    def structured(self, prompt, schema, tier, **kwargs):
        self.prompts.append(prompt)
        return ModelResult(None, json.loads(json.dumps(self.data)), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def test_the_writer_reasons_at_medium_however_large_its_material_and_the_older_writers_ask_nothing():
    """A writing at high measured 27,600 tokens and 194 seconds against about nine thousand and 90 at medium (1 Nov 2026): size does not raise it."""
    small, large = {"original_context": "word " * 100}, {"original_context": "word " * 80_000}
    assert estimate_tokens(json.dumps(small)) < reasoning.LARGE_FILE_TOKENS < estimate_tokens(json.dumps(large))
    efforts = []
    for payload, step in ((small, "write"), (large, "write"), (large, None)):
        spy = Spy({"units": []})
        response_writer._write_part(spy, payload, step=step)
        efforts.append((spy.prompts[0].effort, bool(spy.prompts[0].cache_through)))
    assert efforts == [("medium", True), ("medium", True), (None, False)]


class Watching(Opening):
    """The two-dispute answer of the take-up test, keeping each prompt it is asked."""

    def __init__(self, taking):
        super().__init__(taking)
        self.prompts = []

    def structured(self, prompt, schema, tier, **kwargs):
        self.prompts.append(prompt)
        return super().structured(prompt, schema, tier, **kwargs)


def test_the_answer_asks_the_table_the_take_up_looks_again_and_the_writing_and_the_reviews_stay_at_medium():
    model = Watching(taking_up)
    answered_two(model)
    by = {}
    for prompt in model.prompts:
        by.setdefault(prompt.operation, []).append(prompt.effort)
    assert by["core_response_writer"] == ["medium", "medium"]
    assert by["core_response_overview"] == ["medium"]
    assert by["core_response_take_up"] == ["high"]
    assert by["core_response_cross_check"] == ["medium"]
    # Two sections and the overview are reviewed once each; the overview, changed by its take-up, is reviewed again - at medium too.
    assert by["core_response_review"] == ["medium"] * 4


def test_the_review_reasons_at_medium_and_the_older_reviews_ask_nothing():
    from nm.core_engine import response_authorities
    from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import V14, matter
    from tests.test_the_review_is_shown_the_chronology import Reviewer
    from tests.test_the_writer_and_review_are_shown_copies_read_differently import quiet
    from tests.test_the_writer_is_shown_the_chronology import Writer

    ctx, record, sources = matter()
    draft = response_writer.write_section(Writer(quiet), ctx, record, sources, index=0, contract=V14)
    evidence = response_authorities.check(ctx, record, sources, draft)
    reviewer = Reviewer()
    response_review.review(reviewer, ctx, record, sources, draft, research.execution(record), authority_evidence=evidence,
                           contract=response_review.WORDED_CONTRACT)
    assert reviewer.seen[0][0].effort == "medium", "a review measured at high took twice as long for twice the output (1 Nov 2026)"
    earlier = response_writer.write_section(Writer(quiet), ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    reviewer = Reviewer()
    response_review.review(reviewer, ctx, record, sources, earlier, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, earlier),
                           contract=response_review.PRESENTED_CONTRACT)
    assert reviewer.seen[0][0].effort is None, "an earlier review asks the release's own setting"


def test_the_message_is_read_at_medium():
    model = Understood({"units": [unit()]})
    understanding.understand(model, typed())
    assert model.calls[0][0].effort == "medium" and understanding.MAX_OUTPUT >= 16000


def test_the_time_limits_are_worked_out_at_medium_and_their_correction_looks_again_at_high(store):
    model = Calculating(chain(), correction={"calculations": [fixed_bad()], "cannot": []})
    turn(store, model)
    assert model.seen["calculation"].effort == "medium"
    (correction,) = model.seen["correction"]
    assert correction.effort == "high"


def test_the_output_limits_of_the_steps_that_reason_longer_have_room():
    # A step that reasons longer writes more before it answers, and its limit counts the reasoning: none may stop short (the
    # understanding once did). At the third replay's sizes - understand 20,000 and revise 18,000 tokens at medium, a writing about nine
    # thousand on average and a review about four thousand - each limit is at least twice what its step wrote.
    assert research.MAX_OUTPUT["understand"] >= 48000 and research.MAX_OUTPUT["revise"] >= 48000 and research.MAX_OUTPUT["check"] >= 16000
    assert response_writer.MAX_OUTPUT >= 40000 and response_writer.OVERVIEW_OUTPUT >= 24000
    assert response_writer.REPAIR_OUTPUT >= 24000 and response_writer.TAKE_UP_OUTPUT >= 24000 and response_review.MAX_OUTPUT >= 32000
