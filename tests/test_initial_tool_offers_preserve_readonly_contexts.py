"""A context without capabilities is valid; a dispatch without tools is not."""
from dataclasses import replace

import pytest
from nm.core.tool_offers import OfferRefused, ToolOfferState
from nm.ports.model import ToolDefinition, require_tool_request

pytestmark = pytest.mark.class_a


def definition(name="read"):
    return ToolDefinition(name, "Read the owned source.", {
        "type": "object", "properties": {}, "required": [], "additionalProperties": False})


def test_empty_historic_context_neither_invents_tools_nor_authorises_provider_dispatch():
    offer = ToolOfferState((), "readonly-context", ())
    assert offer.definitions == () and not offer.on_demand
    restored = ToolOfferState.from_record(offer.to_record(), ())
    assert restored == offer
    with pytest.raises(ValueError, match="nonempty"):
        require_tool_request(offer.definitions, ())
    with pytest.raises(OfferRefused):
        offer.require_initial(ToolOfferState((definition(),), "registered", ("read",)))


def test_flat_context_exact_schemas_do_not_require_an_implementation_digest():
    inventory = (definition(),)
    context = ToolOfferState(inventory, "schema-digest", ("read",))
    context.require_initial(ToolOfferState(inventory, "actual-registry-digest", ("read",)))


@pytest.mark.parametrize("mutation", ["description", "parameters", "name", "population"])
def test_flat_context_version_labels_cannot_hide_changed_schema_bytes(mutation):
    held = definition()
    context = ToolOfferState((held,), "same-label", ("read",))
    changed = {
        "description": (replace(held, description="Write a conclusion."),),
        "parameters": (replace(held, parameters={"type": "object", "properties": {
            "scope": {"type": "string"}}, "required": ["scope"],
            "additionalProperties": False}),),
        "name": (definition("write"),),
        "population": (held, definition("more")),
    }[mutation]
    registered = ToolOfferState(changed, "same-label", tuple(sorted(row.name for row in changed)))
    with pytest.raises(OfferRefused):
        context.require_initial(registered)


def test_on_demand_contexts_still_require_exact_registry_and_loader_owners():
    inventory = (definition("inspect"), definition())
    context = ToolOfferState(inventory, "registered-v1", ("inspect",), ("inspect",))
    context.require_initial(context)
    with pytest.raises(OfferRefused):
        context.require_initial(replace(context, registry_version="registered-v2"))
    with pytest.raises(OfferRefused):
        context.require_initial(ToolOfferState(inventory, "registered-v1", ("inspect", "read")))
