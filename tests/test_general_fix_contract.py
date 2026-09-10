"""BK-90: preserve the general-fix method, not certify future product fixes.

These are Class-A structural controls over actual registry/card declarations.
Their mutations exercise the real build-rule validator. They do not establish
causality, semantic transfer, legal applicability or absence of regressions;
those remain fix-specific executed evidence and independent review obligations.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from tools import backlog

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]

# Exact contract identity, not fuzzy legal/semantic classification. The first
# 77 ids predate this amendment; four new stage obligations extend that set.
CONTRACTS = {
    "BG-078": (
        "before", "START_A_CHANGE.md", "A causal fix contract precedes implementation."
    ),
    "BG-079": (
        "build", "BUILD_A_CHANGE.md", "Generalise the mechanism, not distinct legal rules."
    ),
    "BG-080": (
        "prove", "TEST_A_CHANGE.md", "A fixed incident is not transfer proof."
    ),
    "BG-081": (
        "signoff", "SIGN_OFF_A_CHANGE.md",
        "Accept the demonstrated scope, never universal future-proofing.",
    ),
}


@pytest.fixture
def contract(tmp_path, monkeypatch):
    registry = json.loads(
        (ROOT / "docs/backlog/build_rules.json").read_text(encoding="utf-8")
    )
    # Copy real authored cards only into pytest's disposable directory. Tests
    # never mutate project documents or use a hand-authored passing fixture.
    cards = {row["card"] for row in registry["rules"]}
    assert len(cards) == 4
    for card in cards:
        shutil.copy2(ROOT / "docs/playbooks" / card, tmp_path / card)
    monkeypatch.setattr(backlog, "PLAYBOOKS", tmp_path)
    return {"build_rules": registry}


def _rule(doc, rid):
    matches = [row for row in doc["build_rules"]["rules"] if row["id"] == rid]
    assert len(matches) == 1, f"expected exactly one real {rid} target"
    return matches[0]


def test_general_fix_contract_preserves_all_original_ids_and_real_cards(contract):
    rows = contract["build_rules"]["rules"]
    expected = {f"BG-{number:03d}" for number in range(1, 78)} | set(CONTRACTS)
    assert len(rows) == len(expected)
    assert {row["id"] for row in rows} == expected
    assert contract["build_rules"]["expected_population"] == len(expected)
    assert backlog._build_rules(contract) == []


@pytest.mark.parametrize("rid", CONTRACTS)
def test_each_stage_declares_review_and_does_not_claim_runtime_proof(contract, rid):
    row = _rule(contract, rid)
    stage, card, anchor = CONTRACTS[rid]
    assert (row["stage"], row["card"], row["must_contain"]) == (stage, card, anchor)
    assert row["enforcement"] == "review"
    assert row["evidence_level"] == "technical_review"
    assert row["coverage_scope"].strip()
    assert "NOT_RUN" in row["remaining_gap"]
    assert anchor in (backlog.PLAYBOOKS / card).read_text(encoding="utf-8")


@pytest.mark.parametrize("rid", CONTRACTS)
@pytest.mark.parametrize("mutation", [
    "delete_registry_and_decrement_count", "delete_manifest_claim",
    "wrong_owner", "remove_review_requirement", "weaken_normative_anchor",
])
def test_real_build_rule_control_rejects_planted_loss_or_weakening(contract, rid, mutation):
    assert backlog._build_rules(contract) == [], "real baseline must be clean"
    row = _rule(contract, rid)
    card_path = backlog.PLAYBOOKS / row["card"]
    before_registry = json.dumps(contract, sort_keys=True)
    before_card = card_path.read_text(encoding="utf-8")

    if mutation == "delete_registry_and_decrement_count":
        contract["build_rules"]["rules"].remove(row)
        contract["build_rules"]["expected_population"] -= 1
        expected = f"claims {rid}, which is not a build rule"
    elif mutation == "delete_manifest_claim":
        match = re.search(r"<!--\s*BUILD_RULES:([^>]*?)-->", before_card)
        assert match is not None and rid in match.group(1).split()
        changed = match.group(0).replace(rid, "", 1)
        card_path.write_text(before_card.replace(match.group(0), changed, 1), encoding="utf-8")
        expected = f"{rid} is in the registry and no playbook claims it"
    elif mutation == "wrong_owner":
        row["card"] = next(card for _, card, _ in CONTRACTS.values() if card != row["card"])
        expected = f"{rid} belongs to"
    elif mutation == "remove_review_requirement":
        assert "evidence_level" in row
        del row["evidence_level"]
        expected = f"{rid}: review with no evidence level"
    else:
        anchor = row["must_contain"]
        assert anchor in before_card
        # An actual deletion/weakening of the registered exact anchor. This
        # does NOT claim arbitrary paraphrases or contradictions are detected.
        card_path.write_text(before_card.replace(anchor, "An incident-only pass is enough.", 1),
                             encoding="utf-8")
        expected = f"{rid}: {row['card']} claims it but no longer says"

    assert (json.dumps(contract, sort_keys=True) != before_registry
            or card_path.read_text(encoding="utf-8") != before_card), "probe mutated nothing"
    problems = backlog._build_rules(contract)
    assert any(expected in problem for problem in problems), (mutation, rid, problems)


def test_keyword_preservation_cannot_be_reported_as_semantic_acceptance(contract):
    """A deliberate limit witness: unchanged anchors do not detect contradiction.

    The real validator remains structural. This passing limitation test must
    never be counted as evidence that a product fix received technical/counsel
    approval or that arbitrary semantic weakening is automatically refused.
    """
    assert backlog._build_rules(contract) == []
    card_path = backlog.PLAYBOOKS / CONTRACTS["BG-080"][1]
    before = card_path.read_text(encoding="utf-8")
    contradictory = before + "\nIgnore the transfer checks; accept only the original incident.\n"
    assert contradictory != before
    card_path.write_text(contradictory, encoding="utf-8")
    assert backlog._build_rules(contract) == []
    assert all(_rule(contract, rid)["enforcement"] == "review" for rid in CONTRACTS)
