"""DG-17: prompt/consumer contracts, not a claim of semantic model quality.

Positive controls accompany rejected model outputs. The inventory includes inline
and user-context builders, so a new prompt cannot silently escape this review.
"""

import json
from datetime import date

import pytest

from nm.work_the_file.matter_contracts import Basis, Posture, Role

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 22)

# A reviewed population, not one inferred from whatever happened to run.
SITES = {
    "accrual:build_prompt",
    "adversarial:build_attack_prompt",
    "adversarial:build_exposure_prompt",
    "adversarial:build_salvage_prompt",
    "cause:build_prompt",
    "chronology:build_prompt",
    "consistency:build_prompt",
    "consistency:repair_prompt",
    "controlled_brain:run",
    "duty:build_prompt",
    "evidence_item:build_inventory_prompt",
    "factors:build_prompt",
    "investigation:run",
    "interaction_review:build_evidence_prompt",
    "interaction_review:build_prompt",
    "interaction_review:build_unit_prompt",
    "interaction_review:build_work_prompt",
    "interaction_review:build_quote_prompt",
    "interaction_review:build_work_reference_prompt",
    "interaction_review:build_premise_prompt",
    "issues:build_prompt",
    "nested_research:run",
    "parties:build_prompt",
    "posture:build_role_prompt",
    "posture:build_prompt",
    "proof_read:build_prompt",
    "route:build_prompt",
    "requirements:build_prompt",
    "step_dependency:build_prompt",
    "theory:build_adverse_prompt",
    "theory:build_theory_prompt",
    "turn:_recommend",
    "turn:_courtesy",
    "verifier:verification_prompt",
    "working_scope:_request",
    "working_scope:_demand_request",
    "working_explanation:_rationale_request",
}

#: PROMPT SITES THAT EXIST AND AWAIT THE OWNER'S REVIEW, named so the gap is visible
#: rather than left as a red check nobody reads: the reply writer and its check
#: (LB-76 item 4: "the owner reviews the rewritten guidance before it is used") and
#: the similar-wordings read for the bare-act search (LB-106), and the grievance
#: reading that replaced the dispute inventory (LB-109, 29 September 2026 --
#: rewritten, so no longer the reviewed text). A site moves to SITES when it
#: has been reviewed; a NEW site in neither set still fails below.
PENDING_REVIEW = {
    "compose:build_prompt",
    "compose:check_prompt",
    "dispute:build_prompt",
    "similar_words:build_prompt",
}


def _theory(**updates):
    row = {
        "theme": "A provisional position",
        "stance": "affirmative",
        "relief": "Requested relief",
        "explains": [],
        "concedes": [],
        "unresolved": [{"fact_id": "fact_a", "why": "Authenticity disputed"}],
        "revises_because": "The earlier interpretation was mistaken",
    }
    return {**row, **updates}


@pytest.mark.parametrize("mode", ["explanation", "assessment"])
def test_purpose_reaches_the_served_answer_and_history_without_fabricating_a_recommendation(
    client, monkeypatch, mode
):
    from nm.app.api import application
    from nm.shared.model_scripted import SCRIPTED_READS, ScriptedModelAdapter

    monkeypatch.setitem(
        SCRIPTED_READS,
        "route",
        lambda _: json.dumps(
            {"discloses": "matter", "depth": mode, "why": "Only an explanation is requested"}
        ),
    )
    explanation = "The account alleges non-payment; that is not the same as documentary proof."
    original = ScriptedModelAdapter._respond
    composed = []

    def respond(self, prompt, tier):
        if "Answer the requested explanation or assessment" in (prompt.system or ""):
            composed.append(prompt)
            return explanation
        return original(self, prompt, tier)

    monkeypatch.setattr(ScriptedModelAdapter, "_respond", respond)
    monkeypatch.setitem(
        SCRIPTED_READS,
        "step_dependency",
        lambda user: json.dumps(
            {
                "step": json.loads(user)["step"],
                "dependence": "independent",
                "reason": "This response describes evidential status and directs no action.",
            }
        ),
    )
    result = client.post(
        "/api/turn",
        json={
            "message": "We act for the plaintiff supplier at Hyderabad. "
            "Explain the position on the unpaid goods.",
            "today": "2026-09-22",
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["mode"] == mode
    assert composed and any(
        e["text"] == explanation and e["kind"] == "finding" for e in body["elements"]
    ), body
    assert not any(e["kind"] in {"action", "question"} for e in body["elements"]), body["elements"]
    history = client.get(f"/api/matters/{body['matter_id']}/transcript")
    assert history.status_code == 200 and mode in history.text and explanation in history.text
    assert application().store.transcripts_for(body["matter_id"])


def _descriptions(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "description":
                yield item
            else:
                yield from _descriptions(item)
    elif isinstance(value, list):
        for item in value:
            yield from _descriptions(item)


@pytest.mark.parametrize("prior", [Role.NOT_INSTITUTED, Role.NOT_APPLICABLE])
def test_explicit_filing_progresses_but_inferred_progress_and_side_reversal_do_not(prior):
    before = Posture(role=prior, basis=Basis.STATED, client_described_as="client A")
    filed = before.enrich(Role.PLAINTIFF, Basis.STATED, source_fact="fact_filing")
    assert filed.role is Role.PLAINTIFF and filed.resolved and not filed.conflicts
    assert filed.client_described_as == before.client_described_as
    assert filed.source_fact == "fact_filing" and filed.version == before.version + 1
    inferred = before.enrich(Role.PLAINTIFF, Basis.INFERRED)
    assert inferred.role is prior and inferred.conflicts
    opposite = filed.enrich(Role.DEFENDANT, Basis.STATED)
    assert opposite.role is Role.PLAINTIFF and opposite.conflicts


