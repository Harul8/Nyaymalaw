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
same arrangement as `AWAITING` in `assurance/gate/trace.py` and `CLOSED` in
`test_three_states.py`: the question gets answered for every module, including
the next one, and an entry whose wiring has landed fails here rather than
sitting in someone's memory.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Modules nothing imports BY DESIGN. Each with the reason.
ENTRY_POINTS: dict[str, str] = {
    "nm.app.main": "the process entry point — nothing imports a main",
}

#: Modules BUILT AND NOT YET WIRED, each with what will wire it.
#:
#: This is not an exemption list, it is a work queue with the honest name on
#: it. Every entry here is a feature whose mechanism exists and whose product
#: behaviour does not, and the difference is invisible to every other check in
#: this build.


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
    return {".".join(p.relative_to(ROOT ).with_suffix("").parts)
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
    mods = {".".join(p.relative_to(ROOT ).with_suffix("").parts) for p in sources}
    reached: set[str] = set()
    for p in sources:
        me = ".".join(p.relative_to(ROOT ).with_suffix("").parts)
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


# ===== the status field, joined to the wiring =====

#: Which feature each unwired module belongs to. The join is stated here
#: because nothing else in the build knows it: `features.yaml` names slices and
#: evals, and the module tree names files, and no edge connects them.
#: ONE MODULE MAY CARRY SEVERAL FEATURES, and the first version of this map
#: allowed only one. `nm/Archives/legal_brain/reason/adversarial.py` holds both the adversarial pass
#: (D7) and salvage (D8) — it named D7, and D8, the one feature whose status
#: was actually wrong, was the one it could not see. A join that silently
#: drops members is the same defect as a scan whose population went to zero.


def _tested_unwired_runtime_evals(
        features: dict[str, dict], evals: dict[str, dict],
        unwired_features: set[str]) -> list[str]:
    """Return tested features whose runtime evidence has no runtime path."""
    bad: list[str] = []
    for fid in sorted(unwired_features):
        feature = features.get(fid)
        if not feature or feature.get("status") not in ("tested", "verified live"):
            continue
        for eid in feature.get("historical_eval_ids", []):
            evaluation = evals.get(eid, {})
            if (evaluation.get("class") == "B"
                    and "turn" in str(evaluation.get("cadence", "")).lower()):
                bad.append(
                    f"{fid} is `{feature['status']}` and {eid} is class B at "
                    f"cadence {evaluation['cadence']!r} — but its module is UNWIRED, "
                    f"so no turn has ever produced what {eid} inspects")
    return bad


def test_the_runtime_evidence_sweep_can_see_a_planted_unwired_feature():
    """BK-52. Plant a tested feature whose every-turn eval has no caller.

    THE PLANT CARRIES `historical_eval_ids` because that is where the plan's
    eval assignment lives after BK-80-AC5. It said `eval_ids` for an hour after
    the rename and the sweep found nothing -- the control reporting clean while
    the thing it plants was invisible to it. The rule was right; the fixture
    was stale, which is the failure mode a positive control exists to prevent
    and is just as capable of having itself.
    """
    features = {"ZZ": {"id": "ZZ", "status": "tested",
                       "historical_eval_ids": ["E-ZZ"]}}
    evals = {"E-ZZ": {"id": "E-ZZ", "class": "B", "cadence": "Every turn"}}
    bad = _tested_unwired_runtime_evals(features, evals, {"ZZ"})
    assert len(bad) == 1 and "ZZ is `tested`" in bad[0]


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


def _declared_types() -> set[str]:
    src = "\n".join(p.read_text(encoding="utf8", errors="replace")
                    for p in _sources())
    return set(re.findall(r"^\s*class\s+(\w+)", src, re.M)) | set(
        re.findall(r"^\s*(\w+)\s*(?::\s*TypeAlias)?\s*=\s*NewType", src, re.M))


