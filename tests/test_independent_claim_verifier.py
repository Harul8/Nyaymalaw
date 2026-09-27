"""The independent verifier cannot turn citation accuracy into applied legal truth."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from nm.legal_brain.retrieve.evidence_port import (
    Binding,
    Finding,
    ParaKind,
    SourceKind,
    Treatment,
    TreatmentState,
)
from nm.legal_brain.verify.verifier import (
    EvidencePackage,
    EvidenceSpan,
    IndependentVerifier,
    release_verified,
)
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import ProviderUnavailable, Tier
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.work_the_file.matter_contracts import Certainty, Fact, FactBasis, Provenance

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


def package(**updates):
    fields = dict(
        id="claim_1",
        claim="The benefit is available.",
        spans=(EvidenceSpan.from_finding("span_1", finding()),),
        premises=(premise(),),
        author_label="textual",
    )
    fields.update(updates)
    return EvidencePackage(**fields)


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


def verify(subject, judge=None, **updates):
    judge = judge or Judge()
    fields = dict(
        author_provider="scripted",
        author_model="scripted:scripted-author",
        retrieved=tuple(span.finding for span in (*subject.spans, *subject.contrary)),
    )
    fields.update(updates)
    return IndependentVerifier(judge).verify(subject, **fields)


def test_an_unassessed_candidate_can_be_independently_read_without_fabricating_support():
    source = finding(supports=None)
    assert not source.usable and source.blocking_reason
    assert source.source_blocking_reason is None and source.supports is None
    subject = package(spans=(EvidenceSpan.from_finding("span_1", source),))
    result = verify(subject)
    assert result.releasable and source.supports is None


def test_known_unsupported_source_never_gets_a_second_pass_to_relabel_it_sound():
    source = finding(supports=False)
    judge = Judge()
    result = verify(package(spans=(EvidenceSpan.from_finding("span_1", source),)), judge)
    assert not result.releasable and not judge.prompts


@pytest.mark.parametrize(
    "updates",
    [
        {"valid_to": date(2020, 1, 1)},
        {"valid_from": date(2030, 1, 1)},
        {
            "source_kind": SourceKind.AUTHORITY,
            "para_kind": ParaKind.ATTRIBUTABLE,
            "binding": Binding.NOT_ASSESSED,
        },
        {
            "source_kind": SourceKind.AUTHORITY,
            "para_kind": ParaKind.ATTRIBUTABLE,
            "treatment": Treatment.not_checked("No treatment registry"),
        },
        {
            "source_kind": SourceKind.AUTHORITY,
            "para_kind": ParaKind.ATTRIBUTABLE,
            "treatment": Treatment(TreatmentState.NEGATIVE, "This proposition", ("overruled",)),
        },
    ],
)
def test_semantic_unknown_does_not_hide_a_separate_source_boundary(updates):
    source = finding(**updates)
    assert source.source_blocking_reason
    judge = Judge()
    record = verify(package(spans=(EvidenceSpan.from_finding("span_1", source),)), judge)
    assert not record.releasable and not judge.prompts


def test_attribution_is_refused_by_the_existing_source_type_not_a_second_classifier():
    with pytest.raises(ValueError, match="paragraph"):
        finding(source_kind=SourceKind.AUTHORITY, para_kind=ParaKind.NOT_ATTRIBUTABLE)


def test_a_real_source_for_the_wrong_proposition_is_refused():
    subject = package(claim="The certificate removes the notice requirement.")
    record = verify(subject, Judge(response(support=False)))
    assert record.textual_support.assessed is False and not record.releasable


def test_correct_premises_do_not_certify_an_invalid_final_inference():
    subject = package()
    record = verify(subject, Judge(response(inference=False)))
    assert record.textual_support.assessed is True
    assert record.applicability.assessed is True
    assert record.inference.assessed is False and not record.releasable
    assert not release_verified((subject,), (record,)).released


@pytest.mark.parametrize("label", ["textual", "background", "general information", "quotation", ""])
def test_author_labels_cannot_skip_applied_assessment_checks(label):
    subject = package(author_label=label)
    record = verify(subject, Judge(response(textual=True, inference=False)))
    assert record.textual_eligible is False and not record.releasable


def test_only_an_independently_classified_self_contained_text_report_needs_support_alone():
    subject = package(claim="The retrieved rule says that a benefit requires notice.", premises=())
    record = verify(
        subject, Judge(response(textual=True, applies=None, inference=None, opposition=None))
    )
    assert record.releasable
    assert release_verified((subject,), (record,)).released == (subject,)


def test_missing_classification_never_becomes_a_textual_bypass():
    subject = package(premises=())
    record = verify(subject, Judge(response(textual=None)))
    assert not record.releasable


def test_the_same_model_cannot_grade_its_own_output_before_dispatch():
    subject, judge = package(), Judge()
    record = verify(subject, judge, author_model=judge.resolved_model(Tier.JUDGE))
    assert not record.releasable and not judge.prompts
    assert "own claim" in record.reason


def test_an_unavailable_verifier_withholds_decisive_conclusion_and_dependants_not_everything():
    bad = package(id="bad", claim="The benefit is available; verify independently before use.")
    child = package(id="child", dependencies=("bad",))
    safe = package(id="safe", claim="The retrieved rule requires notice.", premises=())
    failed = verify(bad, Judge(error=ProviderUnavailable("offline")))
    supported_child = verify(child)
    independent = verify(safe, Judge(response(textual=True)))
    release = release_verified((bad, child, safe), (failed, supported_child, independent))
    assert release.released == (safe,)
    assert {id for id, _ in release.withheld} == {"bad", "child"}


def test_partial_support_never_releases_the_whole_claim_with_a_disclaimer():
    subject = package(
        claim="The benefit is available and enforcement is certain, subject to review."
    )
    record = verify(subject, Judge(response(support=False)))
    assert not release_verified((subject,), (record,)).released


def test_material_opposition_is_independent_of_support_and_applicability():
    subject = package()
    record = verify(subject, Judge(response(opposition=False)))
    assert record.textual_support.assessed and record.applicability.assessed
    assert record.opposition_resolved.assessed is False and not record.releasable


def test_changed_claim_and_source_version_stale_the_previous_verification():
    subject = package()
    record = verify(subject)
    changed = replace(subject, claim="A different conclusion.")
    assert not release_verified((changed,), (record,)).released
    changed_source = replace(subject.spans[0].finding, binding_reason="A different binding basis")
    changed = replace(subject, spans=(EvidenceSpan.from_finding("span_1", changed_source),))
    assert not release_verified((changed,), (record,)).released


@pytest.mark.parametrize(
    "updates",
    [
        {"confirmed": False},
        {"conflicts_with": ("other",)},
        {"superseded_by": "later"},
    ],
)
def test_unsettled_premises_are_not_treated_as_established(updates):
    judge = Judge()
    record = verify(package(premises=(premise(**updates),)), judge)
    assert not record.releasable and not judge.prompts


def test_the_judge_sees_the_evidence_not_the_authors_label_or_conversation():
    subject, judge = package(author_label="Author says this is surely correct"), Judge()
    verify(subject, judge)
    payload = json.loads(judge.prompts[0].user)
    assert "author_label" not in payload and "conversation" not in payload
    assert payload["premises"][0]["statement"] == subject.premises[0].statement
    assert payload["sources"][0]["text"] == RULE


def test_verifier_cannot_invent_the_words_it_relies_on():
    record = verify(package(), Judge(response(words="words not present anywhere")))
    assert not record.releasable and record.textual_support.assessed is None
    assert record.usage is not None and record.usage.tokens_in > 0


def test_confirmation_preserves_assertion_status_and_does_not_certify_a_documented_finding():
    asserted = premise(
        confirmed=True, certainty=Certainty.ASSERTED, basis=FactBasis.DIRECT_KNOWLEDGE
    )
    subject = package(premises=(asserted,))
    judge = Judge(response(inference=False))
    record = verify(subject, judge)
    supplied = json.loads(judge.prompts[0].user)["premises"][0]
    assert supplied == json.loads(json.dumps(subject.payload()["premises"][0]))
    assert supplied["certainty"] == Certainty.ASSERTED.value
    assert supplied["basis"] == FactBasis.DIRECT_KNOWLEDGE.value
    assert asserted.certainty is Certainty.ASSERTED and not record.releasable


def test_conditional_analysis_can_use_a_confirmed_account_without_promoting_its_status():
    asserted = premise(
        confirmed=True, certainty=Certainty.ASSERTED, basis=FactBasis.DIRECT_KNOWLEDGE
    )
    subject = package(
        claim="On the confirmed account, notice would still be required.", premises=(asserted,)
    )
    record = verify(subject)
    assert record.releasable and subject.premises[0] is asserted
    assert asserted.certainty is Certainty.ASSERTED


def test_current_unconfirmed_allegation_can_be_reasoned_about_conditionally_without_upgrade():
    asserted = premise(confirmed=None, certainty=Certainty.ASSERTED,
                       basis=FactBasis.NOT_ASSESSED)
    subject = package(claim="If the reported certificate is held, notice would still be required.",
                      premises=(asserted,))
    judge = Judge()
    record = verify(subject, judge)
    supplied = json.loads(judge.prompts[0].user)["premises"][0]
    assert record.releasable and record.textual_eligible is False
    assert supplied["confirmed"] is None and supplied["certainty"] == "asserted"
    assert asserted.confirmed is None and asserted.certainty is Certainty.ASSERTED
    assert "unconfirmed current advocate allegation" in judge.prompts[0].system


def test_categorical_upgrade_of_unconfirmed_allegation_needs_a_sound_inference_not_a_label():
    subject = package(claim="The certificate is documented and conclusively establishes service.",
                      premises=(premise(confirmed=None),))
    record = verify(subject, Judge(response(textual=True, inference=False)))
    assert record.textual_eligible is False and not record.releasable
    assert not release_verified((subject,), (record,)).released


def test_the_default_scripted_verifier_never_supplies_an_expert_assessment():
    cfg = ModelConfig({Tier.JUDGE: TierConfig(Tier.JUDGE, "scripted", "judge", None, None)})
    record = verify(package(), ScriptedModelAdapter(cfg))
    assert not record.releasable and record.textual_eligible is None
    assert record.textual_support.assessed is None


def test_a_package_cannot_substitute_a_source_that_was_not_retrieved():
    judge = Judge()
    record = verify(package(), judge, retrieved=())
    assert not record.releasable and not judge.prompts


def test_quote_and_citation_controls_reuse_the_existing_grounding_detector():
    judge = Judge()
    record = verify(
        package(claim='The rule states "A fabricated quotation which sounds plausible".'), judge
    )
    assert not record.releasable and not judge.prompts
    record = verify(package(claim="Section 999 grants this benefit."), judge)
    assert not record.releasable and not judge.prompts


def test_a_quote_elsewhere_in_the_same_document_is_not_in_the_submitted_minimum_window():
    source = finding()
    first = source.span.index(".") + 1
    subject = package(
        claim='The rule says "A certificate alone does not establish service".',
        spans=(EvidenceSpan("narrow", source, 0, first),),
    )
    judge = Judge()
    record = verify(subject, judge)
    assert not record.releasable and not judge.prompts


def test_admission_and_receipt_callbacks_surround_only_actual_judge_dispatch():
    subject, judge, events = package(), Judge(), []
    result = IndependentVerifier(judge).verify(
        subject,
        author_provider="scripted",
        author_model="other-author",
        retrieved=(subject.spans[0].finding,),
        before_dispatch=lambda prompt, tier, ceiling: events.append(
            ("start", prompt.operation, tier, ceiling)
        ),
        after_dispatch=lambda response: events.append(("result", response.model)),
    )
    assert result.releasable
    assert events == [
        ("start", "independent_claim_verification", Tier.JUDGE, 2048),
        ("result", judge.resolved_model(Tier.JUDGE)),
    ]
    events.clear()
    result = IndependentVerifier(judge).verify(
        subject,
        author_provider="scripted",
        author_model=judge.resolved_model(Tier.JUDGE),
        retrieved=(subject.spans[0].finding,),
        before_dispatch=lambda *_: events.append("must not dispatch"),
    )
    assert not result.releasable and events == []


def test_callback_programming_faults_propagate_and_do_not_become_unavailable_models():
    subject, judge = package(), Judge()

    def fault(*_):
        raise KeyError("journal integrity failed")

    with pytest.raises(KeyError, match="journal integrity"):
        IndependentVerifier(judge).verify(
            subject,
            author_provider="scripted",
            author_model="different-author",
            retrieved=(subject.spans[0].finding,),
            before_dispatch=fault,
        )
    assert not judge.prompts


@pytest.mark.parametrize("changed", ["model", "provider", "tier", "downgrade"])
def test_the_returned_judge_identity_cannot_silently_change_or_self_grade(changed):
    class Drifted(Judge):
        def structured(self, *args, **kwargs):
            result = super().structured(*args, **kwargs)
            change = {
                "model": {"model": "different-author"},
                "provider": {"provider": "different-provider"},
                "tier": {"tier": Tier.ROUTINE},
                "downgrade": {"downgraded_from": Tier.JUDGE},
            }[changed]
            return replace(result, **change)

    record = verify(package(), Drifted(), author_model="different-author")
    assert not record.releasable and record.usage is not None


def test_model_failures_are_recorded_only_after_a_dispatch_with_exact_receipts():
    from nm.shared.model_port import Usage

    usage = Usage(22, 11, 0.01)
    error = ProviderUnavailable("lost response", usage=usage, retries=2)
    subject, events = package(), []
    record = IndependentVerifier(Judge(error=error)).verify(
        subject,
        author_provider="scripted",
        author_model="different-author",
        retrieved=(subject.spans[0].finding,),
        before_dispatch=lambda *_: events.append("start"),
        on_error=lambda exc: events.append((type(exc).__name__, exc.usage, exc.retries)),
    )
    assert not record.releasable and record.usage == usage
    assert events == ["start", ("ProviderUnavailable", usage, 2)]


def test_missing_dependency_and_cycles_are_not_clean_partial_releases():
    one = package(id="one", dependencies=("two",))
    two = package(id="two", dependencies=("one",))
    assert not release_verified((one,), (verify(one),)).released
    assert not release_verified((one, two), (verify(one), verify(two))).released


def test_an_empty_release_population_cannot_certify_anything():
    with pytest.raises(ValueError, match="population"):
        release_verified((), ())
