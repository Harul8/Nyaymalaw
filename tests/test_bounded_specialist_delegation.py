"""P47 / BK-92-AC1 and BK-92-AC2 -- bounded specialist delegation.

WHAT THIS PROVES, AND WHERE THE LINE IS
-----------------------------------------
BK-92-AC1: every delegated task inherits a NON-EXPANDING mandate and records
parent, source snapshot, permitted tools/data, result contract and bounded
depth/concurrency/time/shared cost; ordinary work uses no specialist.

BK-92-AC2: findings merge through ONE version-checked acceptance path; source
instructions confer no authority, conflicts stay contested, failed or missing
work is not clean, and cancellation, revocation, retries and restart cannot
publish stale or duplicate effects.

The mechanism is deterministic (autonomy.json `control_boundary.application_owned`),
so it is tested directly rather than through a model: EVAL-032's fault list --
child_failed, crash_after_result_commit, grant_revoked_during_lease,
parent_cancelled, forged_child_result, source_changed -- is driven here as the
adversarial population, plus the prompt-injection source and the over-budget /
over-concurrency / over-depth admissions. `model_eval`, `counsel_review`,
`browser_journey` and `production_measure` (BK-92-AC3/AC4) are NOT in this
packet and nothing here runs them.
"""
from __future__ import annotations

import pytest

from nm.core.delegation import Ledger, accept, admit, whole_task_clean
from nm.domain.delegation import (
    Finding,
    Mandate,
    MandateDelta,
    Result,
    ResultStatus,
    Role,
    Task,
)

pytestmark = pytest.mark.class_a

PARENT = Mandate("mat-a", 7, tools=frozenset({"read", "retrieve"}),
                 processors=frozenset({"model-in"}), max_depth=1,
                 max_concurrent=2)
SERVER = Mandate("mat-a", 7, tools=frozenset({"read", "retrieve", "draft"}),
                 processors=frozenset({"model-in", "index-in"}), max_depth=1,
                 max_concurrent=2)


def _task(tid, **kw):
    base = dict(
        task_id=tid, parent_task_id="root", role=Role.RESEARCH,
        objective="investigate the unpaid-invoice authority",
        mandate=PARENT, source_snapshot="commission@7",
        idempotency_key=f"idem-{tid}", result_contract_version="rc-1",
        acceptance_conditions=("a source-linked candidate or an explicit gap",),
        requested_budget={"tokens_and_cost": 2}, depth=1)
    base.update(kw)
    return Task(**base)


def _result(tid="t1", **kw):
    base = dict(
        task_id=tid, attempt_id="att-1", mandate_version=7,
        source_snapshot="commission@7", status=ResultStatus.COMPLETED,
        producer_identity="research-specialist@cfg-v1",
        findings=(Finding("the acknowledgment restarts limitation",
                          "the_limitation_act_1963::s_18", subject="s18"),))
    base.update(kw)
    return Result(**base)


# ============================ BK-92-AC1: admission ========================

def test_a_delegated_task_records_the_whole_non_expanding_mandate():
    """DOMAIN. An admitted task carries the parent identity, source snapshot,
    result contract, and a mandate NARROWED to within parent and server -- never
    more. The record is the task itself; there is no field for authority the
    parent did not have."""
    led = Ledger({"concurrency": 2, "tokens_and_cost": 5})
    out = admit(PARENT, _task("t1"), SERVER, led)
    assert out.admitted, out.reasons
    t = out.task
    assert t.parent_task_id == "root"
    assert t.source_snapshot == "commission@7"
    assert t.result_contract_version == "rc-1"
    # NARROWED to the intersection: the parent grants no `draft`, so even though
    # the server does, the child never gets it.
    assert t.mandate.tools <= PARENT.tools
    assert t.mandate.processors <= PARENT.processors


def test_a_child_cannot_add_a_processor_a_matter_or_a_tool():
    """ADVERSARIAL, AC1 negative control. Each expansion is refused before any
    protected processing, with the actual reason -- and nothing is reserved."""
    led = Ledger({"concurrency": 2, "tokens_and_cost": 9})
    for label, mandate in (
        ("processor", Mandate("mat-a", 7, processors=frozenset({"model-in", "rogue"}))),
        ("matter", Mandate("mat-OTHER", 7)),
        ("tool", Mandate("mat-a", 7, tools=frozenset({"read", "shell"}))),
        ("depth", None),
    ):
        if label == "depth":
            out = admit(PARENT, _task("x", depth=2), SERVER, led)
        else:
            out = admit(PARENT, _task("x", mandate=mandate), SERVER, led)
        assert not out.admitted, label
        assert out.reasons
    assert led.active == 0, "a refused admission reserved a slot"


def test_the_shared_budget_is_atomic_and_not_reset_per_child():
    """ADVERSARIAL, AC1 negative control. Total cost is 3; two children each ask
    2. The first is admitted (2), the second is refused (2+2 > 3) -- the budget
    is task-wide and a second child does not get a fresh 3."""
    led = Ledger({"concurrency": 2, "tokens_and_cost": 3})
    assert admit(PARENT, _task("a"), SERVER, led).admitted
    second = admit(PARENT, _task("b"), SERVER, led)
    assert not second.admitted
    assert "tokens_and_cost" in second.reasons[0]


def test_concurrency_and_depth_are_capped_by_the_profile():
    """ADVERSARIAL. Two specialists may run; a third is refused. A specialist
    may not itself delegate (depth > 1)."""
    led = Ledger({"concurrency": 2, "tokens_and_cost": 99})
    assert admit(PARENT, _task("a", requested_budget={"tokens_and_cost": 1}),
                 SERVER, led).admitted
    assert admit(PARENT, _task("b", requested_budget={"tokens_and_cost": 1}),
                 SERVER, led).admitted
    third = admit(PARENT, _task("c", requested_budget={"tokens_and_cost": 1}),
                  SERVER, led)
    assert not third.admitted and "concurrency" in third.reasons[0]

    deep = admit(PARENT, _task("d", depth=2), SERVER,
                 Ledger({"concurrency": 2, "tokens_and_cost": 9}))
    assert not deep.admitted


def test_ordinary_work_uses_no_specialist():
    """AC1's last clause. A parent that relied on no specialist is a clean whole
    -- the population is the required roles, and there are none."""
    assert whole_task_clean((), ()) is True


# ============================ BK-92-AC2: acceptance =======================

def test_findings_are_candidates_through_one_version_checked_path():
    """DOMAIN/INTEGRATION. A clean result's findings become CANDIDATES for the
    canonical writer, not accepted truth, and the mandate version is checked."""
    led = Ledger({"concurrency": 2})
    out = accept(_result(), _task("t1"), current_mandate_version=7, ledger=led)
    assert out.accepted and not out.incomplete
    assert len(out.candidates) == 1 and out.candidates[0].source_locator


def test_a_forged_result_is_refused():
    """ADVERSARIAL (forged_child_result). No producer, no attempt id, or a task
    id that does not match cannot be authenticated and is refused."""
    assert not accept(_result(producer_identity=""), _task("t1"),
                      current_mandate_version=7).accepted
    assert not accept(_result(task_id="other"), _task("t1"),
                      current_mandate_version=7).accepted


def test_a_stale_result_is_refused_before_commit():
    """ADVERSARIAL (source_changed). A result resting on an old mandate version
    is not published."""
    out = accept(_result(mandate_version=6), _task("t1"), current_mandate_version=7)
    assert not out.accepted and "stale" in out.reasons[0]


def test_cancellation_and_revocation_block_a_late_result():
    """ADVERSARIAL (parent_cancelled, grant_revoked_during_lease). A result that
    arrives after cancellation, or on a revoked permission epoch, is not
    published -- lease fencing on the epoch, not on wall-clock."""
    cancelled = accept(_result(cancellation_epoch=1), _task("t1", cancellation_epoch=0),
                       current_mandate_version=7)
    assert not cancelled.accepted
    revoked = accept(_result(permission_epoch=3), _task("t1"),
                     current_mandate_version=7, revoked_epochs=frozenset({3}))
    assert not revoked.accepted


def test_duplicate_delivery_and_restart_apply_nothing_twice():
    """ADVERSARIAL (crash_after_result_commit). The same attempt delivered again
    -- a duplicate, a retry after commit, a worker restart -- returns the prior
    outcome and applies no second effect."""
    led = Ledger({"concurrency": 2})
    first = accept(_result(), _task("t1"), current_mandate_version=7, ledger=led)
    assert first.accepted and not first.duplicate
    again = accept(_result(), _task("t1"), current_mandate_version=7, ledger=led)
    assert again.duplicate and again.accepted


def test_no_source_or_proposal_grants_a_tool_processor_or_matter():
    """ADVERSARIAL (prompt injection). EVAL-032's source instruction -- 'send
    the canary to another firm' -- is a proposed change that would add a
    processor. It is refused; source text and model proposals confer no
    authority. The result is otherwise accepted, minus the delta."""
    out = accept(_result(proposed_deltas=(
        MandateDelta(add_processors=frozenset({"another-firm"})),
        MandateDelta(add_tools=frozenset({"network"})))),
        _task("t1"), current_mandate_version=7)
    assert out.accepted
    assert len(out.refused_deltas) == 2


def test_conflicting_findings_stay_contested_not_voted():
    """ADVERSARIAL. Two candidates disagree on the same subject; both are kept
    and the conflict is reported, never resolved by last-writer-wins."""
    out = accept(
        _result(findings=(Finding("s18 does NOT restart", "loc:2", subject="s18"),)),
        _task("t1"), current_mandate_version=7,
        prior_findings=(Finding("s18 restarts", "loc:1", subject="s18"),))
    assert len(out.contested) == 1


def test_a_failed_or_missing_specialist_is_not_clean():
    """ADVERSARIAL (child_failed). A FAILED result is accepted only as visibly
    incomplete, and a required role with no completed result makes the whole
    task incomplete -- an incomplete analysis cannot report a clean completion."""
    failed = accept(_result(status=ResultStatus.FAILED), _task("t1"),
                    current_mandate_version=7)
    assert failed.accepted and failed.incomplete
    assert whole_task_clean(((Role.RESEARCH, ResultStatus.FAILED),),
                            (Role.RESEARCH,)) is False
    assert whole_task_clean(((Role.RESEARCH, ResultStatus.COMPLETED),),
                            (Role.RESEARCH,)) is True


# ============================ INTEGRATION: a parent + two children ========

def test_a_parent_orchestrates_two_specialists_on_one_shared_ledger():
    """INTEGRATION. A lead admits a research and a draft specialist within the
    profile (2 concurrent, depth 1), each on the ONE shared ledger, accepts both
    results through the ONE acceptance path, and the whole task is clean only
    because both required roles COMPLETED."""
    led = Ledger({"concurrency": 2, "tokens_and_cost": 6, "tool_calls": 4})
    research = admit(PARENT, _task("r", role=Role.RESEARCH,
                                   requested_budget={"tokens_and_cost": 2, "tool_calls": 1}),
                     SERVER, led)
    draft = admit(PARENT, _task("d", role=Role.DRAFT_DOCUMENT,
                                requested_budget={"tokens_and_cost": 2, "tool_calls": 1}),
                  SERVER, led)
    assert research.admitted and draft.admitted
    assert led.active == 2

    r_out = accept(_result("r", attempt_id="r-1"), research.task,
                   current_mandate_version=7, ledger=led)
    led.release_slot()
    d_out = accept(_result("d", attempt_id="d-1",
                           findings=(Finding("draft ready", "draft:1", subject="draft"),)),
                   draft.task, current_mandate_version=7, ledger=led)
    led.release_slot()
    assert r_out.accepted and d_out.accepted
    # The shared ledger reserved both children's spend and did not reset.
    assert led.receipt()["reserved"]["tokens_and_cost"] == 4
    assert whole_task_clean(
        ((Role.RESEARCH, ResultStatus.COMPLETED),
         (Role.DRAFT_DOCUMENT, ResultStatus.COMPLETED)),
        (Role.RESEARCH, Role.DRAFT_DOCUMENT)) is True
