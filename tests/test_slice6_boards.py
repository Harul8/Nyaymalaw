"""S6 — the board evals that had never run. E-063c, E-063f, E-066.

A2's structural rules were tested from slice 1; these three were not, and each
is about the board saying something FALSE rather than something missing — which
is the harder half, because a false board looks exactly like a true one.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.deadlines import Deadline, DeadlineKind
from nm.domain.matter import Basis, Matter, Posture, Role, Thread
from nm.edge.projections import board_projection

pytestmark = pytest.mark.class_a

TODAY = date(2026, 8, 31)


def _matter_with(*threads) -> Matter:
    m = Matter.create(advocate_id="adv", title="the file")
    for t in threads:
        m = m.with_thread(t)
    return m


# ========== E-063c — a screen nobody ran never renders as clear =============


@pytest.mark.eval_id("E-063c")
def test_a_screen_that_was_never_run_is_not_reported_as_clear():
    """E-063c's counterexample: *a gate that cannot apply to this matter listed
    as something the advocate must action* — and its twin, a screen that could
    not run rendering as one that passed.

    The screens are slice 10. Everything about them is `not_assessed` today,
    and the summary has to SAY that rather than omit the section — an omitted
    section reads as nothing to report.
    """
    from nm.domain import summary as matter_memory

    s = matter_memory.build(_matter_with(Thread.create(label="a dispute")))
    doc = s.as_dict() if hasattr(s, "as_dict") else None

    assert "screens" in s.handover_blockers, (
        "the screens section is not listed as a handover blocker, so a matter "
        "whose screens were never run reads as one that cleared them")
    assert not s.handover_complete, (
        "handover reported complete while whole sections are unbuilt")
    if doc is not None:
        assert "clear" not in str(doc.get("screens", "")).lower()


@pytest.mark.eval_id("E-063c")
def test_an_unbuilt_gate_is_never_listed_as_something_to_action():
    """The other half. A gate the product cannot evaluate must not appear on
    the advocate's list of open items — that is work they cannot do, on a
    condition nothing is checking.

    The matrix is the source: a gate declared `built=False` is one nothing
    consults, and `tools/trace.py` T9 already fails the build if something
    does. What this asserts is the rendering side.
    """
    from nm.domain.gates import GATES

    unbuilt = {g.id for g in GATES if not g.built}
    assert unbuilt, "no unbuilt gates, so this proves nothing"

    m = _matter_with(Thread.create(label="a dispute"))
    board = board_projection(m, None, TODAY)
    rendered = str(board)
    for gate_id in unbuilt:
        assert gate_id not in rendered, (
            f"{gate_id} is declared unbuilt and appears on the board as "
            f"something the advocate can act on")


# ========== E-063f — a deferred thread stays on the board ==================


@pytest.mark.eval_id("E-063f")
def test_a_deferred_thread_stays_on_the_board_with_its_deadline():
    """E-063f's counterexample: *a thread the advocate deferred vanishing from
    the board.*

    Deferring is a decision about ORDER, not about existence. A deferred thread
    with a deadline in three weeks is exactly the one that must not disappear —
    the advocate deprioritised it believing they would see it again.
    """
    live = Thread.create(label="the urgent one")
    parked = Thread.create(label="the deferred one",
                           deferred_reason="the client is abroad until October")
    m = _matter_with(live, parked)

    due = Deadline(thread=parked.id, kind=DeadlineKind.LIMITATION,
                   source="Limitation Act, 1963 Article 14",
                   action="commence the suit", owner="the advocate",
                   consequence="the claim is barred", on=date(2026, 9, 21))
    board = board_projection(m, (due,), TODAY)

    rows = {r["thread"]: r for r in board["threads"]}
    assert "the deferred one" in rows, "a deferred thread vanished from the board"
    assert rows["the deferred one"]["deferred_reason"], (
        "the thread is on the board without saying why it was deferred, which "
        "reads as an oversight rather than a decision")
    assert rows["the deferred one"]["next_deadline"] == "2026-09-21", (
        "the deferred thread lost its deadline — the advocate deprioritised "
        "it believing they would see it again")

    # AND IT SORTS BY THE DEADLINE, not by having been deferred. A deferred
    # thread expiring on Friday leads a live one expiring next year.
    assert board["threads"][0]["thread"] == "the deferred one"


# ========== E-066 — the board and the answer cannot disagree ===============


@pytest.mark.eval_id("E-066")
def test_the_board_and_the_answer_derive_from_the_same_matter():
    """E-066's counterexample: *the board citing Article 66 while the answer
    reasons from Article 65.*

    The mechanism is that neither holds its own copy. `summary.build` rebuilds
    from the matter every time and `board_projection` reads the matter
    directly, so there is no stored projection that can drift.

    This asserts the property that makes them unable to disagree: changing the
    matter changes both, and nothing is cached between them.
    """
    from nm.domain import summary as matter_memory

    t = Thread.create(label="the possession matter")
    m = _matter_with(t)

    board_before = board_projection(m, None, TODAY)["threads"][0]
    summary_before = matter_memory.build(m)
    assert board_before["our_client_is"] == "unknown"

    # Move the matter. NEITHER projection is told; both are rebuilt.
    resolved = t.__class__(**{**t.__dict__,
                              "posture": Posture(role=Role.PLAINTIFF,
                                                 basis=Basis.STATED, version=1)})
    m2 = _matter_with(resolved)

    board_after = board_projection(m2, None, TODAY)["threads"][0]
    summary_after = matter_memory.build(m2)

    assert board_after["our_client_is"] == "plaintiff", (
        "the board did not follow the matter, so it holds a copy")
    assert board_after != board_before
    assert summary_after.as_context() != summary_before.as_context(), (
        "the summary did not follow the matter either")

    # THE POSTURE THE BOARD SHOWS IS THE THREAD'S OWN, not a second reading.
    assert board_after["side"] == resolved.posture.side.value
