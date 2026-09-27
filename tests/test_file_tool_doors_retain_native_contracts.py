"""Finite extraction controls; not new capability, legal or full-journey proof."""

from __future__ import annotations

import ast
import importlib
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest

from nm.act.action_proposal_tool import action_proposal_tools
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.working_record import WorkingRecordOwner
from nm.work_the_file.deadline_proposals import deadline_proposal_tools
from nm.work_the_file.private_file_tools import private_file_tools
from nm.work_the_file.write_tools import write_tools

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
# Measured from the actual four factories before extracting their doors.
# These are exact metadata/native-code compatibility controls, not verdicts.
CONTRACTS = {
    "create_dispute": "032986f685d3483bb11c7fc206d5dcefb0423bb0e0639dc217c9848302b73cf5",
    "write_fact": "a9966ca5616aa8464d1fc33b66b733dbc35687c7c5b3e9912cc1b7143820d56a",
    "correct_fact": "7490b527c8a43664c39fcf29cfececf2320e804e251d279c5de0a2754572b855",
    "record_requirement_answer": "0b5c8adcf4bc9a4e6af95338d0503febd28150e4fd064a3c80fd0be6fab32bb8",
    "record_existing_requirement_answer": (
        "d51280052c46ebb8aef3473ff9fadb4ab8bb4f769e5d8bcd0c3b7e2640e1e208"
    ),
    "add_issue": "097a094451cae8609fcb23464509f4cec684080f37dd65b9e4580d9e6ecff286",
    "record_prior_instruction": "346455b2a41e51e31d68eefb84becb8571115bdc9613720f0f75415e73a5fe60",
    "read_private_file_inputs": "6180b16dcdbcdb8aa3269169e8d7fc513a7057f33877f71ba6f1d6e58366eafe",
    "propose_legal_premise": "f4be3554c8b5956f0ab2e3c09b76ac97ec5862803fbee7f13f16574bf58bfec4",
    "propose_product_decision": "49a765113447d9b3e11806896dbc537c6e0c13f37568ac6cd4223edd807a675d",
    "withdraw_private_premise": "a7ecd62145834c8b7ef979b7316871ce5d4e2e756ed46b1a54888647ff1ac6a0",
    "propose_source_deadline": "89ad3ce5d72d01e19dee8aae74cf1579b7b8b2ae97230528b1c8dee429e8fd9e",
    "propose_source_calendar": "53a981763e56b3bc05b502b2bab0500b8b1ec75e2537442438cbb24c44063aa0",
    "propose_action": "c1b785b9b551a51d27d8e9b29438b1bfa78998d54986fd630c70318d37ed1002",
}
NATIVE_CLOSURES = {
    "nm/work_the_file/write_tools.py:instruction_source": (
        "54ff6dcd2499817e9cecc42251ddc903300acc956da065007c5e021850529058"
    ),
    "nm/work_the_file/write_tools.py:prepare": (
        "d6dfe1a7095bc732691af961fbe15acc0b2276ad2e67e58e71e121a08dca7c84"
    ),
    "nm/work_the_file/private_file_tools.py:current": (
        "5685143bfe0c938a254d8feef6cd601253ba02ed0de0cad22d038c805fb202ec"
    ),
    "nm/work_the_file/private_file_tools.py:run": (
        "406be295357a45798e7f599c2e4769d498f99ce853e028a2720af64f130b4821"
    ),
    "nm/work_the_file/deadline_proposals.py:run": (
        "24295f5c27d48d5922d940a16376ad366fd54892b70e15c280eeecb34d4589ef"
    ),
    "nm/act/action_proposal_tool.py:prepare": (
        "b60939e5bd58c51145c61d6e98c1c139a091cb53b3673695e4df2986b4878b15"
    ),
}


def _assembled():
    def source(*_):
        return True

    return (
        *write_tools(object()),
        *private_file_tools(object(), source_generation="generation", source_current=source),
        *deadline_proposal_tools(
            object(),
            owner=WorkingRecordOwner(source_current=source),
            source_generation="generation",
            current_source_generation=lambda: "generation",
        ),
        *action_proposal_tools(object()),
    )


def _metadata(tool):
    return {
        "definition": asdict(tool.definition),
        "kind": tool.kind.value,
        "version": tool.version,
        "parallel_safe": tool.parallel_safe,
        "tests": list(tool.tests),
        "required_act": tool.required_act.value,
        "delegation": asdict(tool.delegation) if tool.delegation else None,
        "offer_role": tool.offer_role.value,
    }


def _module(name):
    phase = "act" if name == "propose_action" else "work_the_file"
    return f"nm.{phase}.tool_{name}"


def test_actual_four_factory_order_and_fourteen_name_population_remain_exact():
    assert tuple(tool.definition.name for tool in _assembled()) == tuple(CONTRACTS)
    assert len(CONTRACTS) == 14


@pytest.mark.parametrize("name", tuple(CONTRACTS))
def test_every_actual_registered_door_retains_its_complete_preextraction_contract(name):
    tool = next(row for row in _assembled() if row.definition.name == name)
    assert digest(_metadata(tool)) == CONTRACTS[name]
    assert tool.handler.__module__ == _module(name)
    assert tool.handler.__name__ == name


@pytest.mark.parametrize("locator", tuple(NATIVE_CLOSURES))
def test_shared_native_validation_and_mutation_closures_are_not_copied_or_changed(locator):
    path, name = locator.split(":")
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    owned = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(owned) == 1
    assert digest(ast.dump(owned[0], include_attributes=False)) == NATIVE_CLOSURES[locator]


@pytest.mark.parametrize("name", tuple(CONTRACTS))
def test_door_fixed_name_delegates_exact_arguments_and_context_to_native_owner(name):
    module = importlib.import_module(_module(name))
    result = object()
    native = Mock(return_value=result)
    dependency = (
        "run"
        if name
        in {
            "read_private_file_inputs",
            "propose_legal_premise",
            "propose_product_decision",
            "withdraw_private_premise",
            "propose_source_deadline",
            "propose_source_calendar",
        }
        else "prepare"
    )
    tool = module.build_tool(**{dependency: native})
    arguments, context = {"not_executed_by_this_forwarding_control": True}, object()
    assert tool.handler(arguments, context) is result
    if name == "propose_action":
        native.assert_called_once_with(arguments, context)
    else:
        native.assert_called_once_with(name, arguments, context)
    assert tool.definition.name == name and tool.handler.__module__ == _module(name)
    assert digest(_metadata(tool)) == CONTRACTS[name]
