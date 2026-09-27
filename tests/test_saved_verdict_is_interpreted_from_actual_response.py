"""An authored STOP PASS cannot overrule the independent model's actual receipt."""
from __future__ import annotations

import pytest

from nm.legal_brain.verify.brain_assessment import saved_package_reviews
from nm.legal_brain.verify.brain_release import ReviewRefused, prepare_claims
from nm.legal_brain.orchestrate.loop_contracts import StepKind
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import response
from tests.test_reviewed_private_preview_checks_saved_words import changed_payload, replace_record

pytestmark = pytest.mark.class_a


def replay(store, brain, outcome):
    matter = store.load("mat_loop")
    return saved_package_reviews(outcome, prepare_claims(outcome, matter), matter, brain.log)


@pytest.mark.parametrize("consumer", ["assessment", "retry"])
def test_false_actual_inference_cannot_be_changed_to_a_saved_positive_stamp(tmp_path, consumer):
    store, brain, outcome, _, _ = _case(tmp_path, judged=response(inference=False))
    initial = brain.review(outcome)
    assert not initial.result.released and initial.records[0].inference.assessed is False

    def lie(saved):
        verification = saved.events[-1].payload["verification"]
        verification["inference"]["assessed"] = True
        return changed_payload(saved, len(saved.events) - 1, verification=verification)

    replace_record(store, "package-turn:verify:p1", lie)
    with pytest.raises(ReviewRefused, match="actual model response"):
        replay(store, brain, outcome) if consumer == "assessment" else brain.review(outcome)


@pytest.mark.parametrize("what", ["textual_support", "applicability", "opposition_resolved",
                                  "reason", "quoted_words", "usage", "retries", "prompt",
                                  "cost", "reserve", "tier", "downgrade", "completion"])
def test_every_positive_judgment_and_its_actual_dispatch_remain_load_bearing(tmp_path, what):
    store, brain, outcome, _, _ = _case(tmp_path)
    original = brain.review(outcome)
    assert original.records[0].releasable

    def alter(saved):
        end = saved.events[-1].payload
        verification = end["verification"]
        if what in {"textual_support", "applicability", "opposition_resolved"}:
            verification[what]["reason"] = "Authored reasoning instead of the actual response"
        elif what == "reason":
            verification["reason"] = "Authored classification"
        elif what == "quoted_words":
            verification["inference"]["supporting_words"] = ["Words never supplied"]
        elif what == "usage":
            verification["usage"]["tokens_out"] += 1
        elif what == "retries":
            verification["retries"] += 1
        elif what == "cost":
            return changed_payload(saved, len(saved.events) - 1,
                                   spend={**end["spend"],
                                          "cost_usd": end["spend"]["cost_usd"] + 0.01})
        elif what in {"prompt", "reserve"}:
            index = next(i for i, row in enumerate(saved.events)
                         if row.kind is StepKind.MODEL_STARTED)
            raw = saved.events[index].payload
            return changed_payload(saved, index, **(
                {"prompt": {**raw["prompt"], "user": "Different evidence"}}
                if what == "prompt" else {"reserved_tokens": 1}))
        else:
            index = next(i for i, row in enumerate(saved.events)
                         if row.kind is StepKind.MODEL_RETURNED)
            raw = saved.events[index].payload["result"]
            value = {**raw["value"], **{
                "tier": {"tier": "routine"},
                "downgrade": {"downgraded_from": "judge"},
                "completion": {"completion": "length_limited"},
            }[what]}
            return changed_payload(saved, index, result={"kind": "ModelResult", "value": value})
        return changed_payload(saved, len(saved.events) - 1, verification=verification)

    replace_record(store, "package-turn:verify:p1", alter)
    with pytest.raises(ReviewRefused):
        replay(store, brain, outcome)


def test_genuine_positive_replay_uses_the_same_pure_live_owner_without_new_calls(tmp_path):
    store, brain, outcome, judge, _ = _case(tmp_path)
    original = brain.review(outcome)
    judge.structured = lambda *_args, **_kwargs: pytest.fail("No replay dispatch")
    assert replay(store, brain, outcome) == original
    assert brain.review(outcome) == original
    assert len(judge.prompts) == 1
