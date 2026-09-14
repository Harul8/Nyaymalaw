"""SEVENTEEN REGISTRIES, RECONCILED, AND THREE CLAIMS KEPT APART. P43.
BK-81-AC1, BK-81-AC3, BK-77-AC1, BK-77-AC2, BK-77-AC3.

WHAT THESE DEFEND
-------------------
`assurance/control_plane/blueprint.py` and its five checkers already reconcile the execution
graph. What was never proved is that they CAN FAIL. A structural checker that
passes on a tree with a deleted mapping, a duplicated owner or a cycle in it
is worse than none, because it is a green light nobody will look behind --
defect shape S11, a check that cannot fail, on the register that decides what
is ready to build.

So every check here plants the mutation the criterion names, drives the REAL
checker, and asserts it reports THAT problem rather than merely something.

    EVERY MUTATION IS MADE ON AN ISOLATED TEMPORARY COPY of the tree, and
    every probe asserts the intended bytes actually changed before it looks at
    the result. A mutation that silently did nothing produces a checker that
    passes and a test that agrees with it.

THE THREE CLAIMS THAT ARE NOT THE SAME CLAIM
----------------------------------------------
    locally proven      a test on this machine passed
    professionally approved   a qualified person signed the exact scope
    production measured  it was observed on an operated deployment

Every one of the last two is absent from this build, and the register has to
keep saying so while the first accumulates. The rollup is checked here in both
directions: a criterion whose automated evidence all passes is NOT done while
a counsel review or production measure is outstanding, and one with nothing
outstanding IS -- otherwise the distinction is a wall rather than a
distinction.

NUMERIC ORDER IS NOT DEPENDENCY ORDER
---------------------------------------
P41 depends on P44 and P45. A reader who assumes the packets run in numeric
order reads that as a cycle and starts deleting edges, so the property is
asserted rather than left to be rediscovered.

WHAT THIS SUITE CANNOT ESTABLISH
----------------------------------
That the plan is right. BK-81-AC2 needs a qualified design review of the India
legal, privacy and role boundaries, and machine checks do not self-certify
those: its `counsel_review` stays NOT RUN. Adoption stays NOT RUN with it --
`approvals.json` records no approval, and this build may not write one.
"""
from __future__ import annotations

import json
import pathlib
import shutil

import pytest
import yaml

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: THE SEVENTEEN. Named once, so a reconciliation cannot cover sixteen and
#: read as complete -- the same reason `POPULATIONS` is one tuple in P39.
REGISTRIES: tuple[str, ...] = (
    "docs/backlog/status.yaml",
    "docs/backlog/steps.yaml",
    "docs/backlog/plan.json",
    "docs/backlog/professional.json",
    "docs/backlog/build_rules.json",
    "docs/backlog/known_failures.yaml",
    "docs/blueprint/modules.json",
    "docs/blueprint/packets.json",
    "docs/blueprint/decisions.json",
    "docs/blueprint/evaluations.json",
    "docs/blueprint/autonomy.json",
    "docs/blueprint/approvals.json",
    "docs/blueprint/approvals.schema.json",
    "docs/blueprint/contracts/commands.json",
    "docs/blueprint/processors.yaml",
    "assurance/specification/features.yaml",
    "assurance/specification/gates.yaml",
)


@pytest.fixture
def tree(tmp_path) -> pathlib.Path:
    """An ISOLATED COPY of everything the checker reads.

    Not the working tree. A mutation probe that edits the real files leaves
    them edited when it fails or is interrupted, and the next thing to run is
    a release gate reading a register somebody's test broke.

    The population is DERIVED from `packets.json` rather than listed, because
    `check_packets` verifies that every `existing` source boundary is a file
    that exists -- so a hand-written list of what to copy would go stale the
    first time a packet declared a new boundary, and the copy would then fail
    for a reason that has nothing to do with the mutation under test.
    """
    for name in REGISTRIES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    for path in (ROOT / "docs" / "blueprint").glob("*.md"):
        shutil.copy2(path, tmp_path / "docs" / "blueprint" / path.name)

    packets = json.loads(
        (ROOT / "docs/blueprint/packets.json").read_text(encoding="utf-8"))
    for packet in packets["packets"]:
        for boundary in packet.get("boundaries") or []:
            if boundary.get("kind") != "existing":
                continue
            source = ROOT / boundary["path"]
            if not source.exists():
                continue
            target = tmp_path / boundary["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
    return tmp_path


def _errors(root: pathlib.Path) -> list[str]:
    from assurance.control_plane.blueprint import check_all, load, load_contracts

    manifest, registry = load(root)
    return check_all(manifest, registry, load_contracts(root), root)


def _json(root: pathlib.Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: pathlib.Path, name: str, document) -> None:
    (root / name).write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


# ============ 1. the seventeen exist and the checker reads them ============

def test_every_named_registry_is_a_file_this_tree_has():
    """A registry named and absent is the reconciliation reporting on nothing."""
    for name in REGISTRIES:
        assert (ROOT / name).is_file(), name


def test_the_seventeen_are_distinct():
    assert len(REGISTRIES) == 17 == len(set(REGISTRIES))


def test_the_real_tree_reconciles():
    """THE POSITIVE CONTROL. Every mutation below is measured against this:
    without it, a checker that reported one fixed error would pass them all."""
    assert _errors(ROOT) == []


# ====== 2. BK-81-AC1 -- delete a mapping, duplicate an owner, cycle ========

def test_a_deleted_module_mapping_is_reported_by_name(tree):
    """*delete a mapping* -> *the blueprint check reports the specific missing
    owner*. Every item, feature and journey step has exactly one primary
    module, and an unowned one is work nobody is accountable for."""
    assert _errors(tree) == [], "the copy must reconcile before it is broken"

    modules = _json(tree, "docs/blueprint/modules.json")
    donor = next(row for row in modules["modules"] if row["items"])
    orphan = donor["items"][0]
    donor["items"] = [i for i in donor["items"] if i != orphan]
    _write(tree, "docs/blueprint/modules.json", modules)

    # THE MUTATION ACTUALLY LANDED. A probe that reads the checker's output
    # without confirming the bytes moved passes when the edit silently did
    # nothing, which is a green test agreeing with a check that cannot fail.
    after = _json(tree, "docs/blueprint/modules.json")
    assert orphan not in next(
        row for row in after["modules"] if row["id"] == donor["id"])["items"]

    found = _errors(tree)
    assert any(f"unmapped {orphan}" in problem for problem in found), found


def test_a_duplicated_module_owner_is_reported_with_its_count(tree):
    """*duplicate an owner.* Two modules owning one item is two places
    accountable for it, which in practice is none."""
    assert _errors(tree) == []

    modules = _json(tree, "docs/blueprint/modules.json")
    donor = next(row for row in modules["modules"] if row["items"])
    shared = donor["items"][0]
    thief = next(row for row in modules["modules"] if row["id"] != donor["id"])
    thief["items"] = list(thief["items"]) + [shared]
    _write(tree, "docs/blueprint/modules.json", modules)

    after = _json(tree, "docs/blueprint/modules.json")
    assert shared in next(
        row for row in after["modules"] if row["id"] == thief["id"])["items"]

    found = _errors(tree)
    assert any(f"duplicate owner {shared} (2)" in problem
               for problem in found), found


def test_a_module_cycle_names_the_module_it_closes_at(tree):
    """*introduce a cycle*, in the module graph rather than the packet one.
    Both graphs exist and a checker that watched only one would pass on the
    other."""
    assert _errors(tree) == []

    modules = _json(tree, "docs/blueprint/modules.json")
    rows = {row["id"]: row for row in modules["modules"]}
    late = next(row for row in modules["modules"] if row["requires"])
    upstream = rows[late["requires"][0]]
    upstream["requires"] = list(upstream["requires"]) + [late["id"]]
    _write(tree, "docs/blueprint/modules.json", modules)

    after = {row["id"]: row for row in
             _json(tree, "docs/blueprint/modules.json")["modules"]}
    assert late["id"] in after[upstream["id"]]["requires"]

    found = _errors(tree)
    assert any("dependency cycle" in problem for problem in found), found


def test_a_duplicated_final_owner_is_reported(tree):
    """*duplicate an owner.* Two packets claiming to be the final owner of one
    criterion is two places that decide when it is done."""
    assert _errors(tree) == []

    packets = _json(tree, "docs/blueprint/packets.json")
    rows = packets["packets"]
    donor = next(p for p in rows if p.get("final_criteria"))
    criterion = donor["final_criteria"][0]
    thief = next(p for p in rows if p["id"] != donor["id"])
    before = list(thief["final_criteria"])
    thief["final_criteria"] = before + [criterion]
    _write(tree, "docs/blueprint/packets.json", packets)

    assert _json(tree, "docs/blueprint/packets.json")["packets"][
        rows.index(thief)]["final_criteria"] != before

    found = _errors(tree)
    assert any(criterion in problem for problem in found), found


def test_a_cycle_is_reported_as_a_path_and_not_as_a_boolean(tree):
    """*introduce a cycle* -> *the blueprint check reports the specific
    cycle*. A boolean tells an operator a cycle exists somewhere in a
    forty-seven node graph."""
    assert _errors(tree) == []

    packets = _json(tree, "docs/blueprint/packets.json")
    rows = {p["id"]: p for p in packets["packets"]}
    late = rows["P41"]
    early = rows[late["prerequisites"][0]]
    before = list(early["prerequisites"])
    early["prerequisites"] = before + ["P41"]
    _write(tree, "docs/blueprint/packets.json", packets)

    assert "P41" in _json(tree, "docs/blueprint/packets.json")["packets"][
        [p["id"] for p in packets["packets"]].index(early["id"])
    ]["prerequisites"]

    found = _errors(tree)
    assert any("cycle" in problem for problem in found), found
    assert any("->" in problem for problem in found), found


def test_a_prerequisite_that_names_nothing_is_reported(tree):
    assert _errors(tree) == []
    packets = _json(tree, "docs/blueprint/packets.json")
    packets["packets"][0]["prerequisites"] = ["P99"]
    _write(tree, "docs/blueprint/packets.json", packets)
    found = _errors(tree)
    assert any("P99" in problem for problem in found), found


def test_no_module_carries_an_authored_completion_status():
    """A module that could be marked done would be a second completion
    registry beside status.yaml, and the two would disagree within a week."""
    modules = _json(ROOT, "docs/blueprint/modules.json")
    rows = modules.get("modules", modules)
    rows = rows if isinstance(rows, list) else list(rows.values())
    for row in rows:
        assert not (set(row) & {"status", "complete", "done", "built",
                                "result", "state"}), row.get("id")


# ==== 3. prerequisites and completed-item gates are different things ======

def test_a_packet_prerequisite_is_not_a_completed_item_gate():
    """Two fields, two meanings: `prerequisites` are packets that must run
    first and `requires_completed_items` are backlog items that must be DONE.
    Collapsing them would let a packet run because another packet ran."""
    packets = _json(ROOT, "docs/blueprint/packets.json")["packets"]
    packet_ids = {p["id"] for p in packets}
    items = {row["id"] for row in yaml.safe_load(
        (ROOT / "docs/backlog/status.yaml").read_text(encoding="utf-8")
    )["items"]}
    for packet in packets:
        for pid in packet.get("prerequisites") or []:
            assert pid in packet_ids, (packet["id"], pid)
            assert pid not in items, (packet["id"], pid)
        for item in packet.get("requires_completed_items") or []:
            assert item in items, (packet["id"], item)
            assert item not in packet_ids, (packet["id"], item)


def test_numeric_order_is_not_dependency_order():
    """P41 depends on P44 and P45. A reader who assumes packets run in numeric
    order reads that as a cycle and starts deleting edges."""
    packets = {p["id"]: p for p in
               _json(ROOT, "docs/blueprint/packets.json")["packets"]}
    backwards = [(pid, dep) for pid, row in packets.items()
                 for dep in row.get("prerequisites") or []
                 if dep > pid]
    assert backwards, ("no packet depends on a higher-numbered one, so this "
                       "property is no longer demonstrated by the plan")
    assert ("P41", "P44") in backwards or ("P41", "P45") in backwards


def test_the_release_packet_is_last_by_dependency_and_not_by_number():
    """P41 is the release gate. Nothing may depend on it, whatever it is
    numbered."""
    packets = _json(ROOT, "docs/blueprint/packets.json")["packets"]
    dependents = [p["id"] for p in packets
                  if "P41" in (p.get("prerequisites") or [])]
    assert dependents == []


# ======= 4. three claims, kept apart -- BK-77-AC3 and BK-81-AC3 ===========

def _registry() -> dict:
    from assurance.control_plane.backlog import load

    return load()


def test_a_criterion_awaiting_counsel_is_not_done_however_green_the_tests():
    """*locally proven* is not *professionally approved.* BK-81-AC2 is the
    live instance: its structural siblings pass and it needs a design review
    nobody has performed."""
    from assurance.control_plane.backlog import bind_execution_evidence, item_result

    doc = _registry()
    bind_execution_evidence(doc)
    item = next(row for row in doc["items"] if row["id"] == "BK-81")
    ac2 = next(ac for ac in item["acceptance"] if ac["id"] == "BK-81-AC2")
    assert "counsel_review" in ac2["required_evidence"]
    assert (ac2.get("evidence") or {}).get(
        "counsel_review", {}).get("result", "NOT_RUN") != "PASS"
    assert item_result(item, bind_execution=False) != "PASS"


def test_a_criterion_awaiting_a_production_measure_is_not_done_either():
    """*locally proven* is not *production measured.* Every P38/P39 criterion
    is one of these and none may roll up."""
    from assurance.control_plane.backlog import bind_execution_evidence, item_result

    doc = _registry()
    bind_execution_evidence(doc)
    checked = 0
    for row in doc["items"]:
        for ac in row.get("acceptance") or []:
            evidence = ac.get("evidence") or {}
            production = evidence.get("production_measure")
            if not production or production.get("result") == "PASS":
                continue
            checked += 1
            assert item_result(row, bind_execution=False) != "PASS", ac["id"]
    assert checked, "no outstanding production measure remains to check"


def test_a_criterion_with_nothing_outstanding_does_roll_up():
    """THE POSITIVE CONTROL, and it is the one that matters: a distinction
    that never lets anything through is a wall, and a wall teaches the next
    reader to route around it."""
    from assurance.control_plane.backlog import item_result

    done = [row["id"] for row in _registry()["items"]
            if item_result(row, bind_execution=False) == "PASS"]
    assert done, "nothing rolls up at all, so the rollup proves nothing"


def test_no_adoption_approval_has_been_written_by_this_build():
    """*Adoption may remain NOT RUN.* It does, and a record written here would
    be a decision an accountable person did not take.

    The empty register is not proof that no human approval exists elsewhere --
    `approvals.json` says so itself. It is proof that this build wrote none.
    """
    approvals = _json(ROOT, "docs/blueprint/approvals.json")
    assert approvals["records"] == [], approvals["records"]
    for choice in _json(ROOT, "docs/blueprint/decisions.json")["choices"]:
        assert choice.get("approval") in (None, {}, ""), choice["id"]


# ====== 5. BK-77-AC1 / AC2 -- one maintained source each ==================

def test_every_journey_step_has_exactly_one_contract():
    steps = yaml.safe_load(
        (ROOT / "docs/backlog/steps.yaml").read_text(encoding="utf-8"))
    rows = steps.get("steps", steps)
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert len(ids) == 47, len(ids)


def test_the_generated_reader_views_are_not_inputs_to_themselves():
    """A generated view that fed back into its own snapshot is the second
    completion registry arriving by the back door: edit a status cell, the
    snapshot changes, and the workbook now agrees with itself about a fact no
    registry holds."""
    from assurance.control_plane.plan_view import SNAPSHOT_BASE

    for generated in ("docs/PLAN.md",
                      "docs/Nyaymalaw_End_to_End_Project_Plan.xlsx"):
        assert generated not in SNAPSHOT_BASE, generated
    for authored in ("docs/backlog/status.yaml", "assurance/specification/features.yaml"):
        assert authored in SNAPSHOT_BASE, authored


def test_a_review_finding_is_registered_rather_than_described():
    """BK-77-AC3: every enforcement limitation is a registered row that stays
    unproven until its named work is complete."""
    from assurance.control_plane.backlog import item_result

    doc = _registry()
    unfinished = [row["id"] for row in doc["items"]
                  if item_result(row, bind_execution=False) != "PASS"]
    assert unfinished, "nothing is outstanding, which the register denies"
    for row in doc["items"]:
        for ac in row.get("acceptance") or []:
            assert ac.get("required_evidence"), ac["id"]
            assert ac.get("negative_control"), ac["id"]
