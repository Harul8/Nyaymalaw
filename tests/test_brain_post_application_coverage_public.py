"""Raw independent application judgments survive saving and exact-prefix replay.

Meanings are explicitly scripted. These tests prove owned operation/history
binding and bounded release; they do not certify a real Judge's interpretation.
"""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as owner
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage, require_schema
from tests.test_brain_material import material, mutation_scope, send
from tests.test_brain_material_purpose import PurposeModel, item, open_account, routed, seed_plan
from tests.test_brain_source_support_verifiers import coverage, disposition, verdict

ORIGINAL = "The keeper holds the signed parcel receipt."
CHANGED = "The keeper corrects the earlier custody account."
WITHDRAWN = "I withdraw the earlier account of holding the signed parcel receipt."
TARGET = "application-original:material:1"


class RawApplicationModel(PurposeModel):
    """The consequential update review is final raw wire output, with no adapter."""

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        if prompt.operation != "verify_material_grounding" or not any(
            row.get("related_material_ids") for row in payload["candidates"]
        ):
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        self.seen.append((prompt.operation, deepcopy(payload)))
        references = payload["source_treatments"]
        (candidate,) = payload["candidates"]
        row = verdict("material", references["L1"])
        row["account_check"]["source_ids"] = list(references)
        row["account_check"]["source_checks"] = [
            {
                "source_id": identity,
                "supplies_account_content": True,
                "supports_proposal": True,
                "support_spans": [{"start": 0, "end": len(reference["quoted"])}],
                "reason": ("The declared latest account and original predecessor "
                           "support this operation."),
            }
            for identity, reference in references.items()
        ]
        row["target_checks"] = [
            {
                "target_id": target,
                "identity_relation": "same_underlying_account",
                "account_preserved": True,
                "required_peer_ids": [],
                "reason": ("The original target's attributed account is retained "
                           "in the checked lineage."),
            }
            for target in candidate["related_material_ids"]
        ]
        data = {
            "verdicts": [row],
            "coverage": coverage(
                references,
                dispositions=[
                    disposition(
                        identity,
                        reference,
                        status="represented",
                        candidate_ids=("D1",) if identity == "L1" else (),
                        record_ids=() if identity == "L1" else (TARGET,),
                    )
                    for identity, reference in references.items()
                ],
            ),
        }
        require_schema(data, schema)
        return ModelResult(
            text=None,
            data=data,
            tier=tier,
            provider="offline-raw",
            model="fabricated-application-review",
            usage=Usage(0, 0, 0),
            latency_ms=0,
            completion=Completion.COMPLETE,
        )


def saved_revision(client, wired, monkeypatch, relation):
    latest = WITHDRAWN if relation == "withdraws" else CHANGED
    changed = material(
        "circumstance",
        latest,
        latest,
        relation=relation,
        scope="current",
        placement="matter",
        references=({"turn_id": "application-original", "role": "advocate", "quoted": ORIGINAL},),
        related_material_ids=(TARGET,),
    )
    follow = routed(
        latest,
        candidates=[changed],
        record_disposition="performed",
        items=[
            {
                **item(latest, latest, purposes=("account_contribution",), intent="contribution"),
                "mutation_scopes": [mutation_scope(TARGET, relations=(relation,))],
            }
        ],
    )
    model = RawApplicationModel([seed_plan(ORIGINAL), follow])
    opened = open_account(
        client, wired, monkeypatch, model, ORIGINAL, turn_id="application-original"
    )
    response = send(client, latest, "application-revision", opened=opened)
    assert response.status_code == 200, response.text
    return model, opened, latest, response.json(), wired.store.load(opened["matter_id"])


@pytest.mark.parametrize("relation", ["corrects", "withdraws"])
def test_raw_checked_revision_preserves_source_history_and_replays_without_extra_calls(
    client, wired, monkeypatch, relation
):
    model, opened, latest, reply, saved = saved_revision(client, wired, monkeypatch, relation)
    execution = reply["material_coverage"]["execution"]
    assert execution["semantic_coverage"] == "complete"
    receipt = execution["coverage_application"]
    assert receipt["pre_application_assessments"]["detail_review"]["state"] == "complete"
    coverage_after = execution["stages"]["detail_review"]["account_coverage"]
    (prior,) = [row for row in coverage_after["dispositions"] if row["source_id"] != "L1"]
    assert prior["record_ids"] == []
    assert prior["historical_representations"][0]["record_id"] == TARGET
    (latest_row,) = [row for row in coverage_after["dispositions"] if row["source_id"] == "L1"]
    if relation == "withdraws":
        assert latest_row["candidate_ids"] == []
        assert (
            latest_row["operation_representations"][0]["representation_kind"]
            == "performed_retirement"
        )
    else:
        assert latest_row["candidate_ids"] == ["D1"]
    for operation, payload in model.seen:
        if operation in ("continue_conversation", "verify_continuation"):
            original = payload.get("input", payload)
            assert "coverage_application" not in original["material_coverage"]["execution"]
    count = len(model.seen)
    replay = send(client, latest, "application-revision", opened=opened)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] and replay.json()["metrics"]["llm_calls"] == 0
    assert len(model.seen) == count and wired.store.load(opened["matter_id"]) == saved


@pytest.mark.parametrize("fault", ["missing", "result", "source", "target", "opening"])
def test_owned_application_dependency_tamper_is_refused_without_model_or_write(
    client, wired, monkeypatch, fault
):
    model, opened, latest, reply, saved = saved_revision(client, wired, monkeypatch, "withdraws")
    changed = deepcopy(saved.brain_chat)
    selected = changed[0] if fault == "opening" else changed[-1]
    execution = selected["response"]["material_coverage"]["execution"]
    receipt = execution["coverage_application"]
    if fault == "missing":
        execution.pop("coverage_application")
    elif fault == "result":
        receipt["bindings"][0]["result_id"] = TARGET
    elif fault == "source":
        receipt["bindings"][0]["review"]["account_check"]["source_checks"][0]["support_spans"][0][
            "end"
        ] = len(WITHDRAWN) + 100
    elif fault == "target":
        receipt["bindings"][0]["review"]["target_checks"][0]["target_id"] = "unowned-target"
    else:
        receipt["opening"]["result"]["title"] = "A different stored heading"
        receipt["opening"]["proposal"]["title"] = "A different stored heading"
    if fault != "missing":
        receipt["seal"] = owner._digest(
            {key: value for key, value in receipt.items() if key != "seal"}
        )
    wired.store.commit(
        replace(saved, brain_chat=changed, version=saved.version + 1),
        expected_version=saved.version,
    )
    before, count = deepcopy(wired.store.load(opened["matter_id"])), len(model.seen)
    response = send(
        client,
        ORIGINAL if fault == "opening" else latest,
        "application-original" if fault == "opening" else "application-revision",
        opened=opened,
    )
    assert response.status_code == 409, response.text
    assert len(model.seen) == count and wired.store.load(opened["matter_id"]) == before
