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


UNWIRED: dict[str, str] = {
    # Kept for the tests and the corpus jobs, never for a served turn
    # (19 Oct 2026, P24: everything else the served app does not reach was deleted).
    "nm.shared.model_scripted":
        "the scripted model double the offline tests and the journey harness build the "
        "app with; production configuration never selects it",
    "nm.shared.model_replay":
        "records and replays model calls for the provider-adapter tests; nothing on a "
        "served turn uses it",
    "nm.Archives.legal_brain.retrieve.hybrid_sections":
        "imported only by the Act-store corpus jobs in pipeline/ (append_bare_acts, "
        "build_acts_v4), which build the index the served search reads",
}


OWNER: dict[str, tuple[str, ...]] = {
    # LB-120's successions answer "which Act do I read for this matter", which
    # is D4's question -- WHICH LAW APPLIES -- one step before D4's cause-to-
    # Article lookup. Named against D4 rather than given a feature of its own,
    # because what it adds is a condition on reading the right provision and
    # not a new promise to the advocate.
    "nm.Archives.legal_brain.procedure.governing_law_adapter": ("D4",),
    # P38's restore serves the persistence promise the store makes -- one
    # matter, versioned and sealed -- so it is named against I1 rather than
    # given a feature of its own. What it adds is that the promise survives
    # being put back, which is a property of the write and not a new promise
    # to the advocate.
    "nm.shared.restore_contracts": ("I1",),
    # P40's rehearsal is about the operation that keeps the matter available
    # and confidential when something goes wrong, so it is named against the
    # persistence promise rather than given a feature of its own: what it adds
    # is that the promise survives an incident, which is a property of the
    # operation and not a new promise to the advocate.
    "nm.shared.incident_contracts": ("I1",),
    # P41's gate decides whether the SERVED PRODUCT may be released at all, so
    # it is named against the turn contract every enabled feature runs through
    # rather than against a feature of its own. A release gate with a feature
    # of its own would be a feature that could be marked done.
    "nm.shared.release_contracts": ("I1",),
    # P35's qualified-review record reviews THE ADVICE AS SERVED, so it is
    # named against the feature that produces it rather than given one of its
    # own -- and against E5, because what the record keeps beyond a score is
    # the disagreement and the reservations. BK-67-AC1's words are that no
    # counsel-facing feature conforms without review with *material
    # reservations kept visible*; E2 and E5 are where those live.
    "nm.shared.legal_review_contracts": ("E2", "E5"),
    # P06/P07/P22's mechanisms, each named against the feature whose contract
    # it serves, so the status check below covers them instead of skipping
    # three modules that run on no turn.
    "nm.shared.egress_contracts": ("I1",),
    "nm.shared.store_envelope": ("I1",),
    # P10's transactional store serves the same persistence contract the
    # file store does -- one matter, versioned and sealed -- so it is named
    # against I1 rather than given a feature of its own. What it adds is
    # atomicity across three records, which is a property of the write and
    # not a new promise to the advocate.
    "nm.shared.store_postgres": ("I1",),
    # P11's worker publishes what a turn accepted, so it serves the turn
    # contract rather than a promise of its own.
    "nm.shared.worker": ("I1",),
    "nm.Archives.legal_brain.reason.premise": ("D2",),
    # P18's currency ledger answers A3's re-orientation promise -- what moved
    # since the advocate was last here, and what they may still rely on -- so
    # it is named against A3 rather than given a feature of its own. The
    # cascade it extends already carries A3's `@implements`.
    "nm.work_the_file.dependency": ("A3",),
    # BK-69's boundary belongs to the feature that will cross it. C6 is
    # document intake and extraction -- the media path -- so when C6 moves off
    # `implementation: none`, the status check above starts asking whether
    # this module is still unwired instead of skipping it.
    "nm.open_matter.media_contracts": ("C6",),
    "nm.open_matter.quarantine": ("B4",),
    "nm.open_matter.screens": ("B2", "B3", "B5", "B6"),
    "nm.open_matter.intake": ("C6",),
}


UNTYPED: dict[str, str] = {
    "TurnRoute":
        "B1. NAMING DRIFT — represented by `nm.Archives.legal_brain.understand.route.ReadRoute`: its "
        "`route`, `mode` and `statement` fields are the contract's route, mode "
        "and stated reading. Implementation owner: `nm/Archives/legal_brain/understand/route.py`, wired "
        "by `nm/Archives/legal_brain/orchestrate/turn.py::_read_route`.",
    "ConflictScreen":
        "B3. GENERIC REPRESENTATION — `nm.open_matter.conflict.screen` produces "
        "`nm.open_matter.screens.Screen(kind=CONFLICT)`, whose state, covers, unread "
        "and release fields carry the declared screen. Implementation owners: "
        "`nm/open_matter/conflict.py` and `nm/open_matter/screens.py`.",
    "CompetenceAssessment":
        "B4. GENERIC REPRESENTATION — `TurnEngine._competence_screen` produces "
        "`nm.open_matter.screens.Screen(kind=COMPETENCE)`; state/detail carry coverage "
        "and the recorded release model is `screens.Release`. Implementation "
        "owners: `nm/Archives/legal_brain/orchestrate/turn.py` and `nm/open_matter/screens.py`.",
    "Reorientation":
        "A3. GENUINELY ABSENT — zero mentions. Consistent with `gaps` and "
        "`cascade` being UNWIRED: nothing composes a re-orientation.",
    "ResearchTask":
        "D4. GENUINELY ABSENT — zero mentions. The research plan is executed "
        "without the typed task record the PRD says it produces.",
    "SessionSeal":
        "I1. GENUINELY ABSENT — zero mentions.",
    "ThresholdMap":
        "D1. NAMING DRIFT — `nm/Archives/legal_brain/reason/thresholds.py` defines `Threshold` and "
        "the map is a plain dict. Either the PRD names the dict or the code "
        "names the type; today neither points at the other.",
    "LimitationComputation":
        "D2. NAMING DRIFT — implemented as `Limitation` in "
        "`nm/Archives/legal_brain/procedure/limitation.py`. The contract is met and the name is not.",
}


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
    same rule `assurance/gate/trace.py` applies to AWAITING.
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
    probe = ROOT / "nm" / "work_the_file" / "_unreached_probe.py"
    probe.write_text("VALUE = 1\n", encoding="utf8")
    try:
        orphans = _modules() - _reached_from_production()
        assert "nm.work_the_file._unreached_probe" in orphans, (
            "the scan did not see a module nothing imports")
    finally:
        probe.unlink()


