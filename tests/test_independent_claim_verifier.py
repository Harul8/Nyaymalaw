"""The independent verifier cannot turn citation accuracy into applied legal truth."""

from __future__ import annotations

from datetime import date

import pytest

from nm.Archives.legal_brain.retrieve.evidence_port import (
    Binding,
    Finding,
    ParaKind,
    SourceKind,
    Treatment,
)
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import Tier
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.work_the_file.matter_contracts import Fact, FactBasis, Provenance

pytestmark = pytest.mark.class_a

RULE = "A benefit requires notice. A certificate alone does not establish service."


def finding(**updates):
    fields = dict(
        proposition="A benefit requires notice",
        source_kind=SourceKind.PROVISION,
        ref="Recorded primary rule",
        span=RULE,
        locator="held:rule:1",
        store="held",
        binding=Binding.BINDING,
        binding_for="Recorded jurisdiction",
        binding_reason="Recorded primary instrument",
        supports=None,
        para_kind=ParaKind.UNKNOWN,
        treatment=Treatment.statutory(),
        valid_from=date(2000, 1, 1),
        governing_date=date(2026, 1, 1),
    )
    fields.update(updates)
    return Finding(**fields)


def premise(**updates):
    fields = dict(
        id="fact_1",
        statement="A certificate is held.",
        provenance=Provenance("advocate_statement", "turn_1", span="A certificate is held."),
        confirmed=True,
        basis=FactBasis.DIRECT_KNOWLEDGE,
    )
    fields.update(updates)
    return Fact(**fields)


def response(
    *,
    textual=False,
    support=True,
    applies=True,
    inference=True,
    opposition=True,
    words="A benefit requires notice",
):
    def judgment(value):
        return {
            "reason": "Short evidence-based assessment",
            "supporting_words": [words],
            "assessed": value,
        }

    return {
        "classification_reason": "Read the actual claim and dependencies",
        "textual_eligible": textual,
        "textual_support": judgment(support),
        "applicability": judgment(applies),
        "inference": judgment(inference),
        "opposition_resolved": judgment(opposition),
    }


class Judge(ScriptedModelAdapter):
    def __init__(self, answer=None, error=None):
        cfg = ModelConfig(
            {Tier.JUDGE: TierConfig(Tier.JUDGE, "scripted", "scripted-judge", None, None)}
        )
        super().__init__(cfg, structured_responses={"claim_verification": answer or response()})
        self.prompts, self.error = [], error

    def structured(self, prompt, schema, tier, **kwargs):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return super().structured(prompt, schema, tier, **kwargs)


def test_attribution_is_refused_by_the_existing_source_type_not_a_second_classifier():
    with pytest.raises(ValueError, match="paragraph"):
        finding(source_kind=SourceKind.AUTHORITY, para_kind=ParaKind.NOT_ATTRIBUTABLE)


