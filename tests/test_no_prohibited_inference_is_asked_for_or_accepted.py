"""MEDIA ADMISSION IS THE ONLY REASONING INPUT. BK-69-AC3. P15.

THE RULE, stated without the vendor that exposed it
-----------------------------------------------------
**A product may not ask a processor to infer who somebody is from their voice
or face, how they felt, or whether they seemed truthful -- and may not accept
such an inference if one comes back unasked.**

The second half is the one that gets missed. A vendor returns a `confidence`
or `sentiment` field beside the transcript, somebody surfaces it because it
looks like metadata, and the product is now telling an advocate that a witness
sounded untruthful. That is not evidence and no advocate asked for it.

WHAT IS ASSERTED
------------------
    the contract is READ, not restated, and an unreadable one refuses
    every prohibited operation is refused before any bytes leave
    unavoidable background processing rejects the ROUTE, not just the request
    an unknown operation or configuration is denied rather than assumed benign
    consent does not override the prohibition
    a nested prohibited field is rejected wherever it is buried
    THE REJECTED VALUE IS NEVER IN THE REFUSAL
    permitted transcription, translation and local diarisation still work
"""
from __future__ import annotations

import pathlib

import pytest

from nm.domain.media_policy import (
    ContractUnreadable,
    Route,
    load,
    refuse_request,
    refuse_response,
)

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = load(ROOT)

#: What a transcription response is allowed to carry. Deliberately small.
TRANSCRIPT_SHAPE = ("transcript", "segments", "text", "start", "end",
                    "speaker_label", "language")


# ========================= the contract is the owner ========================

def test_the_operation_lists_are_read_from_the_blueprint():
    """Copying five prohibited operations into Python would make two lists
    that must agree, and the one that drifts is whichever is read less."""
    assert "voiceprint_creation_or_matching" in CONTRACT.prohibited
    assert "affect_emotion" in CONTRACT.prohibited
    assert "credibility_from_voice_or_appearance" in CONTRACT.prohibited
    assert "transcription" in CONTRACT.allowed
    assert not (CONTRACT.prohibited & CONTRACT.allowed)


def test_an_unreadable_contract_refuses_rather_than_permitting_everything(
        tmp_path):
    """An empty allowlist that permitted everything would be the absent-input
    defect holding the one control that keeps biometrics out of a legal file."""
    with pytest.raises(ContractUnreadable):
        load(tmp_path)


def test_the_policy_module_does_not_restate_the_lists():
    """One owner. A literal list of the prohibited operations in this module
    would be the second copy."""
    source = (ROOT / "nm" / "domain" / "media_policy.py").read_text(
        encoding="utf8")
    body = source.split('"""', 2)[-1]          # past the module docstring
    for operation in ("voice_identity", "voiceprint_creation_or_matching",
                      "affect_emotion"):
        assert f'"{operation}"' not in body, (
            f"{operation} is written into the module rather than read from "
            f"the contract")


# ============================ the request side ==============================

@pytest.mark.parametrize("operation", sorted(CONTRACT.prohibited))
def test_every_prohibited_operation_is_refused_before_any_bytes_leave(operation):
    """Checking the answer is too late -- the recording has already been sent
    to a processor that may retain it."""
    refused = refuse_request(Route("vendor-x", (operation,)), CONTRACT)
    assert refused, operation
    assert any(operation in reason for reason in refused)


@pytest.mark.parametrize("operation", sorted(CONTRACT.allowed))
def test_every_allowed_operation_is_permitted(operation):
    """THE NEGATIVE CONTROL. A policy that refused everything would satisfy
    each refusal above and the product would transcribe nothing."""
    assert refuse_request(Route("vendor-z", (operation,)), CONTRACT) == []


def test_unavoidable_background_processing_rejects_the_route(self=None):
    """CHOICE-05 approves the selected operation AND ITS CONFIGURATION. A
    vendor whose transcription always runs emotion scoring is offering a
    prohibited operation with the word 'optional' in front of it."""
    refused = refuse_request(
        Route("vendor-y", ("transcription",), unavoidable=("affect_emotion",)),
        CONTRACT)
    assert refused
    assert any("route is rejected" in reason for reason in refused)


def test_an_unrelated_optional_vendor_service_is_not_disqualifying():
    """The contract says so explicitly: `unrelated_optional_vendor_services:
    not_disqualifying`. Refusing a vendor because it SELLS something else
    would be an opinion about their catalogue, not about this route."""
    assert refuse_request(
        Route("vendor-z", ("transcription",), note="also sells face search"),
        CONTRACT) == []


def test_an_unknown_operation_is_denied_rather_than_assumed_benign():
    refused = refuse_request(Route("vendor-z", ("mood_summary",)), CONTRACT)
    assert refused and "not in the approved set" in refused[0]


def test_a_route_that_names_no_operation_is_denied():
    """The contract's default is deny; an unnamed operation cannot have been
    approved."""
    assert refuse_request(Route("vendor-z", ()), CONTRACT)


def test_an_unknown_configuration_is_denied():
    refused = refuse_request(
        Route("vendor-z", ("transcription",), configuration_known=False),
        CONTRACT)
    assert refused and "not established" in refused[0]


def test_consent_does_not_override_the_prohibition():
    """The prohibition is about what the product may infer and hold, not only
    about what a person agreed to."""
    refused = refuse_request(
        Route("vendor-x", ("voice_identity",), consent_given=True), CONTRACT)
    assert refused
    assert any("consent does not override" in reason for reason in refused)
    assert CONTRACT.consent_overrides is False


def test_a_refusal_names_the_operation_and_not_the_material():
    """The material has not been sent and must not be quoted into a refusal
    either."""
    for reason in refuse_request(
            Route("vendor-x", ("voiceprint_creation_or_matching",)), CONTRACT):
        assert "recording" not in reason.lower() or "recording_local" in reason


# ============================ the response side =============================

def test_a_clean_transcript_is_accepted():
    """The negative control for every rejection below."""
    verdict = refuse_response(
        {"transcript": "the goods were delivered",
         "segments": [{"text": "the goods", "start": 0, "end": 2}]},
        TRANSCRIPT_SHAPE, CONTRACT)
    assert verdict.clean
    assert verdict.accepted["transcript"] == "the goods were delivered"


def test_a_nested_prohibited_field_is_rejected_wherever_it_is_buried():
    """The field carrying an emotion score sits three levels down inside an
    object whose top-level keys all look ordinary."""
    verdict = refuse_response(
        {"transcript": "x",
         "segments": [{"text": "a"},
                      {"text": "b", "speaker_emotion": "distressed"}]},
        TRANSCRIPT_SHAPE, CONTRACT)
    assert not verdict.clean
    assert verdict.rejected_paths == ("segments[1].speaker_emotion",)


def test_the_rejected_value_never_appears_in_the_verdict():
    """THE POINT. A log line saying *rejected `speaker_emotion` =
    'distressed'* has persisted the exact inference the rejection existed to
    prevent, into a sink the contract lists as protected."""
    secret = "sounded evasive and untruthful"
    verdict = refuse_response(
        {"transcript": "x", "credibility": secret}, TRANSCRIPT_SHAPE, CONTRACT)
    assert not verdict.clean
    blob = " ".join((*verdict.rejected_paths, *verdict.reasons,
                     repr(verdict.accepted)))
    assert secret not in blob
    assert "evasive" not in blob
    assert CONTRACT.persist_rejected is False


def test_nothing_downstream_receives_a_payload_that_had_a_rejected_field():
    """`reject_before_downstream`. Returning the clean half of a payload that
    also carried a prohibited inference would let the rest through while the
    verdict said it had been refused."""
    verdict = refuse_response(
        {"transcript": "x", "speaker_emotion": "angry"},
        TRANSCRIPT_SHAPE, CONTRACT)
    assert verdict.accepted == {}


def test_an_unknown_field_is_rejected_rather_than_ignored():
    """A closed allowlist. `unknown_or_forbidden_fields:
    reject_before_downstream` makes no distinction between the two."""
    verdict = refuse_response(
        {"transcript": "x", "vendor_scratch": {"anything": 1}},
        TRANSCRIPT_SHAPE, CONTRACT)
    assert "vendor_scratch" in verdict.rejected_paths


def test_a_deeply_nested_unknown_field_is_still_found():
    verdict = refuse_response(
        {"segments": [{"text": "a", "start": 0,
                       "end": 1}]},
        ("segments", "text", "start", "end"), CONTRACT)
    assert verdict.clean
    buried = refuse_response(
        {"segments": [{"text": "a", "meta": {"deep": {"affect_emotion": 0.9}}}]},
        ("segments", "text"), CONTRACT)
    assert buried.rejected_paths == ("segments[0].meta",)


def test_the_protected_sinks_include_logs_and_reasoning():
    """Naming them is what makes 'do not log the value' a rule rather than an
    instinct."""
    assert {"logs", "reasoning", "storage"} <= CONTRACT.protected_sinks


# ===================== what must keep working ===============================

def test_attribution_is_not_authentication():
    """`attribution_is_authentication: false`. A speaker label from local
    diarisation says which channel spoke, not who the person is -- and
    treating the first as the second is identity inference by another name."""
    import json

    document = json.loads(
        (ROOT / "docs" / "blueprint" / "evaluations.json").read_text("utf8"))

    def find(node):
        if isinstance(node, dict):
            if "attribution_is_authentication" in node:
                return node["attribution_is_authentication"]
            for value in node.values():
                found = find(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = find(item)
                if found is not None:
                    return found
        return None

    assert find(document) is False


def test_recording_local_diarisation_and_user_confirmed_attribution_survive():
    """The prohibition is on inferring identity, not on organising a
    recording or on recording what a person told you."""
    for operation in ("recording_local_diarisation",
                      "user_confirmed_attribution"):
        assert refuse_request(Route("v", (operation,)), CONTRACT) == []


def test_evidence_based_legal_assessment_is_not_prohibited():
    """Ordinary assessment of what a document says remains the product's job;
    it is inference from a VOICE OR FACE that is out."""
    assert refuse_request(
        Route("v", ("evidence_based_legal_assessment",)), CONTRACT) == []
