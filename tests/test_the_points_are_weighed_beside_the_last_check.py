"""A turn is faster where nothing it decides changes (plan AN.80; owner, 24 Nov 2026: "check where it is taking more time and if there
is scope to improve latency"; D345-D348).

End-to-end run 3 measured where a turn's 19 minutes went. Once no revision can follow the understanding's last check, the understanding
the weighing reads is final, so the weighing starts beside that check, as the search phrases do (D345), and the plan keeps it only where
what it read is what the plan's understanding gives. While the plan waits for the weighing, the line on the page names it (D348), never
before the check and the search phrases are done. The account of what makes a dispute's case stronger and its review are not raised a
level by their input's size, which is large by nature; its check stays at high (D346). The weighing's check runs at the weighing's own
level, raised only by a large input (D347). Fakes stand in for the models: this pins when each call is made and what the plan keeps,
not how a model reasons. The papers are invented.
"""
import threading

import pytest

from nm.app.turn_progress import STAGES
from nm.core_engine import reasoning, research
from tests.test_core_research import _result
from tests.test_the_plan_records_the_chronology import Beside, bundle

pytestmark = pytest.mark.class_a

REVISE = {"verdict": "revise", "problems": [{"problem": "A point is missing.", "fix": "Add it."}]}
SOUND = {"verdict": "sound", "problems": []}


class Weighing(Beside):
    """The research double that also weighs a point. hold_check: the understanding's last check waits for the weighing to be called
    (and records whether it was); hold_weighing: the weighing's check waits for the event given."""

    def __init__(self, *, hold_check=False, hold_weighing=None, **kw):
        super().__init__(**kw)
        self.weighed, self.hold_check, self.hold_weighing = threading.Event(), hold_check, hold_weighing
        self.checks_made, self.met, self.saw_line = 0, None, None

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_check":
            self.checks_made += 1
            if self.hold_check and self.checks_made == research.MAX_REVISIONS + 1:
                self.met = self.weighed.wait(timeout=10)
        if prompt.operation == "core_research_weigh":
            self.calls.append(prompt)
            self.weighed.set()
            return _result({"weights": [{"id": "E1", "dispute": "D1", "effect": "hurts", "weight": "critical",
                                         "why": "It decides the claim.", "question": "", "for_advocate": False}]}, tier)
        if prompt.operation == "core_research_weigh_check":
            self.calls.append(prompt)
            if self.hold_weighing is not None:
                self.saw_line = self.hold_weighing.wait(timeout=10)
            return _result({"corrections": []}, tier)
        return super().structured(prompt, schema, tier, **kwargs)


def revised(**kw):
    from tests.test_core_research import understanding
    return Weighing(checks=[REVISE, SOUND], revisions=[understanding()], **kw)


def test_the_weighing_starts_beside_the_last_check_and_the_plan_keeps_what_it_would_have_kept(monkeypatch):
    """D345: the last check of a revised understanding waits here for the weighing - a plan that weighs only after the loop fails."""
    model = revised(hold_check=True)
    beside = research.plan(model, bundle())
    assert model.met is True, "the weighing was called while the understanding's last check was still out"
    assert [(w["id"], w["checked"]) for w in beside["proposal"]["weights"]] == [("E1", "kept")]
    # The same matter weighed after the loop, as before D345: the plan is the same, record for record.
    original = research._proposal
    monkeypatch.setattr(research, "_proposal", lambda *args, settled=None, **kw: original(*args, **kw))
    after = research.plan(revised(), bundle())
    assert beside == after


def test_a_loop_that_ends_before_its_last_check_weighs_after_it_and_the_line_names_the_weighing():
    """D345 and D348: an understanding its first check finds sound is final only once that check returns, so it is weighed then; the
    page's line says so while it is weighed."""
    stages = []
    model = Weighing()
    record = research.plan(model, bundle(), progress=lambda stage, **detail: stages.append(stage))
    weighing = [p for p in model.calls if p.operation == "core_research_weigh"]
    assert len(weighing) == 1 and [(w["id"], w["checked"]) for w in record["proposal"]["weights"]] == [("E1", "kept")]
    assert "weighing" in STAGES and STAGES["weighing"] == "Weighing the points in your papers"
    assert stages.count("weighing") == 1
    assert stages.index("weighing") > max(i for i, stage in enumerate(stages) if stage in ("checking_understanding",
                                                                                          "writing_search_terms"))


def test_the_line_names_a_weighing_begun_beside_the_check_only_once_the_check_and_the_phrases_are_done():
    """D348: the weighing's check here waits for the line to name the weighing - so the plan names it while it waits for it, and
    only after the last check and the search phrases have reported."""
    named, stages = threading.Event(), []

    def progress(stage, **detail):
        stages.append(stage)
        if stage == "weighing":
            named.set()
    model = revised(hold_weighing=named)
    record = research.plan(model, bundle(), progress=progress)
    assert model.saw_line is True and stages.count("weighing") == 1 and stages[-1] == "weighing"
    assert [(w["id"], w["checked"]) for w in record["proposal"]["weights"]] == [("E1", "kept")]


def test_the_case_account_and_its_review_are_not_raised_by_size_and_the_weighings_check_is_at_the_weighings_level():
    """D346 and D347, read from the code's own table."""
    big = reasoning.LARGE_FILE_TOKENS + 1
    assert reasoning.effort("case", tokens=big) == "medium" and reasoning.effort("case_review", tokens=big) == "medium"
    assert reasoning.effort("case_check") == "high" and reasoning.effort("case_check", tokens=big) == "high"
    assert reasoning.effort("weigh_check") == reasoning.effort("weigh") == "medium"
    assert reasoning.effort("weigh_check", tokens=big) == "high", "a large input still raises the weighing's check"
