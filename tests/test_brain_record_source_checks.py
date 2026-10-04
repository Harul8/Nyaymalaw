"""Selected passage role and support cannot be overridden by overall acceptance."""
import json

import pytest

from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material_verification import verify_material_grounding
from tests.brain_reader_fixture import classified_verifier, scripted_source_treatments
from tests.test_brain_dispute_verification import Model as DisputeModel
from tests.test_brain_dispute_verification import _candidate, _verdict
from tests.test_brain_material_verification import Model as MaterialModel
from tests.test_brain_material_verification import detail, verdict

verify_disputes = classified_verifier(verify_disputes)
verify_material_grounding = classified_verifier(verify_material_grounding)


def source_check(source_id, *, content=True, supports=True):
    return {"source_id": source_id, "supplies_account_content": content,
            "supports_proposal": supports, "reason": "This source's attributed use is checked."}


@pytest.mark.parametrize("kind", ["dispute", "detail"])
@pytest.mark.parametrize("failure,expected", [
    ("missing", "source_checks must cover exactly selected source_ids"),
    ("duplicate", "source_checks repeats a source_id"),
    ("unselected", "source_checks must cover exactly selected source_ids"),
    ("foreign", "source_checks[0].source_id' is outside the permitted vocabulary"),
    ("empty_reason", "source_checks for L1: reason is empty"),
    ("work_only", "review authority or context alone is insufficient"),
    ("work_claims_support", "supports_proposal=true conflicts with independent "
     "content_role=work_instruction"),
    ("unsupported_content", "review authority or context alone is insufficient"),
    ("mixed_without_content", "review authority or context alone is insufficient"),
])
def test_each_selected_source_needs_exact_owned_role_support_check(kind, failure, expected):
    current = "Review the saved interpretation."
    peer_text = "Another record was withheld."
    latest = f"{current} {peer_text}"
    earlier = (Message("old", "advocate", "A related circumstance is reported."),)
    if kind == "dispute":
        ids = ("C1", "C2")
        first = _candidate(current, "Unsupported interpretation", earlier=earlier[0].text)
        peer = _candidate(peer_text, "Another record withheld")
        wrong = _verdict(ids[0], accept=True)
        good = _verdict(ids[1], accept=True)
        rejected = _verdict(ids[0], accept=False)
        model_type = DisputeModel
    else:
        ids = ("D1", "D2")
        first = detail(current, "Unsupported interpretation", earlier=earlier[0].text)
        peer = detail(peer_text, "Another record was withheld.")
        wrong, good, rejected = verdict(ids[0]), verdict(ids[1]), verdict(ids[0], accept=False)
        model_type = MaterialModel
    checks = [source_check("L1")]
    roles = {}
    if failure == "missing":
        checks = []
    elif failure == "duplicate":
        checks *= 2
    elif failure == "unselected":
        checks.append(source_check("P1S1"))
    elif failure == "foreign":
        checks[0]["source_id"] = "PRIVATE_PASSAGE"
    elif failure == "empty_reason":
        checks[0]["reason"] = "  "
    elif failure == "work_only":
        roles["L1"] = "work_instruction"
        checks[0].update(supplies_account_content=False,
                         supports_proposal=False)
    elif failure == "work_claims_support":
        roles["L1"] = "work_instruction"
    elif failure == "unsupported_content":
        checks[0]["supports_proposal"] = False
    else:
        roles["L1"] = "mixed"
        checks[0].update(supplies_account_content=False,
                         supports_proposal=False)
    wrong["account_check"] = {
        "content_role": "reported_matter_account", "supported": True,
        "introduces_legal_analysis": False, "source_ids": ["L1"], "source_checks": checks,
        "reason": "Overall acceptance is deliberately inconsistent with its source checks."}
    model = model_type([{"verdicts": [wrong, good]}, {"verdicts": [rejected]}])
    treatments = scripted_source_treatments(earlier, latest, roles=roles)
    if kind == "dispute":
        retained = verify_disputes(model, candidates=(first, peer), earlier=earlier, latest=latest,
                                   active_disputes=(), source_treatments=treatments)
    else:
        retained = verify_material_grounding(
            model, candidates=(first, peer), earlier=earlier, latest=latest,
            opening=OpeningCandidate(False, "", ""), source_treatments=treatments).details
    assert retained == (peer,) and len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in correction["candidates"]] == [ids[0]]
    assert correction["retained_candidate_context"][0]["candidate_id"] == ids[1]
    assert expected in correction["validation_issue"]
    assert "PRIVATE_PASSAGE" not in correction["validation_issue"]


def test_opening_cannot_use_review_authority_as_its_account_evidence():
    latest = "Review the pending work."
    wrong = verdict("O1")
    wrong["account_check"] = {
        "content_role": "reported_matter_account", "supported": True,
        "introduces_legal_analysis": False, "source_ids": ["L1"],
        "source_checks": [source_check(
            "L1", content=False, supports=False)],
        "reason": "The overall opening decision is deliberately inconsistent."}
    model = MaterialModel([{"verdicts": [wrong]}, {"verdicts": [verdict("O1", accept=False)]}])
    result = verify_material_grounding(
        model, candidates=(),
        opening=OpeningCandidate(True, "Reported dispute", "A dispute exists."),
        earlier=(), latest=latest, source_treatments=scripted_source_treatments(
            (), latest, roles={"L1": "work_instruction"}))
    assert not result.opening_supported and result.details == () and len(model.calls) == 2
    assert "review authority or context alone is insufficient" in json.loads(
        model.calls[1][0].user)["validation_issue"]
