"""THE RELEASE GATE FAILS CLOSED, AND IT CANNOT APPROVE ITSELF. P41.
BK-42-AC5, BK-42-AC7, BK-42-AC9, J-8-AC1.

WHAT THESE DEFEND
-------------------
P41's own declared expected failure: *no aggregate green score overrides a
critical security or legal failure.* A gate that weighed a 98% pass rate
against one critical row would release this product over a legal defect, and
the arithmetic would look responsible while it did.

And the one that comes before it: a gate that could sign its own approval.
There is no function in `nm/domain/release.py` that creates an `Approval`
without being handed one, and this suite asserts that from the source rather
than from a promise.

WHAT THE ANSWER IS FOR THIS BUILD
-----------------------------------
ENGINEERING COMPLETE, RELEASE WITHHELD. Every one of the five required
signatures is absent, every production measure is absent, and the environment
is a working tree. The final test in this file asserts exactly that, because
the honest verdict is a result to hold onto rather than a state to escape.
"""
from __future__ import annotations

import inspect

import pytest

from nm.domain.release import (
    IDENTITIES,
    REQUIRED_APPROVALS,
    REQUIRED_PORTFOLIOS,
    Approval,
    Manifest,
    Portfolio,
    Row,
    RunState,
    Severity,
    Submission,
    blank_manifest_fields,
    projection,
    refuse_release,
    verdict,
)

pytestmark = pytest.mark.class_a

TODAY = "2026-09-14"
DEPLOYED = "ap-south-1-prod"


def _manifest(**kw) -> Manifest:
    base = {name: f"{name}-value" for name in IDENTITIES}
    base["environment"] = DEPLOYED
    base["jurisdiction"] = "in"
    base.update(kw)
    return Manifest(**base)


def _portfolios(manifest, **overrides) -> tuple[Portfolio, ...]:
    out = []
    for name in REQUIRED_PORTFOLIOS:
        out.append(overrides.get(name, Portfolio(
            portfolio_id=name, state=RunState.PASSED,
            covers_manifest=manifest.identity,
            rows=(Row(row_id=f"{name}-1", state=RunState.PASSED,
                      severity=Severity.CRITICAL),))))
    return tuple(out)


def _approvals(manifest, **kw) -> tuple[Approval, ...]:
    common = dict(covers_manifest=manifest.identity, signed_on=TODAY,
                  valid_until="2026-12-31", scope="the enabled pilot scope")
    common.update(kw)
    return tuple(Approval(role=role, approver_id=f"{role}-person", **common)
                 for role in REQUIRED_APPROVALS)


def _submission(manifest=None, **kw) -> Submission:
    manifest = manifest or _manifest()
    base = dict(
        manifest=manifest,
        portfolios=_portfolios(manifest),
        approvals=_approvals(manifest),
        production_measures={"restore": "PASS", "iam": "PASS",
                             "incident": "PASS"},
        enabled_scope=("telangana-civil",),
        approved_scope=("telangana-civil",))
    base.update(kw)
    return Submission(**base)


# ============ 1. the gate can pass, so its refusals mean something =========

def test_a_fully_evidenced_and_signed_release_is_permitted():
    """THE POSITIVE CONTROL, and this file needs it more than most: a gate
    that refused everything would satisfy every other test here and would
    never let this product ship at all."""
    assert refuse_release(_submission(), on=TODAY) == ()
    assert verdict(_submission(), on=TODAY) == "RELEASE PERMITTED BY THIS GATE"


# ============ 2. nineteen identities, frozen together ======================

def test_the_nineteen_identities_are_declared_and_distinct():
    assert len(IDENTITIES) == 19 == len(set(IDENTITIES))
    for needed in ("commit", "tree_fingerprint", "schema_version",
                   "migration_head", "policy_version", "corpus_generation",
                   "model_provider", "model_id", "prompt_digest",
                   "enabled_scope_digest", "jurisdiction"):
        assert needed in IDENTITIES


def test_a_manifest_and_the_identity_list_cannot_drift_apart():
    """The list and the type are checked against each other at construction,
    so adding a field to one and forgetting the other fails loudly rather than
    freezing eighteen of nineteen."""
    declared = set(Manifest.__dataclass_fields__) - {"version"}
    assert declared == set(IDENTITIES)


@pytest.mark.parametrize("moved", [
    "commit", "tree_fingerprint", "schema_version", "policy_version",
    "corpus_generation", "model_id", "prompt_digest", "enabled_scope_digest"])
def test_changing_any_identity_makes_a_different_release(moved):
    """A release is not a commit. Every one of these can move while the commit
    stands still, and each makes a build that inherits nothing."""
    before = _manifest()
    after = _manifest(**{moved: "something-else"})
    assert before.identity != after.identity


def test_no_identity_may_be_left_unestablished():
    for name in IDENTITIES:
        with pytest.raises(ValueError):
            _manifest(**{name: "   "})


def test_blank_manifest_fields_names_what_is_missing():
    proposed = {name: "x" for name in IDENTITIES}
    proposed["prompt_digest"] = ""
    proposed["corpus_generation"] = "   "
    assert set(blank_manifest_fields(proposed)) == {
        "prompt_digest", "corpus_generation"}


def test_india_is_the_only_supported_operating_jurisdiction():
    """A manifest is where a second one would first appear."""
    assert _manifest(jurisdiction="India").jurisdiction == "India"
    for elsewhere in ("kerala", "uk", "us", "global"):
        with pytest.raises(ValueError) as caught:
            _manifest(jurisdiction=elsewhere)
        assert "Telangana and the Union of India" in str(caught.value)


# ====== 3. NO AGGREGATE SCORE OVERRIDES A CRITICAL FAILURE ================

def test_one_critical_failure_refuses_at_any_pass_rate():
    """P41'S OWN DECLARED EXPECTED FAILURE. The arithmetic looks responsible
    right up until it releases over a legal defect."""
    manifest = _manifest()
    rows = tuple(Row(row_id=f"legal-{n}", state=RunState.PASSED,
                     severity=Severity.CRITICAL) for n in range(99))
    rows += (Row(row_id="legal-100", state=RunState.FAILED,
                 severity=Severity.CRITICAL,
                 note="an unsupported jurisdiction was advised on"),)
    loaded = Portfolio(portfolio_id="legal_quality", state=RunState.PASSED,
                       rows=rows, covers_manifest=manifest.identity)
    assert loaded.pass_rate == 0.99

    why = refuse_release(
        _submission(manifest,
                   portfolios=_portfolios(manifest, legal_quality=loaded)),
        on=TODAY)
    assert any("critical failure" in one and "legal-100" in one for one in why)
    assert any("no aggregate score overrides" in one for one in why)
    assert any("99%" in one for one in why)


def test_a_failure_nobody_triaged_refuses_exactly_like_a_critical_one():
    """THE THIRD STATE, AND IT FAILS CLOSED. A row nobody classified is not a
    minor row: the honest answer about a failure nobody has looked at, at a
    release gate, is no. Defaulting to MINOR would let an untriaged legal
    failure be averaged into a 98% pass rate."""
    manifest = _manifest()
    untriaged = Portfolio(
        portfolio_id="legal_quality", state=RunState.PASSED,
        covers_manifest=manifest.identity,
        rows=(Row(row_id="legal-7", state=RunState.FAILED),))
    assert untriaged.rows[0].severity is Severity.NOT_CLASSIFIED
    assert Severity.not_established() is Severity.NOT_CLASSIFIED
    why = refuse_release(
        _submission(manifest,
                   portfolios=_portfolios(manifest, legal_quality=untriaged)),
        on=TODAY)
    assert any("not_classified failure" in one and "legal-7" in one
               for one in why)


def test_an_untriaged_row_that_passed_is_not_a_failure():
    """THE NEGATIVE CONTROL on that rule. Most rows are never triaged because
    most rows pass, and refusing on those would refuse every release."""
    manifest = _manifest()
    ordinary = Portfolio(
        portfolio_id="legal_quality", state=RunState.PASSED,
        covers_manifest=manifest.identity,
        rows=(Row(row_id="legal-8", state=RunState.PASSED),))
    assert ordinary.critical_failures == ()
    assert refuse_release(
        _submission(manifest,
                   portfolios=_portfolios(manifest, legal_quality=ordinary)),
        on=TODAY) == ()


def test_the_pass_rate_is_reported_and_never_consulted():
    """It is shown to a reviewer and it is not an input to the decision."""
    source = inspect.getsource(refuse_release)
    assert "pass_rate" in source, "the rate should be reported in the reason"
    for traded in ("pass_rate >", "pass_rate <", "pass_rate >=", "pass_rate <=",
                   "if portfolio.pass_rate", "pass_rate ==",
                   "and portfolio.pass_rate", "or portfolio.pass_rate"):
        assert traded not in source, traded


def test_a_minor_failure_does_not_refuse_by_itself():
    """THE NEGATIVE CONTROL on severity. If everything refused, `CRITICAL`
    would be decoration and the distinction would carry nothing."""
    manifest = _manifest()
    scuffed = Portfolio(
        portfolio_id="accessibility", state=RunState.PASSED,
        covers_manifest=manifest.identity,
        rows=(Row(row_id="a11y-1", state=RunState.FAILED,
                  severity=Severity.MINOR,
                  note="a label is terse at 1280px"),))
    assert refuse_release(
        _submission(manifest,
                   portfolios=_portfolios(manifest, accessibility=scuffed)),
        on=TODAY) == ()


# ============ 4. a run that did not finish is not a run that passed ========

def test_an_incomplete_portfolio_refuses():
    """A run that crashed at phase 3 leaves green rows behind it."""
    manifest = _manifest()
    stopped = Portfolio(portfolio_id="supported_journey",
                        state=RunState.INCOMPLETE,
                        covers_manifest=manifest.identity,
                        rows=(Row(row_id="j-1", state=RunState.PASSED),))
    why = refuse_release(
        _submission(manifest,
                   portfolios=_portfolios(manifest,
                                          supported_journey=stopped)),
        on=TODAY)
    assert any("did not finish" in one for one in why)


def test_a_portfolio_nobody_ran_refuses_by_name():
    manifest = _manifest()
    kept = tuple(p for p in _portfolios(manifest)
                 if p.portfolio_id != "load_and_degradation")
    why = refuse_release(_submission(manifest, portfolios=kept), on=TODAY)
    assert any("'load_and_degradation' portfolio was not run" in one
               for one in why)
    assert RunState.not_established() is RunState.NOT_RUN


def test_a_portfolio_run_against_another_build_does_not_cover_this_one():
    manifest = _manifest()
    elsewhere = Portfolio(portfolio_id="accessibility", state=RunState.PASSED,
                          covers_manifest="0123456789abcdef",
                          rows=(Row(row_id="a-1", state=RunState.PASSED),))
    why = refuse_release(
        _submission(manifest,
                   portfolios=_portfolios(manifest, accessibility=elsewhere)),
        on=TODAY)
    assert any("0123456789abcdef" in one and manifest.identity in one
               for one in why)


def test_a_portfolio_bound_to_no_manifest_is_a_result_about_some_build():
    manifest = _manifest()
    floating = Portfolio(portfolio_id="legal_quality", state=RunState.PASSED,
                         rows=(Row(row_id="l-1", state=RunState.PASSED),))
    why = refuse_release(
        _submission(manifest,
                   portfolios=_portfolios(manifest, legal_quality=floating)),
        on=TODAY)
    assert any("names no manifest" in one for one in why)


# ============ 5. the gate cannot approve itself ============================

def test_nothing_in_this_module_creates_an_approval():
    """*Do not create a release approval record on behalf of the user.* A gate
    that could sign its own release is the check that cannot fail, holding the
    last decision anybody makes about this product."""
    from nm.domain import release

    for name in ("refuse_release", "verdict", "projection"):
        source = inspect.getsource(getattr(release, name))
        assert "Approval(" not in source, name
    module = inspect.getsource(release)
    body = module.split('"""', 2)[-1]
    assert body.count("Approval(") == 0


def test_every_missing_signature_is_named_by_role():
    """A release manager told "approvals missing" will chase the wrong one."""
    why = refuse_release(_submission(approvals=()), on=TODAY)
    for role in REQUIRED_APPROVALS:
        assert any(f"no current {role!r} approval" in one for one in why), role


def test_an_approval_for_another_release_does_not_travel():
    """BK-42-AC9'S MUTATION: *release a new jurisdiction or professional
    operation using an unrelated or expired legal review.*"""
    manifest = _manifest()
    stale = _approvals(manifest, covers_manifest="a-previous-release")
    why = refuse_release(_submission(manifest, approvals=stale), on=TODAY)
    assert any("cannot inherit approval from another population" in one
               for one in why)


def test_an_expired_approval_does_not_carry():
    manifest = _manifest()
    lapsed = _approvals(manifest, valid_until="2026-09-13")
    why = refuse_release(_submission(manifest, approvals=lapsed), on=TODAY)
    assert any("expired on 2026-09-13" in one for one in why)


def test_an_unreadable_expiry_has_expired():
    """An approval whose validity cannot be read is not one that lasts
    forever, which is what a permissive parse would make it."""
    approval = Approval(role="qualified_counsel", approver_id="c-1",
                        covers_manifest="x", signed_on=TODAY,
                        valid_until="whenever", scope="s")
    assert approval.expired_on(TODAY) is True


def test_scope_nobody_approved_cannot_be_enabled():
    why = refuse_release(
        _submission(enabled_scope=("telangana-civil", "kerala-criminal"),
                   approved_scope=("telangana-civil",)),
        on=TODAY)
    assert any("kerala-criminal" in one for one in why)
    assert any("does not inherit approval from another population" in one
               for one in why)


# ============ 6. production measures and where this actually runs ==========

def test_an_outstanding_production_measure_refuses():
    why = refuse_release(
        _submission(production_measures={"restore": "PASS",
                                        "iam": "NOT_RUN"}),
        on=TODAY)
    assert any("not PASS: iam" in one for one in why)


def test_no_production_measure_at_all_is_an_unrun_measurement():
    """AN EMPTY SET OF MEASUREMENTS IS NOT A CLEAN ONE. This is the absent-
    input defect at the last gate before real client matters."""
    why = refuse_release(_submission(production_measures={}), on=TODAY)
    assert any("empty set of measurements is an unrun measurement" in one
               for one in why)


def test_a_working_tree_is_not_a_deployment():
    """*Local synthetic success must never be presented as target proof.*"""
    for local in ("working_tree", "local", "local_rehearsal", "synthetic"):
        manifest = _manifest(environment=local)
        assert manifest.is_a_deployment is False
        why = refuse_release(_submission(manifest), on=TODAY)
        assert any("is not a deployment" in one for one in why), local


# ============ 7. what this build's answer actually is ======================

def _this_build() -> Submission:
    """The honest candidate for the tree these tests run in."""
    manifest = _manifest(environment="working_tree")
    return Submission(manifest=manifest, portfolios=(), approvals=(),
                     production_measures={}, enabled_scope=(),
                     approved_scope=())


def test_this_build_is_engineering_complete_and_release_withheld():
    """THE RESULT THIS PACKET WAS BUILT TO REACH HONESTLY.

    Not a failure of the gate. The gate is finished and it is telling the
    truth: no signature exists, no production measure exists, and this is a
    working tree. An unsupported production-ready claim would be the defect.
    """
    said = verdict(_this_build(), on=TODAY)
    assert said.startswith("ENGINEERING COMPLETE, RELEASE WITHHELD")
    why = refuse_release(_this_build(), on=TODAY)
    assert len(why) >= 12, why


def test_the_projection_says_the_gate_cannot_approve_anything():
    shown = projection(_this_build(), on=TODAY)
    assert shown["approvals_held"] == []
    assert set(shown["approvals_missing"]) == set(REQUIRED_APPROVALS)
    assert shown["is_a_deployment"] is False
    assert "is not a release approval" in shown["said"]
    assert shown["verdict"].startswith("ENGINEERING COMPLETE")
