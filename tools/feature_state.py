"""What the CURRENT registry says about each PRD feature.

    from tools.feature_state import project, reconcile

WHY THIS EXISTS, 10 September 2026
------------------------------------
`tools/export_spec.py` read each feature's status out of
`docs/Nyaymalaw_Project_Plan.xlsx` -- the ORIGINAL vertical-slice plan, frozen
in August. Eighteen features exported as `tested` on that authority.

Measured today against `docs/backlog/status.yaml`: NOT ONE feature has a
complete implementation with current passing evidence. A1 exported as `tested`
while its own delivery rows are `in_progress` with `implementation: partial`
and every acceptance criterion reachable from it reads `NOT_RUN`.

A generated specification carrying a legacy verdict is worse than one carrying
none, because everything downstream gates on it: T3 asks whether a `built`
feature has code, T4 whether a `tested` feature's evals ran, T7 whether a
shipped feature's NEVER clauses are refused, and the release gate whether a
`tested` feature's evals are declared. All four inherited a fifteen-day-old
spreadsheet cell.

WHAT EACH SOURCE CAN ACTUALLY ANSWER, AND WHAT IT CANNOT
---------------------------------------------------------
Measured before this was written rather than assumed, because a roll-up over
the wrong relation is the corpus trap one layer up: A ZERO FROM THE WRONG INDEX
READS EXACTLY LIKE ABSENCE.

``docs/backlog/steps.yaml`` ``items:``
    NOT a delivery relation. It records which rows TOUCH a step, and one row
    spans up to ELEVEN features -- BK-63 reaches B4, B5, B6, C3, E4, E5, F1,
    F2, F3, F4 and G3. Rolling implementation up through it was tried and
    measured: it reported B2, B6 and G3 as `built` with no implementing code
    anywhere in `nm/`, and it reported D5, D6, D8 and D9 -- four features with
    live production modules -- as `decided`. Wrong in both directions at once,
    which is what a shared relation does when it is read as an exclusive one.

``docs/backlog/status.yaml`` ``delivers:``
    IS the delivery relation, and it is authoritative where it exists. Seven
    rows, nineteen features. Every one of them is a planning row that has not
    started, so today this source can say `none` and nothing else.

``@implements`` in ``nm/``
    Says that code claiming a feature EXISTS. It may never say the feature is
    proven -- BK-48-AC1 is explicit that tested status is not promoted from a
    decorator -- so it can raise a feature to `built` and never past it.

So the projection asks each source only what it can answer, AND RECORDS WHICH
ONE ANSWERED, in `implementation_basis`. A feature whose only evidence is a
decorator is a different fact from one the registry records, and collapsing
them into a single word would be this repository's three-stores defect in a
fourth place.

WHAT THIS DELIBERATELY CANNOT PRODUCE
---------------------------------------
`tested`, unless a delivering row is `implementation: complete` AND its
acceptance evidence is currently PASSING against this source fingerprint.
`verified live` is not derivable here at all: it would need production or
browser evidence, and inventing a path to it would be a status this projection
could grant without anybody measuring anything.
"""
from __future__ import annotations

import collections
import pathlib
import sys
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: The worst state wins, and the order is `tools/backlog.py::proof_state`'s.
#: Imported rather than restated: a second copy of an ordering is a second
#: copy of a decision.
PROOF_ORDER = ["FAIL", "BLOCKED", "STALE", "NOT_RUN", "PASS", "NOT_APPLICABLE"]

#: `not_recorded` is the third state, and it is the point of this field. A
#: feature the registry does not mention and no code declares has NOT been
#: measured as unimplemented -- nobody looked -- and that must be visible in
#: the output rather than rendered as `none`.
IMPLEMENTATION = ("none", "partial", "complete", "not_recorded")

#: WHICH SOURCE ANSWERED, and `contradicted` is not a shade of `trace`.
#:
#:   registry     a delivering row records the implementation.
#:   trace        no row delivers this feature; production code declares it.
#:   contradicted a row DOES deliver it and says `implementation: none`, while
#:                production code declares it. Silence and denial are different
#:                facts and the second is the sharper one -- it is BK-48-AC1's
#:                negative control in the tree already: *a currently
#:                implemented route under a contradictory pre-build state*.
#:   absent       nothing records it and no code claims it. Nobody looked.
BASIS = ("registry", "trace", "contradicted", "absent")


@dataclass(frozen=True)
class FeatureState:
    """One feature's present state, with the source of each half named."""

    feature: str
    implementation: str
    implementation_basis: str
    proof: str
    status: str
    delivered_by: tuple[str, ...]
    declared_in: tuple[str, ...]

    @property
    def recorded_only_in_code(self) -> bool:
        """Code claims this feature and the current registry does not record it.

        BK-48's title is this sentence: *Phase B is built and the register says
        it is not*. It is reported, never resolved silently in either
        direction -- the decorator does not promote the registry, and the
        registry does not silence the decorator.
        """
        return bool(self.declared_in) and self.implementation_basis != "registry"


def implements_map(root: pathlib.Path | None = None) -> dict[str, list[str]]:
    """feature id -> the source files declaring `@implements` for it.

    `scan_tree` is imported from `tools.trace`, which owns the one AST scanner
    in this repository. A second scanner here would be a second answer to
    "does code claim this feature", and the question of what refuses the
    second copy is the one that keeps being answered too late.
    """
    from tools.trace import SRC, scan_tree

    base = SRC if root is None else root / "nm"
    out: dict[str, list[str]] = {}
    for args, files in scan_tree(base, "implements").items():
        for fid in args:
            out.setdefault(str(fid), []).extend(files)
    return {k: sorted(set(v)) for k, v in out.items()}


def reconcile(feature_ids: list[str], steps: list[dict],
              items: list[dict]) -> list[str]:
    """Refuse a projection whose populations do not line up. BK-48-AC1.

    THIS RUNS BEFORE ANYTHING IS WRITTEN, over all 44 current features rather
    than a sample, because the failure mode is not a wrong value in one row --
    it is a row that silently does not exist. A feature absent from the
    reconciliation gets no state at all, and an absent state is exactly what
    `.get(fid, "decided")` would render as a confident `decided`.
    """
    bad: list[str] = []

    seen = collections.Counter(feature_ids)
    for fid, n in sorted(seen.items()):
        if n > 1:
            bad.append(f"{fid} is defined {n} times in the PRD contracts")
    known = set(seen)

    named_by_steps = {f for s in steps for f in s.get("features") or []}
    for fid in sorted(named_by_steps - known):
        bad.append(f"steps.yaml names {fid!r}, which is not a PRD feature")
    for fid in sorted(known - named_by_steps):
        bad.append(f"{fid} is a PRD feature that no journey step reaches")

    for item in items:
        for fid in item.get("delivers") or []:
            if fid not in known:
                bad.append(f"{item.get('id')} delivers {fid!r}, "
                           f"which is not a PRD feature")

    # A DECORATOR NAMING AN UNKNOWN ID IS NOT CHECKED HERE, deliberately.
    # `tools/trace.py` T2 owns that question and it holds the one thing this
    # function does not: the anchors list. H8 and P1 are specified ids that are
    # simply not four-field feature contracts, and a check written here without
    # them would report two false orphans forever. One question, one owner.
    return bad


def _implementation(delivering: list[dict], declared_in: list[str]
                    ) -> tuple[str, str]:
    """(implementation, basis) -- and the basis is not decoration.

    The registry answers where it records a delivery relation. Where it does
    not, a production `@implements` says code exists and says NOTHING about how
    much of the feature it covers, so it yields `partial` and a basis that
    admits the registry was silent.
    """
    states = {it.get("implementation") for it in delivering}
    if delivering and states == {"complete"}:
        return "complete", "registry"
    if delivering and states - {"none"}:
        return "partial", "registry"
    if declared_in:
        return "partial", "contradicted" if delivering else "trace"
    if delivering:
        return "none", "registry"
    return "not_recorded", "absent"


def _proof(delivering: list[dict], proof_state) -> str:
    """Worst effective evidence across the delivering rows. Never the workbook.

    A `legacy: true` row rests on prose in BACKLOG.md. That is real evidence
    and it is not executable, so it contributes NOT_RUN here: AC5 forbids
    restoring a tested label without current trace evidence, and prose is
    precisely what it forbids restoring it from.
    """
    worst = "NOT_APPLICABLE"
    saw_any = False
    for item in delivering:
        if item.get("legacy"):
            saw_any = True
            worst = min(worst, "NOT_RUN", key=PROOF_ORDER.index)
            continue
        for ac in item.get("acceptance") or []:
            saw_any = True
            worst = min(worst, proof_state(ac), key=PROOF_ORDER.index)
    return worst if saw_any else "NOT_RUN"


def project(feature_ids: list[str], *, root: pathlib.Path | None = None,
            bind_execution: bool = True) -> dict[str, FeatureState]:
    """The present state of every named feature, from the current registry.

    Raises nothing and guesses nothing: a feature the registry cannot speak
    about comes back `not_recorded` / `absent`, which is a value a caller must
    handle rather than an absence a caller will not notice.
    """
    import yaml

    from tools.backlog import bind_execution_evidence, proof_state

    base = root or ROOT
    doc = yaml.safe_load(
        (base / "docs" / "backlog" / "status.yaml").read_text(encoding="utf8"))
    if bind_execution:
        bind_execution_evidence(doc)
    items = doc.get("items") or []

    delivers: dict[str, list[dict]] = collections.defaultdict(list)
    for item in items:
        for fid in item.get("delivers") or []:
            delivers[fid].append(item)

    declared = implements_map(root)

    def state(ac: dict) -> str:
        return proof_state(ac, bind_execution=bind_execution)

    out: dict[str, FeatureState] = {}
    for fid in feature_ids:
        delivering = delivers.get(fid, [])
        sites = declared.get(fid, [])
        implementation, basis = _implementation(delivering, sites)
        proof = _proof(delivering, state)
        if implementation == "complete" and proof == "PASS":
            status = "tested"
        elif implementation in ("partial", "complete"):
            status = "built"
        else:
            status = "decided"
        out[fid] = FeatureState(
            feature=fid,
            implementation=implementation,
            implementation_basis=basis,
            proof=proof,
            status=status,
            delivered_by=tuple(sorted(it["id"] for it in delivering)),
            declared_in=tuple(sites),
        )
    return out
