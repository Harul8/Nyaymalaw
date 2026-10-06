"""Isolated drafted material-coverage contracts, not semantic or browser proof.

The strict stub applies the production adapter's whole-envelope schema check.
Schema-valid contradictions exercise coverage-only peer retention; missing or
foreign schema-invalid coverage cannot expose peers before that check.
"""

import json
from copy import deepcopy

import pytest

from nm.brain import material_verification as draft
from nm.brain.conversation import OpeningCandidate
from nm.brain.material import MaterialCandidate, addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    TierUnavailable,
    Usage,
    require_schema,
)


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


def test_checked_peer_survives_missing_second_verdict_after_one_correction():
    first, second = "The handover occurred on Tuesday.", "A separate record was retained."
    candidates = (detail(first), detail(second))
    latest = first + " " + second
    model = Stub(
        [
            lambda p: {"verdicts": [verdict(p, "D1")], "coverage": assessment()},
            {"verdicts": [], "coverage": assessment()},
        ]
    )
    sink = {}
    result = review(model, latest=latest, candidates=candidates, scope={}, sink=sink)
    assert len(model.calls) == 2 and result.details == (candidates[0],)
    assert result.rejected_details == result.withheld_details == 0
    assert result.unread_details == 1 and not result.opening_unread
    (row,) = result.unread_proposals
    assert row["candidate_id"] == "D2" and row["candidate_type"] == "detail"
    assert row["verdict"] == "unassessed" and row["admission_issue"] == "review_unavailable"
    assert row["validation_issues"] == ["verdict is absent"]
    assert row["proposal"]["quoted"] == second
    assert (
        not {"account_check", "target_checks", "operation_supported", "model_decision"} & row.keys()
    )
    assert model.calls[1][0]["retained_candidate_context"][0]["candidate_id"] == "D1"
    assert sink["state"] == "unassessed" and "D2" in sink["validation_issue"]
    assert sink["previous_assessment"]["state"] == "complete"


def test_schema_valid_but_malformed_candidate_does_not_suppress_checked_peer():
    first, second = "The handover occurred on Tuesday.", "A separate record was retained."

    def output(payload):
        rows = []
        for item in payload["candidates"]:
            row = verdict(payload, item["candidate_id"])
            if item["candidate_id"] == "D2":
                row["reason"] = ""
            rows.append(row)
        return {"verdicts": rows, "coverage": assessment()}

    model = Stub([output, output])
    candidates = (detail(first), detail(second))
    result = review(model, latest=first + " " + second, candidates=candidates, scope={}, sink={})
    assert result.details == (candidates[0],) and len(model.calls) == 2
    assert result.unread_details == 1 and result.rejected_details == 0
    assert "reason is empty" in result.unread_proposals[0]["validation_issues"]


def test_strict_envelope_failure_does_not_claim_hidden_first_attempt_peer_retention():
    first, second = "The handover occurred on Tuesday.", "A separate record was retained."

    def first_response(payload):
        bad = verdict(payload, "D2")
        del bad["account_check"]
        return {"verdicts": [verdict(payload, "D1"), bad], "coverage": assessment()}

    model = Stub(
        [first_response, lambda p: {"verdicts": [verdict(p, "D1")], "coverage": assessment()}]
    )
    candidates = (detail(first), detail(second))
    result = review(model, latest=first + " " + second, candidates=candidates, scope={}, sink={})
    assert result.details == (candidates[0],) and result.unread_details == 1
    assert len(model.calls) == 2
    assert [r["candidate_id"] for r in model.calls[1][0]["candidates"]] == ["D1", "D2"]
    assert model.calls[1][0]["retained_candidate_context"] == []


def test_all_unread_is_distinct_from_no_material_or_semantic_rejection():
    latest = "A record was withheld. Its return was requested."
    candidates = (detail("A record was withheld."), detail("Its return was requested."))
    model = Stub(
        [
            {"verdicts": [], "coverage": assessment("partial", ["L1"], "Account remains missing.")},
            {"verdicts": [], "coverage": assessment("partial", ["L1"], "Account remains missing.")},
        ]
    )
    sink = {}
    result = review(model, latest=latest, candidates=candidates, scope={}, sink=sink)
    assert len(model.calls) == 2 and result.details == ()
    assert result.rejected_details == result.withheld_details == 0 and result.unread_details == 2
    assert result.rejected_proposals == result.withheld_proposals == ()
    assert sink["state"] == "unassessed"
    assert sink["previous_assessment"]["state"] == "partial"
    assert sink["previous_assessment"]["missing_source_ids"] == ["L1"]


def test_valid_semantic_rejection_remains_distinct_and_needs_no_retry():
    first, second = "The handover occurred on Tuesday.", "A separate record was retained."
    candidates = (detail(first), detail(second))
    model = Stub(
        [
            lambda p: {
                "verdicts": [verdict(p, "D1"), verdict(p, "D2", accepted=False)],
                "coverage": assessment(),
            }
        ]
    )
    result = review(model, latest=first + " " + second, candidates=candidates, scope={}, sink={})
    assert result.details == (candidates[0],) and len(model.calls) == 1
    assert result.rejected_details == 1 and result.unread_details == result.withheld_details == 0
    assert result.rejected_proposals[0]["candidate_id"] == "D2"
    assert result.unread_proposals == result.withheld_proposals == ()


@pytest.mark.parametrize("peer_status", ["unread", "reject"])
def test_required_successor_failure_keeps_prior_target_and_independent_peer(peer_status):
    one, two, three = "First reported event.", "Second reported event.", "Third reported event."
    candidates = (detail(one, target=("merged",)), detail(two, target=("merged",)), detail(three))
    target = {"id": "merged", "statement": "Unsupported merged interpretation."}

    def first(payload):
        rows = [verdict(payload, "D1", peers=("D2",)), verdict(payload, "D3")]
        if peer_status == "reject":
            rows.append(verdict(payload, "D2", accepted=False))
        return {"verdicts": rows, "coverage": assessment()}

    replies = [first] + (
        [{"verdicts": [], "coverage": assessment()}] if peer_status == "unread" else []
    )
    model = Stub(replies)
    sink = {}
    result = review(
        model,
        latest=" ".join((one, two, three)),
        candidates=candidates,
        prior_material=(target,),
        active_material=(target,),
        scope={},
        sink=sink,
    )
    assert result.details == (candidates[2],)
    assert result.withheld_details == 1
    assert result.withheld_proposals[0]["candidate_id"] == "D1"
    assert (
        result.withheld_proposals[0]["admission_issue"] == "required_restoration_peer_unavailable"
    )
    assert result.withheld_proposals[0]["model_decision"]["verdict"] == "accept"
    assert result.rejected_details == (1 if peer_status == "reject" else 0)
    assert result.unread_details == (1 if peer_status == "unread" else 0)
    assert len(model.calls) == (2 if peer_status == "unread" else 1)
    assert sink["state"] == "unassessed"
    assert "Final admission withheld reviewed proposals D1" in sink["validation_issue"]


def test_unread_opening_never_defaults_to_accept_and_does_not_count_as_unread_detail():
    latest = "The client reports a withheld record."
    candidate = detail(latest)
    opening = OpeningCandidate(True, "Return of records", latest)
    model = Stub(
        [
            lambda p: {"verdicts": [verdict(p, "D1")], "coverage": assessment()},
            {"verdicts": [], "coverage": assessment()},
        ]
    )
    sink = {}
    result = draft.verify_material_grounding(
        model,
        candidates=(candidate,),
        opening=opening,
        earlier=(),
        latest=latest,
        source_treatments=treatments((), latest),
        review_scope={},
        coverage=sink,
    )
    assert result.details == (candidate,) and len(model.calls) == 2
    assert not result.opening_supported and result.opening_unread
    assert result.unread_details == 0 and result.rejected_details == 0
    (row,) = result.unread_proposals
    assert row["candidate_id"] == "O1" and row["candidate_type"] == "opening"
    assert row["proposal"]["title"] == "Return of records"
    assert "no usable independent verdict" in result.opening_reason
    assert sink["state"] == "unassessed"


def test_checked_opening_can_survive_unread_detail_without_certifying_material_coverage():
    latest = "The client reports a withheld record."
    opening = OpeningCandidate(True, "Return of records", latest)

    def accepted_opening(payload):
        # The owning output contract uses the same checked fields for openings.
        opening_row = next(r for r in payload["candidates"] if r["candidate_id"] == "O1")
        opening_row["related_material_ids"] = []
        return {"verdicts": [verdict(payload, "O1")], "coverage": assessment()}

    model = Stub([accepted_opening, {"verdicts": [], "coverage": assessment()}])
    sink = {}
    result = draft.verify_material_grounding(
        model,
        candidates=(detail(latest),),
        opening=opening,
        earlier=(),
        latest=latest,
        source_treatments=treatments((), latest),
        review_scope={},
        coverage=sink,
    )
    assert result.opening_supported and not result.opening_unread
    assert result.unread_details == 1 and result.rejected_details == 0
    assert len(model.calls) == 2 and sink["state"] == "unassessed"


@pytest.mark.parametrize("strict", [False, True])
def test_unknown_candidate_output_never_enters_accepted_or_unread_canonical_proposals(strict):
    latest = "The client reports a withheld record."

    def foreign(payload):
        row = verdict(payload, "D1")
        row["candidate_id"] = "UNOWNED_PRIVATE"
        return {"verdicts": [row], "coverage": assessment()}

    model = Stub([foreign, foreign], strict=strict)
    result = review(model, latest=latest, candidates=(detail(latest),), scope={}, sink={})
    assert result.details == () and result.rejected_details == 0 and result.unread_details == 1
    assert result.unread_proposals[0]["candidate_id"] == "D1"
    assert "UNOWNED_PRIVATE" not in json.dumps(result.unread_proposals)
    assert len(model.calls) == 2


@pytest.mark.parametrize(
    "catalogue",
    [(), ({"id": "target", "statement": "one"}, {"id": "target", "statement": "different"})],
)
def test_owned_target_catalogue_failure_still_blocks_before_any_model_call(catalogue):
    latest = "The client reports a withheld record."
    model = Stub([])
    with pytest.raises(SchemaViolation, match="unowned|conflicting"):
        review(
            model,
            latest=latest,
            candidates=(detail(latest, target=("target",)),),
            prior_material=catalogue,
            scope={},
            sink={},
        )
    assert model.calls == []


def test_source_catalogue_ownership_failure_remains_blocking():
    latest = "The client reports a withheld record."
    model = Stub([])
    with pytest.raises(SchemaViolation, match="every owned advocate span"):
        draft.verify_material_grounding(
            model,
            candidates=(detail(latest),),
            opening=OpeningCandidate(False, "", ""),
            earlier=(),
            latest=latest,
            source_treatments={},
            review_scope={},
            coverage={},
        )
    assert model.calls == []


@pytest.mark.parametrize(
    "error",
    [
        ProviderUnavailable("Provider unavailable."),
        TierUnavailable("Independent review unavailable."),
    ],
)
def test_provider_or_tier_fault_still_propagates_instead_of_masquerading_as_candidate_rejection(
    error,
):
    first, second = "The handover occurred on Tuesday.", "A separate record was retained."
    model = Stub([lambda p: {"verdicts": [verdict(p, "D1")], "coverage": assessment()}, error])
    sink = {}
    with pytest.raises(type(error)):
        review(
            model,
            latest=first + " " + second,
            candidates=(detail(first), detail(second)),
            scope={},
            sink=sink,
        )
    assert len(model.calls) == 2 and sink == {}


def test_unrequested_legacy_mode_reports_unread_result_without_fabricating_coverage():
    first, second = "The handover occurred on Tuesday.", "A separate record was retained."
    model = Stub([lambda p: {"verdicts": [verdict(p, "D1")]}, {"verdicts": []}])
    sink = {"legacy": "unchanged"}
    candidates = (detail(first), detail(second))
    result = review(model, latest=first + " " + second, candidates=candidates, sink=sink)
    assert result.details == (candidates[0],) and result.unread_details == 1
    assert result.rejected_details == 0 and len(model.calls) == 2
    assert sink == {"legacy": "unchanged"}


def test_old_positional_result_constructors_and_well_formed_outcomes_keep_zero_recovery_defaults():
    result = draft.GroundingResult((), True, 0)
    assert result.withheld_details == result.unread_details == 0 and not result.opening_unread
    assert result.withheld_proposals == result.unread_proposals == ()
    model = Stub([])
    result = review(model, latest="Please recap.")
    assert model.calls == [] and result.opening_supported and result.unread_details == 0
