"""A TOOL THAT WRITES EVIDENCE RECORDS CAN MANUFACTURE THEM.
BK-21-AC3, BK-42-AC1/AC9, BK-81-AC2, BK-85-AC5, BK-88-AC3.

WHAT THIS DEFENDS
-------------------
Twenty-two criteria carry a row no test can close, so `pipeline/measure.py` gives
each one a command. That is useful and it is also the most dangerous thing in
the repository: the outstanding rows are exactly the ones that say this build
is not releasable, and a command that writes them is a command that can make
them go away.

So the tool is allowed to do two things and nothing else. It PREPARES a
protocol that confers nothing, or it PROMOTES an exact schema-2 record only
after the configured verifier authenticates both payload and authority. It may
never decide that something passed. The parametrised test below includes both
local names and plausible production-looking names: vocabulary is not proof.

    If that check ever comes out permissive, every NOT RUN in the register
    becomes a PASS somebody can type.

WHAT THIS SUITE CANNOT ESTABLISH
----------------------------------
That any measurement happened. It proves the machinery refuses; the rows stay
NOT RUN until somebody runs the commands somewhere real.
"""
from __future__ import annotations

import pathlib

import pytest

from nm.shared.deployment_contracts import (
    STRUCTURED_LEVELS,
    Candidate,
    EvidenceRecord,
    OperationState,
    refuse_record,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
TODAY = "2026-09-14"


def _record(**kw) -> EvidenceRecord:
    base = dict(criterion="BK-42-AC3", level="production_measure",
                subject="a restore into an isolated environment",
                method="observed on the target", actor="ops-lead",
                observed_at=TODAY, result="PASS")
    base.update(kw)
    return EvidenceRecord(**base)


def _deployed() -> Candidate:
    return Candidate(commit="a" * 40, environment="ap-south-1-prod",
                     config_digest="cfg-1",
                     operation_state=OperationState.VERIFIED)


# ====== 1. a production measure cannot be written from this machine ========

@pytest.mark.parametrize("environment", Candidate.LOCAL + (
    "prod", "production", "ap-south-1-prod", " PROD ", "verified",
    "customer-live",
))
def test_no_environment_this_build_can_create_may_write_a_production_measure(
        environment):
    """THE ONE THAT MATTERS. Every outstanding production measure says this
    build is not releasable; a permissive answer here turns all of them into
    a PASS somebody can type."""
    here = Candidate(commit="a" * 40, environment=environment)
    why = refuse_record(_record(), about=here, observed=True)
    assert any("not a deployment" in one or "local" in one
               for one in why), (environment, why)


def test_domain_shape_alone_cannot_permit_a_pass_even_on_a_deployment():
    """Authentication is a verifier result, not another trusted boolean."""
    why = refuse_record(_record(), about=_deployed(), observed=True)
    assert any("domain object cannot authenticate" in one for one in why), why


def test_a_pass_nobody_observed_is_refused():
    why = refuse_record(_record(), about=_deployed(), observed=False)
    assert any("never from an intention" in one for one in why), why


def test_a_record_that_did_not_pass_needs_no_observation():
    """NOT_RUN is the honest default and must stay writable, or the register
    cannot record that a measurement is outstanding."""
    assert refuse_record(_record(result="NOT_RUN"), about=_deployed(),
                         observed=False) == ()


def test_the_default_result_is_not_run_and_not_pass():
    """The direction of the default is the whole argument: a record somebody
    forgot to fill in must read as unmeasured rather than as met."""
    assert EvidenceRecord(
        criterion="BK-1-AC1", level="counsel_review", subject="s",
        method="m", actor="a", observed_at=TODAY).result == "NOT_RUN"


# ============ 2. the other ways a record can be dishonest ==================

def test_a_review_of_ones_own_work_is_not_an_independent_one():
    why = refuse_record(
        _record(level="counsel_review", actor="ops-lead"),
        about=_deployed(), observed=True, operator="ops-lead")
    assert any("not an independent one" in one for one in why), why


def test_another_name_does_not_authenticate_a_review():
    why = refuse_record(
        _record(level="counsel_review", actor="senior counsel"),
        about=_deployed(), observed=True, operator="ops-lead")
    assert any("domain object cannot authenticate" in one for one in why), why


def test_a_plausible_record_without_authentication_is_still_refused():
    why = refuse_record(_record(), about=_deployed(), observed=True)
    assert any("cannot authenticate" in one for one in why), why


def test_an_undated_observation_cannot_be_bound_to_anything():
    why = refuse_record(_record(observed_at="recently"), about=_deployed(),
                        observed=True)
    assert any("not a date" in one for one in why), why


def test_a_level_that_is_not_a_signed_record_is_refused():
    """`domain_test` comes from running the test, not from writing a file.
    A record claiming one would be a test result nobody ran."""
    for level in ("domain_test", "integration_test", "browser_journey"):
        why = refuse_record(_record(level=level), about=_deployed(),
                            observed=True)
        assert any("not a structured evidence level" in one for one in why)
    assert set(STRUCTURED_LEVELS) == {
        "model_eval", "counsel_review", "production_measure"}


def test_every_field_of_a_record_is_required():
    for blanked in ("criterion", "level", "subject", "method", "actor",
                    "observed_at"):
        with pytest.raises(ValueError):
            _record(**{blanked: "   "})


# ============ 3. the tool itself refuses from here =========================


# ============ 4. the packs carry the protocol and confer nothing ===========


