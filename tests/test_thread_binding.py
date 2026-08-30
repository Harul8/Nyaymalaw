"""Slice 3 — the frame. Never answer a question whose frame is unsettled.

THE ASYMMETRY EVERY TEST HERE RESTS ON
---------------------------------------
A wrong SPLIT duplicates work and is visible: the advocate sees two rows where
they expected one and says so.

A wrong MERGE attaches one thread's posture, chronology and limitation to facts
they do not govern. Every citation stays correct, the board looks tidier, and
the advice inverts silently.

Five disputes on one file is the ordinary case in Indian practice, not the edge
case — a landlord suing on arrears and on possession is two threads, two
limitation positions, two postures, between the same two parties.
"""
from __future__ import annotations

import pytest

from nm.core.threading import BindState, bind, identifiers_in
from nm.core.turn import TurnInput
from nm.domain.matter import Fact, Matter, Provenance, Role, Thread
from nm.domain.traceability import refuses
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a


def _fact(text: str = "an account") -> Fact:
    return Fact.create(statement=text,
                       provenance=Provenance(kind="advocate_statement", turn="t1"))


def _matter(*threads: Thread) -> Matter:
    m = Matter.create(advocate_id="adv", title="file")
    for t in threads:
        m = m.with_thread(t)
    return m


# ============================================ identifier extraction ========

def test_a_case_number_is_recognised_however_it_is_written():
    """`O.S.442/2023`, `OS 442 of 2023` and `O. S. No. 442/2023` are ONE
    identifier. An identifier that only matches its own spelling is not an
    identifier — it is a string, and a second mention opens a second thread."""
    forms = ["O.S. 442/2023", "OS 442 of 2023", "O.S.No.442/2023", "os 442/2023"]
    values = {identifiers_in(f).get("case_number") for f in forms}
    assert len(values) == 1, f"the same case number read four ways: {values}"


def test_an_fir_number_and_a_case_number_are_different_identifiers():
    ids = identifiers_in("FIR No. 45/2024 was registered and O.S. 442/2023 is pending")
    assert ids["fir"] == "45/2024"
    assert "442/2023" in ids["case_number"]


def test_prose_alone_yields_no_identifier():
    """A DESCRIPTION IS NEVER AN IDENTIFIER. "the Kukatpally property" and "the
    land matter" can be one dispute or three, and nothing in those strings
    tells you which."""
    assert identifiers_in("the Kukatpally land matter with the same builder") == {}


# =================================================== binding ===============

def test_the_first_account_opens_the_first_thread():
    result = bind(_matter(), "we act for the plaintiff in a possession suit", _fact())
    assert result.state is BindState.BOUND
    assert result.created


def test_a_decisive_identifier_binds_to_the_thread_that_carries_it():
    existing = Thread.create(label="possession", identifiers={"case_number": "OS442/2023"})
    other = Thread.create(label="arrears", identifiers={"case_number": "OS991/2024"})
    result = bind(_matter(existing, other),
                  "in O.S. 442/2023 the written statement is due", _fact())
    assert result.state is BindState.BOUND
    assert result.thread.id == existing.id
    assert not result.created


def test_a_new_number_of_record_opens_a_new_thread_rather_than_joining_one():
    """Two disputes between the same parties are ordinary. A number of record
    that matches nothing on the file is a NEW dispute, not a stray mention."""
    existing = Thread.create(label="possession", identifiers={"case_number": "OS442/2023"})
    result = bind(_matter(existing),
                  "they have now filed C.C. 77/2025 against the same client", _fact())
    assert result.state is BindState.BOUND
    assert result.created
    assert result.thread.id != existing.id


@refuses("C4", 0)
@pytest.mark.eval_id("E-033")
def test_several_threads_and_no_identifier_blocks_rather_than_guessing():
    """THE COUNTEREXAMPLE. With more than one open thread and nothing decisive,
    a guess attaches facts to the wrong posture and the wrong limitation."""
    a = Thread.create(label="possession suit")
    b = Thread.create(label="cheque complaint")
    result = bind(_matter(a, b), "the hearing went badly yesterday", _fact())
    assert result.state is BindState.AMBIGUOUS
    assert result.blocks
    assert result.thread is None
    assert "possession suit" in result.question


def test_one_open_thread_is_not_automatically_a_continuation():
    """THIS TEST USED TO ASSERT THE DEFECT.

    It read: *"With one thread there is nothing to be wrong about"* — and there
    was. A second dispute described in prose, with no number of record, was
    welded onto the first. Driven three turns, a cheque complaint (he is the
    ACCUSED), a Labour Court claim (he is the RESPONDENT EMPLOYER) and his own
    recovery suit (he is the PLAINTIFF) produced ONE thread carrying
    `role=accused`, so his own suit would have been advised as a defence.

    A second thread was also unreachable any other way: only a number of record
    could create one, so a matter could not hold two disputes unless the
    advocate typed a case number. The golden set calls multi-thread files the
    NORMAL case.

    The half of the old reasoning that was right is kept: asking on every turn
    would train the advocate to ignore the question when it matters. So a read
    that says CONTINUES binds silently, and only a read that could not tell
    asks.
    """
    only = Thread.create(label="possession suit")
    matter = _matter(only)
    account = "the hearing went badly yesterday"

    # CONTINUES -- binds, silently, exactly as before.
    cont = bind(matter, account, _fact(), opens_new_dispute=False)
    assert cont.state is BindState.BOUND
    assert cont.thread.id == only.id
    assert not cont.created and not cont.question

    # OPENS -- a new thread, stated, so the advocate sees the split. A wrong
    # split is visible and recoverable; a wrong merge inverts the advice.
    opens = bind(matter, "separately, he has filed his own recovery suit",
                 _fact(), opens_new_dispute=True)
    assert opens.state is BindState.BOUND
    assert opens.created and opens.thread.id != only.id
    assert "different dispute" in opens.reason

    # COULD NOT TELL -- asks. Never assumes the merge, because that is the
    # direction with no undo.
    unknown = bind(matter, account, _fact(), opens_new_dispute=None)
    assert unknown.state is BindState.AMBIGUOUS
    assert unknown.question and "separate dispute" in unknown.question


def test_the_advocate_naming_a_thread_outranks_everything():
    a = Thread.create(label="possession suit")
    b = Thread.create(label="cheque complaint")
    result = bind(_matter(a, b), "the hearing went badly", _fact(), thread_hint=b.id)
    assert result.state is BindState.BOUND
    assert result.thread.id == b.id


@refuses("C4", 1)
def test_two_threads_with_one_identifier_propose_a_merge_and_never_perform_it():
    """A merge is a decision with no undo that the advocate has the facts to
    make and the product does not."""
    a = Thread.create(label="possession", identifiers={"case_number": "OS442/2023"})
    b = Thread.create(label="the land case", identifiers={"case_number": "OS442/2023"})
    result = bind(_matter(a, b), "in O.S. 442/2023 the matter is listed", _fact())
    assert result.state is BindState.AMBIGUOUS
    assert result.proposal is not None
    assert {result.proposal.left, result.proposal.right} == {a.id, b.id}
    assert "will not merge" in result.proposal.question


@pytest.mark.eval_id("E-033")
def test_label_similarity_never_binds():
    """Two threads whose labels look alike stay two threads. Nothing in a
    display name carries identity."""
    a = Thread.create(label="Kukatpally land — possession")
    b = Thread.create(label="Kukatpally land — arrears")
    result = bind(_matter(a, b), "the Kukatpally land position", _fact())
    assert result.state is BindState.AMBIGUOUS


def test_identifiers_accumulate_and_are_never_overwritten():
    """A second number on a thread is new information about the dispute, not a
    correction of the first. Replacing it loses the link to everything filed
    under the old number."""
    t = Thread.create(label="possession", identifiers={"case_number": "OS442/2023"})
    result = bind(_matter(t), "FIR No. 45/2024 has been registered on the same "
                              "dispute in O.S. 442/2023", _fact())
    assert result.thread.identifiers["case_number"] == "OS442/2023"
    assert result.thread.identifiers["fir"] == "45/2024"


@pytest.mark.eval_id("E-032")
def test_a_renamed_thread_keeps_its_id_and_its_old_label():
    t = Thread.create(label="the land matter")
    renamed = t.renamed("O.S. 442/2023 — possession")
    assert renamed.id == t.id
    assert "the land matter" in renamed.aliases


# ============================================= through the engine ==========

def test_an_ambiguous_binding_blocks_the_turn_and_keeps_the_account(tmp_path):
    """The fact is recorded BEFORE binding is attempted. An account that cannot
    be placed is still an account that was heard — discarding it teaches the
    advocate to re-type what they already said, and they stop volunteering
    detail."""
    engine, store = build(tmp_path)

    first = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff in O.S. 442/2023, a possession suit"))
    mid = engine.run(TurnInput(
        advocate_id="adv", matter_id=first.matter.id,
        message="they have also filed C.C. 77/2025, a cheque complaint"))
    assert len(mid.matter.threads) == 2

    out = engine.run(TurnInput(
        advocate_id="adv", matter_id=mid.matter.id,
        message="the hearing yesterday went badly and we need to move quickly"))

    assert out.answer.blocked
    assert "G-THREAD" in out.answer.blocked_reason
    assert any(g.gate_id == "G-THREAD" for g in out.metrics.gates_fired)
    # No model call was made and no directive step was computed. The block IS
    # the answer.
    # Only the reads that SETTLE the gate. Discovering that two threads are
    # candidates costs one cheap read, and refusing to spend it would mean
    # never discovering the second dispute at all.
    assert out.metrics.llm_calls == out.metrics.settling_reads

    # And the account survived: the fact is on the matter even though it is on
    # no thread.
    reloaded = store.load(mid.matter.id)
    assert any("hearing yesterday" in f.statement for f in reloaded.facts)


@pytest.mark.eval_id("E-033")
def test_posture_is_settled_per_thread_not_per_matter(tmp_path):
    """Two disputes on one file can have opposite postures. A matter-level
    posture is the defect that told an employer he could claim reinstatement
    from himself."""
    engine, _ = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the plaintiff in O.S. 442/2023, a possession suit"))
    second = engine.run(TurnInput(
        advocate_id="adv", matter_id=first.matter.id,
        message="in C.C. 77/2025 our client is the accused on a cheque complaint"))

    by_label = {t.identifiers.get("case_number"): t for t in second.matter.threads}
    assert by_label["OS442/2023"].posture.role is Role.PLAINTIFF
    assert by_label["CC77/2025"].posture.role is Role.ACCUSED
    assert by_label["OS442/2023"].posture.side is not by_label["CC77/2025"].posture.side


@refuses("C4", 1)
@pytest.mark.eval_id("E-033")
def test_a_second_dispute_does_not_inherit_the_first_thread_s_posture(tmp_path):
    """B-052, ON THE ENGINE. The defect that made multi-thread files impossible.

    A second thread could only ever be created by a NUMBER OF RECORD, so a
    dispute described in prose was welded onto the one already open. Driven
    three turns:

        a cheque complaint filed against him   -> he is the ACCUSED
        a Labour Court claim by a fitter       -> he is the RESPONDENT EMPLOYER
        his own recovery suit for 11 lakhs     -> he is the PLAINTIFF

    produced ONE thread carrying `role=accused, side=defending`. His own
    recovery suit would have been advised as a defence, with every citation
    correct — the measured original defect, reached through the binder instead
    of through the posture reader.

    The golden set calls multi-thread files THE NORMAL CASE (GS-08, GS-09,
    GS-10, GS-22), and none of them could pass.
    """
    from nm.core.turn import TurnInput
    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv",
        message="we act for the accused in a cheque complaint filed against him"))
    assert out.matter is not None
    first = out.matter.threads[0].id

    out = engine.run(TurnInput(
        advocate_id="adv", matter_id=out.matter.id,
        message="second, he has filed his own recovery suit against a customer"))
    assert out.matter is not None

    ids = {t.id for t in out.matter.threads}
    assert len(ids) == 2, (
        f"a plainly different dispute joined the existing thread. Threads: "
        f"{[t.label for t in out.matter.threads]}. The recovery suit he FILED "
        f"now carries the posture of a complaint filed AGAINST him.")
    assert first in ids, "the original thread was replaced rather than added to"


@pytest.mark.eval_id("E-033")
def test_a_dispute_read_that_could_not_tell_asks_rather_than_merging():
    """THE ASYMMETRY, as a default rather than as a preference.

    A wrong split duplicates work, is visible on the board, and is corrected in
    a turn. A wrong merge attaches one thread's posture, chronology and
    limitation to facts they do not govern, and the advice inverts silently.

    So the unread state must never fall back to `continues`. It asks — which is
    what rule 6 already does when several threads are open and nothing is
    decisive.
    """
    only = Thread.create(label="possession suit")
    for unread in (None,):
        r = bind(_matter(only), "he came back about the other thing", _fact(),
                 opens_new_dispute=unread)
        assert r.state is BindState.AMBIGUOUS, (
            "an unread dispute defaulted to a merge, which is the direction "
            "with no undo")
        assert r.blocks and r.question
