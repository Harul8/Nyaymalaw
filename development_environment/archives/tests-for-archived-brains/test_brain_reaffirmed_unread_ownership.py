"""Recovery eligibility checks preserve owned units without certifying meaning."""
from dataclasses import asdict

import pytest

from nm.brain.conversation import OpeningCandidate
from nm.brain.turn import _reaffirmed_unread_candidates
from nm.shared.model_port import SchemaViolation
from tests.test_brain_material_coverage import detail

WORDS = "The appointed reviewer received the signed record."


def run(rows, *, opening=None):
    return _reaffirmed_unread_candidates(
        rows, (detail(WORDS),), ("L2",), {"L1": WORDS, "L2": "Record this account."},
        {}, prefix="D", opening=opening)


def unit():
    return {"candidate_id": "D1", "verdict": "unassessed",
            "admission_issue": "review_unavailable", "proposal": asdict(detail(WORDS))}


def test_unread_eligibility_preserves_harmless_review_metadata_and_rejected_peers():
    row = {**unit(), "reason": "This unit needs independent examination."}
    assert run([row, {"verdict": "reject"}]) == ("D1",)
    assert row["proposal"] == asdict(detail(WORDS))


@pytest.mark.parametrize("fault", (None, "owner", "account"))
def test_recovery_cannot_select_an_unreadable_foreign_or_altered_unit(fault):
    row = unit()
    if fault == "owner":
        row["candidate_id"] = "D2"
    elif fault == "account":
        row["proposal"]["statement"] = "A different person retained a different record."
    else:
        row = None
    with pytest.raises(SchemaViolation):
        run([row])


@pytest.mark.parametrize("projection", ("verifier", "owned_hold"))
def test_owned_opening_projections_share_the_same_recovery_eligibility(projection):
    opening = OpeningCandidate(True, "Reported document receipt", WORDS)
    party, subject = opening.title_parts()
    proposal = ({"type": "opening", "title": opening.title, "party_name": party,
                 "subject": subject, "summary": opening.summary}
                if projection == "verifier" else asdict(opening))
    row = {**unit(), "candidate_id": "O1", "proposal": proposal}
    assert run([row], opening=opening) == ("O1",)
