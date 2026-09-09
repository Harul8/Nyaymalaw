"""The backlog control plane. `docs/backlog/status.yaml` is the only source of
current status; this validates it and generates everything anybody reads.

    python tools/backlog.py lint      schema, vocabulary and invariants
    python tools/backlog.py status    current phase and release readiness
    python tools/backlog.py graph     cycles and dependency ordering
    python tools/backlog.py render    regenerate the board in BACKLOG.md
    python tools/backlog.py check     everything CI needs

WHY THIS EXISTS
---------------
`Open — 13` was typed by hand and was already wrong when it was typed. So were
"sixteen phases" and "18 pass" -- both in this repository's own backlog, both
describing a suite that collects 24. A count maintained by a person is a claim
that decays the moment anybody else edits anything.

And one word was carrying five questions. `PARTLY DONE` said nothing about
whether the code existed, whether it had been proven, whether it could ship, or
what to do next -- so every reader resolved it differently and the optimistic
reading always won.

THE DIVISION
------------
    status.yaml     what is true NOW
    BACKLOG.md      WHY the work exists
    tests, journey  PROOF that it is true
    the board       what people SEE, generated
    events          HOW the state changed

`done` IS NOT IN THE VOCABULARY. It cannot be typed, only derived -- see
`derive_done`. That is the whole point of the file: nobody makes something true
by writing the word.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402

utf8_console()

STATUS = ROOT / "docs" / "backlog" / "status.yaml"
STEPS = ROOT / "docs" / "backlog" / "steps.yaml"
BACKLOG = ROOT / "docs" / "BACKLOG.md"
START, END = "<!-- BACKLOG_STATUS:START -->", "<!-- BACKLOG_STATUS:END -->"

PHASES = {
    "A": "Arrive", "B": "Open a matter", "C": "Take the brief",
    "D": "Work the file", "E": "Advise", "F": "Act", "G": "Carry",
    "H": "Close", "I": "Leave",
}

#: `done` IS ABSENT DELIBERATELY. It is derived and the linter refuses it as an
#: authored value -- point 5 of the design, and the reason this file exists.
DELIVERY = {"planned", "ready", "in_progress", "blocked", "verifying",
            "deferred", "superseded", "cancelled"}
IMPLEMENTATION = {"none", "partial", "complete"}
VERIFICATION = {"none", "failing", "partial", "passing", "stale"}
PRIORITY = {"P0", "P1", "P2", "P3"}
KIND = {"journey", "substrate", "control", "finding", "decision"}

#: The evidence hierarchy. A criterion names every level its risk requires, not
#: one convenient proof.
EVIDENCE = {"domain_test", "integration_test", "browser_journey",
            "adversarial_test", "model_eval", "counsel_review",
            "production_measure"}

#: THE PROOF STATE OF ONE CRITERION AT ONE EVIDENCE LEVEL.
#:
#: Only `PASS` satisfies. `NOT_RUN` is the default and it is NOT a pass -- a
#: missing browser, an absent credential, a collection error and a conditional
#: xfail all land here, and every one of them has produced a green build in
#: this repository already.
RESULT = {"PASS", "FAIL", "NOT_RUN", "STALE", "BLOCKED", "NOT_APPLICABLE"}

#: A row whose subject is legal advice cannot be closed on automated tests
#: alone. Point 5, and it is the difference between the plumbing and the water.
COUNSEL_FACING_KINDS = {"journey", "finding"}


#: A step contract is only a contract when it says all of this. A step with a
#: name and nothing else is a heading.
CONTRACT_FIELDS = ("actor", "entry_conditions", "user_action",
                   "expected_visible_result", "expected_domain_effect",
                   "failure_behaviour", "recovery_behaviour",
                   "exit_conditions")

#: Where a step came from. The PRD states a sequence for two phases and a
#: question for the other seven, so a derived step is a reading of the plan and
#: must never be quoted back as the plan -- the same separation the product
#: keeps between STATED and INFERRED posture.
BASIS = {"prd_sequence", "derived_from_features"}


def load() -> dict:
    doc = yaml.safe_load(STATUS.read_text(encoding="utf-8"))
    doc["steps"] = (yaml.safe_load(STEPS.read_text(encoding="utf-8"))
                    or {}).get("steps", []) if STEPS.exists() else []
    return doc


# ------------------------------------------------------------------ lint ---

def lint(doc: dict) -> list[str]:
    bad: list[str] = []
    items = doc.get("items") or []
    feats = doc.get("features") or []

    seen: dict[str, int] = {}
    for i, it in enumerate(items):
        rid = it.get("id")
        if not rid:
            bad.append(f"items[{i}] has no id")
            continue
        if rid in seen:
            bad.append(f"{rid} appears twice (items[{seen[rid]}] and [{i}]) "
                       f"-- a list is used precisely so this is visible "
                       f"rather than silently overwritten")
        seen[rid] = i

    known = set(seen)
    for it in items:
        rid = it.get("id", "?")

        for field, vocab in (("delivery_status", DELIVERY),
                             ("implementation", IMPLEMENTATION),
                             ("verification", VERIFICATION),
                             ("priority", PRIORITY), ("kind", KIND)):
            v = it.get(field)
            if v not in vocab:
                extra = ("  `done` is DERIVED and may never be authored"
                         if field == "delivery_status" and v == "done" else "")
                bad.append(f"{rid}: {field}={v!r} is not in the vocabulary."
                           + extra)

        # kind decides which locator the row carries. A control that claims a
        # single phase is the filing error this schema exists to refuse.
        if it.get("kind") in ("journey", "finding"):
            if it.get("phase") not in PHASES:
                bad.append(f"{rid}: kind={it.get('kind')} needs one `phase`, "
                           f"got {it.get('phase')!r}")
            if "affects_phases" in it:
                bad.append(f"{rid}: a {it['kind']} row has one phase, not "
                           f"`affects_phases`")
        else:
            aff = it.get("affects_phases")
            if not isinstance(aff, list) or not aff:
                bad.append(f"{rid}: kind={it.get('kind')} needs "
                           f"`affects_phases`")
            elif set(aff) - set(PHASES):
                bad.append(f"{rid}: unknown phase(s) "
                           f"{sorted(set(aff) - set(PHASES))}")
            if "phase" in it:
                bad.append(f"{rid}: a {it.get('kind')} row does not sit in one "
                           f"phase; use `affects_phases`")

        ds = it.get("delivery_status")
        if ds == "blocked" and not it.get("blocked_by"):
            bad.append(f"{rid}: blocked with no `blocked_by`")
        if it.get("blocked_by") and not (
                isinstance(it["blocked_by"], dict)
                and it["blocked_by"].get("type")
                and it["blocked_by"].get("description")):
            bad.append(f"{rid}: `blocked_by` needs a type and a description")
        if ds == "superseded" and not it.get("superseded_by"):
            bad.append(f"{rid}: superseded with no `superseded_by`")
        if it.get("superseded_by") and it["superseded_by"] not in known:
            bad.append(f"{rid}: superseded_by {it['superseded_by']!r} is not "
                       f"a row")
        if ds == "deferred" and not it.get("reason"):
            bad.append(f"{rid}: deferred with no `reason` -- 'not done' with "
                       f"no reason is indistinguishable from forgotten")
        if ds == "cancelled" and not it.get("decision"):
            bad.append(f"{rid}: cancelled with no `decision`")

        for field in ("depends_on", "sequenced_after"):
            for dep in it.get(field) or []:
                if dep == rid:
                    bad.append(f"{rid}: {field} names itself")
                elif dep not in known:
                    bad.append(f"{rid}: {field} names {dep!r}, which is not a "
                               f"row")

        if ds == "ready":
            for dep in it.get("depends_on") or []:
                d = items[seen[dep]] if dep in seen else {}
                if d.get("implementation") != "complete":
                    bad.append(f"{rid}: ready, but {dep} is not implemented")

        for ac in it.get("acceptance") or []:
            acid = ac.get("id", "")
            if not acid.startswith(rid + "-"):
                bad.append(f"{rid}: acceptance id {acid!r} does not belong to "
                           f"this row")
            if not ac.get("requirement"):
                bad.append(f"{acid}: no requirement")
            req = ac.get("required_evidence") or []
            if not req:
                bad.append(f"{acid}: names no required evidence, so nothing "
                           f"can ever prove it")
            for lvl in req:
                if lvl not in EVIDENCE:
                    bad.append(f"{acid}: {lvl!r} is not in the evidence "
                               f"hierarchy")
            # ONE RESULT PER REQUIRED LEVEL, and absence is NOT_RUN rather
            # than silence. A level with no entry is the missing link the
            # whole system exists to refuse.
            got = ac.get("evidence") or {}
            for lvl in req:
                e = got.get(lvl)
                if e is None:
                    continue                      # reported as NOT_RUN below
                if e.get("result") not in RESULT:
                    bad.append(f"{acid}/{lvl}: result {e.get('result')!r} is "
                               f"not a proof state")
                if e.get("result") == "NOT_APPLICABLE" and not e.get("reason"):
                    bad.append(f"{acid}/{lvl}: NOT_APPLICABLE with no "
                               f"approved reason")
                if lvl in ("domain_test", "integration_test",
                           "adversarial_test"):
                    bad += _missing_pytest(f"{acid}/{lvl}", e.get("ref", ""))
            if it.get("priority") == "P0" and not ac.get("negative_control"):
                bad.append(f"{acid}: a P0 criterion with no negative control. "
                           f"A passing test is not evidence until it has been "
                           f"shown able to fail (B-049).")

    bad += _cycles(items, seen)
    bad += _missing_records(items)

    fids = [f.get("id") for f in feats]
    if len(fids) != len(set(fids)):
        bad.append("duplicate feature ids in `features`")
    for f in feats:
        if f.get("phase") not in PHASES:
            bad.append(f"feature {f.get('id')}: phase {f.get('phase')!r}")
        if f.get("implementation") not in IMPLEMENTATION:
            bad.append(f"feature {f.get('id')}: implementation "
                       f"{f.get('implementation')!r}")
        if f.get("implementation") == "none" and not (
                f.get("delivery_items") or f.get("deferred_reason")):
            bad.append(f"feature {f.get('id')}: not implemented and names "
                       f"neither a delivery item nor a deferral -- which is "
                       f"how a phase says 'nothing implemented' with no plan")

    bad += _steps(doc, known, {f.get("id"): f for f in feats})

    for ev in doc.get("events") or []:
        if ev.get("item") not in known:
            bad.append(f"event names {ev.get('item')!r}, which is not a row")
        if not ev.get("reason"):
            bad.append(f"event on {ev.get('item')} at {ev.get('at')}: no "
                       f"reason")

    # A row that came back from done must say so in the log, not in prose.
    reopened = {e["item"] for e in (doc.get("events") or [])
                if e.get("from") == "done"}
    for it in items:
        if it.get("legacy") and it["id"] in reopened:
            bad.append(f"{it['id']}: reopened and still marked legacy")
    return bad


def _missing_pytest(acid: str, ref: str) -> list[str]:
    """A proof naming a test nobody wrote is worse than no proof."""
    path, _, node = ref.partition("::")
    f = ROOT / path
    if not f.exists():
        return [f"{acid}: proof names {path}, which does not exist"]
    if node and node.split("[")[0] not in f.read_text(encoding="utf-8"):
        return [f"{acid}: proof names {node!r}, which is not in {path}"]
    return []


def _steps(doc: dict, items: set, features: dict) -> list[str]:
    """The journey steps, and the links that must not be missing.

    A step is the object the roll-up needs in the middle: criteria prove an
    item, items and features serve a step, steps make a phase. Without them
    nothing above an item can be computed, which is why an empty registry here
    would make every phase-level claim vacuous rather than green.
    """
    steps = doc.get("steps") or []
    order = list(PHASES)
    bad: list[str] = []
    seen: set[str] = set()

    for st in steps:
        sid = st.get("id", "")
        m = re.fullmatch(r"STEP-([A-I])-(\d{2})", sid)
        if not m:
            bad.append(f"step {sid!r} is not STEP-<phase>-<nn>")
            continue
        if sid in seen:
            bad.append(f"{sid} appears twice")
        seen.add(sid)
        if st.get("phase") != m.group(1):
            bad.append(f"{sid}: phase {st.get('phase')!r} does not match "
                       f"its id")
        if st.get("basis") not in BASIS:
            bad.append(f"{sid}: basis {st.get('basis')!r} -- a step must say "
                       f"whether the PRD states it or it was derived")
        if not st.get("name"):
            bad.append(f"{sid}: no name")

        for fid in st.get("features") or []:
            f = features.get(fid)
            if not f:
                bad.append(f"{sid}: names feature {fid!r}, which is not "
                           f"registered")
            # A step may rest on an EARLIER phase's feature -- the PRD's Phase
            # D sequence opens on parties and side, which is captured in C.
            # It may never rest on a LATER one: that is a step that cannot run
            # when the journey reaches it.
            elif order.index(f["phase"]) > order.index(st["phase"]):
                bad.append(f"{sid} (phase {st['phase']}) rests on {fid}, "
                           f"which belongs to the later phase {f['phase']}")
        for iid in st.get("items") or []:
            if iid not in items:
                bad.append(f"{sid}: names row {iid!r}, which is not in the "
                           f"registry")

        got = [k for k in CONTRACT_FIELDS if st.get(k)]
        if got and len(got) != len(CONTRACT_FIELDS):
            bad.append(f"{sid}: a partial contract is not a contract -- "
                       f"missing "
                       f"{[k for k in CONTRACT_FIELDS if k not in got]}")

    # EVERY JOURNEY FEATURE IS EXERCISED SOMEWHERE. A feature no step reaches
    # is one the journey never asks for, which is how a phase passes without
    # doing what it was built to do.
    exercised = {f for st in steps for f in (st.get("features") or [])}
    for fid, f in sorted(features.items()):
        if fid not in exercised:
            bad.append(f"feature {fid} ({f['phase']}) is exercised by no "
                       f"journey step")
    return bad


def _missing_records(items: list[dict]) -> list[str]:
    """Every row's `record` must reach prose that exists.

    The registry says WHAT is true and the prose says WHY. A registry row whose
    record points nowhere is half a story, and it is the half that cannot be
    reconstructed later -- which is exactly what happened to the rows this
    repository closed with a heading and no reasoning.
    """
    if not BACKLOG.exists():
        return ["docs/BACKLOG.md is missing"]
    text = BACKLOG.read_text(encoding="utf-8")
    present = {m.group(1) for m in
               re.finditer(r"^#{2,4} ((?:BK|J)-\d+)\b", text, re.M)}
    bad = []
    for it in items:
        rid = it.get("id")
        rec = it.get("record", "")
        if not rec:
            bad.append(f"{rid}: no `record`, so nothing says why it exists")
        elif rid not in present:
            bad.append(f"{rid}: `record` points at BACKLOG.md, which has no "
                       f"row for it")
    return bad


def _cycles(items: list[dict], seen: dict[str, int]) -> list[str]:
    graph = {it["id"]: [d for d in (it.get("depends_on") or []) if d in seen]
             for it in items if it.get("id")}
    bad, state = [], {}

    def walk(n, trail):
        if state.get(n) == "done":
            return
        if state.get(n) == "open":
            bad.append("dependency cycle: " + " -> ".join(trail + [n]))
            return
        state[n] = "open"
        for m in graph.get(n, []):
            walk(m, trail + [n])
        state[n] = "done"

    for n in graph:
        walk(n, [])
    return bad


# ---------------------------------------------------------------- derive ---

def proof_state(ac: dict) -> str:
    """The single state of one acceptance criterion, across its levels.

    THE WORST LEVEL WINS, and a level with no entry at all is `NOT_RUN`. That
    is the rule the whole system turns on: a missing link is NOT PROVEN, never
    implicitly passing.
    """
    worst = "PASS"
    order = ["FAIL", "BLOCKED", "STALE", "NOT_RUN", "PASS", "NOT_APPLICABLE"]
    got = ac.get("evidence") or {}
    for lvl in ac.get("required_evidence") or []:
        r = (got.get(lvl) or {}).get("result", "NOT_RUN")
        if order.index(r) < order.index(worst):
            worst = r
    return worst


def item_result(it: dict) -> str:
    """NOT_PROVEN unless every criterion passes. No criteria is not a pass."""
    acc = it.get("acceptance") or []
    if not acc:
        return "NOT_PROVEN"
    states = {proof_state(a) for a in acc}
    if states <= {"PASS", "NOT_APPLICABLE"}:
        return "PASS"
    if "FAIL" in states:
        return "FAIL"
    return "NOT_PROVEN"


def derive_done(it: dict, by_id: dict) -> bool:
    """DONE IS COMPUTED. Nobody types it and thereby makes it true.

    A legacy row -- closed before this registry existed -- rests on prose in
    BACKLOG.md. That is real evidence and it is not executable, so it counts
    here ONLY because it is declared as `legacy: true` and counted by `status`.
    An admitted gap is work; a silent one is a surprise.
    """
    if it.get("implementation") != "complete":
        return False
    if it.get("blocked_by"):
        return False
    for dep in it.get("depends_on") or []:
        d = by_id.get(dep)
        if not d or not derive_done(d, by_id):
            return False
    if it.get("legacy"):
        return it.get("verification") in ("stale", "passing")
    if item_result(it) != "PASS":
        return False
    levels = {lvl for a in it.get("acceptance") or []
              for lvl in (a.get("required_evidence") or [])}
    if it.get("kind") in COUNSEL_FACING_KINDS and it.get("priority") == "P0" \
            and "counsel_review" not in levels:
        return False
    return True


def readiness(it: dict, by_id: dict) -> str:
    if derive_done(it, by_id):
        return "releasable"
    if it.get("priority") in ("P0",) and not derive_done(it, by_id):
        return "not_ready"
    if it.get("implementation") == "complete":
        return "conditional"
    return "not_ready"


# ---------------------------------------------------------------- report ---

def board(doc: dict) -> str:
    items = doc["items"]
    by_id = {i["id"]: i for i in items}
    feats = doc["features"]

    lines = [
        "## Part 0 — The current control board",
        "",
        "**Generated by `python tools/backlog.py render`. Do not edit by "
        "hand.** Every count below was maintained manually once and every one "
        "of them was wrong: `Open — 13`, *sixteen phases*, *18 pass* against a "
        "suite that collects 24.",
        "",
        "| Phase | | Features | Steps | Contracted | Verified | Open P0 | "
        "Readiness |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    steps = doc.get("steps") or []
    for ph, name in PHASES.items():
        fs = [f for f in feats if f["phase"] == ph]
        sts = [s for s in steps if s.get("phase") == ph]
        contracted = sum(1 for s in sts if s.get("entry_conditions"))
        impl = sum(1 for f in fs if f["implementation"] == "complete")
        mine = [i for i in items
                if i.get("phase") == ph or ph in (i.get("affects_phases") or [])]
        done = sum(1 for i in mine if derive_done(i, by_id))
        p0 = sum(1 for i in mine
                 if i.get("priority") == "P0" and not derive_done(i, by_id))
        # A PHASE WITH UNBUILT FEATURES IS NOT RELEASABLE, whatever its rows
        # say. F, G and H have no open P0 for the same reason they have no
        # code: nothing has been built there to go wrong yet, and reading that
        # as `conditional` was the absence-as-success shape (§9) at the level
        # of a whole phase.
        ready = ("not releasable" if (p0 or impl < len(fs)) else
                 "conditional" if done < len(mine) else "releasable")
        lines.append(f"| {ph} | {name} | {impl}/{len(fs)} | {len(sts)} | "
                     f"{contracted}/{len(sts)} | {done}/{len(mine)} | {p0} | "
                     f"{ready} |")

    uncontracted = sum(1 for s in steps if not s.get("entry_conditions"))
    derived = sum(1 for s in steps
                  if s.get("basis") == "derived_from_features")
    openp0 = [i for i in items
              if i.get("priority") == "P0" and not derive_done(i, by_id)]
    blocked = [i for i in items if i.get("delivery_status") == "blocked"]
    legacy = [i for i in items if i.get("legacy")]
    noacc = [i for i in items
             if not i.get("legacy") and not (i.get("acceptance") or [])]

    lines += [
        "",
        f"**{len(items)} rows · {len(openp0)} open P0 · {len(blocked)} "
        f"blocked · {sum(1 for f in feats if f['implementation'] == 'complete')}"
        f"/{len(feats)} features implemented**",
        "",
        "### Open P0 — what is unsafe",
        "",
    ]
    for i in sorted(openp0, key=lambda x: x["id"]):
        where = i.get("phase") or "/".join(i.get("affects_phases") or [])
        lines.append(f"- **{i['id']}** [{where}] {i['title']} — "
                     f"*{i['delivery_status']}*"
                     + (f" · {i['next_action']}" if i.get("next_action") else ""))
    if blocked:
        lines += ["", "### Blocked — waiting on a decision", ""]
        for i in blocked:
            lines.append(f"- **{i['id']}** {i['title']} — "
                         f"{i['blocked_by']['type']}: "
                         f"{i['blocked_by']['description']}")

    lines += [
        "",
        "### Admitted gaps in the evidence",
        "",
        f"- **{len(legacy)} rows rest on prose evidence** (`legacy: true`), "
        f"closed before this registry existed. Each is retired by attaching an "
        f"executable proof, not by editing a heading.",
        f"- **{len(noacc)} active rows carry no acceptance criteria yet**, so "
        f"`done` cannot be derived for them however much work is finished.",
        f"- **{uncontracted} of {len(steps)} journey steps carry no "
        f"contract**, so what the step must do, refuse and recover from is "
        f"not yet stated anywhere a check can read.",
        f"- **{derived} steps are DERIVED, not stated by the PRD.** The PRD "
        f"gives a sequence for Phase B and Phase D and a question for the "
        f"other seven; a derived step is a reading of the plan and is not "
        f"the plan.",
        "",
    ]
    return "\n".join(lines)


def render(doc: dict) -> bool:
    text = BACKLOG.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print(f"{BACKLOG.name} has no {START} / {END} markers", file=sys.stderr)
        return False
    new = re.sub(f"{re.escape(START)}.*?{re.escape(END)}",
                 f"{START}\n\n{board(doc)}\n{END}", text, flags=re.S)
    changed = new != text
    if changed:
        BACKLOG.write_text(new, encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["lint", "status", "graph", "render",
                                        "check"])
    args = ap.parse_args()
    doc = load()

    if args.command in ("lint", "check"):
        bad = lint(doc)
        for b in bad:
            print(f"  {b}")
        print(f"LINT {'FAILED' if bad else 'OK'}  {len(bad)} problem(s), "
              f"{len(doc['items'])} rows, {len(doc['features'])} features")
        if bad:
            return 1

    if args.command in ("status", "check"):
        print()
        print(board(doc))

    if args.command == "graph":
        by_id = {i["id"]: i for i in doc["items"]}
        blockers = {}
        for it in doc["items"]:
            for d in it.get("depends_on") or []:
                blockers.setdefault(d, []).append(it["id"])
        print("BLOCKS THE MOST DOWNSTREAM WORK")
        for k, v in sorted(blockers.items(), key=lambda kv: -len(kv[1]))[:8]:
            done = "done" if derive_done(by_id[k], by_id) else "NOT done"
            print(f"  {k:7} blocks {len(v)}: {', '.join(sorted(v))}  [{done}]")

    if args.command in ("render", "check"):
        changed = render(doc)
        if args.command == "check" and changed:
            print("\nBOARD WAS STALE and has been regenerated. Commit it.",
                  file=sys.stderr)
            return 1
        print(f"\nboard {'regenerated' if changed else 'already current'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
