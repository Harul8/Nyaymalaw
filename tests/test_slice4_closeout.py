"""S4 ON THE SERVED PATH. D1, D2 and D3 as the advocate actually receives them.

`tests/test_limitation.py`, `tests/test_thresholds.py` and
`tests/test_deadlines.py` test the three modules. Every one of them passed
while the modules were called by nothing — built, unit-tested, and absent from
every turn the product served. That is the gap CLAUDE.md §8 names: *40/40
offline passed while every served turn crashed, and every defect the first
external review found lived between a correct module and the served path.*

So this file drives `TurnEngine.run` and reads the answer.

WHAT IT CAUGHT ON ITS FIRST RUN
--------------------------------
The engine passed `years=3` into every limitation it computed. On a turn that
had just retrieved *Article 65 — twelve years* it reported the claim barred
three years after accrual. The Article was right, the accrual was right, every
citation was right, and the answer was wrong by nine years. No unit test could
have seen it: `compute` was handed a period and used it faithfully, and the
invention happened at the call site.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.turn import TurnInput
from nm.domain.answer import ElementKind, Signal
from nm.ports.evidence import Coverage, EvidenceResult
from tests.test_turn_contract import _Evidence, build, finding

pytestmark = pytest.mark.class_a

TODAY = date(2026, 8, 31)

#: Article 65 and its TWELVE years, which is what the corpus actually holds.
ARTICLE_65 = "For possession of immovable property... twelve years."

MOVING = ("we act for the plaintiff. the defendant dispossessed our client on "
          "15 April 2019 and has refused to hand back possession.")
DEFENDING = ("we act for the defendant. the plaintiff says our client "
             "trespassed on 15 April 2019 and they have now sued.")


def run(tmp_path, message, evidence=None, today=TODAY):
    engine, _ = build(tmp_path, evidence=evidence)
    return engine.run(TurnInput(advocate_id="adv", message=message,
                                today=today)).answer


def grounds(answer) -> str:
    """Everything the advocate reads, as one string."""
    return "\n".join(e.text for e in answer.elements)


# ============ D2 — the period comes from the text, on the served path =======


@pytest.mark.eval_id("E-043")
def test_the_period_on_a_served_turn_is_the_one_the_retrieved_text_states(
        tmp_path):
    """THE MEASURED DEFECT. Twelve years on Article 65, not three.

    This is the whole argument for testing the composition root. `compute` was
    correct, `period_in` did not yet exist, and the engine supplied `years=3`
    to every computation — so the served answer barred a live claim by nine
    years while every unit test in the suite passed.
    """
    answer = run(tmp_path, MOVING)

    text = grounds(answer)
    assert "2031-04-15" in text, (
        f"twelve years from 15 April 2019 is 15 April 2031. The turn said:\n"
        f"{text}")
    assert "2022-04-15" not in text, (
        "the answer carries a three-year expiry on a twelve-year Article — the "
        "period was supplied by the product, not read from the text")


@pytest.mark.eval_id("E-043")
def test_an_article_whose_text_states_no_period_is_not_computed_and_says_so(
        tmp_path):
    """THE THIRD STATE, on the wire. A period the text does not state is not
    guessed, and the turn says which of the two it is.

    `not computed` and `computed and fine` must never look alike: the first
    needs the advocate to act, the second does not.
    """
    silent_text = _Evidence(EvidenceResult(
        coverage=Coverage.ANSWERED,
        findings=(finding(span="This section shall come into force on such "
                               "date as the Central Government may appoint."),),
        searched_stores=("the_limitation_act_1963",)))
    answer = run(tmp_path, MOVING, evidence=silent_text)

    text = grounds(answer)
    assert "not computed" in text.lower() or "have not computed" in text.lower()
    assert "period is not stated in the text retrieved" in text, (
        f"the turn did not name WHY there is no date. The advocate cannot act "
        f"on a silence:\n{text}")


# ============ D2 — the opponent's limitation, on a defending thread =========


@pytest.mark.eval_id("E-045")
def test_on_a_defending_thread_the_turn_computes_the_opponents_limitation(
        tmp_path):
    """E-045, and it is a class-A eval that ran only against the module.

    Where we are defending, their limitation is often the whole answer — it
    disposes of the claim without touching the merits. A defence that never
    checks whether their claim is time-barred has missed the cheapest point on
    the file.
    """
    answer = run(tmp_path, DEFENDING)
    text = grounds(answer)

    assert "Limitation for them" in text, (
        f"a defending thread and the opponent's limitation was never "
        f"computed:\n{text}")
    # AND OURS IS STILL THERE. Replacing one with the other would be the same
    # defect facing the other way.
    assert "Limitation for us" in text


@pytest.mark.eval_id("E-045")
def test_a_moving_thread_does_not_invent_an_opponents_position(tmp_path):
    """THE POSITIVE CONTROL for the eval above. A test that only ever asserts
    the opponent's row is present would pass against an engine that emitted it
    unconditionally — including where there is no claim of theirs to compute.
    """
    answer = run(tmp_path, MOVING)
    assert "Limitation for them" not in grounds(answer)


# ================== D1 — the map, and its silence ===========================


@pytest.mark.eval_id("E-044")
def test_the_turn_names_every_threshold_it_did_not_assess(tmp_path):
    """D1: *Never leave a threshold silent.*

    An advocate reading a map with one row on it believes the others were
    checked and found irrelevant. Eight of the nine are unassessed in this
    slice, and the answer says which eight and that they are gaps.
    """
    answer = run(tmp_path, MOVING)
    text = grounds(answer)

    for threshold in ("jurisdiction", "forum", "standing", "maintainability",
                      "statutory_notice", "valuation", "court_fees",
                      "arbitration_clause"):
        assert threshold in text, f"{threshold} is silent in the served answer"
    assert "gaps in the map, not findings" in text, (
        "the unassessed thresholds are listed without saying they are gaps, "
        "which reads as a finding that they do not arise")


@pytest.mark.eval_id("E-044")
def test_a_bar_is_signalled_loudly_and_is_not_reported_as_a_verdict(tmp_path):
    """D2: *Never report a bar as a verdict.* A period that has run is a
    LIMITATION_BAR signal, which §6.2 forbids collapsing — and the sentence
    beside it turns to what else the file offers.
    """
    answer = run(tmp_path, MOVING, today=date(2040, 1, 1))

    bars = [e for e in answer.elements if e.signal is Signal.LIMITATION_BAR]
    assert bars, "twelve years from 2019 had run by 2040 and nothing was loud"
    assert not any(e.collapsible for e in bars)
    assert "separate question" in bars[0].text, (
        "the bar is stated as a verdict with nothing after it")


# ============== D3 — an action carries a by-when it actually has ============


@pytest.mark.eval_id("E-046")
def test_a_recommended_action_carries_the_by_when_the_register_holds(tmp_path):
    """D3: *Every recommended action carries a by-when, or an express statement
    that no deadline applies.*

    `Element.__post_init__` has always refused an ACTION with neither. What it
    cannot see is whether the reason is TRUE — and it was not. The engine set a
    fixed `no_deadline_reason="no statutory window identified on this turn"` on
    every recommendation it ever made: a finding that nothing was found,
    asserted whether or not anything had been looked for. Defect shape S1.
    """
    answer = run(tmp_path, MOVING)
    actions = [e for e in answer.elements if e.kind is ElementKind.ACTION]
    assert actions, "the turn recommended nothing"

    assert actions[0].by_when == date(2031, 4, 15), (
        f"the register holds a live limitation window and the action did not "
        f"carry it: by_when={actions[0].by_when!r} "
        f"reason={actions[0].no_deadline_reason!r}")
    assert actions[0].no_deadline_reason is None, (
        "an action with a date must not also carry a reason it has none")


@pytest.mark.eval_id("E-046")
def test_where_no_window_could_be_established_the_action_says_which(tmp_path):
    """THE OTHER TWO STATES, and they must not read alike.

    *Assessed and there is no dated deadline* is a finding. *Nobody computed a
    register* is a gap. The fixed sentence said the first while meaning the
    second, on every turn.
    """
    silent_text = _Evidence(EvidenceResult(
        coverage=Coverage.ANSWERED,
        findings=(finding(span="This section binds the Government."),),
        searched_stores=("the_limitation_act_1963",)))
    answer = run(tmp_path, MOVING, evidence=silent_text)

    actions = [e for e in answer.elements if e.kind is ElementKind.ACTION]
    assert actions and actions[0].by_when is None
    reason = actions[0].no_deadline_reason or ""
    assert "no deadline with an established date" in reason, (
        f"the action does not distinguish an assessed register with no date "
        f"from one nobody computed: {reason!r}")
    assert "no statutory window identified on this turn" not in reason, (
        "the fixed sentence is back — it asserts a finding of no window on "
        "every turn, whether or not one was looked for")


@pytest.mark.eval_id("E-046")
def test_a_passed_deadline_never_becomes_the_by_when_of_an_action(tmp_path):
    """D3: *Never list an action due eight months ago under "these will not
    wait".*

    A passed window is reported as passed. Presenting it as this action's
    by-when would file the thing that can no longer be done among the things
    that still can, and the advocate scans the second for work.
    """
    answer = run(tmp_path, MOVING, today=date(2040, 1, 1))
    actions = [e for e in answer.elements if e.kind is ElementKind.ACTION]
    assert actions and actions[0].by_when is None, (
        "an expiry twelve years in the past was presented as a live by-when")
    assert "has passed" in (actions[0].no_deadline_reason or ""), (
        "the action does not say the window has gone")


# =============== the posture gate still comes first =========================


def test_an_unresolved_posture_computes_no_limitation_for_either_side(tmp_path):
    """"Is this claim in time" is asked OF A SIDE.

    Whose limitation — ours or theirs — is not answerable while the side is
    unknown, and answering it for a guessed side is precisely the defect
    G-POSTURE exists for. So the map does not run under the gate.
    """
    answer = run(tmp_path, "the landlord issued a quit notice on 15 April 2019")
    assert answer.blocked
    text = grounds(answer)
    assert "Limitation for us" not in text
    assert "Limitation for them" not in text


# ================= the board says WHICH null it is showing ==================


@pytest.mark.eval_id("E-046")
def test_the_board_distinguishes_no_deadline_from_no_register(tmp_path):
    """A2.5 / D3, and the two nulls are not the same fact.

    `board_projection` took `deadlines=()` by default and the served endpoint
    never passed a register, so every row rendered `next_deadline: null` — a
    file with no deadlines on it, as far as anyone reading the board could
    tell. Defect shape S1 again: the absent input produced the shape of a
    clean result.
    """
    from nm.core.deadlines import Deadline, DeadlineKind
    from nm.domain.matter import Matter, Thread
    from nm.edge.projections import board_projection

    matter = Matter.create(advocate_id="adv", title="t")
    thread = Thread.create(label="the possession matter")
    matter = matter.with_thread(thread)

    # 1. NOBODY COMPUTED A REGISTER.
    unassessed = board_projection(matter, None)["threads"][0]
    assert unassessed["next_deadline"] is None
    assert unassessed["next_deadline_status"] == "not_assessed"
    assert unassessed["passed_deadlines"] is None, (
        "an empty list here claims the register was read and held no passed "
        "deadline, which nobody established")

    # 2. A REGISTER WAS COMPUTED AND THIS THREAD HAS NOTHING IN IT. Same null,
    # different fact, and the advocate needs to tell them apart.
    empty = board_projection(matter, (), TODAY)["threads"][0]
    assert empty["next_deadline"] is None
    assert empty["next_deadline_status"] == "none_on_this_thread"
    assert empty["passed_deadlines"] == []

    # 3. THE ANSWER.
    live = Deadline(thread=thread.id, kind=DeadlineKind.LIMITATION,
                    source="Limitation Act, 1963 Article 65",
                    action="commence the suit", owner="the advocate",
                    consequence="the claim is barred",
                    on=date(2031, 4, 15))
    held = board_projection(matter, (live,), TODAY)["threads"][0]
    assert held["next_deadline"] == "2031-04-15"
    assert held["next_deadline_status"] == "future"


@pytest.mark.eval_id("E-046")
def test_the_matter_list_orders_by_a_deadline_it_actually_holds():
    """THE RULE THAT COULD NOT FIRE.

    The list sorts nearest-deadline-first and reads `next_deadline` as the
    first key — and that field was hard-coded `None` on every row, so the sort
    always fell through to recency and the ordering rule the list exists to
    obey had never once applied. Shape S11: a check that cannot fail.
    """
    from nm.core.deadlines import Deadline, DeadlineKind
    from nm.domain.matter import Matter, Thread
    from nm.edge.projections import matter_list_projection

    def matter_with(title, on):
        m = Matter.create(advocate_id="adv", title=title)
        t = Thread.create(label=title)
        m = m.with_thread(t)
        return m, Deadline(thread=t.id, kind=DeadlineKind.LIMITATION,
                           source="Limitation Act, 1963 Article 65",
                           action="commence the suit", owner="the advocate",
                           consequence="the claim is barred", on=on)

    far, far_d = matter_with("the far one", date(2039, 1, 1))
    near, near_d = matter_with("the near one", date(2031, 1, 1))

    ordered = matter_list_projection(
        [far, near], {far.id: (far_d,), near.id: (near_d,)})["matters"]
    assert ordered[0]["matter"] == "the near one", (
        "the list did not put the nearest deadline first — the interesting "
        "file will still be there next week and the one expiring will not")

    # AND WITH NO REGISTERS the field says so rather than reading as a matter
    # with no deadline at all.
    blind = matter_list_projection([far, near])["matters"]
    assert all(r["next_deadline_status"] == "not_assessed" for r in blind)


@pytest.mark.eval_id("E-046")
def test_the_thread_board_puts_the_nearest_window_first():
    """D3: *Where several threads are live, the thread carrying the nearest
    deadline is addressed first, regardless of which is legally the most
    interesting.*

    The thread board did not sort its rows at all — they came back in whatever
    order the threads sat on the matter — while the matter list sorted on a
    field hard-coded `None`. So the rule was written in the PRD, written in a
    docstring, and applied by neither board. `nearest_thread` had a test and
    no production caller, which is the same fact from the other side.
    """
    from nm.core.deadlines import Deadline, DeadlineKind
    from nm.domain.matter import Matter, Thread
    from nm.edge.projections import board_projection

    matter = Matter.create(advocate_id="adv", title="t")
    slow = Thread.create(label="the interesting one")
    urgent = Thread.create(label="the one expiring on Friday")
    matter = matter.with_thread(slow).with_thread(urgent)

    def deadline(thread_id, on):
        return Deadline(thread=thread_id, kind=DeadlineKind.LIMITATION,
                        source="Limitation Act, 1963 Article 65",
                        action="commence the suit", owner="the advocate",
                        consequence="the claim is barred", on=on)

    board = board_projection(
        matter,
        (deadline(slow.id, date(2039, 1, 1)),
         deadline(urgent.id, date(2026, 9, 4))),
        TODAY)

    assert board["threads"][0]["thread"] == "the one expiring on Friday", (
        "the board led with the interesting thread. The interesting one will "
        "still be there next week and the expiring one will not.")
    # AND THE ROW COUNT IS UNCHANGED. An ordering that drops a row is worse
    # than one that does not order.
    assert board["row_count"] == 2
