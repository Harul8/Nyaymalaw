"""Relocated tool doors stay the actual registrations, not decorative aliases."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock

import pytest

from nm.legal_brain.loop_contracts import LoopIdentity, LoopMode
from nm.legal_brain.tool_catalogue import catalogue_tools
from nm.legal_brain.tool_discovery import discovery_tools
from nm.legal_brain.tools import Boundary, ToolContext, ToolRefused, ToolRegistry, foundation_tools
from nm.shared.model_port import SchemaViolation, ToolCall
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a


def actual_rows():
    matter = Matter("owned-matter", "owned-actor", "Owned exact file", version=1)
    store = Mock(load=Mock(return_value=matter))
    evidence, manifest, documents, principles = Mock(), Mock(), Mock(), Mock()

    def allow(*_):
        return Boundary(True, "Owned current test admission")

    foundation = foundation_tools(
        store,
        evidence,
        manifest=manifest,
        source_version="owned-generation",
        before=allow,
        after=allow,
    )
    rows = (
        *foundation._tools.values(),
        *catalogue_tools(
            store,
            evidence,
            source_version="owned-generation",
            matter_documents=documents,
        ),
    )
    registry = ToolRegistry(rows, before=allow, after=allow)
    rows = (*rows, *discovery_tools(lambda: registry, principles))
    return rows, (store, evidence, manifest, documents, principles)


def minimum_arguments(schema):
    kind = schema["type"]
    if "enum" in schema:
        return schema["enum"][0]
    if isinstance(kind, list):
        return None if "null" in kind else minimum_arguments({**schema, "type": kind[0]})
    if kind == "object":
        return {key: minimum_arguments(schema["properties"][key]) for key in schema["required"]}
    if kind == "string":
        return "2026-09-27"
    if kind == "integer":
        return schema.get("minimum", 0)
    if kind == "array":
        return [minimum_arguments(schema["items"]) for _ in range(schema.get("minItems", 0))]
    raise AssertionError(f"The actual tool declared an unexamined argument type: {kind}")


def test_each_separated_tool_file_owns_the_actual_handler_and_registration():
    rows, _ports = actual_rows()
    names = [row.definition.name for row in rows]
    assert len(names) == len(set(names))
    for row in rows:
        assert_owned_door(row)


def assert_owned_door(row):
    expected = "nm.legal_brain.tool_" + row.definition.name
    if row.handler.__module__.startswith(("nm.work_the_file.", "nm.act.")):
        expected = row.handler.__module__.rsplit(".", 1)[0] + ".tool_" + row.definition.name
    assert row.handler.__module__ == expected
    owner = importlib.import_module(expected)
    assert Path(inspect.getfile(owner)).name == "tool_" + row.definition.name + ".py"
    source = inspect.getsource(owner)
    tree = ast.parse(source)
    registrations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "RegisteredTool"
    ]
    assert registrations
    handler = row.handler.__name__
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == handler for node in ast.walk(tree)
    )
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ToolDefinition"
    ]
    assert definitions
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    imported_names = {
        getattr(owner, node.args[0].id, None)
        for node in definitions
        if isinstance(node.args[0], ast.Name)
    }
    assert row.definition.name in literals | imported_names


def test_every_separated_door_still_crosses_the_registry_before_any_native_port():
    rows, ports = actual_rows()
    attempted = []

    def refuse(name, _args, _context):
        attempted.append(name)
        return Boundary(False, "The current owner refuses this operation")

    registry = ToolRegistry(rows, before=refuse, after=Mock())
    context = ToolContext(
        LoopIdentity(
            "owned-matter",
            "owned-actor",
            "owned-turn",
            "a" * 64,
            "b" * 64,
            registry.version,
            1,
            LoopMode.SYNTHETIC,
        )
    )
    for row in rows:
        with pytest.raises(ToolRefused, match="current owner refuses"):
            registry.invoke(
                ToolCall(
                    row.definition.name,
                    row.definition.name,
                    minimum_arguments(row.definition.parameters),
                ),
                context,
            )
    assert attempted == [row.definition.name for row in rows]
    assert not any(port.mock_calls for port in ports)


def test_the_three_factories_do_not_retain_duplicate_separated_handlers():
    from nm.legal_brain import tool_catalogue, tool_discovery, tools

    rows, _ = actual_rows()
    separated_handlers = {row.handler.__name__ for row in rows}
    for factory in (
        tools.foundation_tools,
        tool_catalogue.catalogue_tools,
        tool_discovery.discovery_tools,
    ):
        tree = ast.parse(inspect.getsource(factory))
        retained = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name != factory.__name__
        }
        assert not retained & separated_handlers


@pytest.mark.parametrize("reviewed", [False, True])
def test_complete_actual_application_and_optional_population_have_physical_owned_doors(
    client, monkeypatch, reviewed
):
    from tests.test_controlled_registry_has_one_actual_handler_assembly import captured_application

    _app, _matter, _scope, _model, brain, _assembly = captured_application(
        client, monkeypatch, reviewed=reviewed
    )
    for row in brain.registry._tools.values():
        assert_owned_door(row)
    assert ("check_candidate_independently" in brain.registry._tools) is reviewed
    assert "finish_research" not in brain.registry._tools
    assert "finish_opposition" not in brain.registry._tools

    # Close the population against actual manufacturers, not a second name list.
    root = Path(inspect.getfile(brain.__class__)).parents[1]
    declared = set()
    for file in root.glob("*/*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        constructors = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RegisteredTool"
        ]
        if constructors:
            assert file.name.startswith("tool_"), file
            declared.add(file.stem.removeprefix("tool_"))
    baseline, _ = actual_rows()
    observed = set(brain.registry._tools) | {row.definition.name for row in baseline}
    if not reviewed:
        declared.remove("check_candidate_independently")
    assert observed == declared


@pytest.mark.parametrize("name", ["finish_research", "finish_opposition"])
def test_child_finish_definition_and_actual_dispatch_stay_in_child_only_owned_file(name):
    from nm.legal_brain import nested_research

    module = importlib.import_module("nm.legal_brain.tool_" + name)
    declaration = (
        nested_research.FINISH if name == "finish_research" else nested_research.OPPOSITION_FINISH
    )
    assert declaration is module.DEFINITION
    assert declaration.name == name
    assert module.finish.__module__ == module.__name__
    assert "from nm.legal_brain.tool_" + name in dedent(
        inspect.getsource(nested_research.ResearchDispatcher._work)
    )
    handoff = Mock()
    with pytest.raises(SchemaViolation):
        module.finish(handoff=handoff, session=object(), arguments={}, captured=(), opposition=None)
    handoff.assert_not_called()
