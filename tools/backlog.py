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
import ast
import json
import pathlib
import re
import sys
from datetime import date, datetime, timedelta, timezone

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402
from tools.evidence import (  # noqa: E402
    exact_outcome,
    load_result,
    validate_class_a,
    verification_fingerprint,
)

utf8_console()

STATUS = ROOT / "docs" / "backlog" / "status.yaml"
STEPS = ROOT / "docs" / "backlog" / "steps.yaml"
PLAN = ROOT / "docs" / "backlog" / "plan.json"
PROFESSIONAL = ROOT / "docs" / "backlog" / "professional.json"
BUILD_RULES = ROOT / "docs" / "backlog" / "build_rules.json"
PLAYBOOKS = ROOT / "docs" / "playbooks"
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

#: The four playbooks are a lifecycle, not four documents somebody remembers.
#: A row managed after BK-74 carries all four records. Older rows are counted
#: as a declared migration population at the document root; adding another
#: record-less row changes that population and fails lint rather than quietly
#: extending the exception.
STAGE_RESULT = {
    "start": {"READY", "BLOCKED"},
    "build": {"NOT_STARTED", "OPEN", "BUILT", "BLOCKED"},
    "test": {"NOT_RUN", "OPEN", "VERIFIED", "FAILED", "STALE", "BLOCKED"},
    "signoff": {"NOT_RUN", "OPEN", "SIGNED_OFF", "RETURNED", "BLOCKED"},
}

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
WAVES = tuple(f"W{i}" for i in range(8))

# Backlog review dates are India calendar dates, not the host's local date.
INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


def calendar_date(value: object) -> date:
    """Accept a strict calendar date, including PyYAML's date-only scalar.

    datetime is deliberately excluded although it subclasses date: a review
    day must not acquire an implicit time zone or silently drop a time.
    """
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("expected a valid calendar date in YYYY-MM-DD format")


def india_today(*, now: datetime | None = None) -> date:
    """One clock boundary; callers/tests can inject an aware instant."""
    instant = datetime.now(INDIA_TIMEZONE) if now is None else now
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("the review clock requires a timezone-aware instant")
    return instant.astimezone(INDIA_TIMEZONE).date()


def _deferral_problems(it: dict) -> list[str]:
    """One validation mechanism for every deferred row and every reader."""
    if it.get("delivery_status") != "deferred":
        return []
    rid = it.get("id", "?")
    bad = []
    reason = it.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        bad.append(f"{rid}: deferred with no nonblank text `reason` -- "
                   "'not done' with no reason is indistinguishable from forgotten")
    try:
        calendar_date(it.get("review_on"))
    except ValueError:
        bad.append(f"{rid}: deferred `review_on` must be a valid calendar date "
                   "in YYYY-MM-DD format")
    return bad


def deferral_reviews(doc: dict, *, as_of: date | None = None) -> list[dict]:
    """Derive review attention without changing delivery state or authority.

    Missing/malformed obligations are INVALID (lint errors). Valid dates are
    SCHEDULED, DUE TODAY or OVERDUE: the latter two request reassessment, not
    work authorisation and not an unrelated whole-build failure.
    """
    day = india_today() if as_of is None else calendar_date(as_of)
    rows = []
    for it in doc.get("items") or []:
        if it.get("delivery_status") != "deferred":
            continue
        problems = _deferral_problems(it)
        try:
            review = calendar_date(it.get("review_on"))
        except ValueError:
            review = None
        days = (day - review).days if review is not None else None
        state = ("INVALID" if problems else "OVERDUE" if days > 0 else
                 "DUE TODAY" if days == 0 else "SCHEDULED")
        rows.append({"id": it.get("id", "?"), "review_on": review,
                     "state": state, "overdue_days": max(0, days or 0),
                     "problems": problems})
    return rows


def _deferral_report(doc: dict, *, as_of: date | None = None,
                     live: bool = True) -> list[str]:
    # Persist dates, not a cached 'today' verdict that becomes false overnight.
    day = (india_today() if as_of is None else calendar_date(as_of)) if live else date.min
    rows = deferral_reviews(doc, as_of=day)
    lines = ["", "### Deferred — review is not permission to build", ""]
    if live:
        lines.append(f"As of {day.isoformat()} (Asia/Kolkata): {len(rows)} deferred row(s).")
    else:
        lines.append(f"{len(rows)} deferred row(s). Dates below are recorded obligations, "
                     "not cached current verdicts. Run `python tools/backlog.py status` "
                     "for DUE TODAY / OVERDUE against the current India calendar date.")
    lines += ["", "Missing or invalid dates/reasons fail lint. A due or overdue review "
              "requires recorded reassessment before reactivation; it does not "
              "authorise work or block unrelated work. Delivery stays deferred.", ""]
    for row in rows:
        when = row["review_on"].isoformat() if row["review_on"] else "INVALID DATE"
        state = row["state"] if live or row["state"] == "INVALID" else "REVIEW ON"
        overdue = (f" ({row['overdue_days']} day(s))"
                   if live and state == "OVERDUE" else "")
        lines.append(f"- **{row['id']}** — {state}{overdue}; review_on {when}; "
                     "delivery deferred.")
        lines.extend(f"  - {problem}" for problem in row["problems"])
    return lines


def load() -> dict:
    doc = yaml.safe_load(STATUS.read_text(encoding="utf-8"))
    doc["steps"] = (yaml.safe_load(STEPS.read_text(encoding="utf-8"))
                    or {}).get("steps", []) if STEPS.exists() else []
    doc["plan"] = json.loads(PLAN.read_text(encoding="utf-8"))
    doc["professional"] = json.loads(
        PROFESSIONAL.read_text(encoding="utf-8"))
    doc["build_rules"] = json.loads(
        BUILD_RULES.read_text(encoding="utf-8")) if BUILD_RULES.exists() else {}
    bind_execution_evidence(doc)
    return doc


AUTOMATED_EVIDENCE = {"domain_test", "integration_test", "adversarial_test"}
STRUCTURED_EVIDENCE = {"model_eval", "counsel_review", "production_measure"}
EVIDENCE_RECORDS = ROOT / "docs" / "backlog" / "evidence"


def _structured_record(acid: str, level: str, ref: str) -> list[str]:
    """Validate a dated non-automated decision without exposing its subject.

    THE RULES MOVED TO `tools/structured_evidence.py`. BK-80-AC1. This checked
    five fields -- subject, method, result, actor, observed_at -- and the
    resulting PASS was then good forever: `subject` is prose so nothing
    compared it to anything, `actor` is a string so an unattributable assertion
    weighed the same as a qualified review, and there was no validity period at
    all. Both halves of the criterion's negative control passed.
    """
    from tools.structured_evidence import problems

    return problems(acid, level, ref,
                    source_fingerprint=verification_fingerprint())


def _structured_record_legacy(acid: str, level: str, ref: str) -> list[str]:
    """The pre-BK-80-AC1 check, retained only as the thing under test.

    `tests/test_structured_evidence_binds_its_subject.py` runs the criterion's
    negative control against BOTH, so the claim that the new rules refuse what
    the old ones admitted is measured rather than asserted.
    """
    if not ref or "#" in ref:
        return [f"{acid}/{level}: PASS has no structured evidence record"]
    try:
        path = (ROOT / ref).resolve()
        path.relative_to(EVIDENCE_RECORDS.resolve())
    except (OSError, ValueError):
        return [f"{acid}/{level}: structured evidence record is outside "
                "docs/backlog/evidence"]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"{acid}/{level}: evidence record {ref!r} cannot be read"]
    bad = []
    for field in ("subject", "method", "result", "actor", "observed_at"):
        if not record.get(field):
            bad.append(f"{acid}/{level}: evidence record has no {field}")
    if record.get("criterion") != acid or record.get("level") != level:
        bad.append(f"{acid}/{level}: evidence record names a different claim")
    if record.get("result") != "PASS":
        bad.append(f"{acid}/{level}: evidence record does not record PASS")
    return bad


def bind_execution_evidence(doc: dict, class_a: dict | None = None) -> list[str]:
    """Resolve authored claims through current machine or review records.

    ``result`` remains the reported status for audit history.  Roll-ups consume
    ``_effective_result``: a stale/missing run can therefore never derive done.
    """
    class_a = load_result() if class_a is None else class_a
    run_bad = validate_class_a(class_a)
    bad = list(run_bad)
    for item in doc.get("items") or []:
        for ac in item.get("acceptance") or []:
            acid = ac.get("id", "?")
            for level, evidence in (ac.get("evidence") or {}).items():
                result = evidence.get("result", "NOT_RUN")
                evidence["_effective_result"] = result
                if result != "PASS":
                    continue
                if level in AUTOMATED_EVIDENCE:
                    if run_bad:
                        evidence["_effective_result"] = "STALE"
                        continue
                    outcome = exact_outcome(class_a, evidence.get("ref", ""))
                    if outcome != "passed":
                        evidence["_effective_result"] = (
                            "FAIL" if outcome == "failed" else "NOT_RUN")
                        bad.append(
                            f"{acid}/{level}: {evidence.get('ref')!r} did not "
                            "PASS in the bound Class-A execution")
                elif level in STRUCTURED_EVIDENCE:
                    record_bad = _structured_record(
                        acid, level, evidence.get("ref", ""))
                    if record_bad:
                        evidence["_effective_result"] = "NOT_RUN"
                        bad += record_bad
                elif level == "browser_journey":
                    # THE WHOLE REPORT, NOT ONE ROW. BK-80-AC2.
                    #
                    # This checked the fingerprint and looked up one nodeid, so
                    # every one of these conferred a PASS: a run that crashed
                    # at phase 3 leaving green rows behind it, a phase renamed
                    # out of existence so nothing asked for it, a row appearing
                    # twice, a tree that moved mid-run, and last week's
                    # screenshots listed as this run's artifacts. All of them
                    # have `rows` that are green and a fingerprint that matches.
                    from tools.browser_evidence import load, problems, row_for
                    from tools.journey import EXPECTED

                    ref, _, nodeid = evidence.get("ref", "").partition("#")
                    report = load(ROOT / ref) if ref else None
                    incomplete = problems(
                        report, expected=EXPECTED,
                        fingerprint=verification_fingerprint())
                    state = row_for(report, nodeid)
                    if incomplete or state != "PASS":
                        evidence["_effective_result"] = "STALE"
                        if state != "PASS":
                            bad.append(f"{acid}/{level}: {nodeid!r} did not "
                                       f"PASS in the bound browser run "
                                       f"(recorded {state!r})")
                        # EACH INCOMPATIBLE CONDITION NAMED, not one summary.
                        # An advocate of this register debugging a refused
                        # release needs to know which of five things is wrong.
                        bad += [f"{acid}/{level}: {problem}"
                                for problem in incomplete]
    doc["_class_a_result"] = class_a
    doc["_execution_problems"] = bad
    return bad


# ------------------------------------------------------------------ lint ---

def lint(doc: dict, *, verify_execution: bool = False) -> list[str]:
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
        bad.extend(_deferral_problems(it))
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
    bad += _build_rules(doc)
    bad += _delivery_lifecycle(doc, items)
    if verify_execution:
        bad += doc.get("_execution_problems") or bind_execution_evidence(doc)

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

    feature_map = {f.get("id"): f for f in feats}
    bad += _steps(doc, known, feature_map)

    wave_bad, waves = _waves(doc, items, seen)
    bad += wave_bad
    bad += _professional(doc, known, set(feature_map),
                         {s.get("id") for s in doc.get("steps") or []}, waves)

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


def _delivery_lifecycle(doc: dict, items: list[dict]) -> list[str]:
    """The playbook hand-offs, including the declared pre-cutover population."""
    bad: list[str] = []
    unmanaged = [it.get("id", "?") for it in items if not it.get("stage_records")]
    expected = doc.get("legacy_lifecycle_population")
    if expected != len(unmanaged):
        bad.append(
            "lifecycle migration population is "
            f"{len(unmanaged)}, expected {expected!r}; a work item gained or lost "
            "stage records without reconciling the declared pre-cutover population")

    for it in items:
        records = it.get("stage_records")
        if not records:
            continue
        rid = it.get("id", "?")
        for stage, vocabulary in STAGE_RESULT.items():
            record = records.get(stage)
            if not isinstance(record, dict):
                bad.append(f"{rid}: stage_records has no {stage} record")
                continue
            result = record.get("result")
            if result not in vocabulary:
                bad.append(f"{rid}: {stage} result {result!r} is not valid")
            if not record.get("ref"):
                bad.append(f"{rid}: {stage} record has no reference")

        start = (records.get("start") or {}).get("result")
        build = (records.get("build") or {}).get("result")
        test = (records.get("test") or {}).get("result")
        signoff = (records.get("signoff") or {}).get("result")
        if build not in (None, "NOT_STARTED") and start != "READY":
            bad.append(f"{rid}: Build began before the Start Record was READY")
        # EVIDENCE MAY ACCUMULATE WHILE THE BUILD IS OPEN; IT MAY NOT BE
        # DECLARED COMPLETE. BK-74.
        #
        # This read `test not in (None, "NOT_RUN") and build != "BUILT"`, a
        # waterfall: no criterion could carry a result until every criterion
        # was built. Measured 10 September 2026 against the 53 unmanaged rows,
        # it refused seven that have a full contract and are being built
        # exactly as this repository builds -- one criterion at a time, with
        # evidence recorded as each lands. BK-34 is the plain case: two of four
        # criteria PASS and AC3 is blocked on BK-53, which is a correct state
        # the model could not write down.
        #
        # The three rows BK-74 was tested against were all complete-build rows,
        # so the assumption was never put to a partial one -- the same reason
        # the sign-off gate went unexamined for the population that had no
        # records.
        #
        # WHAT THE RULE WAS PROTECTING IS KEPT, and it is the only part worth
        # protecting: a VERIFIED Evidence Pack asserts the whole row's evidence
        # stands, and over a half-built row that is false. OPEN and FAILED
        # assert nothing of the kind. `done` is unaffected either way -- it
        # still requires SIGNED_OFF, which still requires VERIFIED, which still
        # requires BUILT.
        if test == "VERIFIED" and build != "BUILT":
            bad.append(f"{rid}: the Evidence Pack is VERIFIED before the Build "
                       f"Record was BUILT")
        if signoff not in (None, "NOT_RUN") and test != "VERIFIED":
            bad.append(f"{rid}: Sign-off began before the Evidence Pack was VERIFIED")

        status = it.get("delivery_status")
        if status == "ready" and start != "READY":
            bad.append(f"{rid}: ready without a READY Start Record")
        if status == "in_progress" and build not in ("OPEN", "BUILT"):
            bad.append(f"{rid}: in_progress without an open Build Record")
        if status == "verifying" and build != "BUILT":
            bad.append(f"{rid}: verifying before the Build Record is BUILT")
    return bad


def _waves(doc: dict, items: list[dict], seen: dict[str, int]
           ) -> tuple[list[str], dict[str, str | None]]:
    """Validate the one delivery-wave assignment for every registered row.

    The plan intentionally uses a list. A mapping would silently keep the last
    duplicate and make the exact drift this control exists to detect invisible.
    """
    rows = (doc.get("plan") or {}).get("item_waves") or []
    bad: list[str] = []
    waves: dict[str, str | None] = {}
    duplicates: set[str] = set()
    for n, row in enumerate(rows):
        rid = row.get("id")
        if not rid:
            bad.append(f"item_waves[{n}] has no id")
            continue
        if rid in waves:
            duplicates.add(rid)
            bad.append(f"delivery wave for {rid} appears twice")
        else:
            waves[rid] = row.get("wave")

    known = set(seen)
    for rid in sorted(known - set(waves)):
        bad.append(f"{rid}: has no delivery-wave assignment")
    for rid in sorted(set(waves) - known):
        bad.append(f"delivery wave names {rid!r}, which is not a row")

    terminal = {"deferred", "superseded", "cancelled"}
    for it in items:
        rid, wave = it.get("id"), waves.get(it.get("id"))
        if rid in duplicates or rid not in waves:
            continue
        if wave is None:
            if it.get("delivery_status") not in terminal:
                bad.append(f"{rid}: active item has no delivery wave")
        elif wave not in WAVES:
            bad.append(f"{rid}: delivery wave {wave!r} is not W0-W7")
        elif it.get("delivery_status") in terminal:
            bad.append(f"{rid}: terminal item has wave {wave}; use null so "
                       "the plan does not imply scheduled delivery")

    rank = {w: i for i, w in enumerate(WAVES)}
    for it in items:
        rid, current = it.get("id"), waves.get(it.get("id"))
        if current not in rank:
            continue
        for dep in it.get("depends_on") or []:
            earlier = waves.get(dep)
            if earlier in rank and rank[earlier] > rank[current]:
                bad.append(f"{rid} ({current}) depends on {dep} ({earlier}), "
                           "which is scheduled later")
    return bad, waves


def professional_population(doc: dict) -> dict[str, int]:
    """The population printed by lint and shown on the generated board."""
    pro = doc.get("professional") or {}
    return {name: len(pro.get(name) or []) for name in
            ("advocate_standards", "workflow_states", "advice_maturity",
             "roles", "gap_closures")}


def _professional(doc: dict, items: set[str], features: set[str],
                  steps: set[str], waves: dict[str, str | None]) -> list[str]:
    """Validate the professional model and its delivery crosswalk.

    PA/EW/AM/ROLE are durable product standards, not backlog statuses. GC is a
    crosswalk: its current state is always derived from the linked work items.
    """
    pro = doc.get("professional") or {}
    expected = pro.get("expected_populations") or {}
    bad: list[str] = []
    groups = (
        ("advocate_standards", "PA", ("features", "steps", "work_items")),
        ("workflow_states", "EW", ("features", "steps", "work_items")),
        ("advice_maturity", "AM", ("features", "steps", "work_items")),
        ("roles", "ROLE", ("features", "steps", "work_items")),
    )

    known_by_kind: dict[str, set[str]] = {}
    for name, prefix, required_refs in groups:
        rows = pro.get(name) or []
        want = expected.get(name)
        if not isinstance(want, int) or want <= 0:
            bad.append(f"professional expected population for {name} is not "
                       "a positive integer")
        elif len(rows) != want:
            bad.append(f"professional {name} population is {len(rows)}, "
                       f"expected {want}")
        ids = [r.get("id") for r in rows]
        if len(ids) != len(set(ids)):
            bad.append(f"duplicate ids in professional {name}")
        expected_ids = [f"{prefix}-{i:02d}" for i in range(1, len(rows) + 1)]
        if ids != expected_ids:
            bad.append(f"professional {name} ids are not the complete ordered "
                       f"{prefix}-01..{prefix}-{len(rows):02d} sequence")
        known_by_kind[prefix] = set(ids)
        for row in rows:
            rid = row.get("id", "?")
            for field in required_refs:
                refs = row.get(field)
                if not isinstance(refs, list) or not refs:
                    bad.append(f"{rid}: {field} is empty; professional coverage "
                               "cannot be proved vacuously")
                    continue
                universe = (features if field == "features" else
                            steps if field == "steps" else items)
                for ref in refs:
                    if ref not in universe:
                        bad.append(f"{rid}: {field} names {ref!r}, which is not "
                                   "registered")

    gaps = pro.get("gap_closures") or []
    want = expected.get("gap_closures")
    if not isinstance(want, int) or want <= 0:
        bad.append("professional expected population for gap_closures is not "
                   "a positive integer")
    elif len(gaps) != want:
        bad.append(f"professional gap_closures population is {len(gaps)}, "
                   f"expected {want}")
    gids = [g.get("id") for g in gaps]
    if len(gids) != len(set(gids)):
        bad.append("duplicate ids in professional gap_closures")
    expected_gids = [f"GC-{i:02d}" for i in range(1, len(gaps) + 1)]
    if gids != expected_gids:
        bad.append("professional gap_closures ids are not the complete ordered "
                   f"GC-01..GC-{len(gaps):02d} sequence")

    rank = {w: i for i, w in enumerate(WAVES)}
    stage_field = {"foundation": "foundation_wave",
                   "feature": "feature_complete_wave",
                   "release": "release_gate_wave"}
    ref_fields = {"standards": "PA", "workflow": "EW", "advice": "AM"}
    for gap in gaps:
        gid = gap.get("id", "?")
        for forbidden in ("status", "planning_status", "delivery_status"):
            if forbidden in gap:
                bad.append(f"{gid}: {forbidden} is authored; gap state must be "
                           "derived from linked work")
        boundaries = [gap.get("foundation_wave"),
                      gap.get("feature_complete_wave"),
                      gap.get("release_gate_wave")]
        if any(w not in rank for w in boundaries):
            bad.append(f"{gid}: foundation, feature-complete and release-gate "
                       "waves must each be W0-W7")
        elif not (rank[boundaries[0]] <= rank[boundaries[1]]
                  <= rank[boundaries[2]]):
            bad.append(f"{gid}: stage waves are not ordered foundation <= "
                       "feature-complete <= release-gate")

        links = gap.get("links")
        if not isinstance(links, list) or not links:
            bad.append(f"{gid}: has no registered work links")
        else:
            stages = {link.get("stage") for link in links}
            if "feature" not in stages and "foundation" not in stages:
                bad.append(f"{gid}: has no foundation or feature delivery link")
            for link in links:
                item, stage = link.get("item"), link.get("stage")
                if item not in items:
                    bad.append(f"{gid}: link names {item!r}, which is not a row")
                if stage not in stage_field:
                    bad.append(f"{gid}: link stage {stage!r} is not foundation, "
                               "feature or release")
                    continue
                boundary = gap.get(stage_field[stage])
                item_wave = waves.get(item)
                if boundary in rank and item_wave in rank and \
                        rank[item_wave] > rank[boundary]:
                    bad.append(f"{gid}: {stage} item {item} is scheduled "
                               f"{item_wave}, after its {boundary} boundary")
        for field, prefix in ref_fields.items():
            refs = gap.get(field)
            if not isinstance(refs, list) or not refs:
                bad.append(f"{gid}: {field} is empty")
                continue
            for ref in refs:
                if ref not in known_by_kind.get(prefix, set()):
                    bad.append(f"{gid}: {field} names {ref!r}, which is not "
                               "registered")
    return bad


def _missing_pytest(acid: str, ref: str) -> list[str]:
    """A proof naming a test nobody wrote is worse than no proof.

    A DEFINITION, NOT A SUBSTRING. BK-80-AC4 forbids treating test-name
    existence as executed enforcement, and this read
    `node not in f.read_text()` -- so a node id quoted in a docstring, named in
    a comment, or living inside a `CONTROLS` table satisfied it. This suite
    quotes node ids in prose constantly; the same loose match reported ten
    false failures when `tools/known_failures.py` first ran, and here it fails
    the other way, silently.

    It still does not prove the test RAN. That is `bind_execution_evidence`'s
    exact lookup into the bound Class-A population, and the two are deliberately
    separate questions: this one refuses a reference to something that was
    never written, that one refuses a reference to something that did not pass.
    """
    path, _, node = ref.partition("::")
    f = ROOT / path
    if not f.exists():
        return [f"{acid}: proof names {path}, which does not exist"]
    if not node:
        return []
    wanted = node.split("[")[0].rsplit("::", 1)[-1]
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    except SyntaxError as exc:
        return [f"{acid}: proof names {path}, which does not parse ({exc.msg})"]
    defined = {n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if wanted not in defined:
        return [f"{acid}: proof names {wanted!r}, which is not defined in "
                f"{path} -- it may appear there as prose, but a name in a "
                f"docstring is not a test that can run"]
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


def _build_rules(doc: dict) -> list[str]:
    """THE BUILD GUIDE, MADE UNABLE TO LOSE A RULE.

    Splitting the 792-line guide into four stage playbooks was right: a
    document that must be re-read in full before every change is one that gets
    skipped. But the split DROPPED TWO RULES silently --

        "A recommendation treated as authority to act."
        "A fixed intake questionnaire that ignores known or retrievable
         material."

    -- and the first is the boundary between advising a client and binding
    one. Nothing failed. It surfaced only by diffing against a version of the
    guide that no longer exists on disk, and next time there would be nothing
    to diff against.

    So each playbook CLAIMS its rules in a `BUILD_RULES` manifest. Losing one
    now means deleting an id, which this refuses.

    A MANIFEST AND NOT PHRASE MATCHING, deliberately. Deciding whether a card
    still "contains" a rule by keyword overlap is fuzzy matching used to
    IDENTIFY, which CLAUDE.md section 5 forbids and which has already misled
    this session twice. An id is exact. `must_contain` adds an exact phrase for
    the few rules whose loss would be worst, so a card cannot claim a rule it
    no longer states.
    """
    reg = doc.get("build_rules") or {}
    rules = reg.get("rules") or []
    if not rules:
        return ["docs/backlog/build_rules.json holds no rules, so every check "
                "below would pass by having nothing to check"]

    bad: list[str] = []
    expected = reg.get("expected_population")
    if expected is not None and len(rules) != expected:
        bad.append(f"build rules: {len(rules)} present, {expected} expected. "
                   f"A rule was added or lost without the count being moved.")

    seen: set[str] = set()
    for r in rules:
        rid = r.get("id", "?")
        if rid in seen:
            bad.append(f"build rule {rid} appears twice")
        seen.add(rid)
        if r.get("enforcement") not in ("runner", "review", "unenforced"):
            bad.append(f"{rid}: enforcement {r.get('enforcement')!r} is not "
                       f"runner, review or unenforced")
        if r.get("enforcement") == "runner" and not r.get("check"):
            bad.append(f"{rid}: claims a runner and names no check")
        if r.get("enforcement") == "unenforced" and not r.get("why_not"):
            bad.append(f"{rid}: unenforced with no reason -- an admitted gap "
                       f"is work, a silent one is a surprise")
        if r.get("enforcement") == "review" and not r.get("evidence_level"):
            bad.append(f"{rid}: review with no evidence level, so nothing "
                       f"says what kind of recorded result it needs")
        # A named test must exist. A rule pointing at a check nobody wrote is
        # worse than one admitting it has none.
        chk = r.get("check", "")
        if "::" in chk:
            bad += _missing_pytest(rid, chk)

    # ---- every rule is claimed by exactly one playbook, and by the right one
    claimed: dict[str, str] = {}
    for card in sorted({r.get("card") for r in rules if r.get("card")}):
        path = PLAYBOOKS / card
        if not path.exists():
            bad.append(f"playbook {card} is missing, so the rules assigned to "
                       f"it are carried by nothing")
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r"<!--\s*BUILD_RULES:([^>]*?)-->", text)
        if not m:
            bad.append(f"{card}: no BUILD_RULES manifest, so a rule can be "
                       f"dropped from it without anything noticing")
            continue
        for rid in m.group(1).split():
            if rid in claimed:
                bad.append(f"{rid} is claimed by {claimed[rid]} and {card}; "
                           f"one rule has one home")
            claimed[rid] = card

    for r in rules:
        rid, card = r.get("id"), r.get("card")
        where = claimed.get(rid)
        if where is None:
            bad.append(f"{rid} is in the registry and no playbook claims it "
                       f"-- exactly how the guide lost two rules in the split")
        elif where != card:
            bad.append(f"{rid} belongs to {card} and is claimed by {where}")
        phrase = r.get("must_contain")
        if phrase and where and (PLAYBOOKS / where).exists():
            body = (PLAYBOOKS / where).read_text(encoding="utf-8").lower()
            if phrase.lower() not in body:
                bad.append(f"{rid}: {where} claims it but no longer says "
                           f"{phrase!r}")
    for rid in sorted(set(claimed) - seen):
        bad.append(f"{claimed[rid]} claims {rid}, which is not a build rule")
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

def proof_state(ac: dict, *, bind_execution: bool = True) -> str:
    """The single state of one acceptance criterion, across its levels.

    THE WORST LEVEL WINS, and a level with no entry at all is `NOT_RUN`. That
    is the rule the whole system turns on: a missing link is NOT PROVEN, never
    implicitly passing.
    """
    worst = "PASS"
    order = ["FAIL", "BLOCKED", "STALE", "NOT_RUN", "PASS", "NOT_APPLICABLE"]
    got = ac.get("evidence") or {}
    for lvl in ac.get("required_evidence") or []:
        evidence = got.get(lvl) or {}
        r = (evidence.get("_effective_result", evidence.get("result", "NOT_RUN"))
             if bind_execution else evidence.get("result", "NOT_RUN"))
        if order.index(r) < order.index(worst):
            worst = r
    return worst


def item_result(it: dict, *, bind_execution: bool = True) -> str:
    """NOT_PROVEN unless every criterion passes. No criteria is not a pass."""
    acc = it.get("acceptance") or []
    if not acc:
        return "NOT_PROVEN"
    states = {proof_state(a, bind_execution=bind_execution) for a in acc}
    if states <= {"PASS", "NOT_APPLICABLE"}:
        return "PASS"
    if "FAIL" in states:
        return "FAIL"
    return "NOT_PROVEN"


def derive_done(it: dict, by_id: dict, *, bind_execution: bool = True) -> bool:
    """DONE IS COMPUTED. Nobody types it and thereby makes it true.

    A legacy row -- closed before this registry existed -- rests on prose in
    BACKLOG.md. That is real evidence and it is not executable, so it counts
    here ONLY because it is declared as `legacy: true` and counted by `status`.
    An admitted gap is work; a silent one is a surprise.
    """
    if it.get("delivery_status") == "deferred":
        return False
    if it.get("implementation") != "complete":
        return False
    if it.get("blocked_by"):
        return False
    for dep in it.get("depends_on") or []:
        d = by_id.get(dep)
        if not d or not derive_done(d, by_id,
                                    bind_execution=bind_execution):
            return False
    if it.get("legacy"):
        return it.get("verification") in ("stale", "passing")
    if item_result(it, bind_execution=bind_execution) != "PASS":
        return False
    levels = {lvl for a in it.get("acceptance") or []
              for lvl in (a.get("required_evidence") or [])}
    if it.get("kind") in COUNSEL_FACING_KINDS and it.get("priority") == "P0" \
            and "counsel_review" not in levels:
        return False
    # THE SIGN-OFF IS REQUIRED, NOT OFFERED. BK-74.
    #
    # This read `if records and ...`, so a row carrying NO stage records
    # skipped the sign-off requirement altogether. Measured on 10 September
    # 2026: 80 of 83 rows had no records, 54 of those were NOT legacy, and
    # BK-21 -- a P0 product row with four PASSing criteria -- derived
    # `done: True` with `signoff: None`, having never been asked.
    #
    # The gate was therefore inverted in effect: rows that RECORDED their
    # lifecycle were held at NOT_RUN, and rows that recorded nothing were
    # waved through. Absence read as exemption, which is §9 in the one
    # function that decides whether work is finished -- and the direct
    # negation of this registry's governing rule, that A MISSING LINK MUST
    # MEAN NOT PROVEN AND NEVER IMPLICITLY PASSING.
    #
    # THE LEGACY POPULATION IS UNAFFECTED and that is why this can be
    # unconditional: a `legacy` row returns above, on prose evidence that is
    # declared and counted. Every row reaching this line is one this registry
    # governs, and a governed row with no record has not proven its lifecycle
    # -- it has merely not been asked about it.
    records = it.get("stage_records") or {}
    if (records.get("signoff") or {}).get("result") != "SIGNED_OFF":
        return False
    return True


def gap_state(gap: dict, by_id: dict[str, dict], *,
              bind_execution: bool = True) -> str:
    """Derive a gap's state; the professional registry may never author it."""
    linked = [by_id.get(link.get("item"))
              for link in gap.get("links") or []]
    linked = [it for it in linked if it]
    if not linked:
        return "UNREGISTERED"
    if all(derive_done(it, by_id, bind_execution=bind_execution)
           for it in linked):
        return "CLOSED"
    if any(it.get("delivery_status") == "blocked" for it in linked):
        return "BLOCKED"
    if any(derive_done(it, by_id, bind_execution=bind_execution)
           or it.get("implementation") in ("partial", "complete")
           or it.get("delivery_status") in ("ready", "in_progress", "verifying")
           for it in linked):
        return "IN_PROGRESS"
    return "PLANNED"


def readiness(it: dict, by_id: dict, *, bind_execution: bool = True) -> str:
    if it.get("delivery_status") == "deferred":
        return "not_ready"
    if derive_done(it, by_id, bind_execution=bind_execution):
        return "releasable"
    if (it.get("priority") in ("P0",)
            and not derive_done(it, by_id,
                                bind_execution=bind_execution)):
        return "not_ready"
    if it.get("implementation") == "complete":
        return "conditional"
    return "not_ready"


# ---------------------------------------------------------------- report ---

def board(doc: dict, *, bind_execution: bool = True,
          as_of: date | None = None) -> str:
    items = doc["items"]
    by_id = {i["id"]: i for i in items}
    feats = doc["features"]

    evidence_scope = (
        "This live view binds every automated PASS to the current execution "
        "artifact."
        if bind_execution else
        "This persisted view projects the authored registry contract. "
        "`backlog check` separately refuses stale or absent execution evidence "
        "before it can report success.")
    lines = [
        "## Part 0 — The current control board",
        "",
        "**Generated by `python tools/backlog.py render`. Do not edit by "
        "hand.** Every count below was maintained manually once and every one "
        "of them was wrong: `Open — 13`, *sixteen phases*, *18 pass* against a "
        "suite that collects 24.",
        "",
        evidence_scope,
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
        done = sum(1 for i in mine
                   if derive_done(i, by_id,
                                  bind_execution=bind_execution))
        p0 = sum(1 for i in mine
                 if i.get("priority") == "P0"
                 and not derive_done(i, by_id,
                                     bind_execution=bind_execution))
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
              if i.get("priority") == "P0"
              and not derive_done(i, by_id,
                                  bind_execution=bind_execution)]
    blocked = [i for i in items if i.get("delivery_status") == "blocked"]
    legacy = [i for i in items if i.get("legacy")]
    noacc = [i for i in items
             if not i.get("legacy") and not (i.get("acceptance") or [])]
    pop = professional_population(doc)
    wave_rows = (doc.get("plan") or {}).get("item_waves") or []
    gaps = (doc.get("professional") or {}).get("gap_closures") or []
    gap_counts: dict[str, int] = {}
    for gap in gaps:
        state = gap_state(gap, by_id, bind_execution=bind_execution)
        gap_counts[state] = gap_counts.get(state, 0) + 1

    lines += [
        "",
        f"**{len(items)} rows · {len(openp0)} open P0 · {len(blocked)} "
        f"blocked · {sum(1 for f in feats if f['implementation'] == 'complete')}"
        f"/{len(feats)} features implemented**",
        "",
        "### Professional plan — registered and derived",
        "",
        f"**{pop['advocate_standards']} advocate standards · "
        f"{pop['workflow_states']} expert-workflow states · "
        f"{pop['advice_maturity']} advice levels · {pop['roles']} roles · "
        f"{pop['gap_closures']} gap closures · {len(wave_rows)} wave rows**",
        "",
        "Gap status below is computed from the linked BK/J rows. It is never "
        "authored in `professional.json` or maintained in the workbook.",
        "",
        "| Gap | Foundation | Feature complete | Release gate | Derived state | Registered work |",
        "|---|---:|---:|---:|---|---|",
    ]
    for gap in gaps:
        work = ", ".join(link["item"] for link in gap.get("links") or [])
        lines.append(f"| {gap['id']} | {gap['foundation_wave']} | "
                     f"{gap['feature_complete_wave']} | "
                     f"{gap['release_gate_wave']} | "
                     f"{gap_state(gap, by_id, bind_execution=bind_execution)} | "
                     f"{work} |")
    lines += [
        "",
        "Derived gap state: " + ", ".join(
            f"{state} {count}" for state, count in sorted(gap_counts.items())),
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

    lines += _deferral_report(doc, as_of=as_of, live=bind_execution)

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
                 f"{START}\n\n{board(doc, bind_execution=False)}\n{END}",
                 text, flags=re.S)
    changed = new != text
    if changed:
        BACKLOG.write_text(new, encoding="utf-8")
    return changed


#: Fallback for the declared pre-BK-74 migration population. Managed rows use
#: their four records below. READY means Start is closed, so Build is next.
STAGE_FOR = {
    "planned": "before", "ready": "build", "blocked": "before",
    "in_progress": "build", "verifying": "prove",
}


def next_stage(it: dict, by_id: dict[str, dict]) -> str | None:
    """Return the playbook stage the item must open next; None is terminal."""
    if it.get("delivery_status") == "deferred":
        return None
    if derive_done(it, by_id):
        return None
    records = it.get("stage_records")
    if records:
        if (records.get("start") or {}).get("result") != "READY":
            return "before"
        if (records.get("build") or {}).get("result") != "BUILT":
            return "build"
        if (records.get("test") or {}).get("result") != "VERIFIED":
            return "prove"
        if (records.get("signoff") or {}).get("result") != "SIGNED_OFF":
            return "signoff"
        return None
    if (it.get("implementation") == "complete"
            and item_result(it) == "PASS"):
        return "signoff"
    return STAGE_FOR.get(it.get("delivery_status"))


def stage_report(doc: dict, rid: str, *, as_of: date | None = None) -> tuple[str, int]:
    """WHICH PLAYBOOK, FOR THIS ITEM, RIGHT NOW -- and what already fails.

    A playbook I must remember to open is one I will skip under context
    pressure; that is the whole reason the guide was split, and splitting alone
    does not fix it. This makes the tooling hand me the card instead.
    """
    by = {i["id"]: i for i in doc["items"]}
    it = by.get(rid)
    if it is None:
        return (f"{rid} is not in the registry. Work with no registered item "
                f"is the first stop rule (BG-048)."), 1

    ds = it.get("delivery_status")
    stage = next_stage(it, by)
    reg = doc.get("build_rules") or {}
    out = [f"{rid}  {it.get('title')}",
           f"  {ds} / impl {it.get('implementation')} / "
           f"verification {it.get('verification')} / {it.get('priority')}"]

    if ds == "deferred":
        out += _deferral_report({"items": [it]}, as_of=as_of)
        out.append("Record the reassessment, reason and any new review date; "
                   "reactivate explicitly through Start before Build. This "
                   "row is not DONE and no build playbook is opened automatically.")
        return "\n".join(out), 1

    if stage is None:
        out.append("\n  DONE is derived and the lifecycle is closed: no "
                   "playbook applies. Reopen the row before doing work against it.")
        return "\n".join(out), 0

    card = (reg.get("cards") or {}).get(stage, "?")
    out.append(f"\n  OPEN  docs/playbooks/{card}")

    # What is already true against this item, so the card is not read blind.
    blocking = []
    if it.get("blocked_by"):
        blocking.append(f"BLOCKED: {it['blocked_by'].get('description','')}")
    if not (it.get("acceptance") or []):
        blocking.append("no acceptance criteria, so `done` can never derive "
                        "(BG-027, BG-028)")
    for ac in it.get("acceptance") or []:
        st = proof_state(ac)
        if st != "PASS":
            blocking.append(f"{ac['id']} is {st}")
    for dep in it.get("depends_on") or []:
        d = by.get(dep)
        if d and not derive_done(d, by):
            blocking.append(f"depends on {dep}, which is not done")
    if blocking:
        out.append("\n  ALREADY FAILING FOR THIS ITEM")
        out += [f"    - {b}" for b in blocking]

    rules = [r for r in (reg.get("rules") or []) if r.get("stage") == stage]
    runner = [r for r in rules if r["enforcement"] == "runner"]
    review = [r for r in rules if r["enforcement"] == "review"]
    unenf = [r for r in rules if r["enforcement"] == "unenforced"]
    out.append(f"\n  {len(rules)} rules at this stage: {len(runner)} enforced "
               f"by a check, {len(review)} need a recorded human review, "
               f"{len(unenf)} rest on judgement alone")
    if unenf:
        out.append("\n  NOTHING CHECKS THESE. They are yours to hold:")
        for r in unenf:
            out.append(f"    {r['id']}  {r['statement'][:88]}")
    return "\n".join(out), 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["lint", "status", "graph", "render",
                                        "check", "stage", "rules"])
    ap.add_argument("item", nargs="?", help="BK-/J- id, for `stage`")
    ap.add_argument("--as-of", type=calendar_date,
                    help="India calendar date for read-only status/stage review")
    args = ap.parse_args()
    if args.as_of is not None and args.command not in {"status", "stage"}:
        ap.error("--as-of is only allowed for read-only status or stage")
    doc = load()

    if args.command == "stage":
        if not args.item:
            print("usage: backlog.py stage <BK-id>", file=sys.stderr)
            return 2
        text, code = stage_report(doc, args.item, as_of=args.as_of)
        print(text)
        return code

    if args.command == "rules":
        rules = (doc.get("build_rules") or {}).get("rules") or []
        for stage in ("before", "build", "prove", "signoff"):
            at = [r for r in rules if r["stage"] == stage]
            en = sum(1 for r in at if r["enforcement"] == "runner")
            rv = sum(1 for r in at if r["enforcement"] == "review")
            print(f"  {stage:8} {len(at):3} rules   {en:2} runner  {rv:2} "
                  f"review  {len(at)-en-rv:2} unenforced")
        print(f"\n  {len(rules)} build rules; "
              f"{sum(1 for r in rules if r['enforcement'] == 'unenforced')} "
              f"rest on judgement alone and are declared, not hidden.")
        return 0

    if args.command in ("lint", "check"):
        bad = lint(doc, verify_execution=True)
        for b in bad:
            print(f"  {b}")
        pop = professional_population(doc)
        wave_count = len((doc.get("plan") or {}).get("item_waves") or [])
        print(f"LINT {'FAILED' if bad else 'OK'}  {len(bad)} problem(s), "
              f"{len(doc['items'])} rows, {len(doc['features'])} features, "
              f"{len(doc.get('steps') or [])} steps, "
              f"{pop['advocate_standards']} PA, "
              f"{pop['workflow_states']} EW, "
              f"{pop['advice_maturity']} AM, {pop['roles']} roles, "
              f"{pop['gap_closures']} GC, {wave_count} wave rows")
        print("\n".join(_deferral_report(doc)))
        if bad:
            return 1

    if args.command in ("status", "check"):
        print()
        print(board(doc, as_of=args.as_of))

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
