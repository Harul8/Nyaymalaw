"""A SECURITY CLAIM IS ABOUT ONE EXACT CANDIDATE. P39.
BK-42-AC1, BK-42-AC2, BK-42-AC8, BK-85-AC1, BK-85-AC6, BK-21-AC3, BK-88-AC2,
BK-88-AC4.

WHAT THESE DEFEND
-------------------
"Secrets are not in the artifact" is true of some build. The question is
whether it is true of THIS one, and the only thing that makes those the same
sentence is an identity on both. A passing scan from last month, read as a
fact about the build being released, is the whole failure mode.

And three substitutions, each of which has been offered as the thing on the
left:

    a penetration test        <- a scanner exiting zero
    target IAM enforcement    <- a local file permission
    a credential rotation     <- an edit to an environment file

Each has a named refusal here rather than a comment somewhere.

WHAT IS DRIVEN RATHER THAN REBUILT
------------------------------------
`nm/domain/egress.py` already owns region, purpose, processor and sink policy,
and the inventory it enforces is the REAL `docs/blueprint/processors.yaml`
read through `nm/bootstrap/egress_policy.py` -- a synthetic policy would prove
that the checker compiles. `nm/domain/media_policy.py` owns the prohibited-
processing contract. `nm/adapters/store/sealing.py` owns matter-scoped key
derivation and `nm/edge/uploads.py` owns the served ownership check.
`nm/domain/retention.py` owns what makes a deletion claim false, and
`nm/domain/metrics.py` owns which fields reach a plaintext file. None of them
is reimplemented, because a second copy of "may this leave the country" is one
that will disagree.

WHAT THIS SUITE CANNOT ESTABLISH
----------------------------------
Anything about a deployed environment. There is not one. `Candidate.operated`
is False for every environment this build can create, and every
`production_measure` on all nine P39 criteria stays NOT RUN.
"""
from __future__ import annotations

import inspect
import json
import pathlib

import pytest

from nm.domain.deployment import (
    POPULATIONS,
    AccessRequest,
    Assessed,
    Candidate,
    Claim,
    ClaimKind,
    Factor,
    Inventory,
    Population,
    Rotation,
    Waiver,
    distinct_secrets,
    projection,
    refuse_access,
    refuse_claim,
    refuse_rotation_claim,
    shared_values,
    shares_value_with,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMIT = "9d376aa" + "0" * 33
TODAY = "2026-09-14"


def _candidate(**kw) -> Candidate:
    base = dict(commit=COMMIT, environment="working_tree", config_digest="cfg-1")
    base.update(kw)
    return Candidate(**base)


def _inventory(candidate=None, missing=()) -> Inventory:
    candidate = candidate or _candidate()
    rows = {name: Population(rows=(f"{name}-row",), state=Assessed.ASSESSED)
            for name in POPULATIONS if name not in missing}
    return Inventory(candidate=candidate, populations=rows)


# ============ 1. evidence is bound to the candidate it is about ============

def test_a_complete_inventory_of_this_candidate_supports_a_claim():
    """THE POSITIVE CONTROL. A rule that refused every claim would satisfy
    this whole file and admit no evidence at all."""
    here = _candidate()
    claim = Claim(kind=ClaimKind.INVENTORIED, candidate=here, made_by="operator",
                  made_at=TODAY, note="enumerated on the working tree")
    assert refuse_claim(claim, about=here, inventory=_inventory(here)) == ()


def test_a_claim_about_another_candidate_does_not_cover_this_one():
    """A passing scan from another build is a fact about that build."""
    elsewhere = _candidate(commit="a" * 40)
    claim = Claim(kind=ClaimKind.SCANNED, candidate=elsewhere,
                  made_by="operator", made_at="2026-09-01", note="clean")
    why = refuse_claim(claim, about=_candidate())
    assert why and "and the release candidate is" in why[0]


def test_a_changed_configuration_is_a_different_candidate():
    """Same commit, different configuration, different deployment. The commit
    alone is not the thing being released."""
    before = _candidate(config_digest="cfg-1")
    after = _candidate(config_digest="cfg-2")
    assert before.identity != after.identity
    claim = Claim(kind=ClaimKind.SCANNED, candidate=before, made_by="operator",
                  made_at=TODAY, note="clean")
    assert refuse_claim(claim, about=after)


def test_the_inventory_must_describe_the_same_candidate():
    here = _candidate()
    claim = Claim(kind=ClaimKind.INVENTORIED, candidate=here, made_by="operator",
                  made_at=TODAY, note="enumerated")
    other = _inventory(_candidate(commit="c" * 40))
    assert any("a different candidate" in why
               for why in refuse_claim(claim, about=here, inventory=other))


# ========== 2. an empty population is not the same as an unchecked one =====

def test_the_fourteen_populations_are_declared_and_distinct():
    assert len(POPULATIONS) == 14 == len(set(POPULATIONS))
    for needed in ("artifacts", "lockfiles", "provenance", "runtimes",
                   "secret_sources", "application_identities",
                   "service_identities", "privileged_roles", "emergency_roles",
                   "support_paths", "telemetry_destinations", "subprocessors",
                   "storage_boundaries", "allowed_egress"):
        assert needed in POPULATIONS


def test_a_population_nobody_enumerated_blocks_the_claim():
    """A SCAN THAT FOUND NOTHING AND A SCAN THAT DID NOT RUN look the same in
    every report that stores a list."""
    here = _candidate()
    claim = Claim(kind=ClaimKind.INVENTORIED, candidate=here, made_by="operator",
                  made_at=TODAY, note="enumerated")
    why = refuse_claim(claim, about=here,
                       inventory=_inventory(here, missing=("subprocessors",)))
    assert any("never enumerated" in one and "subprocessors" in one
               for one in why)


def test_an_empty_population_that_was_checked_reads_as_checked():
    """THE POSITIVE CONTROL on the distinction. A rule that blocked on every
    empty population would make "we have no subprocessors" unstatable."""
    checked = Population(rows=(), state=Assessed.EMPTY)
    assert checked.state.can_be_relied_on is True
    assert checked.render() == "none, and that was checked"
    assert "nobody enumerated" in Population().render()
    assert Assessed.not_established() is Assessed.NOT_ASSESSED


def test_a_population_cannot_carry_rows_and_claim_nobody_looked():
    assert Population(rows=("x",)).state is Assessed.ASSESSED
    assert Population(rows=(), state=Assessed.ASSESSED).state is Assessed.EMPTY


# ============ 3. the three substitutions, each refused by name =============

@pytest.mark.parametrize("kind", [
    ClaimKind.PENETRATION_TESTED, ClaimKind.IAM_ENFORCED,
    ClaimKind.CREDENTIAL_ROTATED])
def test_an_operated_claim_cannot_be_made_from_a_working_tree(kind):
    """*A scanner result is not a penetration-test or compliance certificate.
    Synthetic local permissions do not prove target IAM/KMS/network
    isolation.* -- P39's own declared expected failures."""
    here = _candidate()
    claim = Claim(kind=kind, candidate=here, made_by="operator", made_at=TODAY,
                  note="ran locally")
    why = refuse_claim(claim, about=here)
    assert any("is not a penetration test" in one for one in why), why
    assert kind.needs_an_operated_environment is True


def test_an_inventory_or_scan_claim_is_fine_from_a_working_tree():
    """THE POSITIVE CONTROL. Enumerating what a tree contains is exactly what
    a tree can answer, and refusing it would leave nothing provable at all."""
    here = _candidate()
    for kind in (ClaimKind.INVENTORIED, ClaimKind.SCANNED):
        claim = Claim(kind=kind, candidate=here, made_by="operator",
                      made_at=TODAY, note="ran locally")
        assert refuse_claim(claim, about=here) == ()
        assert kind.needs_an_operated_environment is False


def test_no_environment_this_build_can_create_is_operated():
    for environment in Candidate.LOCAL:
        assert _candidate(environment=environment).operated is False
    assert _candidate(environment="ap-south-1-prod").operated is True


def test_a_claim_records_who_made_it_and_why():
    for missing in ({"made_by": "  "}, {"note": ""}, {"made_at": ""}):
        with pytest.raises(ValueError):
            Claim(kind=ClaimKind.SCANNED, candidate=_candidate(),
                  **{"made_by": "operator", "made_at": TODAY, "note": "clean",
                     **missing})


# ======= 4. BK-21-AC3 -- the seal shares its value with nothing ============

def test_a_shared_secret_is_reported_by_name_and_never_by_value():
    """BK-21-AC3'S MUTATION: *restore the previous .env, where NM_MATTER_KEY
    equalled NM_MODEL_API_KEY*.

    The comparison is on digests: one that compared plaintext would hold both
    values beside each other, and the report naming the collision would be
    carrying the value it was reporting on.
    """
    secret = "the-same-thing-in-two-places"
    found = distinct_secrets({"NM_MATTER_KEY": secret,
                              "NM_MODEL_API_KEY": secret,
                              "NM_SESSION_KEY": "something else"})
    assert len(found) == 1
    assert "NM_MATTER_KEY" in found[0] and "NM_MODEL_API_KEY" in found[0]
    assert secret not in " ".join(found)
    assert "something else" not in " ".join(found)


def test_distinct_secrets_are_not_reported():
    """THE POSITIVE CONTROL."""
    assert distinct_secrets({"A": "one", "B": "two", "C": "three"}) == ()
    assert shared_values({"A": "one", "B": "two"}) == ()


def test_two_unset_variables_are_not_a_shared_secret():
    """Reporting them as a collision buries the real one."""
    assert distinct_secrets({"A": "", "B": "   ", "C": "real"}) == ()


def test_the_composition_root_asks_this_module_rather_than_comparing_values():
    """ONE OWNER OF "DO THESE HOLD THE SAME STRING".

    Two implementations is CLAUDE.md section 4 at the point where the answer
    decides whether 247 sealed matters stay readable. `_refuse_a_shared_seal`
    keeps its own policy about WHICH names count as credentials, and asks this
    module the value question.
    """
    from nm.bootstrap import composition

    source = inspect.getsource(composition._refuse_a_shared_seal)
    assert "shares_value_with" in source
    assert "value.strip() == key.strip()" not in source

    seal = "a-seal-value"
    assert shares_value_with("NM_MATTER_KEY",
                             {"NM_MATTER_KEY": seal, "OPENAI_API_KEY": seal,
                              "OTHER": "different"}) == ("OPENAI_API_KEY",)
    assert shares_value_with("NM_MATTER_KEY",
                             {"NM_MATTER_KEY": seal, "OTHER": "x"}) == ()


# THE REAL ENVIRONMENT IS NOT READ HERE, and that is the point.
#
# A first version of this file asked whether THIS MACHINE's NM_MATTER_KEY
# shares its value with NM_MODEL_API_KEY, and skipped when neither was set.
# Class-A refused it, correctly: a skip inside the offline every-commit suite
# is a node that did not pass wearing a green tick, which is section 9's
# absent-input defect at the exact place this packet is about.
#
# It was also a SECOND COPY. `tests/test_the_deployment_environment_keeps_its
# _seal_separate.py` is deliberately unmarked and already owns that reading,
# and it is the ref BK-21-AC3 records -- BLOCKED, because this worktree holds
# no key and an absent value cannot show a separation that was never at risk.
# What belongs here is the MECHANISM, which is hermetic and above.


# ======= 5. BK-21-AC4 -- an env edit is not a provider rotation ============

def test_editing_the_environment_file_is_not_a_rotation():
    """The old value keeps working until somebody revokes it AT THE PROVIDER,
    which is the entire difference."""
    why = refuse_rotation_claim(Rotation.LOCAL_EDIT, operator_authority="ops")
    assert "the old value keeps working" in why
    assert Rotation.LOCAL_EDIT.revokes_the_old_value is False


def test_a_real_rotation_still_needs_a_named_operator_authority():
    """Rotating a live provider credential breaks every process still holding
    the old value. It is an operational act with a blast radius."""
    assert refuse_rotation_claim(Rotation.AT_THE_PROVIDER,
                                 operator_authority="") != ""
    assert refuse_rotation_claim(Rotation.AT_THE_PROVIDER,
                                 operator_authority="ops lead") == ""


def test_not_done_is_the_default_and_is_not_a_rotation():
    assert Rotation.not_established() is Rotation.NOT_DONE
    assert refuse_rotation_claim(Rotation.NOT_DONE, operator_authority="ops")


# ============ 6. BK-42-AC2 -- the second factor and its exception ==========

def _deployed(**kw) -> Candidate:
    return _candidate(environment="ap-south-1-prod", **kw)


def _waiver(**kw) -> Waiver:
    base = dict(owner="ops lead", approved_by="security officer",
                expires_on="2026-10-01",
                approved_for_environment="ap-south-1-prod",
                compensating_controls=("hardware token in escrow",))
    base.update(kw)
    return Waiver(**base)


def test_a_present_second_factor_is_admitted():
    """THE POSITIVE CONTROL. Nobody can reach the deployment otherwise."""
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.PRESENT)
    assert refuse_access(request, on=TODAY) == ()


def test_an_absent_second_factor_with_no_exception_is_refused():
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT)
    why = refuse_access(request, on=TODAY)
    assert any("no second factor was presented" in one for one in why)
    assert any("no approved exception" in one for one in why)


def test_a_factor_nobody_assessed_is_not_a_present_one():
    """THE ABSENT-INPUT DEFECT AT THE FRONT DOOR. `NOT_ASSESSED` is the
    default, so a flow that forgets to record the factor refuses."""
    request = AccessRequest(account_id="ops-1", candidate=_deployed())
    assert request.factor is Factor.NOT_ASSESSED
    assert Factor.not_established() is Factor.NOT_ASSESSED
    why = refuse_access(request, on=TODAY)
    assert any("nobody established whether a second factor" in one
               for one in why)


def test_an_expired_exception_is_refused_and_names_both_dates():
    """*attempt production access with ... an expired exception.*"""
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT,
                            waiver=_waiver(expires_on="2026-09-13"))
    why = refuse_access(request, on=TODAY)
    assert any("expired on 2026-09-13" in one and TODAY in one for one in why)


def test_an_exception_expiring_today_still_holds():
    """THE BOUNDARY, driven rather than asserted around. An exception valid
    until the first is valid on the first."""
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT,
                            waiver=_waiver(expires_on=TODAY))
    assert not any("expired" in one for one in refuse_access(request, on=TODAY))


def test_a_prototype_or_local_roster_decision_cannot_waive_the_second_factor():
    """The population the approval reasoned about is not the population it
    would waive. That is why `Candidate.LOCAL` is one list."""
    for roster in Candidate.LOCAL:
        request = AccessRequest(
            account_id="ops-1", candidate=_deployed(), factor=Factor.ABSENT,
            waiver=_waiver(approved_for_environment=roster))
        why = refuse_access(request, on=TODAY)
        assert any("cannot waive the second factor" in one for one in why), why


def test_an_exception_with_no_compensating_control_is_a_waiver():
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT,
                            waiver=_waiver(compensating_controls=()))
    why = refuse_access(request, on=TODAY)
    assert any("a waiver rather than an exception" in one for one in why)


def test_an_exception_cannot_be_approved_by_the_account_it_covers():
    """*separately approved* -- an exception nobody else agreed to is a
    decision taken alone."""
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT,
                            waiver=_waiver(approved_by="ops-1"))
    why = refuse_access(request, on=TODAY)
    assert any("approved by the same account" in one for one in why)


def test_an_exception_approved_for_another_deployment_does_not_travel():
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT,
                            waiver=_waiver(
                                approved_for_environment="eu-west-1-prod"))
    why = refuse_access(request, on=TODAY)
    assert any("'eu-west-1-prod'" in one and "'ap-south-1-prod'" in one
               for one in why)


def test_a_prototype_access_flow_cannot_demonstrate_the_deployed_one():
    """The whole criterion is about the DEPLOYED access flow, so an exception
    exercised against a working tree is refused even when it is otherwise
    perfect."""
    request = AccessRequest(
        account_id="ops-1", candidate=_candidate(), factor=Factor.ABSENT,
        waiver=_waiver(approved_for_environment="working_tree"))
    why = refuse_access(request, on=TODAY)
    assert any("not a deployed environment" in one for one in why)


def test_an_exception_that_cannot_expire_does_not():
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT,
                            waiver=_waiver(expires_on="whenever"))
    why = refuse_access(request, on=TODAY)
    assert any("which is not a date" in one for one in why)


def test_an_exception_missing_an_owner_or_an_approver_is_refused_outright():
    for blanked in ("owner", "approved_by", "expires_on",
                    "approved_for_environment"):
        with pytest.raises(ValueError):
            _waiver(**{blanked: "   "})


def test_an_unreadable_clock_cannot_clear_an_expiry():
    request = AccessRequest(account_id="ops-1", candidate=_deployed(),
                            factor=Factor.ABSENT, waiver=_waiver())
    why = refuse_access(request, on="not-a-date")
    assert any("not a date" in one and "unreadable clock" in one for one in why)


# ====== 7. BK-85-AC1 -- egress fails closed on the REAL inventory ==========

def _policy():
    from nm.bootstrap.egress_policy import egress_policy

    return egress_policy(ROOT)


def _route(**kw):
    from nm.domain.egress import DataClass, Route, Sink

    base = dict(sink=Sink.MODEL, processor_id="scripted", purpose=Sink.MODEL,
                data_classes=(DataClass.CLIENT_MATTER,), size_bytes=1024)
    base.update(kw)
    return Route(**base)


def test_the_configured_inventory_permits_the_processor_it_recorded():
    """THE POSITIVE CONTROL, on the REAL `docs/blueprint/processors.yaml`.
    A policy that refused everything would satisfy every test below it."""
    from nm.domain.egress import refuse

    assert refuse(_route(), _policy()) == []


def test_an_unapproved_processor_fails_closed_on_the_real_inventory():
    """*enable a foreign processor* -- and an unlisted one is not a processor
    nobody wrote a rule for, it is one nobody approved."""
    from nm.domain.egress import refuse

    why = refuse(_route(processor_id="openai"), _policy())
    assert why and "not in the reviewed inventory" in why[0]


def test_a_foreign_region_processor_is_refused_until_a_review_names_it():
    """The real inventory has no foreign processor, so the refusal is driven
    against a policy that does -- and the empty `approved_foreign_regions` of
    the real one is asserted beside it, which is the fact that matters."""
    from nm.domain.egress import (
        DataClass,
        Policy,
        Processor,
        Sink,
        refuse,
    )

    assert _policy().approved_foreign_regions == {}
    abroad = Policy(processors=(Processor(
        processor_id="elsewhere", region="us", purposes=(Sink.MODEL,),
        data_classes=(DataClass.CLIENT_MATTER,), approval_id="A-1"),))
    why = refuse(_route(processor_id="elsewhere"), abroad)
    assert any("no legal review admits that region" in one for one in why)


def test_privileged_text_may_never_reach_diagnostic_telemetry():
    """BK-85-AC1'S MUTATION: *send privileged text through diagnostic
    telemetry*. The two sinks are declared once, in the owner, and the refusal
    holds *whatever the inventory says*."""
    from nm.domain.egress import (
        NEVER_CLIENT_MATERIAL,
        DataClass,
        Policy,
        Processor,
        Sink,
        refuse,
    )

    assert set(NEVER_CLIENT_MATERIAL) == {Sink.TELEMETRY, Sink.SUPPORT}
    for sink in NEVER_CLIENT_MATERIAL:
        admitted = Policy(processors=(Processor(
            processor_id="diagnostics", region="in", purposes=(sink,),
            data_classes=(DataClass.CLIENT_MATTER,), approval_id="A-1"),))
        why = refuse(_route(sink=sink, purpose=sink,
                            processor_id="diagnostics"), admitted)
        assert any("may never reach" in one for one in why), (sink, why)


def test_the_home_region_is_india_and_it_is_declared_once():
    from nm.domain.egress import HOME_REGION

    assert HOME_REGION == "in"
    assert all(row.region == HOME_REGION for row in _policy().processors)


def test_the_refusal_audit_line_carries_no_client_material():
    """*a content-free audit identifies the refusal.* A message quoting what
    it refused to send defeats the control it is part of."""
    from nm.domain.egress import audit_line, refuse

    route = _route(processor_id="openai")
    line = audit_line(route, refuse(route, _policy()))
    assert "REFUSED" in line and "openai" in line
    assert "bytes=1024" in line


# ===== 8. BK-85-AC6 / BK-88-AC2 -- one tenant cannot read another ==========

def test_a_support_account_cannot_open_an_unrelated_matter():
    """BK-85-AC6'S MUTATION: *use a support account to inspect an unrelated
    matter*, driven through the SERVED entry path rather than a copy of it."""
    import tempfile

    from nm.adapters.store.file_store import FileMatterStore
    from nm.domain.matter import Matter, MatterId
    from nm.edge.uploads import UploadRefused, UploadService

    with tempfile.TemporaryDirectory() as tmp:
        store = FileMatterStore(pathlib.Path(tmp), key="a-test-seal-value")
        store.commit(Matter(id=MatterId("m_owned"), advocate_id="adv_owner",
                            title="Another advocate's matter", version=1),
                     expected_version=0)
        service = UploadService(store, store.upload_storage())
        assert service.owned("m_owned", "adv_owner").id == MatterId("m_owned")
        with pytest.raises(UploadRefused):
            service.owned("m_owned", "support_desk")


def test_a_worker_holding_one_matters_key_cannot_read_another():
    """*bypass the shared gateway from a worker.* There is no check to
    forget: the matter id is an input to the derivation, so the wrong key
    does not open the record."""
    from nm.adapters.store.envelope import (
        CrossMatterAccess,
        LocalKeyRing,
        new_data_key,
    )

    ring = LocalKeyRing("a-test-kek-secret")
    key = new_data_key()
    wrapped = ring.wrap("matter-A", key)
    assert ring.unwrap("matter-A", wrapped) == key
    with pytest.raises(CrossMatterAccess):
        ring.unwrap("matter-B", wrapped)


def test_a_secret_bearing_artifact_is_found_by_the_same_digest_question():
    """*introduce a secret-bearing artifact.* The artifact carries a value
    that is also a live credential, and it is found without either being
    printed or compared as text."""
    secret = "sk-proj-a-value-that-should-not-be-in-a-build"
    found = distinct_secrets({"NM_MODEL_API_KEY": secret,
                              "dist/app.bundle.js": secret,
                              "dist/README.md": "no secret here"})
    assert len(found) == 1
    assert "dist/app.bundle.js" in found[0]
    assert secret not in found[0]


# ====== 9. BK-42-AC8 -- a log discloses nothing, a deletion is real =======

def test_a_gate_detail_quoting_the_matter_never_reaches_the_plaintext_file():
    """BK-42-AC8'S MUTATION: *place privileged content in a log.* Driven
    through the projection `file_store.record_metrics` actually writes."""
    from nm.domain.metrics import TurnMetrics

    privileged = "the agreement is dated 15 April 1984 and the client says"
    metrics = TurnMetrics(turn_id="t1", matter_id="m1")
    metrics.fire("G-LIMITATION", "computed", privileged)
    metrics.violate("a-rule", privileged)

    assert privileged in json.dumps(metrics.as_served())
    written = json.dumps(metrics.as_dict())
    assert privileged not in written
    assert "G-LIMITATION" in written and "a-rule" in written


def test_a_deletion_cannot_be_claimed_complete_while_a_copy_is_outstanding():
    """*retain an unauthorised derivative after a deletion claim.*"""
    from nm.domain.retention import (
        AssetRef,
        Copy,
        RequestedAction,
        RequestScope,
        RetentionState,
        advance,
        refuse_transition,
        request,
    )

    asked = request(
        request_id="r1", matter_id="m1", requested_by="adv_1",
        requested_at=TODAY, scope=RequestScope.SELECTED_ASSETS,
        requested_action=RequestedAction.ERASE,
        purpose="the client withdrew consent", authority_id="auth-1",
        authority_version=1, assets=(AssetRef(id="a1", version=1),),
        copies=(Copy(location="a1#derivative-index",
                     kind="derivative"),))
    working = advance(asked, RetentionState.APPROVED)
    working = advance(working, RetentionState.IN_PROGRESS)
    working = advance(working, RetentionState.ERASED_FROM_ACTIVE_SYSTEMS)
    why = refuse_transition(working, RetentionState.COMPLETE_FOR_DECLARED_SCOPE)
    assert "the declared scope is not gone" in why
    assert "a1#derivative-index" in why


def test_a_deletion_whose_copies_are_resolved_does_complete():
    """THE POSITIVE CONTROL. A lifecycle that never completes is not a
    lifecycle, and the advocate is owed the finished answer."""
    from dataclasses import replace

    from nm.domain.retention import (
        AssetRef,
        Copy,
        RequestedAction,
        RequestScope,
        RetentionState,
        Tombstone,
        advance,
        refuse_transition,
        request,
    )

    asked = request(
        request_id="r2", matter_id="m1", requested_by="adv_1",
        requested_at=TODAY, scope=RequestScope.SELECTED_ASSETS,
        requested_action=RequestedAction.ERASE,
        purpose="the client withdrew consent", authority_id="auth-1",
        authority_version=1, assets=(AssetRef(id="a1", version=1),),
        copies=(Copy(location="a1#derivative-index", kind="derivative",
                     resolved_at=TODAY),))
    working = advance(asked, RetentionState.APPROVED)
    working = advance(working, RetentionState.IN_PROGRESS)
    working = advance(working, RetentionState.ERASED_FROM_ACTIVE_SYSTEMS)
    working = replace(working, tombstones=(
        Tombstone(asset_id="a1", asset_version=1, erased_at=TODAY,
                  request_id="r2"),))
    assert refuse_transition(
        working, RetentionState.COMPLETE_FOR_DECLARED_SCOPE) == ""


# ========= 10. BK-88-AC4 -- nothing prohibited is asked or accepted ========

def test_media_preflight_refuses_before_bytes_leave_the_boundary():
    """*The media preflight must refuse before any bytes leave the controlled
    boundary.* `refuse_request` takes the ROUTE -- it cannot be called after
    the send, because it is never given anything to send."""
    from nm.domain import media_policy

    parameters = inspect.signature(media_policy.refuse_request).parameters
    assert list(parameters) == ["route", "contract"]
    route_fields = set(
        inspect.signature(media_policy.Route).parameters)
    assert not route_fields & {"payload", "bytes", "content", "audio", "data"}


def test_the_prohibited_operations_are_read_from_the_declared_contract():
    """ONE OWNER. A second list of what may not be done to a recording is one
    that will disagree with the first."""
    from nm.domain.media_policy import load

    contract = load(ROOT)
    for banned in ("voice_identity", "voiceprint_creation_or_matching",
                   "affect_emotion",
                   "credibility_from_voice_or_appearance"):
        assert banned in contract.prohibited, banned
    assert not (contract.prohibited & contract.allowed)


def test_a_prohibited_operation_is_refused_before_the_call_is_made():
    from nm.domain.media_policy import Route, load, refuse_request

    contract = load(ROOT)
    approved = sorted(contract.allowed)[0]
    assert refuse_request(Route(processor="local", operations=(approved,)),
                          contract) == []
    for banned in sorted(contract.prohibited):
        why = refuse_request(Route(processor="local", operations=(banned,)),
                             contract)
        assert why and "is prohibited" in why[0], (banned, why)


def test_an_unavoidable_background_operation_rejects_the_route():
    """*enable a prohibited processor capability on the deployed
    configuration.* What is approved is the operation AND its configuration,
    so a vendor that scores affect anyway is refused even unasked."""
    from nm.domain.media_policy import Route, load, refuse_request

    contract = load(ROOT)
    approved = sorted(contract.allowed)[0]
    why = refuse_request(
        Route(processor="vendor", operations=(approved,),
              unavoidable=("affect_emotion",)), contract)
    assert any("unavoidable background processing" in one for one in why)


def test_an_unknown_configuration_is_denied_rather_than_assumed_benign():
    from nm.domain.media_policy import Route, load, refuse_request

    contract = load(ROOT)
    approved = sorted(contract.allowed)[0]
    why = refuse_request(
        Route(processor="vendor", operations=(approved,),
              configuration_known=False), contract)
    assert any("not established" in one for one in why)


def test_a_forbidden_field_nested_in_a_response_is_found():
    """BK-88-AC4'S MUTATION: *inject a prohibited nested response field into
    the real configured path.* A top-level check finds the top level."""
    from nm.domain.media_policy import refuse_response

    allow = frozenset({"transcript", "segments", "text", "start"})
    clean = refuse_response(
        {"transcript": "words", "segments": [{"text": "a", "start": 0}]}, allow)
    assert clean.clean, clean.reasons

    nested = refuse_response(
        {"transcript": "words",
         "segments": [{"text": "a", "speaker_embedding": [0.1, 0.2]}]}, allow)
    assert not nested.clean
    assert nested.rejected_paths == ("segments[0].speaker_embedding",)
    assert nested.accepted == {}


def test_the_rejected_value_is_never_carried_in_the_refusal():
    """A message saying *rejected `speaker_emotion` = "distressed"* has
    persisted the exact inference the rejection existed to prevent."""
    from nm.domain.media_policy import refuse_response

    verdict = refuse_response(
        {"transcript": "words", "speaker_emotion": "distressed"},
        frozenset({"transcript"}))
    assert not verdict.clean
    assert "distressed" not in " ".join(verdict.reasons + verdict.rejected_paths)


# ============ 11. what the projection says about where this ran ============

def test_the_projection_says_it_describes_a_working_tree():
    shown = projection(_inventory())
    assert shown["operated"] is False
    assert "not a deployed environment" in shown["said"]
    assert "no penetration test has been performed" in shown["said"]


def test_the_projection_names_every_population_nobody_enumerated():
    shown = projection(_inventory(missing=("emergency_roles", "lockfiles")))
    assert set(shown["unassessed"]) == {"emergency_roles", "lockfiles"}
    assert shown["populations"]["emergency_roles"].startswith("not assessed")
    assert shown["populations"]["artifacts"] == "artifacts-row"
