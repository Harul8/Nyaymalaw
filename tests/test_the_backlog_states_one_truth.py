"""THE REGISTRY IS THE ONLY PLACE CURRENT STATUS LIVES, and it is checkable.

BK-60. `docs/backlog/status.yaml` states what is true now; `BACKLOG.md` keeps
the forensic prose and explains why; tests prove it; the board is generated.

WHAT WENT WRONG WITHOUT THIS
----------------------------
`Open — 13` was typed by hand. So were *sixteen phases* and *18 pass*, both
describing a suite that collects **24**. Every count a person maintained in
this repository was wrong within days of being written, and each was quoted
onward as though measured.

And one word carried five questions. `PARTLY DONE` said nothing about whether
the code existed, whether it had been proven, whether it could ship, or what
to do next -- so every reader resolved it, and the optimistic reading won.

THE RULE THESE TESTS ENFORCE
----------------------------
A missing link is NOT PROVEN, never implicitly passing. That is the whole
system: no criteria means not proven, no evidence means not proven, an
unresolved level means not proven. `NOT_RUN` is not a pass, and it is where a
missing browser, an absent credential, a collection error and a conditional
xfail all land -- every one of which has produced a green build here already.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest
import yaml

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "backlog" / "status.yaml"


def _tool():
    spec = importlib.util.spec_from_file_location(
        "_backlog_tool", ROOT / "tools" / "backlog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc() -> dict:
    return yaml.safe_load(STATUS.read_text(encoding="utf-8"))


def test_the_registry_lints_clean():
    """BK-60-AC1. Ids are unique and every journey feature is accounted for.

    Run against the REAL registry, because the registry is the thing under
    test. A synthetic fixture would prove the linter compiles.
    """
    problems = _tool().lint(_doc())
    assert not problems, (
        "docs/backlog/status.yaml does not satisfy its own schema:\n  "
        + "\n  ".join(problems))


def test_the_lint_can_see_a_planted_duplicate():
    """THE POSITIVE CONTROL for the sweep above.

    Ids live in a LIST rather than as YAML keys precisely so a duplicate is
    visible instead of silently overwriting the row before it -- which is what
    `BK-8` did in the prose, appearing twice with two different statuses.
    """
    tool = _tool()
    doc = _doc()
    doc["items"] = list(doc["items"]) + [dict(doc["items"][0])]
    assert any("appears twice" in p for p in tool.lint(doc)), (
        "the linter did not report a duplicated id, so it would not have "
        "caught BK-8 and reports a clean registry either way")


def test_the_lint_can_see_a_row_whose_prose_is_missing():
    """THE OTHER POSITIVE CONTROL. The registry says WHAT; the prose says WHY.

    A `record` pointing nowhere loses the half that cannot be reconstructed
    afterwards, which is what happened to every row this repository closed with
    a heading and no reasoning.
    """
    tool = _tool()
    doc = _doc()

    orphan = dict(doc["items"][0], id="BK-999",
                  record="docs/BACKLOG.md#bk-999")
    assert any("BK-999" in p and "no row for it" in p
               for p in tool.lint({**doc, "items": list(doc["items"]) + [orphan]})), (
        "a registry row with no prose in BACKLOG.md was not reported")

    blank = [dict(doc["items"][0], record="")] + list(doc["items"][1:])
    assert any("no `record`" in p for p in tool.lint({**doc, "items": blank})), (
        "a registry row with no record at all was not reported")


def test_done_cannot_be_authored():
    """BK-60-AC2. Nobody makes something true by writing the word.

    `done` is absent from the delivery vocabulary on purpose: it is derived
    from evidence in `derive_done`, and typing it is refused.
    """
    tool = _tool()
    assert "done" not in tool.DELIVERY, (
        "`done` is in the authored vocabulary, so a row can declare itself "
        "finished without any evidence at all")

    doc = _doc()
    doc["items"] = [dict(doc["items"][0], delivery_status="done")]
    assert any("done` is DERIVED" in p for p in tool.lint(doc)), (
        "the linter accepted an authored `done`")


def test_a_missing_link_is_not_proven():
    """BK-60-AC3. The decisive rule, in both directions.

    A criterion that requires evidence and has none is NOT_RUN, an item with
    no criteria at all is NOT_PROVEN, and neither may read as a pass.
    """
    tool = _tool()

    nothing = {"id": "X-AC1", "requirement": "r",
               "required_evidence": ["domain_test"]}
    assert tool.proof_state(nothing) == "NOT_RUN", (
        "a required evidence level with no result read as something other "
        "than NOT_RUN")

    partial = {"id": "X-AC2", "requirement": "r",
               "required_evidence": ["domain_test", "counsel_review"],
               "evidence": {"domain_test": {"result": "PASS"}}}
    assert tool.proof_state(partial) == "NOT_RUN", (
        "a criterion passing at one level and unrun at another read as "
        "proven -- which is how technical tests come to stand in for counsel "
        "review")

    failing = {"id": "X-AC3", "requirement": "r",
               "required_evidence": ["domain_test"],
               "evidence": {"domain_test": {"result": "FAIL"}}}
    assert tool.proof_state(failing) == "FAIL"

    assert tool.item_result({"id": "X", "acceptance": []}) == "NOT_PROVEN", (
        "an item with no acceptance criteria read as proven, so a row could "
        "be closed by promising nothing")

    assert not tool.derive_done(
        {"id": "X", "implementation": "complete", "acceptance": []}, {}), (
        "an implemented row with no criteria derived as done")


def test_the_board_is_not_stale():
    """BK-60-AC4. The generated section matches the registry.

    Counts are generated because every hand-maintained one in this repository
    has been wrong. A board that has drifted is a hand-maintained count with
    extra steps.
    """
    tool = _tool()
    text = (ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    assert tool.START in text and tool.END in text, (
        "BACKLOG.md has lost its generated-board markers")
    current = re.search(
        f"{re.escape(tool.START)}(.*?){re.escape(tool.END)}", text, re.S)
    assert current, "the board markers are present but do not enclose anything"
    assert current.group(1).strip() == tool.board(_doc()).strip(), (
        "the board in BACKLOG.md has drifted from status.yaml. Run:\n"
        "    python tools/backlog.py render")


def test_every_feature_in_the_prd_is_in_the_registry():
    """No feature may be missing from the plan.

    Phase F saying 'nothing implemented' is only honest if something in the
    registry says what would implement it.
    """
    spec = yaml.safe_load(
        (ROOT / "spec" / "features.yaml").read_text(encoding="utf-8"))
    declared = {f["id"] for f in spec["features"]}
    registered = {f["id"] for f in _doc()["features"]}
    assert declared == registered, (
        f"the registry and the PRD feature list disagree:\n"
        f"  in the PRD, not the registry: {sorted(declared - registered)}\n"
        f"  in the registry, not the PRD: {sorted(registered - declared)}")
