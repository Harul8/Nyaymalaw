"""The readiness plan: authored stages along the journey, measured against the registries.

    from assurance.control_plane.readiness_plan import problems, derive

WHY THIS IS TWO FUNCTIONS AND ONE OWNER
-----------------------------------------
`docs/backlog/plan.json::readiness_plan` says what must happen between the current
state and a release, in the order an advocate meets the product: stages, the journey
steps each covers, the work, the authority each needs, what it depends on and the bar
it must clear. That is INTENT, and it is authored once, there.

What the gap IS at any moment is a different kind of fact. It is measured, it moves
with every commit, and a number typed into a plan is wrong the day after it is typed
-- which is the whole reason `done` is derived in this repository and never written.
So `derive` computes each step's and each stage's current state from the same
functions the release checker uses (`proof_state`, `derive_done`, the profiles'
required work), and the workbook shows the two side by side. Nothing measured is
stored, and nothing authored is recomputed.

WHAT `problems` REFUSES, AND WHY EACH
---------------------------------------
    a journey step in no stage     -- a step the plan forgot is a step nobody makes ready
    a journey step in two stages   -- two owners for one step's readiness drift apart
    stages out of journey order    -- the plan's premise is that readiness advances as the
                                      advocate does; a stage for Advise before Work the file
                                      would claim advice on a file nobody could work
    an unknown item, step, stage or release profile
    a dependency cycle, or a stage depending on itself
    an authority outside the closed vocabulary -- "who can unblock this" must be answerable
                                      by name, and a free-text authority is one nobody owns
    an empty goal, action list or exit bar -- a stage with no exit cannot be finished

WHAT IT DOES NOT DO
---------------------
It does not approve a stage, certify an exit bar or infer readiness from counts. An exit
bar is prose a reviewer applies; the measured columns tell them where to look.
"""
from __future__ import annotations

import collections
import re

#: WHO CAN UNBLOCK A STAGE. Closed, because the plan's value is that every stage names
#: the kind of authority it waits on, and "someone" is not a kind.
AUTHORITY = frozenset({
    "engineering",
    "counsel",
    "model_budget",
    "representative_advocates",
    "labelling",
    "deployment",
    "security_review",
    "accountable_approval",
})

#: The evidence levels a team can satisfy alone, and the ones that need outside authority.
CODE_LEVELS = ("domain_test", "integration_test", "adversarial_test")
LEVEL_GROUPS = {
    "code": CODE_LEVELS,
    "browser": ("browser_journey",),
    "counsel": ("counsel_review",),
    "model": ("model_eval",),
    "production": ("production_measure",),
}

_STAGE_ID = re.compile(r"^RP-[A-Z0-9]+$")
PHASE_ORDER = "ABCDEFGHI"
PHASES = frozenset(PHASE_ORDER)


def _stages(doc: dict) -> list[dict]:
    plan = (doc.get("plan") or {}).get("readiness_plan")
    if not isinstance(plan, dict):
        return []
    stages = plan.get("stages")
    return stages if isinstance(stages, list) else []


def _nonblank_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(v, str) and v.strip() for v in value)


def problems(doc: dict) -> list[str]:
    """Every structural problem with the authored readiness plan. Empty is a pass."""
    plan = (doc.get("plan") or {}).get("readiness_plan")
    if plan is None:
        return ["plan.json has no readiness_plan: the route to release is not registered"]
    if not isinstance(plan, dict) or not isinstance(plan.get("stages"), list) \
            or not plan["stages"]:
        return ["readiness_plan needs a non-empty list of stages"]

    bad: list[str] = []
    stages = plan["stages"]
    steps = [s.get("id") for s in doc.get("steps") or []]
    step_phase = {s.get("id"): s.get("phase") for s in doc.get("steps") or []}
    items = {it.get("id") for it in doc.get("items") or []}
    profiles = {p.get("id") for p in (doc.get("plan") or {}).get("release_profiles") or []}

    ids: list[str] = []
    for n, stage in enumerate(stages):
        where = f"readiness_plan.stages[{n}]"
        if not isinstance(stage, dict):
            bad.append(f"{where} is not an object")
            continue
        sid = stage.get("id")
        if not isinstance(sid, str) or not _STAGE_ID.fullmatch(sid):
            bad.append(f"{where}: id {sid!r} is not an RP- identifier")
            continue
        where = sid
        if sid in ids:
            bad.append(f"{sid}: appears twice")
        ids.append(sid)
        for field in ("name", "goal"):
            if not isinstance(stage.get(field), str) or not stage[field].strip():
                bad.append(f"{sid}: {field} is empty")
        for field in ("actions", "pilot_exit", "production_exit"):
            if not _nonblank_list(stage.get(field)):
                bad.append(f"{sid}: {field} must be a non-empty list of statements")
        for field in ("journey_steps", "items", "depends_on", "decisions"):
            value = stage.get(field)
            if not isinstance(value, list) or not all(
                    isinstance(v, str) and v.strip() for v in value):
                bad.append(f"{sid}: {field} must be a list of non-blank strings")
        authority = stage.get("authority")
        if not _nonblank_list(authority):
            bad.append(f"{sid}: authority must name who can unblock it")
        else:
            unknown = sorted(set(authority) - AUTHORITY)
            if unknown:
                bad.append(f"{sid}: authority {unknown} is outside the closed vocabulary "
                           f"{sorted(AUTHORITY)}")
        for rid in stage.get("items") or []:
            if rid not in items:
                bad.append(f"{sid}: names {rid!r}, which is not a registered item")
        for step in stage.get("journey_steps") or []:
            if step not in step_phase:
                bad.append(f"{sid}: names {step!r}, which is not a journey step")
        profile = stage.get("release_profile")
        if profile is not None and profile not in profiles:
            bad.append(f"{sid}: release_profile {profile!r} is not a registered profile")
        if not stage.get("journey_steps") and profile is None and not stage.get("items"):
            bad.append(f"{sid}: covers no journey step, names no work and no release "
                       f"profile, so nothing can be measured against it")

    # EVERY STEP EXACTLY ONCE.
    placed = collections.Counter(
        step for stage in stages if isinstance(stage, dict)
        for step in stage.get("journey_steps") or [])
    for step in steps:
        if placed[step] == 0:
            bad.append(f"{step}: is in no readiness stage")
        elif placed[step] > 1:
            bad.append(f"{step}: is in {placed[step]} readiness stages")

    # JOURNEY ORDER: step-bearing stages advance through the phases, never back.
    last = -1
    for stage in stages:
        if not isinstance(stage, dict) or not stage.get("journey_steps"):
            continue
        # AN UNKNOWN STEP IS REPORTED ABOVE AND SKIPPED HERE. It has no phase, and
        # `None in "ABCDEFGHI"` raises -- which turned one bad reference into a crash
        # that hid every other problem. Membership is in the phase SET, not the
        # string, so a value like "AB" cannot pass as a substring either.
        positions = [PHASE_ORDER.index(step_phase[s]) for s in stage["journey_steps"]
                     if step_phase.get(s) in PHASES]
        if not positions:
            continue
        if min(positions) < last:
            bad.append(f"{stage.get('id')}: comes after a later journey phase; stages must "
                       f"follow the advocate's journey")
        last = max(last, max(positions))

    # DEPENDENCIES: known, not self, acyclic.
    known = set(ids)
    graph = {}
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("id"), str):
            continue
        deps = stage.get("depends_on") or []
        graph[stage["id"]] = [d for d in deps if isinstance(d, str)]
        for dep in deps:
            if dep == stage["id"]:
                bad.append(f"{stage['id']}: depends on itself")
            elif dep not in known:
                bad.append(f"{stage['id']}: depends on {dep!r}, which is not a stage")
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 2 or node not in graph:
            return
        if state.get(node) == 1:
            bad.append("readiness_plan dependency cycle: " + " -> ".join(trail + [node]))
            return
        state[node] = 1
        for dep in graph[node]:
            if dep != node:
                visit(dep, trail + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])
    return bad


def _recorded(entry: object) -> str:
    """The RECORDED result of one level; absence and a materialised row are ABSENT.

    RECORDED, NOT BOUND, and deliberately. The plan works against the evidence
    population -- what has ever been proven and what has not -- and that does not
    change when an unrelated edit moves the verification fingerprint. Whether a
    recorded PASS is CURRENT is a separate fact, shown beside it from `proof_state`
    with binding, so a stale tree reads as "recorded 21, bound 0" rather than as a
    product that lost every proof overnight.
    """
    if not isinstance(entry, dict) or entry.get("_materialised"):
        return "ABSENT"
    return str(entry.get("result", "NOT_RUN"))


def _measure(item_ids: list[str], items: dict, proof_state, derive_done,
             final_packet: dict[str, str]) -> dict:
    recorded = collections.Counter()
    bound = collections.Counter()
    open_rows = {group: 0 for group in LEVEL_GROUPS}
    absent = 0
    packets = collections.Counter()
    for rid in item_ids:
        for ac in items[rid].get("acceptance") or []:
            recorded[proof_state(ac, bind_execution=False)] += 1
            bound[proof_state(ac)] += 1
            packets[final_packet.get(ac["id"], "UNOWNED")] += 1
            evidence = ac.get("evidence") or {}
            for level in ac.get("required_evidence") or []:
                result = _recorded(evidence.get(level))
                absent += result == "ABSENT"
                if result in ("PASS", "NOT_APPLICABLE"):
                    continue
                for group, levels in LEVEL_GROUPS.items():
                    if level in levels:
                        open_rows[group] += 1
    passing = ("PASS", "NOT_APPLICABLE")
    return {
        "criteria": sum(recorded.values()),
        "criteria_recorded_pass": sum(recorded.get(s, 0) for s in passing),
        "criteria_bound_pass": sum(bound.get(s, 0) for s in passing),
        "open": open_rows,
        "absent": absent,
        "done": sum(1 for rid in item_ids if derive_done(items[rid], items)),
        "packets": [p for p, _n in packets.most_common()],
    }


def derive(doc: dict, packets: list[dict]) -> dict:
    """The measured state of every journey step and every stage. Nothing is stored.

    Items linked to several steps are measured once PER ROW they appear on: a step row
    answers "what stands between THIS step and release", and a stage row answers the
    same for its union of work. Rows are never summed into a total, because summing
    step rows would count shared work once per step.
    """
    from assurance.control_plane.backlog import derive_done, proof_state

    items = {it["id"]: it for it in doc.get("items") or []}
    features = {f["id"]: f for f in doc.get("features") or []}
    profiles = {p["id"]: p for p in (doc.get("plan") or {}).get("release_profiles") or []}
    final_packet = {ac: p["id"] for p in packets for ac in (p.get("final_criteria") or [])}
    stages = _stages(doc)
    stage_of = {step: stage["id"] for stage in stages
                for step in stage.get("journey_steps") or []}

    def required(pid: str) -> set[str]:
        return set((profiles.get(pid) or {}).get("required_items") or [])

    step_rows = []
    for step in doc.get("steps") or []:
        work = [rid for rid in step.get("items") or [] if rid in items]
        measured = _measure(work, items, proof_state, derive_done, final_packet)
        step_rows.append({
            "id": step["id"], "phase": step.get("phase"), "name": step.get("name"),
            "stage": stage_of.get(step["id"], ""),
            "features": [f"{f} {features.get(f, {}).get('implementation', 'unregistered')}"
                         for f in step.get("features") or []],
            "items": list(step.get("items") or []),
            "pilot_required": [r for r in work if r in required("pilot")],
            "production_required": [r for r in work if r in required("production")],
            **measured,
        })

    stage_rows = []
    steps_by_id = {s["id"]: s for s in doc.get("steps") or []}
    for stage in stages:
        work: list[str] = []
        for step in stage.get("journey_steps") or []:
            for rid in (steps_by_id.get(step) or {}).get("items") or []:
                if rid in items and rid not in work:
                    work.append(rid)
        for rid in stage.get("items") or []:
            if rid in items and rid not in work:
                work.append(rid)
        profile = stage.get("release_profile")
        if profile:
            for rid in sorted(required(profile), key=lambda r: (r.split("-")[0],
                                                               int(r.split("-")[1]))):
                if rid in items and rid not in work:
                    work.append(rid)
        stage_rows.append({"id": stage["id"], "work": work,
                           **_measure(work, items, proof_state, derive_done, final_packet)})
    return {"steps": step_rows, "stages": stage_rows}
