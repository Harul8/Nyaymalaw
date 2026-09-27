"""A new registered member is discoverable without another authored catalogue."""
import hashlib
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from nm.core.brain_context import ContextRefused, ContextSession, assemble_brief
from nm.core.tool_discovery import discovery_tools
from nm.core.tools import Boundary, ToolContext, ToolRefused, foundation_tools
from nm.domain.loop import LoopIdentity, LoopMode
from nm.domain.matter import Matter
from nm.ports.model import SchemaViolation, ToolCall
from nm.ports.principles import PrinciplesSnapshot

pytestmark = pytest.mark.class_a


def identity_snapshot(text):
    return PrinciplesSnapshot(text, hashlib.sha256(text.encode("utf8")).hexdigest())


def configured():
    snapshot = identity_snapshot("Recorded owner principles, not a legal source.")
    principles = Mock()
    principles.load.return_value = snapshot
    registry = foundation_tools(Mock(), Mock(), manifest=Mock(), source_version="recorded-source",
        before=lambda *_: Boundary(True, "Current test permission."),
        after=lambda *_: Boundary(True, "Current test permission."))
    registry = registry.extend(discovery_tools(lambda: registry, principles))
    context = ToolContext(LoopIdentity("matter", "actor", "turn", "a" * 64,
        snapshot.version, registry.version, 1, LoopMode.SYNTHETIC))
    return registry, context, principles


def test_discovery_is_the_actual_registry_not_a_second_catalogue():
    registry, context, _ = configured()
    receipt = registry.invoke(
        ToolCall("d", "discover_tools", {"query": "unmatched wording"}), context)
    assert receipt.data["registered_count"] == len(registry.definitions) == 10
    assert {row["name"] for row in receipt.data["tools"]} == {
        row.name for row in registry.definitions}
    assert receipt.data["returned_count"] == 10 and receipt.data["ranking_only"] is True
    assert not receipt.data["grants_permission"]
    assert not receipt.data["establishes_law_or_case_facts"]
    for definition in registry.definitions:
        result = registry.invoke(ToolCall("i", "inspect_tool", {"name": definition.name}), context)
        assert result.data["definition"]["parameters"] == definition.parameters
        assert result.data["required_act"] == registry.authority_for(definition.name).value


@pytest.mark.parametrize("name", ["READ_MATTER", "read_matter ", "external_filing", ""])
def test_inspection_never_fuzzily_identifies_or_invents_a_tool(name):
    registry, context, _ = configured()
    with pytest.raises((ToolRefused, SchemaViolation)):
        registry.invoke(ToolCall("i", "inspect_tool", {"name": name}), context)


def test_the_guide_is_the_single_admitted_owner_text_not_a_prompt_copy():
    registry, context, principles = configured()
    result = registry.invoke(ToolCall("g", "read_owner_guide", {
        "expected_version": context.identity.principles_version}), context)
    assert result.data["text"] == principles.load().text
    assert result.data["trust"] == "owner_guidance_not_permission_or_legal_authority"
    original = principles.load.return_value
    principles.load.return_value = identity_snapshot("Changed owner instructions.")
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("g", "read_owner_guide", {
            "expected_version": original.version}), context)


def test_registry_and_guide_version_arguments_cannot_self_certify_currentness():
    registry, context, _ = configured()
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("d", "discover_tools", {"query": ""}),
                        replace(context, identity=replace(
                            context.identity, tools_version="b" * 64)))
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("g", "read_owner_guide", {"expected_version": "b" * 64}), context)
    with pytest.raises(ToolRefused):
        registry.invoke(ToolCall("d", "discover_tools", {"query": "a" * 2001}), context)


def _guidance_identity(system):
    marker = "\nTRUSTED OWNER GUIDANCE IDENTITY\n"
    assert system.count(marker) == 1
    return json.loads(system.split(marker, 1)[1].splitlines()[0])


@pytest.mark.parametrize("on_demand", [False, True])
def test_the_actual_request_exposes_the_required_pin_from_its_captured_owner(on_demand):
    registry, context, principles = configured()
    matter = Matter("matter", "actor", "A user-supplied guide version is not an owner pin.")
    session = ContextSession(principles.load(), registry.definitions,
        assemble_brief(matter, advocate_id="actor"), provider="scripted", model="model",
        tool_offer=registry.offer_state() if on_demand else None)
    session.assert_request(session.system, session.messages, model=session.model)
    captured = _guidance_identity(session.system)
    assert captured == {"principles_version": context.identity.principles_version}
    result = registry.invoke(ToolCall("g", "read_owner_guide", {
        "expected_version": captured["principles_version"]}), context)
    assert result.data["guide_version"] == captured["principles_version"]
    assert result.data["text"] == principles.load().text
    assert not result.data["grants_permission"]
    resumed = ContextSession.from_record(session.to_record(), matter, advocate_id="actor")
    assert resumed.system == session.system
    assert _guidance_identity(resumed.system) == captured
    resumed.compact(matter, reason="capacity boundary")
    assert _guidance_identity(resumed.system) == captured


@pytest.mark.parametrize("alteration", ["missing", "wrong", "duplicate"])
def test_recovery_cannot_silently_add_or_replace_the_owner_pin(alteration):
    registry, _, principles = configured()
    matter = Matter("matter", "actor", "Owned file")
    session = ContextSession(principles.load(), registry.definitions,
        assemble_brief(matter, advocate_id="actor"), provider="scripted", model="model")
    record = session.to_record()
    marker = "\nTRUSTED OWNER GUIDANCE IDENTITY\n"
    block = marker + json.dumps({"principles_version": principles.load().version},
                                sort_keys=True, separators=(",", ":"))
    assert block in record["system"]
    if alteration == "missing":
        record["system"] = record["system"].replace(block, "")
    elif alteration == "wrong":
        record["system"] = record["system"].replace(principles.load().version, "b" * 64)
    else:
        record["system"] += block
    with pytest.raises(ContextRefused):
        ContextSession.from_record(record, matter, advocate_id="actor")
