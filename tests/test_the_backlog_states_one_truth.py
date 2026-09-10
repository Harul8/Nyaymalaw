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

import copy
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
    """THROUGH THE LOADER, not off the file.

    `status.yaml` holds the rows and `steps.yaml` holds the journey steps --
    one fact in one file -- and `load()` is what puts them together. Reading
    the YAML directly here gave a document with no steps in it, so every
    feature came back unexercised and the suite reported a broken registry
    that was not broken.
    """
    return _tool().load()


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


def _managed_item() -> dict:
    return {
        "id": "X", "title": "managed", "kind": "control", "priority": "P1",
        "delivery_status": "verifying", "implementation": "complete",
        "verification": "passing", "affects_phases": ["A"],
        "record": "docs/BACKLOG.md#x", "acceptance": [{
            "id": "X-AC1", "requirement": "the rule",
            "required_evidence": ["domain_test"],
            "evidence": {"domain_test": {"result": "PASS"}},
        }],
        "stage_records": {
            "start": {"result": "READY", "ref": "record#start"},
            "build": {"result": "BUILT", "ref": "record#build"},
            "test": {"result": "VERIFIED", "ref": "record#test"},
            "signoff": {"result": "OPEN", "ref": "record#signoff"},
        },
    }


def test_ready_routes_to_build_and_verified_routes_to_signoff():
    """BK-74-AC1. The router follows the playbook hand-offs."""
    tool = _tool()
    ready = _managed_item()
    ready.update(delivery_status="ready", implementation="none",
                 verification="none")
    ready["stage_records"]["build"]["result"] = "NOT_STARTED"
    ready["stage_records"]["test"]["result"] = "NOT_RUN"
    ready["stage_records"]["signoff"]["result"] = "NOT_RUN"
    assert tool.next_stage(ready, {"X": ready}) == "build"

    verified = _managed_item()
    assert tool.next_stage(verified, {"X": verified}) == "signoff"


def test_stage_records_are_sequential_and_the_legacy_population_is_fixed():
    """BK-74-AC2. A later playbook cannot float free of its predecessor."""
    tool = _tool()
    doc = copy.deepcopy(_doc())
    before = tool.lint(doc)
    assert not before
    next(i for i in doc["items"] if i["id"] == "BK-74").pop(
        "stage_records")
    assert any("lifecycle migration population" in problem
               for problem in tool.lint(doc))

    doc = copy.deepcopy(_doc())
    managed = next(i for i in doc["items"] if i["id"] == "BK-74")
    managed["stage_records"]["build"]["result"] = "BUILT"
    managed["stage_records"]["start"]["result"] = "BLOCKED"
    assert any("Build began before" in problem for problem in tool.lint(doc))


def test_signoff_is_required_for_managed_done_and_then_closes_the_router():
    """BK-74-AC3. Passing tests are an input to sign-off, not sign-off."""
    tool = _tool()
    item = _managed_item()
    assert not tool.derive_done(item, {"X": item})
    assert tool.next_stage(item, {"X": item}) == "signoff"
    item["stage_records"]["signoff"]["result"] = "SIGNED_OFF"
    assert tool.derive_done(item, {"X": item})
    assert tool.next_stage(item, {"X": item}) is None


def test_evidence_may_accumulate_on_an_open_build_but_not_be_declared_complete():
    """BK-74-AC2, and the waterfall it originally encoded.

    The rule was `test not in (None, "NOT_RUN") and build != "BUILT"`, so no
    criterion could carry a result until every criterion was built. Measured
    10 September 2026 across the 53 unmanaged rows, it refused seven with a
    full contract that are being built the way this repository builds -- one
    criterion at a time, evidence recorded as each lands. BK-34 is the plain
    case: two of four criteria PASS with AC3 blocked on BK-53, which is a
    correct state the model could not write down.

    The three rows BK-74 was tested against were all complete-build rows, so
    the assumption was never put to a partial one.

    WHAT IS KEPT IS THE PART WORTH KEEPING: a VERIFIED Evidence Pack asserts
    the whole row's evidence stands, and over a half-built row that is false.
    """
    tool = _tool()
    doc = tool.load()

    def complaints(build: str, test: str) -> list[str]:
        item = _managed_item()
        item.update(id="Y", delivery_status="in_progress",
                    implementation="partial", verification="partial")
        item["stage_records"]["build"]["result"] = build
        item["stage_records"]["test"]["result"] = test
        item["stage_records"]["signoff"]["result"] = "NOT_RUN"
        probe = dict(doc, items=[item])
        return [p for p in tool._delivery_lifecycle(probe, [item])
                if p.startswith("Y:")]

    for test_state in ("OPEN", "FAILED", "STALE"):
        assert not complaints("OPEN", test_state), (
            f"an OPEN build with a {test_state} Evidence Pack was refused; "
            f"that is a row being built one criterion at a time")

    # THE NEGATIVE CONTROL, which is the whole reason the rule survives at
    # all: VERIFIED still means the row's evidence stands, and it cannot.
    assert any("VERIFIED before the Build Record was BUILT" in p
               for p in complaints("OPEN", "VERIFIED")), (
        "a VERIFIED Evidence Pack over an OPEN build was accepted, so the "
        "relaxation removed the rule rather than narrowing it")

    # AND `done` IS UNMOVED BY ANY OF IT.
    open_row = _managed_item()
    open_row["stage_records"]["build"]["result"] = "OPEN"
    open_row["stage_records"]["test"]["result"] = "OPEN"
    open_row["stage_records"]["signoff"]["result"] = "NOT_RUN"
    assert not tool.derive_done(open_row, {"X": open_row})


def test_a_row_with_no_stage_records_is_not_exempt_from_sign_off():
    """BK-74-AC3, THE HALF THE MANAGED CASE COULD NOT SEE.

    `test_signoff_is_required_for_managed_done` asks a row that HAS stage
    records, and it passed throughout. The gate read `if records and ...`, so
    the question was never put to a row that had none -- and 80 of 83 rows had
    none, 54 of them live and not legacy.

    Measured 10 September 2026: BK-21, a P0 product row with four PASSing
    criteria, derived `done: True` with `signoff: None`. The rows that
    recorded their lifecycle were held at NOT_RUN and the rows that recorded
    nothing went through, which is absence reading as exemption in the one
    function that decides whether work is finished.

    A CONTROL SCOPED TO THE OPTED-IN POPULATION CANNOT SEE THE OPT-OUT. That
    is CLAUDE.md §1 step 4 -- the check draws its population from the whole
    product -- arriving at the delivery registry.
    """
    tool = _tool()
    unmanaged = _managed_item()
    unmanaged.pop("stage_records")
    assert not tool.derive_done(unmanaged, {"X": unmanaged}), (
        "a governed row with NO stage records derived done. Absence of a "
        "record is not a sign-off; it is the absence of one")

    # AND THE ROUTER AGREES, so the board cannot say `done` while the router
    # still has somewhere to send it -- two answers to one question.
    assert tool.next_stage(unmanaged, {"X": unmanaged}) is not None, (
        "the row is not done and the router has nowhere to send it")

    # THE NEGATIVE CONTROL. Without this the assertion above would pass on a
    # `derive_done` that returned False for everything.
    signed = _managed_item()
    signed["stage_records"]["signoff"]["result"] = "SIGNED_OFF"
    assert tool.derive_done(signed, {"X": signed}), (
        "a fully recorded and signed row did not derive done, so the check "
        "above proves nothing")


def test_the_legacy_population_keeps_its_declared_exemption():
    """The fix above must not close the door on the ADMITTED gap.

    A `legacy` row rests on prose in BACKLOG.md, which is real evidence and
    not executable. It is declared, counted, and returns before the sign-off
    check -- so making that check unconditional had to leave it untouched.
    Asserted rather than assumed, because "my fix broke the exemption" and
    "my fix worked" look identical on a board that only counts `done`.
    """
    tool = _tool()
    legacy = _managed_item()
    legacy.pop("stage_records")
    legacy.update(legacy=True, verification="stale")
    assert tool.derive_done(legacy, {"X": legacy}), (
        "a declared legacy row lost its exemption; the pre-cutover population "
        "rests on prose and is counted, not silently dropped")


def _persisted_board_matches(tool, doc: dict, text: str) -> bool:
    current = re.search(
        f"{re.escape(tool.START)}(.*?){re.escape(tool.END)}", text, re.S)
    return bool(current and current.group(1).strip()
                == tool.board(doc, bind_execution=False).strip())


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
    assert _persisted_board_matches(tool, _doc(), text), (
        "the board in BACKLOG.md has drifted from status.yaml. Run:\n"
        "    python tools/backlog.py render")


def test_the_board_check_catches_a_hand_edited_count():
    """BK-75-AC2. Decoupling freshness must not make the board decorative."""
    tool = _tool()
    text = (ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    rows = len(_doc()["items"])
    planted = text.replace(f"**{rows} rows ·", f"**{rows + 1} rows ·", 1)
    assert planted != text, "the mutation changed nothing"
    assert not _persisted_board_matches(tool, _doc(), planted)


def test_stale_execution_cannot_change_the_persisted_board_projection():
    """BK-75-AC1. Evidence must be able to replace its stale predecessor.

    The live view still changes, proving the mutation is real. Only the
    persisted contract projection is stable, so the Class-A run no longer
    depends on the artifact it is trying to produce.
    """
    tool = _tool()
    doc = _doc()
    for item in doc["items"]:
        for criterion in item.get("acceptance") or []:
            for evidence in (criterion.get("evidence") or {}).values():
                evidence["_effective_result"] = evidence.get("result", "NOT_RUN")

    recorded_before = tool.board(doc, bind_execution=False)
    live_before = tool.board(doc, bind_execution=True)
    target = next(i for i in doc["items"] if i["id"] == "BK-73")
    automated = next(
        evidence
        for criterion in target["acceptance"]
        for level, evidence in (criterion.get("evidence") or {}).items()
        if level in tool.AUTOMATED_EVIDENCE and evidence.get("result") == "PASS")
    automated["_effective_result"] = "STALE"

    assert tool.board(doc, bind_execution=False) == recorded_before
    assert tool.board(doc, bind_execution=True) != live_before, (
        "the planted stale result changed no live roll-up, so the stability "
        "assertion above proved nothing")


@pytest.mark.parametrize("label,mutate,expect", [
    ("a step resting on a later phase's feature",
     lambda d: d["steps"][0].update(features=["F3"]), "later phase"),
    ("a step naming a feature nobody registered",
     lambda d: d["steps"][0].update(features=["Z9"]), "not registered"),
    ("a step naming a row nobody registered",
     lambda d: d["steps"][0].update(items=["BK-999"]), "not in the registry"),
    ("an id that is not STEP-<phase>-<nn>",
     lambda d: d["steps"][0].update(id="STEP-A-1"), "is not STEP-"),
    ("a phase that contradicts the id",
     lambda d: d["steps"][0].update(phase="D"), "does not match its id"),
    ("a step that will not say where it came from",
     lambda d: d["steps"][0].pop("basis"), "whether the PRD states it"),
    ("half a contract",
     lambda d: d["steps"][0].update(actor="advocate"), "not a contract"),
    ("a duplicated step id",
     lambda d: d["steps"].append(dict(d["steps"][0])), "appears twice"),
    ("AN EMPTY STEPS REGISTRY",
     lambda d: d.update(steps=[]), "exercised by no journey step"),
])
def test_the_step_rules_can_each_fail(label, mutate, expect):
    """THE POSITIVE CONTROLS FOR THE JOURNEY STEPS.

    The last case is the one that matters. Steps are the object the roll-up
    needs in the middle -- criteria prove an item, items and features serve a
    step, steps make a phase -- so a registry with no steps in it would let
    every phase-level claim pass by having nothing to check. It fails instead,
    because 44 features would then be exercised by nothing.
    """
    import copy
    tool = _tool()
    doc = copy.deepcopy(tool.load())
    before = tool.lint(doc)
    mutate(doc)
    new = [p for p in tool.lint(doc) if p not in before]
    assert any(expect in p for p in new), (
        f"planting {label} produced no new complaint containing {expect!r}; "
        f"the rule cannot fail and reports a clean journey either way. "
        f"new: {new[:3]}")


def test_the_cycle_check_can_see_a_cycle():
    """The dependency graph, and it had no control until this was written.

    `_cycles` is the check that would catch a loop, and nothing had ever shown
    it capable of finding one -- which is B-049's exact position: passing on
    every commit, never once having run.
    """
    tool = _tool()
    doc = _doc()
    a, b = doc["items"][0]["id"], doc["items"][1]["id"]
    doc["items"] = [dict(doc["items"][0], depends_on=[b]),
                    dict(doc["items"][1], depends_on=[a])] + \
        list(doc["items"][2:])
    assert any("dependency cycle" in p for p in tool.lint(doc)), (
        f"a planted {a} -> {b} -> {a} cycle was not reported")

    doc2 = _doc()
    doc2["items"] = [dict(doc2["items"][0],
                          depends_on=[doc2["items"][0]["id"]])] + \
        list(doc2["items"][1:])
    assert any("names itself" in p for p in tool.lint(doc2)), (
        "a row depending on itself was not reported")


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


def test_professional_registries_are_complete_and_cross_referenced():
    """BK-71-AC1. Expert practice is registered, populated and connected."""
    tool = _tool()
    doc = _doc()
    items = doc["items"]
    seen = {item["id"]: n for n, item in enumerate(items)}
    wave_problems, waves = tool._waves(doc, items, seen)
    assert not wave_problems, "\n  ".join(wave_problems)
    problems = tool._professional(
        doc,
        set(seen),
        {feature["id"] for feature in doc["features"]},
        {step["id"] for step in doc["steps"]},
        waves,
    )
    assert not problems, "\n  ".join(problems)
    assert tool.professional_population(doc) == {
        "advocate_standards": 20,
        "workflow_states": 13,
        "advice_maturity": 5,
        "roles": 7,
        "gap_closures": 14,
    }


def test_delivery_waves_are_complete_and_ordered():
    """BK-71-AC2. There is one schedulable plan and hard edges run forward."""
    tool = _tool()
    doc = _doc()
    items = doc["items"]
    seen = {item["id"]: n for n, item in enumerate(items)}
    problems, waves = tool._waves(doc, items, seen)
    assert not problems, "\n  ".join(problems)

    # DERIVED, NOT COUNTED. This read `== 80` twice and broke on the first
    # population change -- a hand-maintained count inside the very file that
    # exists because `Open - 13` was hand-maintained and wrong. The rule is
    # that every registered row has exactly one wave and the plan schedules
    # nothing that is not a row. The number is whatever the registry holds.
    assert len((doc["plan"] or {})["item_waves"]) == len(items), (
        "one row, one wave: the plan holds "
        f"{len((doc['plan'] or {})['item_waves'])} assignments for "
        f"{len(items)} rows, so one is duplicated or missing")
    assert set(waves) == set(seen)


def test_gap_closure_is_derived_from_registered_work():
    """BK-71-AC3. GC is a crosswalk, never a fifth status system."""
    tool = _tool()
    doc = _doc()
    forbidden = {"status", "planning_status", "delivery_status"}
    for gap in doc["professional"]["gap_closures"]:
        assert not forbidden.intersection(gap)
        assert tool.gap_state(
            gap, {item["id"]: item for item in doc["items"]}
        ) in {"PLANNED", "IN_PROGRESS", "BLOCKED", "CLOSED"}

    gap = {"links": [{"item": "X"}, {"item": "Y"}]}
    planned = {
        "X": {"id": "X", "delivery_status": "planned",
              "implementation": "none"},
        "Y": {"id": "Y", "delivery_status": "planned",
              "implementation": "none"},
    }
    assert tool.gap_state(gap, planned) == "PLANNED"
    planned["X"].update(delivery_status="in_progress", implementation="partial")
    assert tool.gap_state(gap, planned) == "IN_PROGRESS"
    planned["Y"].update(delivery_status="blocked",
                        blocked_by={"type": "decision", "description": "x"})
    assert tool.gap_state(gap, planned) == "BLOCKED"
    complete = {
        key: {"id": key, "delivery_status": "verifying",
              "implementation": "complete", "verification": "stale",
              "legacy": True, "acceptance": []}
        for key in ("X", "Y")
    }
    assert tool.gap_state(gap, complete) == "CLOSED"


def _replace_existing(mapping, key, value):
    """Mutate a field only after proving the probe names a real field."""
    assert key in mapping, f"positive control tried to mutate absent field {key!r}"
    before = copy.deepcopy(mapping[key])
    mapping[key] = value
    assert mapping[key] != before, f"positive control left {key!r} unchanged"


def _wave(doc, item):
    return next(row for row in doc["plan"]["item_waves"]
                if row["id"] == item)


def _drop_first_wave(doc):
    rows = doc["plan"]["item_waves"]
    before = len(rows)
    rows.pop(0)
    assert len(rows) == before - 1


def _duplicate_first_wave(doc):
    rows = doc["plan"]["item_waves"]
    before = len(rows)
    rows.append(dict(rows[0]))
    assert len(rows) == before + 1


def _author_gap_status(doc):
    gap = doc["professional"]["gap_closures"][0]
    assert "planning_status" not in gap
    gap["planning_status"] = "DONE"


_PROFESSIONAL_PROBES = [
    ("empty advocate standards",
     lambda d: _replace_existing(d["professional"], "advocate_standards", []),
     "advocate_standards population is 0"),
    ("empty workflow states",
     lambda d: _replace_existing(d["professional"], "workflow_states", []),
     "workflow_states population is 0"),
    ("empty advice maturity",
     lambda d: _replace_existing(d["professional"], "advice_maturity", []),
     "advice_maturity population is 0"),
    ("empty roles",
     lambda d: _replace_existing(d["professional"], "roles", []),
     "roles population is 0"),
    ("empty gap closures",
     lambda d: _replace_existing(d["professional"], "gap_closures", []),
     "gap_closures population is 0"),
    ("dangling feature",
     lambda d: _replace_existing(
         d["professional"]["advocate_standards"][0], "features", ["Z9"]),
     "features names 'Z9', which is not registered"),
    ("dangling step",
     lambda d: _replace_existing(
         d["professional"]["advocate_standards"][0], "steps", ["STEP-Z-99"]),
     "steps names 'STEP-Z-99', which is not registered"),
    ("dangling standard",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0], "standards", ["PA-99"]),
     "standards names 'PA-99', which is not registered"),
    ("dangling workflow state",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0], "workflow", ["EW-99"]),
     "workflow names 'EW-99', which is not registered"),
    ("dangling advice level",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0], "advice", ["AM-99"]),
     "advice names 'AM-99', which is not registered"),
    ("dangling linked work item",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0]["links"][0], "item", "BK-999"),
     "link names 'BK-999', which is not a row"),
    ("missing delivery wave", _drop_first_wave,
     "has no delivery-wave assignment"),
    ("duplicate delivery wave", _duplicate_first_wave,
     "delivery wave for BK-1 appears twice"),
    ("out-of-range delivery wave",
     lambda d: _replace_existing(_wave(d, "BK-1"), "wave", "W9"),
     "delivery wave 'W9' is not W0-W7"),
    ("null wave on active work",
     lambda d: _replace_existing(_wave(d, "BK-1"), "wave", None),
     "active item has no delivery wave"),
    ("authored gap status", _author_gap_status,
     "planning_status is authored"),
    ("foundation after feature",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0], "foundation_wave", "W2"),
     "stage waves are not ordered"),
    ("release before feature",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0], "release_gate_wave", "W0"),
     "stage waves are not ordered"),
    ("empty gap links",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0], "links", []),
     "has no registered work links"),
    ("invalid link stage",
     lambda d: _replace_existing(
         d["professional"]["gap_closures"][0]["links"][0],
         "stage", "nonsense"),
     "link stage 'nonsense' is not foundation, feature or release"),
    ("reverse-wave hard dependency",
     lambda d: _replace_existing(_wave(d, "BK-65"), "wave", "W1"),
     "BK-65 (W1) depends on BK-64 (W2)"),
    ("late foundation link",
     lambda d: _replace_existing(_wave(d, "BK-69"), "wave", "W1"),
     "after its W0 boundary"),
]


@pytest.mark.parametrize(
    "label,mutate,expected",
    _PROFESSIONAL_PROBES,
    ids=[probe[0].replace(" ", "-") for probe in _PROFESSIONAL_PROBES],
)
def test_professional_lint_positive_controls(label, mutate, expected):
    """BK-71-AC4. Every reported probe is an independent Class-A case."""
    tool = _tool()
    doc = copy.deepcopy(_doc())
    before = tool.lint(doc)
    assert not before, "the positive-control baseline is not clean: " + repr(before)
    mutate(doc)
    problems = tool.lint(doc)
    assert any(expected in problem for problem in problems), (
        f"planting {label} produced no complaint containing {expected!r}; "
        f"got: {problems[:8]}")


# ================= BK-60: the build guide cannot lose a rule ================

@pytest.mark.parametrize("label,mutate,expect", [
    ("a rule no playbook claims",
     lambda d: d["build_rules"]["rules"].append(
         dict(d["build_rules"]["rules"][0], id="BG-999")),
     "no playbook claims it"),
    ("a rule claimed by the wrong playbook",
     lambda d: d["build_rules"]["rules"][0].update(card="TEST_A_CHANGE.md"),
     "is claimed by"),
    ("an emptied registry",
     lambda d: d["build_rules"].update(rules=[]),
     "would pass by having nothing to check"),
    ("a population that moved without its count",
     lambda d: d["build_rules"]["rules"].pop(),
     "was added or lost without the count"),
    ("an unenforced rule with no reason",
     lambda d: next(r for r in d["build_rules"]["rules"]
                    if r["enforcement"] == "unenforced").pop("why_not"),
     "an admitted gap"),
    ("a runner naming no check",
     lambda d: next(r for r in d["build_rules"]["rules"]
                    if r["enforcement"] == "runner").pop("check"),
     "names no check"),
    ("a review with no evidence level",
     lambda d: next(r for r in d["build_rules"]["rules"]
                    if r["enforcement"] == "review").pop("evidence_level"),
     "what kind of recorded result"),
    ("a runner pointing at a test nobody wrote",
     lambda d: next(r for r in d["build_rules"]["rules"]
                    if r["enforcement"] == "runner").update(
                        check="tests/test_nothing.py::test_imaginary"),
     "does not exist"),
])
def test_a_build_rule_cannot_be_lost(label, mutate, expect):
    """BUILD RULES ARE DATA SO THE SPLIT CANNOT DROP ONE AGAIN.

    Dividing the 792-line guide into four stage playbooks was right -- a
    document that must be re-read in full before every change is one that gets
    skipped, and the per-stage cost is now about 200 lines instead of 792.

    But the split silently LOST TWO RULES: *a recommendation treated as
    authority to act*, and *a fixed intake questionnaire that ignores known or
    retrievable material*. The first is the boundary between advising a client
    and binding one -- the whole senior-counsel framing rests on it. Nothing
    failed. It was found only by diffing against a version of the guide that
    no longer exists on disk, and next time there would be nothing to diff.

    Each playbook now CLAIMS its rules by id. Losing one means deleting an id,
    which is a deliberate act, and these are the plants that prove the refusal
    works.
    """
    import copy
    tool = _tool()
    doc = copy.deepcopy(tool.load())
    before = tool.lint(doc)
    mutate(doc)
    new = [p for p in tool.lint(doc) if p not in before]
    assert any(expect in p for p in new), (
        f"planting {label} produced no complaint containing {expect!r}; the "
        f"rule cannot fail and reports a clean guide either way. new: "
        f"{new[:3]}")


def test_the_two_rules_the_split_dropped_are_back():
    """THE REGRESSION, NAMED. Not 'the manifest is complete' in the abstract.

    A count can be satisfied by any 77 rules. These two are the ones that were
    actually lost, so these two are asserted by their words -- and their
    playbooks must still say them, not merely list their ids.
    """
    tool = _tool()
    doc = tool.load()
    rules = {r["id"]: r for r in doc["build_rules"]["rules"]}

    for phrase in ("recommendation treated as authority to act",
                   "fixed intake questionnaire"):
        assert any(phrase in r["statement"].lower() for r in rules.values()), (
            f"{phrase!r} is not in the build-rule registry; it was dropped "
            f"once already when the guide was split")

    for rid, must in (("BG-068", "authority to act"),
                      ("BG-063", "questionnaire")):
        card = tool.PLAYBOOKS / rules[rid]["card"]
        assert must in card.read_text(encoding="utf-8").lower(), (
            f"{rid} is registered and {card.name} no longer says {must!r} -- "
            f"the id survived and the rule did not")
