"""POPULARITY IS NOT RELEVANCE, AND HAVING IT IS NOT APPLYING IT. BK-24-AC1. P44.

WHAT THESE DEFEND
-------------------
BK-24-AC1's negative control, in its own words: *offer equally relevant old and
new decisions with zero citations on the new one* -> *the new decision is not
excluded solely by citation age and the selection report names the governing
rule.* That half was already built and already passes; the tests below keep it
passing while four rules are added around it, and each of the four closes a way
the mechanism could still have said something it had not established.

    THE COURT WAS NOT A RULE. `issuing_body` was carried on every candidate and
    used only to compose a source id, so an approval to take High Court
    judgments admitted anything filed anywhere in the jurisdiction.

    THE RIGHT TO ACQUIRE WAS NOT A RULE. Rights were recorded on the STAGED
    bytes -- honest about what had already been fetched, and silent on whether
    it should have been.

    SIX CLAIMS WERE THREE. Discovered, acquired, quarantined, verified,
    published and applicable are six different sentences, and the last of them
    is a legal judgement about a matter that no acquisition can reach.

    THE SUBMISSION TO P20 LIVED IN A TEST HELPER. A correct module with no path
    from the product to it, which is the shape CLAUDE.md section 8 records
    every externally-found defect as having.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from nm.knowledge.acquisition import (
    ACQUISITION_ESTABLISHES,
    POLICY_VERSION,
    AcquiredArtifact,
    AcquisitionRefused,
    AcquisitionRoute,
    AcquisitionScope,
    JudgmentCandidate,
    SelectionState,
    Stage,
    select_candidates,
    stage_acquisition,
    submit_for_publication,
)
from nm.knowledge.source_registry import RightsState

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
COURT = "High Court for the State of Telangana"
OTHER_COURT = "District Court, Ranga Reddy"


def _scope(**kw) -> AcquisitionScope:
    base = dict(
        route=AcquisitionRoute.API,
        source="synthetic official reporter",
        jurisdiction="Telangana",
        document_types=("judgment",),
        from_date=date(2019, 1, 1),
        to_date=date(2026, 12, 31),
        discovery_budget=20,
        selection_budget=20,
        authorization_id="auth-synthetic-1",
        issuing_bodies=(COURT,),
        source_rights=RightsState.PERMITTED,
    )
    base.update(kw)
    return AcquisitionScope(**base)


def _candidate(cid: str, **kw) -> JudgmentCandidate:
    base = dict(
        candidate_id=cid,
        source="synthetic official reporter",
        jurisdiction="Telangana",
        issuing_body=COURT,
        document_type="judgment",
        source_url=f"https://synthetic.invalid/{cid}",
        source_date=date(2026, 3, 1),
        citation_count=0,
    )
    base.update(kw)
    return JudgmentCandidate(**base)


def _decision(report, cid: str):
    return next(d for d in report.decisions if d.candidate_id == cid)


# ============ 1. the criterion itself -- recency, never popularity ==========

def test_a_recent_uncited_decision_is_selected():
    """THE CRITERION'S POSITIVE CASE. A decision three months old with nobody
    citing it yet is the ordinary state of recent law, not a signal about it."""
    report = select_candidates(_scope(), (
        _candidate("new-uncited", source_date=date(2026, 6, 1),
                   citation_count=0),))
    got = _decision(report, "new-uncited")
    assert got.state is SelectionState.SELECTED, got.reasons


def test_the_new_decision_outranks_the_old_one_however_cited():
    """BK-24-AC1's NEGATIVE CONTROL: *offer equally relevant old and new
    decisions with zero citations on the new one*.

    Recency is the outer cohort and citation count orders only inside a year,
    so a heavily cited 2019 decision cannot displace an uncited 2026 one.
    """
    report = select_candidates(_scope(selection_budget=1), (
        _candidate("old-famous", source_date=date(2019, 4, 1),
                   citation_count=900),
        _candidate("new-uncited", source_date=date(2026, 6, 1),
                   citation_count=0),
    ))
    assert _decision(report, "new-uncited").state is SelectionState.SELECTED
    assert _decision(report, "old-famous").state is SelectionState.REJECTED
    # AND THE REPORT NAMES THE GOVERNING RULE, which is the second half of the
    # criterion: an advocate or an operator can read why.
    assert any("selection budget" in r
               for r in _decision(report, "old-famous").reasons)
    assert any("citation count" in r and "same source year" in r
               for r in _decision(report, "new-uncited").reasons)


def test_absent_citation_metadata_is_not_read_as_zero():
    """A source that does not publish citation counts is not a source of
    uncited decisions, and treating the two the same is the wrong-index shape
    at the level of a whole reporter."""
    report = select_candidates(_scope(), (
        _candidate("unknown-citations", citation_count=None),))
    got = _decision(report, "unknown-citations")
    assert got.state is SelectionState.SELECTED
    assert any("citation metadata is unavailable" in r for r in got.reasons)


def test_an_ineligible_decision_is_rejected_however_cited():
    """Popularity cannot make a document eligible. The mutation is the same
    one in the other direction: a famous case outside the scope."""
    report = select_candidates(_scope(), (
        _candidate("famous-elsewhere", jurisdiction="Kerala",
                   citation_count=5000),))
    got = _decision(report, "famous-elsewhere")
    assert got.state is SelectionState.REJECTED
    assert any("jurisdiction" in r for r in got.reasons)


# ================= 2. the court, which was not a rule at all ================

def test_a_judgment_from_an_unauthorised_court_is_rejected():
    """A JURISDICTION IS NOT A COURT. An approval to take High Court judgments
    is not an approval to take everything filed anywhere in Telangana."""
    report = select_candidates(_scope(), (
        _candidate("district", issuing_body=OTHER_COURT),))
    got = _decision(report, "district")
    assert got.state is SelectionState.REJECTED
    assert any("issuing court is outside the authorised scope" in r
               for r in got.reasons)


def test_the_authorised_court_is_admitted():
    """THE POSITIVE CONTROL on the same rule."""
    report = select_candidates(_scope(issuing_bodies=(COURT, OTHER_COURT)), (
        _candidate("district", issuing_body=OTHER_COURT),))
    assert _decision(report, "district").state is SelectionState.SELECTED


def test_a_scope_that_names_no_court_cannot_be_constructed():
    """Empty is refused rather than defaulted to "any". A blank field reading
    as "all of them" is the absent-input-as-success shape at the widest
    possible scope, and it is the one place it would be least visible."""
    with pytest.raises(ValueError, match="names the courts it covers"):
        _scope(issuing_bodies=())
    with pytest.raises(ValueError, match="names the courts it covers"):
        _scope(issuing_bodies=("   ",))


# ============= 3. the right to acquire, which is not a default ==============

def test_a_scope_that_did_not_review_the_right_cannot_be_constructed():
    """UNKNOWN IS NOT PERMISSION. An authorisation id is a REFERENCE to a
    decision; recording one is not the same as somebody having made it, and a
    default that read the reference as the decision is what fetches another
    publisher's copyright."""
    with pytest.raises(ValueError, match="reviewed right"):
        _scope(source_rights=RightsState.UNKNOWN)


def test_a_source_reviewed_as_restricted_refuses_every_candidate():
    report = select_candidates(_scope(source_rights=RightsState.RESTRICTED), (
        _candidate("anything"),))
    got = _decision(report, "anything")
    assert got.state is SelectionState.REJECTED
    assert any("restricted" in r for r in got.reasons)


def test_one_sealed_judgment_is_refused_out_of_a_permitted_source():
    """A DOCUMENT MAY NARROW THE SOURCE'S RIGHT. A sealed or in-camera
    judgment is restricted whatever the source-level review said."""
    report = select_candidates(_scope(), (
        _candidate("sealed", rights=RightsState.RESTRICTED),
        _candidate("ordinary"),
    ))
    assert _decision(report, "sealed").state is SelectionState.REJECTED
    assert _decision(report, "ordinary").state is SelectionState.SELECTED


def test_a_document_cannot_widen_a_restricted_source():
    """AND IT ONLY NARROWS. A candidate declaring itself permitted out of a
    source nobody was allowed to take from is the whole reason this is a
    function rather than a fallback expression."""
    report = select_candidates(_scope(source_rights=RightsState.RESTRICTED), (
        _candidate("optimistic", rights=RightsState.PERMITTED),))
    assert _decision(report, "optimistic").state is SelectionState.REJECTED


def test_the_effective_right_is_decided_in_one_place():
    from nm.knowledge.acquisition import effective_right

    permitted = _scope()
    restricted = _scope(source_rights=RightsState.RESTRICTED)
    assert effective_right(permitted, _candidate("a")) is RightsState.PERMITTED
    assert effective_right(
        permitted, _candidate("a", rights=RightsState.RESTRICTED)
    ) is RightsState.RESTRICTED
    assert effective_right(
        restricted, _candidate("a", rights=RightsState.PERMITTED)
    ) is RightsState.RESTRICTED


def test_a_restricted_document_does_not_consume_the_selection_budget():
    """A candidate nobody may fetch must not crowd out one they may -- the
    budget is for work that can actually be done."""
    report = select_candidates(_scope(selection_budget=1), (
        _candidate("sealed", rights=RightsState.RESTRICTED),
        _candidate("fine"),
    ))
    assert _decision(report, "fine").state is SelectionState.SELECTED


# ================ 4. six stages, and the four it never proves ===============

def test_acquisition_never_reaches_published_or_applicable():
    assert Stage.QUARANTINED.reached_by_acquisition is True
    assert Stage.VERIFIED.reached_by_acquisition is True
    assert Stage.PUBLISHED.reached_by_acquisition is False
    assert Stage.APPLICABLE.reached_by_acquisition is False
    assert Stage.not_established() is Stage.NOT_ASSESSED


def test_the_six_stages_are_six_and_are_distinct():
    assert {s.value for s in Stage} == {
        "discovered", "acquired", "quarantined", "verified", "published",
        "applicable", "not_assessed"}


def test_no_function_in_the_module_returns_applicable():
    """STRUCTURAL, over the compiled module rather than its prose. Three
    checks in this build have matched a docstring and passed for it."""
    import nm.knowledge.acquisition as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    body = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    assert "Stage.APPLICABLE" not in body.split('"""')[0] + "".join(
        body.split('"""')[2::2])


def test_the_disclosure_names_all_four_things_it_does_not_establish():
    for absent in ("current", "correct", "treated", "complete"):
        assert absent in ACQUISITION_ESTABLISHES, absent


# ========================= 5. the receipt and P20 ===========================

def _run(tmp_path: Path, *, payload: bytes = b"synthetic judgment text",
         cid: str = "new-uncited") -> Path:
    scope = _scope(selection_budget=1)
    selection = select_candidates(scope, (_candidate(cid),))
    return stage_acquisition(
        tmp_path / "runs", run_id="run-1", scope=scope, selection=selection,
        artifacts=(AcquiredArtifact(cid, f"src-{cid}",
                                    f"https://synthetic.invalid/{cid}",
                                    payload),),
        observed_at=NOW)


def test_the_receipt_carries_the_stage_and_the_disclosure(tmp_path):
    run = _run(tmp_path)
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["stage"] == Stage.QUARANTINED.value
    assert receipt["establishes"] == ACQUISITION_ESTABLISHES
    assert receipt["published"] is False
    assert receipt["selection_policy"]["version"] == POLICY_VERSION


def test_a_reconciled_run_can_be_offered_to_publication(tmp_path):
    """THE PATH THAT ONLY EXISTED IN A TEST HELPER, now in the product."""
    run = _run(tmp_path)
    (offer,) = submit_for_publication(run)
    assert offer.candidate_id == "new-uncited"
    assert offer.stage is Stage.QUARANTINED
    assert offer.establishes == ACQUISITION_ESTABLISHES
    assert (Path(offer.acquisition_run) / offer.relative_path).exists()


def test_the_submission_is_not_a_publication(tmp_path):
    """Nothing in this module activates a snapshot. Acquisition that could
    publish is acquisition that will."""
    import nm.knowledge.acquisition as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "publish_corpus(" not in source
    assert "from nm.knowledge.manifest import" not in source


def test_a_run_that_did_not_reconcile_offers_nothing(tmp_path):
    """NOT A PARTIAL ANSWER. A receipt whose staged bytes and recorded digests
    disagree is a run nobody can say what is in, and offering its readable
    half would publish exactly the members whose absence was the problem."""
    run = _run(tmp_path)
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf-8"))
    staged = run / receipt["artifacts"][0]["file"]
    staged.write_bytes(b"something else entirely")
    with pytest.raises(AcquisitionRefused, match="cannot be offered"):
        submit_for_publication(run)


def test_a_run_already_published_is_not_offered_twice(tmp_path):
    """AND THE REFUSAL COMES FROM ONE OWNER. `reconcile_acquisition` already
    refuses a receipt that does not declare an unpublished quarantine, so
    `submit_for_publication` does not check it a second time -- the day two
    checks of one rule disagreed, one of them would be the permissive one."""
    run = _run(tmp_path)
    path = run / "receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["published"] = True
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(AcquisitionRefused,
                       match="does not declare an unpublished quarantine"):
        submit_for_publication(run)


def test_the_wrong_run_is_refused_rather_than_read(tmp_path):
    run = _run(tmp_path)
    with pytest.raises(AcquisitionRefused, match="was expected"):
        submit_for_publication(run, expected_run_id="run-2")


def test_an_empty_submission_is_refused_rather_than_returned(tmp_path):
    """S1: an absent input must never read as success. An empty tuple from a
    submission function reads as "nothing needed publishing"."""
    scope = _scope(selection_budget=1)
    selection = select_candidates(scope, (
        _candidate("sealed", rights=RightsState.RESTRICTED),))
    run = stage_acquisition(
        tmp_path / "runs", run_id="run-empty", scope=scope,
        selection=selection, artifacts=(), observed_at=NOW)
    with pytest.raises(AcquisitionRefused, match="staged nothing"):
        submit_for_publication(run)
