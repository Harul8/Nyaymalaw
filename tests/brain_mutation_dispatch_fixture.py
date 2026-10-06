"""Full immutable dispatch context for offline mutation presentation tests."""
import json
from copy import deepcopy

from nm.brain.conversation import Conversation, Message
from nm.brain.mutation_contracts import (
    AUTHORITY_CONTRACT,
    authorize_mutation,
    build_mutation_authorities,
    validate_saved_mutation_authority,
)
from tests.brain_reader_fixture import scripted_source_treatments
from tests.test_brain_continuation import conversation_plan
from tests.test_brain_continuation_record_outcome import evidence, material, no_record_requirement


def context(*, repeats=1):
    original = (
        "The client reports an earlier uncertain event and retains the original signed account. "
        * repeats
    )
    latest = "I have a signed receipt. Explain the original account."
    conversation = Conversation((
        Message("first", "advocate", original),
        Message("first", "nm", "The earlier reading remains an NM interpretation."),
    ), current_matter_id="matter")
    treatments = scripted_source_treatments(
        conversation.messages, latest, roles={"L2": "work_instruction"}, turn_id="current")
    receipt = evidence(record_requirement=no_record_requirement())
    packet = material(receipt)
    packet["rows"][0]["statement"] = original
    targets = {row["id"]: deepcopy(row) for row in packet["rows"]}
    source_catalogue = deepcopy(treatments)
    grant = build_mutation_authorities(
        owner=receipt["owner"], expected_version=receipt["expected_version"],
        target_catalogue=targets, source_catalogue=source_catalogue,
        request_indices=[0], proposals=[{
            "request_index": 0, "authority_kind": "interpretation_review",
            "authority_source_ids": ["L2"], "target_scope": "exact",
            "target_ids": ["saved-observation"], "permitted_relations": ["corrects"],
        }])
    support = next(identity for identity, value in source_catalogue.items()
                   if value["turn_id"] == "first")
    reference = {name: source_catalogue["L2"][name] for name in ("turn_id", "role", "quoted")}
    binding = authorize_mutation(
        ledger=grant, owner=receipt["owner"], snapshot_version=receipt["expected_version"],
        authority_ids=[grant["authorities"][0]["id"]], relation="corrects",
        target_ids=["saved-observation"], current_source_reference=reference,
        supporting_source_ids=[support], attached_context_source_ids=[support])
    receipt.update(mutation_authority_contract=AUTHORITY_CONTRACT,
                   mutation_authorities=grant, mutation_bindings=[binding])
    return {
        "conversation": conversation, "latest": latest, "latest_turn_id": "current",
        "plan": conversation_plan(), "material": packet, "source_treatments": treatments,
    }


def input_payload(owner, inputs):
    return owner._input(
        inputs["conversation"], inputs["latest"], inputs["plan"], None, inputs["material"],
        None, None, (), inputs["latest_turn_id"], None, inputs["source_treatments"],
    )[0]


def check_backend(payload):
    receipt = payload["material_coverage"]["execution"]
    grant = receipt["mutation_authorities"]
    binding = receipt["mutation_bindings"][0]
    assert {"target_catalogue", "source_catalogue", "seal", "snapshot_digest", "source_digest"} <= (
        grant.keys())
    assert validate_saved_mutation_authority(
        certificate=binding, ledger=grant, owner=receipt["owner"],
        snapshot_version=receipt["expected_version"], relation=binding["relation"],
        target_ids=binding["target_ids"],
        current_source_reference=binding["current_source_reference"],
        supporting_source_ids=binding["supporting_source_ids"],
        attached_context_source_ids=binding["attached_context_source_ids"],
    ) == binding


def check_presentation(shown, raw):
    grant = shown["material_coverage"]["execution"]["mutation_authorities"]
    original = raw["material_coverage"]["execution"]["mutation_authorities"]
    assert set(grant) == {"contract", "owner", "expected_version", "authorities"}
    assert grant == {name: original[name] for name in grant}
    for field in ("earlier_conversation", "latest_message_spans", "source_classifications",
                  "record_catalogue", "legal_sources", "legal_coverage", "progress"):
        assert shown[field] == raw[field]
    assert shown["material_coverage"]["execution"]["mutation_bindings"] == (
        raw["material_coverage"]["execution"]["mutation_bindings"])
    assert len(json.dumps(shown)) < len(json.dumps(raw))
