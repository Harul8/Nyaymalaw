"""ONLY A VERIFIED MATCHING APPROVAL AUTHORISES A DECISION. BK-80-AC6.

`check_approvals` answers whether the register PARSES. `adoption_labels`
answered "not machine-resolved" for every choice — honest while nothing
resolved, and a permanent abstention once something can.

SEVEN STATES, AND SIX OF THEM ARE REFUSALS. The criterion names them because
collapsing them loses the only thing a reader can act on:

    not_recorded   nobody has approved this
    unverified     something is recorded and it does not establish authority
    valid          this record authorises this decision at this gate
    stale          what was approved has changed underneath the approval
    expired        it was valid and its period has ended — renewable
    revoked        it was withdrawn — not renewable
    out_of_scope   somebody approved a different gate or a different packet

A boolean sends `expired` and `revoked` to the same place, and they are not the
same conversation.

THE CRITERION'S OWN MUTATION, run below: *reuse approval after relevant
configuration changes, revoke or expire it, substitute an unauthorised signer,
widen scope or replace signed authority with a PASS measurement or proposal
flag.* The last clause is why `resolve` reads the approval store and nothing
else — a resolver that could see a measurement would eventually be asked to
accept one.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tools.blueprint_approvals import (
    EXPIRED,
    NOT_RECORDED,
    OUT_OF_SCOPE,
    REVOKED,
    STALE,
    STATES,
    UNVERIFIED,
    VALID,
    resolve,
)

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
PROPOSAL = "a" * 64
CONFIG = "config-2026-09"


def _artifact(digest: str = "b" * 64) -> dict:
    return {"ref": "docs/blueprint/signed/record.pdf", "sha256": digest}


def _record(**overrides) -> dict:
    base = {
        "id": "ADOPT-01",
        "choice": "CHOICE-02",
        "proposal_sha256": PROPOSAL,
        "scope": {"gate": "packet", "packets": ["P01"], "configuration": CONFIG},
        "approvers": [{"person_id": "person-1", "name": "A Signer",
                       "role": "accountable owner",
                       "authority_basis": "delegated by the account holder",
                       "authority_evidence": _artifact("c" * 64)}],
        "signed_record": _artifact(),
        "approved_at": "2026-09-01T00:00:00+00:00",
        "effective_from": "2026-09-02T00:00:00+00:00",
        "valid_until": "2026-12-01T00:00:00+00:00",
        "conditions": [],
        "supersedes": [],
    }
    base.update(overrides)
    return base


def _store(records=None, revocations=None) -> dict:
    # `records if records is not None`, NOT `records or`. The first version
    # used `or`, so `_store(records=[])` -- the empty register, which is the
    # whole point of the `not_recorded` state -- fell back to the default
    # record and the test asked a question it thought it was avoiding. An
    # empty list is a value; that is the same distinction this file is about.
    return {"schema": 1, "purpose": "synthetic",
            "records": [_record()] if records is None else records,
            "revocations": [] if revocations is None else revocations}


CHOICES = {"choices": [{"id": "CHOICE-02", "approval_required_for": ["packet"]}]}
PACKETS = {"packets": [{"id": "P01", "decisions": ["CHOICE-02"]}]}


def _resolve(store, **kwargs):
    options = {"choice": "CHOICE-02", "gate": "packet", "packet": "P01",
               "proposal_sha256": PROPOSAL, "configuration": CONFIG, "now": NOW}
    options.update(kwargs)
    return resolve(store, CHOICES, PACKETS, **options)


# ============================ the negative control ==========================

def test_a_complete_matching_approval_authorises():
    """Without this, a resolver that refused everything would satisfy every
    other test here and block the project permanently."""
    got = _resolve(_store())
    assert got.state == VALID, got.why
    assert got.authorises
    assert got.record == "ADOPT-01"


# ======================= the criterion's own mutations ======================

def test_a_configuration_change_makes_the_approval_stale():
    """*Reuse approval after relevant configuration changes.*"""
    got = _resolve(_store(), configuration="config-2026-10")
    assert got.state == STALE, got.why
    assert not got.authorises


def test_a_changed_proposal_makes_the_approval_stale():
    got = _resolve(_store(), proposal_sha256="d" * 64)
    assert got.state == STALE, got.why


def test_a_revoked_approval_is_revoked_and_not_merely_absent():
    """*Revoke it.* And the state is not `not_recorded`: somebody withdrew
    this, which is a different conversation from nobody having approved."""
    got = _resolve(_store(revocations=[{
        "id": "REVOKE-01", "approval_id": "ADOPT-01",
        "effective_at": "2026-09-05T00:00:00+00:00",
        "reason": "the accountable owner withdrew it"}]))
    assert got.state == REVOKED, got.why
    assert "withdrew" in got.why


def test_an_expired_approval_is_expired_and_not_revoked():
    """*Expire it.* Renewable, where a revoked one is not — which is exactly
    what a boolean would lose."""
    got = _resolve(_store([_record(valid_until="2026-09-05T00:00:00+00:00")]))
    assert got.state == EXPIRED, got.why


@pytest.mark.parametrize("mutation", [
    {"approvers": []},
    {"approvers": [{"person_id": "p", "name": "n", "role": "r",
                    "authority_basis": "", "authority_evidence": _artifact()}]},
    {"approvers": [{"person_id": "p", "name": "n", "role": "r",
                    "authority_basis": "stated", "authority_evidence": {}}]},
    {"signed_record": {}},
])
def test_an_unauthorised_or_unsigned_record_does_not_verify(mutation):
    """*Substitute an unauthorised signer* and *replace signed authority.*

    A stated basis with no evidence and evidence with no stated basis are both
    assertions about authority rather than demonstrations of it.
    """
    got = _resolve(_store([_record(**mutation)]))
    assert got.state == UNVERIFIED, got.why
    assert not got.authorises


@pytest.mark.parametrize("gate,packet,why", [
    ("deployment", "P01", "gate"),
    ("packet", "P42", "packet"),
])
def test_widening_scope_is_refused_at_the_gate_that_was_not_approved(gate, packet, why):
    """*Widen scope.* An approval for one packet gate must never satisfy a
    deployment gate, which is the criterion's *never all packet or deployment
    gates* in one assertion."""
    got = _resolve(_store(), gate=gate, packet=packet)
    assert got.state == OUT_OF_SCOPE, got.why
    assert why in got.why


def test_an_unmet_condition_leaves_the_approval_unverified():
    got = _resolve(_store([_record(conditions=[
        {"id": "COND-1", "requirement": "an isolated rehearsal", "evidence": {}}])]))
    assert got.state == UNVERIFIED
    assert "COND-1" in got.why


def test_a_condition_with_evidence_does_not_block():
    got = _resolve(_store([_record(conditions=[
        {"id": "COND-1", "requirement": "an isolated rehearsal",
         "evidence": _artifact("e" * 64)}])]))
    assert got.state == VALID, got.why


# ============================== absent inputs ===============================

def test_no_record_is_not_recorded_and_an_unreadable_store_is_unverified():
    """§9. These are three states and the middle one is the one that matters:
    reporting an unreadable register as 'nothing recorded' sends the reader to
    write an approval that may already exist."""
    assert _resolve(_store(records=[])).state == NOT_RECORDED
    for unreadable in (None, {}, {"records": "not a list"}, []):
        got = _resolve(unreadable)
        assert got.state == UNVERIFIED, (unreadable, got)
        assert "unreadable" in got.why or "does not verify" in got.why


def test_an_approval_not_yet_in_force_does_not_authorise():
    got = _resolve(_store(), now=datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
    assert got.state == UNVERIFIED
    assert "take effect" in got.why


def test_a_superseded_record_is_not_the_one_that_answers():
    older = _record(id="ADOPT-00", approved_at="2026-08-01T00:00:00+00:00")
    newer = _record(id="ADOPT-01", supersedes=["ADOPT-00"],
                    scope={"gate": "packet", "packets": ["P01"],
                           "configuration": "config-2026-10"})
    got = _resolve(_store([older, newer]))
    assert got.record == "ADOPT-01", "the superseded record answered"
    assert got.state == STALE


# =========================== the shape of the answer ========================

def test_every_declared_state_is_reachable():
    """A vocabulary with an unreachable member is a vocabulary that lies about
    what the resolver can tell you."""
    reached = {
        _resolve(_store(records=[])).state,
        _resolve(None).state,
        _resolve(_store()).state,
        _resolve(_store(), configuration="other").state,
        _resolve(_store([_record(valid_until="2026-09-05T00:00:00+00:00")])).state,
        _resolve(_store(revocations=[{
            "id": "R", "approval_id": "ADOPT-01",
            "effective_at": "2026-09-05T00:00:00+00:00", "reason": "x"}])).state,
        _resolve(_store(), gate="deployment").state,
    }
    assert reached == set(STATES), sorted(set(STATES) - reached)


def test_only_valid_authorises_and_every_state_carries_a_reason():
    for state in STATES:
        assert isinstance(state, str) and state
    for got in (_resolve(_store()), _resolve(None), _resolve(_store(records=[])),
                _resolve(_store(), gate="deployment")):
        assert got.why.strip(), got
        assert got.authorises == (got.state == VALID)


def test_the_resolver_cannot_see_a_measurement_at_all():
    """*Replace signed authority with a PASS measurement or proposal flag.*

    Checked on the signature rather than by feeding one in: a resolver that
    took an evaluation result as a parameter would eventually be asked to
    honour it, and the criterion's first clause is that adoption is resolved
    separately from measurement.
    """
    import inspect

    accepted = set(inspect.signature(resolve).parameters)
    forbidden = {"result", "results", "evaluation", "evaluations", "measurement",
                 "passed", "coverage", "proposal_flag", "approved"}
    assert not (accepted & forbidden), sorted(accepted & forbidden)
    source = inspect.getsource(resolve)
    for token in ("PASS", "evaluations", "coverage.yaml", "measure"):
        assert token not in source.split('"""', 2)[-1], (
            f"the resolver body references {token!r}")
