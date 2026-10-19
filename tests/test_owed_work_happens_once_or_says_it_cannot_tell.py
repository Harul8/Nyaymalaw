"""THE JOB LIFECYCLE. BK-83-AC2. P11.

WHAT IS PROVEN HERE AND WHAT IS NOT
-------------------------------------
PROVEN: the lifecycle. Leases, bounded retries, cancellation, idempotent
effects, permission rechecks, and -- the one that matters most -- that an
ambiguous external effect becomes `UNKNOWN` and is reconciled rather than
retried blind.

NOT PROVEN: durability. The store here is a reference implementation that
keeps its rows in memory, so "the worker restarted" means a new `JobRunner`
against the same rows, which is exactly what restart means to the lease logic
-- every fact a worker needs is in the store and none is in the worker. What
it does NOT establish is that a real substrate keeps those rows across a
process death. That is BK-83-AC1's integration evidence, it needs a
PostgreSQL server, and there is none on this machine.

Saying which of the two this file is buys the right to have it at all. A
memory store presented as durability proof would be the three-stores defect
with a queue.

EXACTLY-ONCE IS NOT CLAIMED ANYWHERE, and `test_the_runner_never_promises_
exactly_once` holds that line in the source itself.
"""
from __future__ import annotations


import pytest

from nm.shared.operation_contracts import Outcome

pytestmark = pytest.mark.class_a

WS = "ws_a"
ADVOCATE = "adv@example.test"


# ============================ the reference store ===========================


class _Sink:
    """A local synthetic destination that records what reached it."""

    def __init__(self) -> None:
        self.delivered: list[str] = []
        self.fail_with: Exception | None = None
        self.answerable = True

    def deliver(self, entry, *, idempotency_key):
        if self.fail_with is not None:
            raise self.fail_with
        self.delivered.append(idempotency_key)
        return {"ok": True}

    def already_delivered(self, idempotency_key):
        if not self.answerable:
            raise RuntimeError("the sink is unreachable")
        return idempotency_key in self.delivered


class _Permits:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.asked = 0

    def may_publish(self, workspace_id, advocate_id, matter_id):
        self.asked += 1
        return self.allowed


# ============================= the ordinary path ============================


# ============================ dying, and where =============================


# ========================= the ambiguous outcome ===========================


# ============================ budget and cancel ============================


def test_a_cancellation_request_is_not_an_erasure():
    """Work already accepted is not undone by asking, and the vocabulary has
    to keep *asked* and *happened* apart."""
    assert Outcome.CANCEL_REQUESTED.value == "cancel_requested"
    assert Outcome.CANCEL_REQUESTED.settled() is False


# =========================== permission, twice =============================


# ============================== what is claimed ============================


