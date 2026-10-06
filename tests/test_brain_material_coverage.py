"""Isolated drafted material-coverage contracts, not semantic or browser proof.

The strict stub applies the production adapter's whole-envelope schema check.
Schema-valid contradictions exercise coverage-only peer retention; missing or
foreign schema-invalid coverage cannot expose peers before that check.
"""

import json
from copy import deepcopy
from dataclasses import fields

import pytest

from nm.brain import material_verification as draft
from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import MaterialCandidate, addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage, require_schema


class Stub:
    def __init__(self, replies, *, strict=True):
        self.replies = iter(replies)
        self.strict = strict
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append((payload, schema, prompt.system))
        response = next(self.replies)
        data = response(payload) if callable(response) else deepcopy(response)
        if isinstance(data, Exception):
            raise data
        if self.strict:
            require_schema(data, schema)
        return ModelResult(
            text=None,
            data=data,
            tier=tier,
            provider="offline",
            model="offline",
            usage=Usage(0, 0, 0),
            latency_ms=0,
            completion=Completion.COMPLETE,
        )


def treatments(earlier, latest, roles=None):
    roles = roles or {}
    _, current, prior = addressed_sources(earlier, latest)
    result = {
        identity: {
            "turn_id": ref.turn_id,
            "role": ref.role,
            "quoted": ref.quoted,
            "content_role": roles.get(identity, "reported_matter_account"),
            "reason": "Explicit scripted original-source treatment.",
        }
        for identity, ref in prior.items()
        if ref.role == "advocate"
    }
    result.update(
        {
            identity: {
                "turn_id": "latest",
                "role": "advocate",
                "quoted": words,
                "content_role": roles.get(identity, "reported_matter_account"),
                "reason": "Explicit scripted original-source treatment.",
            }
            for identity, words in current.items()
        }
    )
    return result


def assessment(
    state="complete", missing=(), reason="Original account is already faithfully represented."
):
    return {"state": state, "reason": reason, "missing_source_ids": list(missing)}


def detail(quoted, *, target=()):
    return MaterialCandidate(
        kind="event",
        statement=quoted,
        quoted=quoted,
        relation="corrects" if target else "new",
        prior_references=(),
        matter_scope="current",
        basis="stated",
        importance="relevant",
        why_material="This reported event changes the chronology.",
        placement="matter",
        related_material_ids=tuple(target),
    )


def verdict(payload, identity, *, accepted=True, peers=()):
    row = next(r for r in payload["candidates"] if r["candidate_id"] == identity)
    sources = row["allowed_account_source_ids"][:1] if accepted else []
    return {
        "candidate_id": identity,
        "operation_supported": accepted,
        "verdict": "accept" if accepted else "reject",
        "reason": "Scripted proposal judgment against original account.",
        "account_check": {
            "content_role": "reported_matter_account" if accepted else "uncertain",
            "supported": accepted,
            "introduces_legal_analysis": False,
            "source_ids": sources,
            "source_checks": [
                {
                    "source_id": i,
                    "supplies_account_content": True,
                    "supports_proposal": True,
                    "reason": "Original advocate content supports this proposal.",
                }
                for i in sources
            ],
            "reason": "Whole attributed proposal was explicitly judged.",
        },
        "target_checks": [
            {
                "target_id": i,
                "identity_relation": "restore_invalid_interpretation",
                "account_preserved": accepted,
                "required_peer_ids": list(peers),
                "reason": "Scripted atomic restoration preserves underlying account.",
            }
            for i in row["related_material_ids"]
        ],
    }


def review(
    model,
    *,
    latest,
    candidates=(),
    earlier=(),
    scope=None,
    sink=None,
    active_material=(),
    active_disputes=(),
    prior_material=(),
):
    return draft.verify_material_grounding(
        model,
        candidates=candidates,
        opening=OpeningCandidate(False, "", ""),
        earlier=earlier,
        latest=latest,
        source_treatments=treatments(earlier, latest),
        review_scope=scope,
        active_material=active_material,
        active_disputes=active_disputes,
        prior_material=prior_material,
        coverage=sink,
    )


def test_legacy_read_only_empty_still_has_no_call_and_no_fabricated_coverage():
    model = Stub([])
    sink = {"existing": "unchanged"}
    result = review(model, latest="Give a recap.", sink=sink)
    assert result.details == () and result.opening_supported
    assert model.calls == [] and sink == {"existing": "unchanged"}
    assert [f.name for f in fields(result)] == [
        "details",
        "opening_supported",
        "rejected_details",
        "opening_reason",
        "rejected_proposals",
        "withheld_proposals",
        "unread_proposals",
    ]


def test_legacy_nonempty_keeps_verdict_only_schema_and_return_shape():
    latest = "The handover occurred on Tuesday."
    model = Stub([lambda payload: {"verdicts": [verdict(payload, "D1")]}])
    candidate = detail(latest)
    result = review(model, latest=latest, candidates=(candidate,))
    assert result.details == (candidate,) and len(model.calls) == 1
    assert "coverage" not in model.calls[0][1]["properties"]
    assert "coverage_source_ids" not in model.calls[0][0]


@pytest.mark.parametrize("state,missing", [("partial", ["P1S1"]), ("complete", [])])
def test_requested_empty_reviews_distinguish_omission_from_already_represented_no_change(
    state, missing
):
    earlier = (
        Message("original", "advocate", "The handover occurred on Tuesday."),
        Message("old-answer", "nm", "The handover occurred on Wednesday."),
    )
    latest = "Review the saved interpretation."
    active = (
        {
            "id": "date",
            "statement": earlier[0].text,
            "source_turn_id": "original",
            "quoted": earlier[0].text,
        },
        {
            "id": "held-owner",
            "statement": "The custody may concern another matter.",
            "matter_scope": "uncertain",
            "placement": "unresolved",
        },
    )
    disputes = ({"id": "issue", "label": "Custody of records"},)
    scope = {"requests": [{"request_index": 0, "material_purposes": ["interpretation_review"]}]}
    sink = {}
    model = Stub(
        [
            {
                "verdicts": [],
                "coverage": assessment(
                    state,
                    missing,
                    "P1S1 chronology needs reconciliation."
                    if missing
                    else "Existing date faithfully represents P1S1; no change is needed.",
                ),
            }
        ]
    )
    result = review(
        model,
        latest=latest,
        earlier=earlier,
        scope=scope,
        sink=sink,
        active_material=active,
        active_disputes=disputes,
    )
    assert result.details == () and len(model.calls) == 1
    sent, schema, system = model.calls[0]
    assert sent["candidates"] == [] and sent["coverage_source_ids"] == ["P1S1", "L1"]
    assert "P2S1" not in sent["coverage_source_ids"]
    assert [r["id"] for r in sent["active_material"]] == ["date", "held-owner"]
    assert all(r["record_role"] == "nm_interpretation" for r in sent["active_material"])
    assert sent["active_disputes"][0]["id"] == "issue"
    assert schema["properties"]["verdicts"]["maxItems"] == 0
    assert schema["required"] == ["verdicts", "coverage"]
    assert "Activity 6" in system
    assert sink["state"] == state and sink["contract"] == "independent_account_coverage_v1"
    assert sink["review_scope"] == scope
    scope["requests"][0]["request_index"] = 8
    assert sink["review_scope"]["requests"][0]["request_index"] == 0
    assert sink["missing_sources"] == (
        [
            {
                "source_id": "P1S1",
                "turn_id": "original",
                "role": "advocate",
                "quoted": earlier[0].text,
            }
        ]
        if missing
        else []
    )


@pytest.mark.parametrize("state", ["partial", "unassessed"])
def test_valid_unlocalised_assessment_is_not_retried_into_complete(state):
    sink = {}
    model = Stub(
        [
            {
                "verdicts": [],
                "coverage": assessment(
                    state, (), "The relevant ownership/reconciliation gap cannot be localised."
                ),
            }
        ]
    )
    review(model, latest="Review the reported uncertainty.", scope={}, sink=sink)
    assert len(model.calls) == 1 and sink["state"] == state
    assert sink["missing_source_ids"] == [] and sink["missing_sources"] == []
    assert "validation_issue" not in sink


@pytest.mark.parametrize(
    "bad",
    [
        {"state": "complete", "reason": "No omission.", "missing_source_ids": ["L1"]},
        {"state": "unassessed", "reason": "  ", "missing_source_ids": []},
        {
            "state": "partial",
            "reason": "A source is missing.",
            "missing_source_ids": ["FOREIGN_PRIVATE"],
        },
        None,
    ],
)
def test_malformed_or_foreign_empty_coverage_has_one_correction_then_truthful_diagnostic(bad):
    sink = {}
    data = {"verdicts": [], "coverage": bad} if bad is not None else {"verdicts": []}
    model = Stub([data, data])
    result = review(model, latest="The handover date is Tuesday.", scope={}, sink=sink)
    assert result.details == () and len(model.calls) == 2
    assert sink["state"] == "unassessed" and sink["missing_source_ids"] == []
    assert sink["missing_sources"] == [] and "$coverage" in sink["validation_issue"]
    assert "FOREIGN_PRIVATE" not in sink["validation_issue"]
    assert model.calls[1][0]["candidates"] == []
    assert model.calls[1][0]["retained_candidate_context"] == []


@pytest.mark.parametrize("repaired", [True, False])
def test_coverage_only_correction_retains_valid_peer_and_never_restarts_bound(repaired):
    latest = "The handover occurred on Tuesday."
    candidate = detail(latest)
    def first(p):
        return {
            "verdicts": [verdict(p, "D1")],
            "coverage": assessment("complete", ["L1"], "Contradictory scripted coverage."),
        }
    final = {
        "verdicts": [],
        "coverage": assessment(
            "complete",
            () if repaired else ("L1",),
            "No new row is necessary."
            if repaired
            else "Complete contradicts a selected missing source.",
        ),
    }
    sink = {}
    model = Stub([first, final])
    result = review(model, latest=latest, candidates=(candidate,), scope={}, sink=sink)
    assert result.details == (candidate,) and len(model.calls) == 2
    repaired_input = model.calls[1][0]
    assert repaired_input["candidates"] == []
    assert repaired_input["retained_candidate_context"][0]["candidate_id"] == "D1"
    assert repaired_input["retained_candidate_context"][0]["decision"]["verdict"] == "accept"
    assert sink["state"] == ("complete" if repaired else "unassessed")


def test_missing_coverage_at_strict_adapter_boundary_cannot_claim_first_peer_retention():
    latest = "The handover occurred on Tuesday."
    candidate = detail(latest)
    def first(p):
        return {"verdicts": [verdict(p, "D1")]}

    def second(p):
        return {"verdicts": [verdict(p, "D1")], "coverage": assessment()}
    model = Stub([first, second])
    sink = {}
    result = review(model, latest=latest, candidates=(candidate,), scope={}, sink=sink)
    assert result.details == (candidate,) and len(model.calls) == 2
    assert [r["candidate_id"] for r in model.calls[1][0]["candidates"]] == ["D1"]
    assert model.calls[1][0]["retained_candidate_context"] == []


def test_candidate_repair_reassesses_coverage_and_preserves_prior_known_omission_if_later_invalid():
    first_text = "The handover occurred on Tuesday."
    second_text = "A separate record was retained."
    latest = first_text + " " + second_text
    first_candidate, second_candidate = detail(first_text), detail(second_text)

    def first(payload):
        incomplete = verdict(payload, "D2")
        incomplete["reason"] = ""
        return {
            "verdicts": [verdict(payload, "D1"), incomplete],
            "coverage": assessment("partial", ["L2"], "L2 retains an unresolved account."),
        }

    def second(payload):
        return {
            "verdicts": [verdict(payload, "D2")],
            "coverage": assessment(
                "complete", ["L2"], "Malformed complete contradicts selected missing source."
            ),
        }

    model = Stub([first, second])
    sink = {}
    result = review(
        model, latest=latest, candidates=(first_candidate, second_candidate), scope={}, sink=sink
    )
    assert result.details == (first_candidate, second_candidate) and len(model.calls) == 2
    assert [r["candidate_id"] for r in model.calls[1][0]["candidates"]] == ["D2"]
    assert model.calls[1][0]["retained_candidate_context"][0]["candidate_id"] == "D1"
    assert sink["state"] == "unassessed"
    assert sink["previous_assessment"]["state"] == "partial"
    assert sink["previous_assessment"]["missing_source_ids"] == ["L2"]
    assert sink["previous_assessment"]["missing_sources"][0]["quoted"] == second_text


def test_unresolved_candidate_is_visible_unread_and_cannot_become_complete_empty_coverage():
    latest = "The handover occurred on Tuesday."
    model = Stub(
        [{"verdicts": [], "coverage": assessment()}, {"verdicts": [], "coverage": assessment()}]
    )
    sink = {}
    result = review(model, latest=latest, candidates=(detail(latest),), scope={}, sink=sink)
    assert len(model.calls) == 2 and result.details == ()
    assert result.unread_details == 1 and result.rejected_details == 0
    assert sink["state"] == "unassessed"


def test_exact_duplicate_missing_ids_are_normalized_without_changing_partial_meaning():
    sink = {}
    model = Stub(
        [
            {
                "verdicts": [],
                "coverage": assessment("partial", ["L1", "L1"], "  L1 chronology is omitted.  "),
            }
        ]
    )
    review(model, latest="The handover occurred on Tuesday.", scope={}, sink=sink)
    assert len(model.calls) == 1 and sink["state"] == "partial"
    assert sink["missing_source_ids"] == ["L1"] and len(sink["missing_sources"]) == 1
    assert sink["reason"] == "L1 chronology is omitted."


def test_final_admission_downgrade_invalidates_coverage_and_keeps_independent_peer():
    one, two, three = "First reported event.", "Second reported event.", "Third reported event."
    latest = " ".join((one, two, three))
    target = {"id": "merged", "statement": "Unsupported merged interpretation."}
    candidates = (detail(one, target=("merged",)), detail(two, target=("merged",)), detail(three))

    def response(payload):
        return {
            "verdicts": [
                verdict(payload, "D1", peers=("D2",)),
                verdict(payload, "D2", accepted=False),
                verdict(payload, "D3"),
            ],
            "coverage": assessment("complete", (), "Raw reviewed set was scripted complete."),
        }

    sink = {}
    model = Stub([response])
    result = review(
        model,
        latest=latest,
        candidates=candidates,
        prior_material=(target,),
        active_material=(target,),
        scope={},
        sink=sink,
    )
    assert result.details == (candidates[2],) and len(model.calls) == 1
    assert sink["state"] == "unassessed"
    assert "Final admission withheld reviewed proposals D1" in sink["validation_issue"]
    assert sink["previous_assessment"]["state"] == "complete"
