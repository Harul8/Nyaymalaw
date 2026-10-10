"""Source fixture transport preserves authored roles and malformed adversaries."""
from copy import deepcopy

import pytest

from tests.brain_reader_fixture import source_portion_reply, source_treatment_reply


def payload():
    return {
        "source_selection_contract": "owned_substantive_spans_v2",
        "source_ids": ["L1"],
        "original_source_catalogue": {
            "L1": {"turn_id": "current", "role": "advocate",
                   "quoted": "Review this unadopted draft; do not make it my account."},
        },
    }


@pytest.mark.parametrize("role", [
    "reported_matter_account", "reported_party_position", "mixed",
    "examination_material", "work_instruction", "nm_interpretation", "uncertain",
])
def test_portions_follow_declared_roles_without_reading_content(role):
    original = payload()
    reply = {"source_treatments": {"L1": {
        "content_role": role, "reason": "Explicit scenario annotation.",
    }}}
    before = deepcopy(reply)
    result = source_portion_reply(original, reply)
    expected = ([{"start": 0, "end": len(original["original_source_catalogue"]["L1"]["quoted"])}]
                if role in ("reported_matter_account", "reported_party_position", "mixed") else [])
    assert result["source_treatments"]["L1"]["substantive_spans"] == expected
    assert reply == before
    assert result["source_treatments"]["L1"]["content_role"] == role


@pytest.mark.parametrize("spans", [[], [{"start": -1, "end": 1}],
                                  [{"start": 0, "end": 1000}], "not a list"])
def test_explicit_ranges_remain_unchanged_for_owner_validation(spans):
    reply = {"source_treatments": {"L1": {
        "content_role": "reported_matter_account", "reason": "Authored attack.",
        "substantive_spans": spans,
    }}}
    assert source_portion_reply(payload(), reply) == reply


def test_foreign_sources_and_malformed_shapes_remain_unmodified():
    foreign = {"source_treatments": {"foreign": {
        "content_role": "reported_matter_account", "reason": "Unowned attack.",
    }}}
    assert source_portion_reply(payload(), foreign) == foreign
    wrong_shape = {"source_treatments": [{"source_id": "L1"}]}
    assert source_portion_reply(payload(), wrong_shape) == wrong_shape


def test_legacy_payload_is_not_recertified_and_correction_uses_original_catalogue():
    reply = {"source_treatments": {"L1": {
        "content_role": "reported_matter_account", "reason": "Explicit annotation.",
    }}}
    assert source_portion_reply({"source_ids": ["L1"]}, reply) == reply
    assert source_portion_reply({"original_input": payload()}, reply) == source_portion_reply(
        payload(), reply)


def test_ordinary_classifier_helper_keeps_signature_and_authors_fresh_ranges():
    result = source_treatment_reply("classify_account_sources", payload())
    assert result["source_treatments"]["L1"]["substantive_spans"] == [{
        "start": 0, "end": len(payload()["original_source_catalogue"]["L1"]["quoted"]),
    }]
    assert source_treatment_reply("classify_account_sources", {"original_input": payload()}) == result
    assert source_treatment_reply("reconsider_account_sources", payload()) is None
