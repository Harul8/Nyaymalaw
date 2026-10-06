"""Full supplied-pool omission checks share the candidate's independent call."""

import json
from copy import deepcopy

import pytest

from nm.brain.legal_requirements import (
    retrieved_coverage_verification_valid,
    verify_findings,
)
from nm.shared.model_port import Tier
from tests.test_brain_legal_requirements import (
    CONVERSATION,
    REQUEST_SUBJECT,
    Model,
    conversation_words,
    finding,
    request_hits,
    supported_verdict,
)


def _supported(candidate_id="r1", source_id="s1"):
    decision = supported_verdict(candidate_id, source_id)
    decision["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    return decision


def _scope(identifier="q1", outcome="complete", missing=(), reason=None):
    return {
        "subject_id": identifier,
        "outcome": outcome,
        "missing_source_ids": list(missing),
        "reason": reason or "The full supplied pool contains no useful omitted work.",
    }


def _fixture(*, peer=False):
    pool = request_hits()
    pool["q1"]["candidates"].append(
        {
            "id": "s2",
            "kind": "judgment",
            "title": "Supplied notice exception",
            "locator": "paragraph 4",
            "court": "",
            "date": "",
            "jurisdiction": {"reported": ["Region A"], "status": "unresolved"},
            "text": "The Court held that the agreement's express exclusion of notice governs. "
            "No notice is needed if the agreement expressly excludes it.",
        }
    )
    subjects = [deepcopy(REQUEST_SUBJECT)]
    proposals = {"q1": [{**finding(), "sources": [deepcopy(pool["q1"]["candidates"][0])]}]}
    if peer:
        subjects.append({**deepcopy(REQUEST_SUBJECT), "id": "q2", "owner_id": "peer"})
        source = {**deepcopy(pool["q1"]["candidates"][0]), "id": "peer-source"}
        pool["q2"] = {"state": "ok", "candidates": [source]}
        proposals["q2"] = [{**finding(source_ids=["peer-source"]), "sources": [deepcopy(source)]}]
    return tuple(subjects), proposals, pool


def _verify(model, subjects, proposals, pool):
    return verify_findings(
        model,
        subjects=subjects,
        material_by_subject={row["id"]: [] for row in subjects},
        proposed=proposals,
        conversation=CONVERSATION,
        search_results=pool,
    )


def test_useful_uncited_adverse_limit_is_reported_without_discarding_checked_finding():
    subjects, proposals, pool = _fixture()
    original = deepcopy((subjects, proposals, pool))
    scope = _scope(
        outcome="partial",
        missing=("s2",),
        reason="The uncited court passage supports an express exception to notice.",
    )
    model = Model([{"decisions": [_supported()], "subject_coverage": [scope]}])

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 1 and model.calls[0][2] is Tier.JUDGE
    assert len(checked.rows["q1"]) == 1
    assert checked.rows["q1"][0]["source_ids"] == ["s1"]
    coverage = checked.coverage["q1"]
    assert coverage["state"] == "partial"
    assert coverage["semantic_state"] == "partial"
    assert coverage["checked_items"] == 1 and coverage["unread_items"] == 0
    assert coverage["retrieved_coverage"]["missing_source_ids"] == ["s2"]
    payload = json.loads(model.calls[0][0].user)
    row = payload["subjects"][0]
    assert row["retrieved_sources"] == pool["q1"]["candidates"]
    assert row["all_proposed_findings"] == [{"candidate_id": "r1", **proposals["q1"][0]}]
    assert row["checked_candidate_context"] == []
    assert payload["coverage_subject_ids"] == ["q1"]
    assert conversation_words(payload) == [
        {"turn_id": row.turn_id, "role": row.role, "text": row.text} for row in CONVERSATION
    ]
    assert (subjects, proposals, pool) == original
    assert retrieved_coverage_verification_valid(coverage["retrieved_coverage"], subject_id="q1")


@pytest.mark.parametrize("kind", ["principle", "condition", "adverse", "support"])
def test_bounded_conditional_work_can_be_complete_without_kind_quota_or_currency_metadata(kind):
    subjects, proposals, pool = _fixture()
    # Both supplied propositions are represented; no mandate or fixed category list is required.
    proposals["q1"][0]["kind"] = kind
    proposals["q1"].append(
        {
            **finding(
                kind="adverse",
                source_ids=["s2"],
                label="Express exclusion of notice",
                need="If the agreement expressly excludes notice, notice is not needed.",
                why="The deciding court preserves the agreement's express exclusion.",
            ),
            "sources": [deepcopy(pool["q1"]["candidates"][1])],
        }
    )
    model = Model(
        [{"decisions": [_supported(), _supported("r2", "s2")], "subject_coverage": [_scope()]}]
    )

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 1 and len(checked.rows["q1"]) == 2
    assert checked.coverage["q1"]["state"] == "ok"
    receipt = checked.coverage["q1"]["retrieved_coverage"]
    assert receipt["outcome"] == "complete" and receipt["missing_source_ids"] == []
    assert receipt["semantic_extent"] == "supplied_retrieved_passages"
    assert receipt["sources"] == pool["q1"]["candidates"]


def test_legitimate_rejection_does_not_require_replacement_findings_or_an_empty_reader_receipt():
    subjects, proposals, pool = _fixture()
    pool["q1"]["candidates"] = [
        {
            "id": "s1",
            "kind": "judgment",
            "title": "Supplied procedural history",
            "locator": "paragraph 1",
            "text": "The party had sent a notice before filing the appeal.",
        }
    ]
    proposals["q1"] = [{**finding(), "sources": deepcopy(pool["q1"]["candidates"])}]
    rejection = {
        "candidate_id": "r1",
        "verdict": "unsupported",
        "source_checks": [],
        "reason": "Case history does not impose a notice rule in another matter.",
    }
    model = Model(
        [
            {
                "decisions": [rejection],
                "subject_coverage": [
                    _scope(
                        reason=("The supplied background supplies no adopted rule "
                                "or useful replacement finding.")
                    )
                ],
            }
        ]
    )

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 1 and checked.rows == {"q1": []}
    coverage = checked.coverage["q1"]
    assert coverage["state"] == "ok" and coverage["semantic_state"] == "complete"
    assert coverage["checked_items"] == 1 and coverage["withheld_items"] == 1
    assert coverage["unread_items"] == 0 and "empty_reading" not in coverage
    assert coverage["retrieved_coverage"]["outcome"] == "complete"


@pytest.mark.parametrize("outcome", ["partial", "unassessed"])
def test_unlocalized_or_uncertain_scope_is_legitimate_without_retry_or_losing_checked_content(
    outcome,
):
    subjects, proposals, pool = _fixture()
    scope = _scope(
        outcome=outcome, reason="The source words permit only a bounded assessment of the question."
    )
    model = Model([{"decisions": [_supported()], "subject_coverage": [scope]}])

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 1 and len(checked.rows["q1"]) == 1
    assert checked.coverage["q1"]["state"] == "partial"
    assert checked.coverage["q1"]["semantic_state"] == outcome
    assert checked.coverage["q1"]["retrieved_coverage"]["missing_source_ids"] == []


def test_scope_only_correction_preserves_checked_findings_and_sound_subject_peer():
    subjects, proposals, pool = _fixture(peer=True)
    bad = _scope(missing=("peer-source",), outcome="partial")
    model = Model(
        [
            {
                "decisions": [_supported(), _supported("r2", "peer-source")],
                "subject_coverage": [bad, _scope("q2")],
            },
            {
                "decisions": [],
                "subject_coverage": [
                    _scope(
                        outcome="partial",
                        missing=("s2",),
                        reason="The supplied exception is missing from the first subject's work.",
                    )
                ],
            },
        ]
    )

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 2
    assert len(checked.rows["q1"]) == len(checked.rows["q2"]) == 1
    assert checked.coverage["q2"]["semantic_state"] == "complete"
    assert checked.coverage["q2"]["state"] == "ok"
    repair, schema, tier, _ = model.calls[1]
    payload = json.loads(repair.user)
    assert payload["coverage_subject_ids"] == ["q1"]
    assert [row["subject"]["id"] for row in payload["subjects"]] == ["q1"]
    assert payload["subjects"][0]["candidates"] == []
    context = payload["subjects"][0]["checked_candidate_context"]
    assert len(context) == 1 and context[0]["outcome"] == "retained"
    assert payload["subjects"][0]["retrieved_sources"] == pool["q1"]["candidates"]
    assert "coverage:q1" in payload["validation_issues"]
    assert schema["properties"]["decisions"]["maxItems"] == 0 and tier is Tier.JUDGE


def test_exhausted_scope_correction_retains_valid_finding_and_discloses_unassessed_coverage():
    subjects, proposals, pool = _fixture()
    model = Model(
        [
            {"decisions": [_supported()], "subject_coverage": []},
            {"decisions": [], "subject_coverage": []},
        ]
    )

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 2 and len(checked.rows["q1"]) == 1
    coverage = checked.coverage["q1"]
    assert coverage["state"] == "partial" and coverage["semantic_state"] == "unassessed"
    assert coverage["unread_items"] == 1 and coverage["checked_items"] == 1
    assert "retrieved_coverage" not in coverage


def test_exact_duplicate_scope_and_missing_ids_normalize_without_retry():
    subjects, proposals, pool = _fixture()
    scope = _scope(outcome="partial", missing=("s2", "s2"))
    model = Model([{"decisions": [_supported()], "subject_coverage": [scope, deepcopy(scope)]}])

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 1
    assert checked.coverage["q1"]["retrieved_coverage"]["missing_source_ids"] == ["s2"]


def test_complete_with_missing_support_gets_one_scope_correction_without_rechecking_finding():
    subjects, proposals, pool = _fixture()
    model = Model(
        [
            {"decisions": [_supported()], "subject_coverage": [_scope(missing=("s2",))]},
            {"decisions": [], "subject_coverage": [_scope(outcome="partial", missing=("s2",))]},
        ]
    )

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 2 and len(checked.rows["q1"]) == 1
    assert checked.coverage["q1"]["semantic_state"] == "partial"
    assert (
        "useful omission" in json.loads(model.calls[1][0].user)["validation_issues"]["coverage:q1"]
    )


def test_unconfirmed_old_candidate_check_remains_useful_but_never_claims_full_supplied_scope():
    subjects, proposals, _ = _fixture()
    model = Model([{"decisions": [_supported()]}])

    checked = verify_findings(
        model,
        subjects=subjects,
        material_by_subject={"q1": []},
        proposed=proposals,
        conversation=CONVERSATION,
    )

    assert len(model.calls) == 1 and len(checked.rows["q1"]) == 1
    assert checked.coverage["q1"]["semantic_state"] == "unassessed"
    assert checked.coverage["q1"]["semantic_extent"] == "cited_candidate_passages"
    assert "subject_coverage" not in model.calls[0][1]["properties"]
    assert "retrieved_coverage" not in checked.coverage["q1"]


def test_large_full_pool_can_be_unassessed_without_erasing_a_fitting_cited_finding():
    subjects, proposals, pool = _fixture()
    pool["q1"]["candidates"][1]["text"] += " Exact unused source context." * 8_000
    model = Model([{"decisions": [_supported()]}], budget=16_000)

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 1 and len(checked.rows["q1"]) == 1
    assert checked.coverage["q1"]["state"] == "partial"
    assert checked.coverage["q1"]["semantic_state"] == "unassessed"
    assert "subject_coverage" not in model.calls[0][1]["properties"]
    assert checked.coverage["q1"]["semantic_extent"] == "cited_candidate_passages"
    assert "retrieved_coverage" not in checked.coverage["q1"]
    assert any("exceeds context" in note for note in checked.coverage["q1"]["diagnostics"])


def test_malformed_pool_does_not_erase_cited_check_or_sound_owned_pool_peer():
    subjects, proposals, pool = _fixture(peer=True)
    pool["q1"]["candidates"][1]["text"] = None
    model = Model(
        [
            {
                "decisions": [_supported(), _supported("r2", "peer-source")],
                "subject_coverage": [_scope("q2")],
            }
        ]
    )

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 1
    assert len(checked.rows["q1"]) == len(checked.rows["q2"]) == 1
    assert checked.coverage["q1"]["semantic_state"] == "unassessed"
    assert checked.coverage["q1"]["state"] == "partial"
    assert checked.coverage["q2"]["semantic_state"] == "complete"
    assert checked.coverage["q2"]["state"] == "ok"


def test_complete_scope_waits_for_an_unresolved_candidate_in_the_same_existing_correction():
    subjects, proposals, pool = _fixture()
    bad = _supported()
    bad["source_checks"][0]["scope_fragment_id"] = "foreign-fragment"
    model = Model(
        [
            {"decisions": [bad], "subject_coverage": [_scope()]},
            {"decisions": [_supported()], "subject_coverage": [_scope()]},
        ]
    )

    checked = _verify(model, subjects, proposals, pool)

    assert len(model.calls) == 2 and len(checked.rows["q1"]) == 1
    assert checked.coverage["q1"]["state"] == "ok"
    repair = json.loads(model.calls[1][0].user)
    assert set(repair["validation_issues"]) == {"r1", "coverage:q1"}


@pytest.mark.parametrize(
    "damage", ["foreign_subject", "foreign_source", "missing_source_text", "false_complete"]
)
def test_persisted_bounded_coverage_validator_rejects_only_consequential_scope_damage(damage):
    subjects, proposals, pool = _fixture()
    checked = _verify(
        Model([{"decisions": [_supported()], "subject_coverage": [_scope()]}]),
        subjects,
        proposals,
        pool,
    )
    receipt = deepcopy(checked.coverage["q1"]["retrieved_coverage"])
    if damage == "foreign_subject":
        receipt["subject_id"] = "another-subject"
    elif damage == "foreign_source":
        receipt["missing_source_ids"] = ["another-source"]
    elif damage == "missing_source_text":
        del receipt["sources"][0]["text"]
    else:
        receipt["missing_source_ids"] = ["s2"]
    assert not retrieved_coverage_verification_valid(receipt, subject_id="q1")


def test_rejected_candidate_context_survives_scope_only_correction_without_forcing_new_law():
    subjects, proposals, pool = _fixture()
    pool["q1"]["candidates"] = [
        {
            "id": "s1",
            "kind": "judgment",
            "title": "Background",
            "locator": "paragraph 1",
            "text": "A party sent a notice in the earlier litigation.",
        }
    ]
    proposals["q1"] = [{**finding(), "sources": deepcopy(pool["q1"]["candidates"])}]
    rejected = {
        "candidate_id": "r1",
        "verdict": "unsupported",
        "source_checks": [],
        "reason": "This background does not prescribe notice in another matter.",
    }
    model = Model(
        [
            {"decisions": [rejected], "subject_coverage": [_scope(missing=("foreign",))]},
            {
                "decisions": [],
                "subject_coverage": [
                    _scope(
                        reason="The supplied background permits no useful replacement legal work."
                    )
                ],
            },
        ]
    )
    checked = _verify(model, subjects, proposals, pool)
    assert len(model.calls) == 2 and checked.rows == {"q1": []}
    assert checked.coverage["q1"]["state"] == "ok"
    assert checked.coverage["q1"]["checked_items"] == 1
    assert checked.coverage["q1"]["withheld_items"] == 1
    context = json.loads(model.calls[1][0].user)["subjects"][0]["checked_candidate_context"]
    assert len(context) == 1 and context[0]["outcome"] == "rejected"
    assert context[0]["decision"]["verdict"] == "unsupported"


def test_scope_correction_provider_outage_preserves_independently_checked_content():
    from nm.shared.model_port import ProviderUnavailable

    subjects, proposals, pool = _fixture()
    model = Model(
        [
            {"decisions": [_supported()], "subject_coverage": []},
            ProviderUnavailable("Independent review is unavailable"),
        ]
    )
    checked = _verify(model, subjects, proposals, pool)
    assert len(model.calls) == 2 and len(checked.rows["q1"]) == 1
    assert checked.outage == "ProviderUnavailable"
    assert checked.coverage["q1"]["state"] == "partial"
    assert checked.coverage["q1"]["semantic_state"] == "unassessed"
    assert "retrieved_coverage" not in checked.coverage["q1"]


@pytest.mark.parametrize("downgraded_from", [None, Tier.JUDGE])
def test_downgraded_judge_cannot_supply_candidate_or_coverage_attestation(downgraded_from):
    from dataclasses import replace

    class Downgraded(Model):
        def structured(self, *args, **kwargs):
            return replace(
                super().structured(*args, **kwargs),
                tier=Tier.ROUTINE,
                downgraded_from=downgraded_from,
            )

    subjects, proposals, pool = _fixture()
    model = Downgraded([{"decisions": [_supported()], "subject_coverage": [_scope()]}])
    checked = _verify(model, subjects, proposals, pool)
    assert len(model.calls) == 1 and checked.rows == {"q1": []}
    assert checked.outage == "TierUnavailable"
    assert checked.coverage["q1"]["state"] == "unavailable"
    assert checked.coverage["q1"]["semantic_state"] == "unassessed"
    assert "retrieved_coverage" not in checked.coverage["q1"]


@pytest.mark.parametrize("extra", [None, "", [], {}])
def test_empty_inapplicable_envelope_metadata_does_not_repeat_useful_review(extra):
    subjects, proposals, pool = _fixture()
    model = Model(
        [{"decisions": [_supported()], "subject_coverage": [_scope()], "unused_metadata": extra}]
    )
    checked = _verify(model, subjects, proposals, pool)
    assert len(model.calls) == 1 and len(checked.rows["q1"]) == 1
    assert checked.coverage["q1"]["state"] == "ok"
    assert "unused_metadata" not in checked.coverage["q1"]["retrieved_coverage"]


_LONG_SCOPE_REASON = (
    "The supplied provision states a notice condition tied to the agreement, "
    "and the finding preserves that condition. "
    "The supplied court passage adds the express exclusion of notice "
    "and is represented as conditional adverse work. "
    "No finding upgrades missing agreement facts into satisfaction of either predicate. "
    "No mandate is inferred from procedural background, topic overlap or absent metadata. "
    "Both propositions remain limited to their actual actors, period and route; "
    "the checks do not establish current or binding law. "
    "This coverage assessment concerns only the supplied passages. Scope is bounded."
)


@pytest.mark.parametrize(
    "reason",
    [
        "The conditional rule and its adverse exception account for the supplied pool.",
        _LONG_SCOPE_REASON,
    ],
)
def test_substantive_coverage_reason_length_does_not_repeat_or_weaken_valid_review(reason):
    assert len(_LONG_SCOPE_REASON) == 600
    subjects, proposals, pool = _fixture()
    proposals["q1"].append(
        {
            **finding(
                kind="adverse",
                source_ids=["s2"],
                label="Express notice exclusion",
                need="If the agreement expressly excludes notice, notice is not needed.",
                why="The court preserves the agreement's express exclusion.",
            ),
            "sources": [deepcopy(pool["q1"]["candidates"][1])],
        }
    )
    model = Model(
        [
            {
                "decisions": [_supported(), _supported("r2", "s2")],
                "subject_coverage": [_scope(reason=reason)],
            }
        ]
    )
    checked = _verify(model, subjects, proposals, pool)
    assert len(model.calls) == 1 and len(checked.rows["q1"]) == 2
    assert checked.coverage["q1"]["state"] == "ok"
    receipt = checked.coverage["q1"]["retrieved_coverage"]
    assert receipt["outcome"] == "complete" and receipt["reason"] == reason
    assert retrieved_coverage_verification_valid(receipt, subject_id="q1")
