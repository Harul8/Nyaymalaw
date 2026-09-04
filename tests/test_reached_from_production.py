"""EVERY MODULE IS REACHED FROM PRODUCTION, or says why not.

WHY THIS EXISTS, AND WHY M2 DID NOT CATCH IT
----------------------------------------------
`test_no_declared_owner_is_dead` asks whether a function is REFERENCED
ANYWHERE, and counts a test reference. That is the right question for a dead
function and the wrong one for a dead module: a module with a full unit suite
and no caller passes it, every time, while doing nothing on any served turn.

That is the defect S4 was built out of. `limitation`, `thresholds` and
`deadlines` were built, unit-tested, mutation-covered and called by nothing —
and four defects (B-057 to B-060) were sitting in the wiring, invisible to a
green suite, until a served turn was actually driven.

The lesson was applied in S4 and S5 and then dropped. Measured on 31 August
2026: TEN modules built across S6 to S10 were reachable only from their own
tests, while five of their features were marked `tested`.

THE POPULATION IS THE MODULE TREE
-----------------------------------
Asked the other way — does every import resolve — it would confirm that the
things being imported exist, which cannot fail. This asks which modules NOTHING
imports, which is the only direction that finds anything.

A DECLARED EXEMPTION IS WORK; A SILENT ONE IS A SURPRISE
----------------------------------------------------------
`UNWIRED` names each module nothing calls yet and what will call it. It is the
same arrangement as `AWAITING` in `tools/trace.py` and `CLOSED` in
`test_three_states.py`: the question gets answered for every module, including
the next one, and an entry whose wiring has landed fails here rather than
sitting in someone's memory.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest
import yaml

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Modules nothing imports BY DESIGN. Each with the reason.
ENTRY_POINTS: dict[str, str] = {
    "nm.bootstrap.main": "the process entry point — nothing imports a main",
}

#: Modules BUILT AND NOT YET WIRED, each with what will wire it.
#:
#: This is not an exemption list, it is a work queue with the honest name on
#: it. Every entry here is a feature whose mechanism exists and whose product
#: behaviour does not, and the difference is invisible to every other check in
#: this build.
UNWIRED: dict[str, str] = {
    "nm.core.evidence_item":
        "C7. The inventory is built; nothing takes documents in or holds an "
        "evidence position on a matter.",
    "nm.core.theory":
        "D6. One theory per thread, and nothing in the turn forms one.",
    "nm.core.adversarial":
        "D7 and D8. The adversarial pass runs across the whole file AFTER "
        "per-thread analysis, and the turn has no such phase yet.",
    "nm.core.gaps":
        "A3 / §5.1-5.3. The gap queue is built; the turn still asks its "
        "questions from the gates directly rather than from a ranked queue.",
    "nm.core.cascade":
        "A3 / §5.4. The correction cascade is built; nothing detects that a "
        "material fact CHANGED between turns, which is its trigger.",
    "nm.core.quarantine":
        "B4. Deliberate — the conflict screen that quarantines is slice 10 "
        "and is declared unbuilt in the gate matrix.",
    "nm.core.screens":
        "B2-B6. Deliberate — the screens are declared `decided`, and their "
        "NEVER clauses are not implemented.",
    "nm.core.intake":
        "C6. Deliberate — document intake is declared `decided`; nothing "
        "accepts an upload.",
    "nm.domain.tiers":
        "S0's tier vocabulary. Consulted by the model config through the "
        "environment rather than by import.",
    "nm.knowledge.artefact":
        "S11's artefact-identity check, whose counterexample is the real "
        "dense index. Nothing builds a derived artefact on a turn yet.",
}


def _sources() -> list[pathlib.Path]:
    """Every module file that still exists WHEN ITS BYTES ARE READ.

    Other checks in this suite plant probe modules under `nm/` and remove them,
    so a walk can hand back a path that is gone a moment later. Skipping it is
    right: a file that no longer exists is not an orphan, and a scan that
    crashes on a neighbour's probe is a scan people run less often.
    """
    out = []
    for p in (ROOT / "nm").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            p.read_text(encoding="utf8")
        except OSError:
            continue
        out.append(p)
    return out


def _modules() -> set[str]:
    return {".".join(p.relative_to(ROOT).with_suffix("").parts)
            for p in _sources() if p.name != "__init__.py"}


def _reached_from_production() -> set[str]:
    """Modules imported by another module inside `nm/`.

    `from nm.core import chronology` binds a SUBMODULE, not an attribute of
    `nm.core`, and the first version of this scan counted only `node.module` —
    so it reported `chronology`, `cause` and `thresholds` as orphans while the
    turn engine was importing all three. A scan that is wrong in the direction
    of alarm is one people learn to overrule.
    """
    sources = _sources()
    mods = {".".join(p.relative_to(ROOT).with_suffix("").parts) for p in sources}
    reached: set[str] = set()
    for p in sources:
        me = ".".join(p.relative_to(ROOT).with_suffix("").parts)
        try:
            tree = ast.parse(p.read_text(encoding="utf8"))
        except OSError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("nm"):
                base = node.module
                if base in mods and base != me:
                    reached.add(base)
                for a in node.names:
                    cand = f"{base}.{a.name}"
                    if cand in mods and cand != me:
                        reached.add(cand)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in mods and a.name != me:
                        reached.add(a.name)
    return reached


def test_the_scan_can_see_the_module_tree():
    """A guard on the guard: an empty population passes everything below."""
    assert len(_modules()) >= 30, f"only {len(_modules())} modules found"


def test_every_module_is_reached_from_production_or_declared_unwired():
    """THE CHECK. A module nothing calls does nothing on a served turn.

    S4's four defects all lived in the wiring of modules whose unit suites
    were green. The suite could not see them and neither could M2.
    """
    orphans = sorted(_modules() - _reached_from_production())
    undeclared = [m for m in orphans
                  if m not in ENTRY_POINTS and m not in UNWIRED]

    assert not undeclared, (
        "these modules are imported by nothing in `nm/` — they run on no "
        "served turn, however green their tests are:\n  "
        + "\n  ".join(undeclared)
        + "\n\nWire it, or declare it in UNWIRED with what will wire it. A "
          "module with a full unit suite and no caller passes every other "
          "check in this build, which is exactly how B-057 to B-060 reached a "
          "served turn.")


def test_no_declaration_outlives_its_wiring():
    """AN EXEMPTION NOBODY REMOVES IS AN EXEMPTION NOBODY READS.

    The day a module is wired, its UNWIRED entry becomes a false statement
    about the build. It expires here rather than in someone's memory — the
    same rule `tools/trace.py` applies to AWAITING.
    """
    reached = _reached_from_production()
    stale = sorted(m for m in UNWIRED if m in reached)
    assert not stale, (
        "these are declared UNWIRED and something now imports them:\n  "
        + "\n  ".join(stale) + "\n\nDelete the declaration.")

    gone = sorted(m for m in (set(UNWIRED) | set(ENTRY_POINTS))
                  if m not in _modules())
    assert not gone, f"declared and no longer exists: {gone}"


def test_the_scan_can_see_an_unreached_module():
    """THE POSITIVE CONTROL. A scan over a tree whose modules all happen to be
    imported proves nothing about the scan."""
    probe = ROOT / "nm" / "core" / "_unreached_probe.py"
    probe.write_text("VALUE = 1\n", encoding="utf8")
    try:
        orphans = _modules() - _reached_from_production()
        assert "nm.core._unreached_probe" in orphans, (
            "the scan did not see a module nothing imports")
    finally:
        probe.unlink()


# ===== the status field, joined to the wiring =====

#: Which feature each unwired module belongs to. The join is stated here
#: because nothing else in the build knows it: `features.yaml` names slices and
#: evals, and the module tree names files, and no edge connects them.
#: ONE MODULE MAY CARRY SEVERAL FEATURES, and the first version of this map
#: allowed only one. `nm/core/adversarial.py` holds both the adversarial pass
#: (D7) and salvage (D8) — it named D7, and D8, the one feature whose status
#: was actually wrong, was the one it could not see. A join that silently
#: drops members is the same defect as a scan whose population went to zero.
OWNER: dict[str, tuple[str, ...]] = {
    "nm.core.evidence_item": ("C7",),
    "nm.core.theory": ("D6",),
    "nm.core.adversarial": ("D7", "D8"),
    "nm.core.gaps": ("A3",),
    "nm.core.cascade": ("A3",),
    "nm.core.quarantine": ("B4",),
    "nm.core.screens": ("B2", "B3", "B5", "B6"),
    "nm.core.intake": ("C6",),
}


def _spec(name: str) -> list[dict]:
    d = yaml.safe_load((ROOT / "spec" / f"{name}.yaml").read_text(encoding="utf8"))
    return d if isinstance(d, list) else list(d.values())[0]


def test_no_feature_is_tested_while_its_eval_runs_every_turn_and_it_has_no_turn():
    """A RUNTIME EVAL WITHOUT A RUNTIME HAS NOT RUN.

    Class A asks a question about logic, and answering it against the module
    directly is what class A IS — so `tested` is honest for a class-A feature
    whose module is unwired. Class B at "Every turn" cadence asks a question
    about what a SERVED TURN produces, and there is no honest way to answer it
    while nothing serves it.

    Measured on 31 August 2026: D8 (salvage) was `tested`. Its only eval,
    E-084, is class B at every-turn cadence, and no turn produced a salvage
    route at all. Its sibling D7 carried the same shape of eval and was
    correctly `built`, which is how the difference became visible.

    T7 could not see this. It checks that a feature at `tested` has an eval
    that RAN, and E-084 ran — against a module nothing calls.
    """
    features = {f["id"]: f for f in _spec("features")}
    evals = {e["id"]: e for e in _spec("evals")}
    unwired_features = {fid for m in UNWIRED if m in OWNER
                        for fid in OWNER[m]}

    bad = []
    for fid in sorted(unwired_features):
        f = features.get(fid)
        if not f or f.get("status") not in ("tested", "verified live"):
            continue
        for eid in f.get("eval_ids", []):
            e = evals.get(eid, {})
            if e.get("class") == "B" and "turn" in str(e.get("cadence", "")).lower():
                bad.append(
                    f"{fid} is `{f['status']}` and {eid} is class B at "
                    f"cadence {e['cadence']!r} — but its module is UNWIRED, "
                    f"so no turn has ever produced what {eid} inspects")

    assert not bad, (
        "\n  ".join([""] + bad)
        + "\n\nEither wire it, or move the status back to `built`. A "
          "structural eval that ran against a module nothing serves measured "
          "the module, not the product.")


def test_every_unwired_module_names_a_feature_that_exists():
    """The join must not rot. A module renamed out from under OWNER, or a
    feature id that no longer exists, silently empties the check above —
    which is S11: a check whose population went to zero still passes."""
    ids = {f["id"] for f in _spec("features")}
    missing = sorted(f"{m} -> {fid}" for m, fids in OWNER.items()
                     for fid in fids if fid not in ids)
    assert not missing, f"OWNER names features that do not exist: {missing}"

    unowned = sorted(m for m in UNWIRED
                     if m not in OWNER and not m.startswith(("nm.domain.tiers",
                                                            "nm.knowledge.artefact")))
    assert not unowned, (
        f"these modules are UNWIRED and name no feature, so the status check "
        f"above skips them entirely: {unowned}")


# ===== the PRODUCES clause, joined to the code =====

#: PRODUCES types the code does not define, each with WHY and what settles it.
#:
#: `tests/test_produces_contracts.py` refuses a dataclass that contradicts
#: Appendix E, and that is the right check over the wrong population: Appendix
#: E holds ten schemas and the features declare far more PRODUCES types than
#: that. A contract nobody implemented is invisible to a check that starts from
#: the contracts that were implemented.
#:
#: Measured on 4 September 2026 across every feature at `built` or beyond.
#:
#: `AdvocateIdentity` was here and is not, and the reason is worth stating:
#: A1 moved to `decided`, so its contract is no longer CONTRADICTED by its
#: status -- the status now says the feature is not built, which is true.
#: The absence itself is B-082, open, and the register test keeps it open.
#: A declaration whose reason has gone is deleted; the defect it named is not.
UNTYPED: dict[str, str] = {
    "Reorientation":
        "A3. GENUINELY ABSENT — zero mentions. Consistent with `gaps` and "
        "`cascade` being UNWIRED: nothing composes a re-orientation.",
    "ResearchTask":
        "D4. GENUINELY ABSENT — zero mentions. The research plan is executed "
        "without the typed task record the PRD says it produces.",
    "SessionSeal":
        "I1. GENUINELY ABSENT — zero mentions.",
    "Recommendation":
        "E2. BUILT AS A STRING. `turn._recommend` composes prose; the PRD "
        "declares a record. B-074 is what an untyped recommendation costs — "
        "nothing could ask it what it was based on, so it contradicted the "
        "finding printed beneath it.",
    "ThresholdMap":
        "D1. NAMING DRIFT — `nm/core/thresholds.py` defines `Threshold` and "
        "the map is a plain dict. Either the PRD names the dict or the code "
        "names the type; today neither points at the other.",
    "LimitationComputation":
        "D2. NAMING DRIFT — implemented as `Limitation` in "
        "`nm/core/limitation.py`. The contract is met and the name is not.",
}


def _declared_types() -> set[str]:
    src = "\n".join(p.read_text(encoding="utf8", errors="replace")
                    for p in _sources())
    return set(re.findall(r"^\s*class\s+(\w+)", src, re.M)) | set(
        re.findall(r"^\s*(\w+)\s*(?::\s*TypeAlias)?\s*=\s*NewType", src, re.M))


def _produced_types() -> dict[str, str]:
    """Every `Name { ... }` a feature at built-or-beyond says it produces."""
    out: dict[str, str] = {}
    for f in _spec("features"):
        if f["status"] == "decided":
            continue
        for clause in f.get("produces", []):
            for name in re.findall(r"`(\w+)\s*\{", str(clause)):
                out.setdefault(name, f["id"])
    return out


def test_every_produces_contract_has_a_type_or_is_declared_untyped():
    """A FEATURE OUTPUTS WHAT ITS CONTRACT SAYS, or the gap is written down.

    Measured on 4 September 2026: seven features stood at `tested` while the
    typed record each declares was absent, untyped or under another name — and
    nothing in the build could see it, because the only check over PRODUCES
    starts from Appendix E's ten schemas rather than from the clauses.

    Four of the seven had ZERO mentions in `nm/`. One of those is
    `AdvocateIdentity`, so the product had no notion of who was using it beyond
    a string in a query parameter.
    """
    known = _declared_types()
    missing = {n: fid for n, fid in _produced_types().items() if n not in known}
    undeclared = sorted(f"{fid}: {n}" for n, fid in missing.items()
                        if n not in UNTYPED)
    assert not undeclared, (
        "these features declare a PRODUCES type that `nm/` does not define:"
        "\n  " + "\n  ".join(undeclared)
        + "\n\nImplement it, rename one side to match the other, or declare it "
          "in UNTYPED with which of those it needs.")


def test_no_untyped_declaration_outlives_its_type():
    """The list shrinks as the build catches up, and says so."""
    known = _declared_types()
    landed = sorted(n for n in UNTYPED if n in known)
    assert not landed, (
        f"these are declared UNTYPED and `nm/` now defines them: {landed}. "
        f"Delete the declaration.")

    produced = _produced_types()
    orphaned = sorted(n for n in UNTYPED if n not in produced)
    assert not orphaned, (
        f"these are declared UNTYPED and no feature at built-or-beyond "
        f"produces them any more: {orphaned}. Delete the declaration.")


def test_the_produces_scan_can_see_an_unimplemented_contract():
    """THE POSITIVE CONTROL. If the clause parser matched nothing, every
    feature would pass for having produced nothing at all."""
    assert _produced_types(), "no PRODUCES clause was parsed from any feature"
    assert "Fact" in _declared_types(), "the type scan found no known type"
