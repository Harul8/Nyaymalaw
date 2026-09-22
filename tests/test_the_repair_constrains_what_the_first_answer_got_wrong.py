"""THE BOUNDED REPAIR MUST HELP MOST WHERE THE FIRST ANSWER WAS WORST.

`fixed_allocation_repair` exists for one measured failure, and its own
docstring names it: *the model no longer has to invent an array and index that
changing array in the same answer.* It hands the model a FIXED table and an
enum over its indices, so the second attempt cannot be out of range.

It also used to refuse to do that unless the first answer's `verdict` already
agreed with its rows:

    if data.get('verdict') != ('opens' if new else 'continues'):
        return None

So an answer that got the verdict wrong AS WELL AS the allocation fell through
to the unconstrained schema, and the model repeated the same class of mistake.
The repair declined in exactly the case that needed it.

MEASURED 22 September 2026, three live runs of one four-dispute brief:

    G-THREAD :: the inventory marks new disputes but the verdict denies new work
    G-THREAD :: the allocation for S1 names dispute 6, and this inventory has 5

The second is the failure this function was written for.

THE RULE, STATED TWICE: the repair constrains whenever it can build a table,
and the verdict is DERIVED from that table rather than carried from the answer
being repaired. A value determined by the model's own other answers is not a
question worth asking.
"""
from __future__ import annotations

import pytest
from nm.core import dispute
from nm.domain.matter import Thread
from nm.domain.quotable import Quotable

pytestmark = pytest.mark.class_a

SAID = "First, the land at Kandi. Second, the cheque case. Third, the lease."


def _quotable() -> Quotable:
    return Quotable(turn=SAID)


def _rows() -> list[dict]:
    return [{"label": "the land", "thread_id": ""},
            {"label": "the cheque case", "thread_id": ""},
            {"label": "the lease", "thread_id": ""}]


def test_a_wrong_verdict_no_longer_stops_the_repair_constraining():
    """THE RULE. A malformed first answer is the reason to constrain, not a
    reason to decline."""
    wrong = {"verdict": "continues", "disputes": _rows()}   # three NEW rows
    assert dispute.fixed_allocation_repair(_quotable(), wrong, ()) is not None, (
        "the repair declined over a verdict it could have derived, and the "
        "retry then went out unconstrained -- which is how an out-of-range "
        "allocation index survives a bounded repair")


def test_the_repair_bounds_every_index_to_the_table_it_built():
    """WHY IT MATTERS: the enum is the whole mechanism. Without it the model
    indexes an array it is inventing in the same answer, and `dispute 6 of 5`
    is what that looks like."""
    prompt, schema, table = dispute.fixed_allocation_repair(
        _quotable(), {"verdict": "continues", "disputes": _rows()}, ())
    assert len(table) == 3
    for unit in schema["properties"]["source_allocations"]["properties"].values():
        assert unit["items"]["enum"] == [1, 2, 3], (
            "an allocation index was left unbounded in the repair schema")
    assert prompt is not None


def test_the_verdict_is_derived_from_the_rows_that_survive():
    """DERIVED, NOT CARRIED. Repairing the allocation while keeping the
    verdict that contradicted it leaves the contradiction that caused the
    repair."""
    _prompt, _schema, table = dispute.fixed_allocation_repair(
        _quotable(), {"verdict": "continues", "disputes": _rows()}, ())
    merged = dispute.apply_fixed_allocation(
        {"verdict": "continues", "disputes": _rows()},
        {"source_allocations": {"S1": [1], "S2": [2], "S3": [3]}},
        table)
    assert merged["verdict"] == "opens", (
        "every surviving row is new work, so the repaired answer still said "
        "the file merely continues")


def test_a_repair_over_existing_disputes_alone_still_continues():
    """THE POSITIVE CONTROL for the derivation. Deriving `opens` whenever a
    repair runs would open a duplicate on every ordinary later turn -- the
    wrong-merge defect arriving through the repair path."""
    threads = (Thread.create(label="the land"), Thread.create(label="the lease"))
    rows = [{"label": t.label, "thread_id": t.id} for t in threads]
    _prompt, _schema, table = dispute.fixed_allocation_repair(
        _quotable(), {"verdict": "continues", "disputes": rows}, threads)
    merged = dispute.apply_fixed_allocation(
        {"verdict": "continues", "disputes": rows},
        {"source_allocations": {"S1": [1], "S2": [2], "S3": [1]}},
        table)
    assert merged["verdict"] == "continues", (
        "no row is new work, so nothing is opened")


def test_a_verdict_that_over_claims_still_declines():
    """THE ASYMMETRY, and it is the half that protects the advocate.

    `opens` with NO new row says there is new work the inventory does not
    show, and the likeliest reading is that a dispute was omitted. Deriving
    `continues` from the rows would silently drop it -- the wrong-merge
    defect. Under-claiming is recoverable from the rows; over-claiming means
    something is missing from them and cannot be.
    """
    thread = Thread.create(label="the land")
    only_existing = [{"label": thread.label, "thread_id": thread.id}]
    assert dispute.fixed_allocation_repair(
        _quotable(), {"verdict": "opens", "disputes": only_existing},
        (thread,)) is None, (
        "a verdict claiming new work the rows do not show was repaired, which "
        "reconciles it by dropping whatever the model failed to list")


def test_an_incoherent_table_still_declines():
    """THE OTHER NEGATIVE CONTROL. Loosening the verdict precondition must not
    loosen the ones that make the table itself trustworthy: a duplicated
    existing id means the rows disagree about which dispute is which, and
    there is nothing sound to constrain against."""
    thread = Thread.create(label="the land")
    twice = [{"label": "the land", "thread_id": thread.id},
             {"label": "the land again", "thread_id": thread.id}]
    assert dispute.fixed_allocation_repair(
        _quotable(), {"verdict": "continues", "disputes": twice}, (thread,)) is None
    assert dispute.fixed_allocation_repair(
        _quotable(), {"verdict": "opens", "disputes": []}, ()) is None
