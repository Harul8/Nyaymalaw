"""Final planning corrections have exact owners; none is runtime proof."""
from copy import deepcopy

import pytest

from tools import blueprint
from tools.blueprint_execution import check_packets

pytestmark = pytest.mark.class_a


def test_final_review_obligations_have_exact_delivery_and_packet_owners():
    modules, registry = blueprint.load()
    contracts = blueprint.load_contracts()
    assert blueprint.check_all(modules, registry, contracts) == []
    packets = contracts["packets"]["packets"]
    expected = {"BK-69-AC3": "P15", "BK-79-AC3": "P25",
                "BK-88-AC4": "P39", "BK-80-AC6": "P03"}
    assert len(expected) == 4
    for criterion, owner in expected.items():
        assert [p["id"] for p in packets if criterion in p["final_criteria"]] == [owner]
        assert criterion in next(p for p in packets if p["id"] == owner)["criteria"]
    choice = next(c for c in contracts["decisions"]["choices"] if c["id"] == "CHOICE-05")
    assert "BK-69-AC3" in choice["owner_criteria"]
    items = {row["id"]: row for row in registry["items"]}
    for criterion in expected:
        item = items[criterion.rsplit("-AC", 1)[0]]
        ac = next(ac for ac in item["acceptance"] if ac["id"] == criterion)
        assert ac["required_evidence"] and ac["negative_control"]


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "replace_with_product", "blank_reason"])
def test_planning_delivery_exclusions_cannot_hide_product_work(mutation):
    modules, registry = blueprint.load()
    contracts = blueprint.load_contracts()
    catalog = deepcopy(contracts["packets"])
    exclusions = catalog["planning_delivery_exclusions"]
    assert {row["item"] for row in exclusions} == {"BK-87", "BK-89", "BK-90"}
    before = deepcopy(exclusions)
    if mutation == "drop":
        exclusions.pop()
    elif mutation == "duplicate":
        exclusions.append(deepcopy(exclusions[0]))
    elif mutation == "replace_with_product":
        exclusions[0]["item"] = "BK-80"
    else:
        exclusions[0]["reason"] = " "
    assert exclusions != before
    problems = check_packets(
        catalog, registry, modules,
        {r["id"] for r in contracts["commands"]["x-commands"]},
        {r["id"] for r in contracts["decisions"]["choices"]},
        {r["id"] for r in contracts["evaluations"]["synthetic_cases"]}, blueprint.ROOT)
    assert any("only the explained BK-87, BK-89 and BK-90 planning deliveries" in p for p in problems)
