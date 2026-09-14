"""THE COMMANDS THAT TAKE THE MEASUREMENTS THIS BUILD CANNOT TAKE.

    python tools/measure.py seal
    python tools/measure.py production --criterion BK-42-AC3 --environment ...
    python tools/measure.py production-record --file <signed.json>
    python tools/measure.py review-pack --criterion BK-42-AC9
    python tools/measure.py review-record --file <signed.json>
    python tools/measure.py tabletop-pack
    python tools/measure.py tabletop-record --file <exercise.json>

WHY THIS EXISTS
-----------------
Twenty-two criteria across P38 to P41 carry a row that no test can close: a
production measure needs a deployment, a counsel review needs qualified
counsel, and an incident rehearsal needs people. Until now the dependency was
recorded as a SENTENCE in a note. A sentence is not a protocol -- the operator
still has to work out what to run, what to observe and what shape the answer
goes in, and every one of those is a place the evidence goes wrong.

So each outstanding row gets a command. The dependency stops being "somebody
should measure this on a deployment" and becomes a concrete protocol pack.
The observation is then signed outside this repository and promoted only after
the configured evidence verifier authenticates both the exact payload and the
actor's authority. `seal` reports and writes nothing, because BK-21-AC3 asks
for a domain test and no document can be one.

WHAT THIS TOOL MAY NEVER DO
-----------------------------
Decide that something passed.

    A tool that writes evidence records is a tool that can manufacture them.

So it does exactly two things and nothing else: it PREPARES a protocol that
confers no result, or it PROMOTES a cryptographically authenticated schema-2
record somebody else signed. A command-line flag, an environment label and an
unsigned JSON file can never turn NOT RUN into PASS.

WHAT IT WILL NOT DO EITHER
----------------------------
Contact anybody. `review-pack` writes a bundle to a file for a person to read;
it sends no mail and opens no socket. `tabletop-pack` writes a scenario; it
pages nobody. `production` refuses off this machine rather than reaching for a
deployment that does not exist.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.domain.deployment import Candidate, shares_value_with  # noqa: E402
from tools._console import utf8_console  # noqa: E402
from tools.evidence import verification_fingerprint  # noqa: E402
from tools.evidence_verification import configured_verifier  # noqa: E402
from tools.structured_evidence import problems_for_record  # noqa: E402

utf8_console()

EVIDENCE = ROOT / "docs" / "backlog" / "evidence"
PACKS = ROOT / ".nm" / "packs"

#: What a credential-shaped variable looks like. The same broad rule
#: `composition` uses, and for the same reason: naming the one variable that
#: collided would guard today's mistake and none of the others.
CREDENTIAL = ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")
SEAL = "NM_MATTER_KEY"


def _commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:                       # noqa: BLE001 -- never fatal
        return "unknown"


def _today() -> str:
    from nm.domain.clock import today

    return today().isoformat()


def _shown(path: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _criterion(acid: str) -> dict:
    """Return one registered acceptance criterion; unknown work cannot pass."""
    from yaml import safe_load

    doc = safe_load((ROOT / "docs/backlog/status.yaml").read_text(encoding="utf-8"))
    found = [criterion for item in doc.get("items", [])
             for criterion in item.get("acceptance", [])
             if criterion.get("id") == acid]
    if len(found) != 1:
        raise ValueError(f"{acid!r} is not one unique registered criterion")
    return found[0]


def _promote_verified(source: pathlib.Path, *, expected_level: str,
                      verifier=None) -> int:
    """Promote one record only after the existing P03 trust boundary accepts it.

    The source document is not trusted while it chooses its own criterion,
    actor, authority or result.  It is copied to a non-authoritative candidate
    path, verified as an exact schema-2 record and moved into place only after
    every check succeeds. Existing evidence is never overwritten implicitly.
    """
    try:
        record = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  REFUSED  evidence cannot be read ({exc.__class__.__name__}).")
        return 1
    if not isinstance(record, dict):
        print("  REFUSED  evidence is not a JSON object.")
        return 1
    acid, level = str(record.get("criterion") or ""), record.get("level")
    if not re.fullmatch(r"(?:BK-\d+|J-\d+)-AC\d+", acid):
        print("  REFUSED  evidence does not name a safe registered criterion.")
        return 1
    try:
        criterion = _criterion(acid)
    except ValueError as exc:
        print(f"  REFUSED  {exc}")
        return 1
    if level != expected_level or level not in criterion.get("required_evidence", []):
        print(f"  REFUSED  {acid} does not require {expected_level!r} from this command.")
        return 1

    active_verifier = verifier or configured_verifier(base=ROOT)
    bad = problems_for_record(
        acid, expected_level, record,
        source_fingerprint=verification_fingerprint(),
        configuration_identity=active_verifier.configuration_identity,
        verifier=active_verifier,
    )
    if bad:
        print(f"  REFUSED  {acid}/{expected_level} is not authenticated evidence:")
        for why in bad:
            print(f"    - {why}")
        return 1

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    candidate = EVIDENCE / f".{acid}-{expected_level}.{os.getpid()}.candidate.json"
    target = EVIDENCE / f"{acid}-{expected_level}.json"
    try:
        candidate.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        rendered = candidate.read_bytes()
        if target.exists():
            if target.read_bytes() == rendered:
                print(f"  VERIFIED  {_shown(target)} already matches.")
                return 0
            print(f"  REFUSED  {_shown(target)} already exists; "
                  "replace evidence only through an explicit reviewed change.")
            return 1
        try:
            # Same-directory hard-link publication is atomic and cannot
            # overwrite a record another process promoted after our check.
            os.link(candidate, target)
        except FileExistsError:
            if target.read_bytes() == rendered:
                print(f"  VERIFIED  {_shown(target)} already matches.")
                return 0
            print(f"  REFUSED  {_shown(target)} was created concurrently; "
                  "no existing evidence was overwritten.")
            return 1
        print(f"  VERIFIED AND PROMOTED  {_shown(target)}")
        print(f"  Register that exact ref under {acid}.evidence.{expected_level}.")
        return 0
    finally:
        candidate.unlink(missing_ok=True)


# ------------------------------------------------------------------ seal ----

def seal(args) -> int:
    """BK-21-AC3, checked on the installation this actually runs in.

    IT REPORTS AND IT DOES NOT WRITE A RECORD, and the reason is worth
    keeping. BK-21-AC3 requires a `domain_test`, and a domain test is a
    hermetic Class-A node -- it cannot assert a fact about whatever machine
    somebody happens to run it on, and a node that tried would have to skip
    when the key was absent, which Class-A refuses. So no document this
    command could write would close that row, and one that claimed to would
    be evidence of the wrong kind wearing the right name.

    What it does instead is give the operator the check itself: run it on the
    real installation and find out, before a rotation makes 247 matters
    unreadable. The row stays BLOCKED until the criterion is reopened with an
    evidence method that can carry a statement about a configured machine.

    No value is printed, compared as text, or written anywhere. The comparison
    is `deployment.shares_value_with`, which answers by digest.
    """
    from nm.adapters.model.config import load_dotenv

    load_dotenv(ROOT / ".env")
    key = os.environ.get(SEAL, "")
    if not key.strip():
        print(f"  NOT ASSESSED  {SEAL} is not set in this environment.")
        print("    An absent value cannot show a separation that was never at")
        print("    risk here. Run this on the installation that holds the key.")
        return 2

    population = {name: value for name, value in os.environ.items()
                  if name != SEAL and any(w in name.upper() for w in CREDENTIAL)}
    population[SEAL] = key
    shared = sorted(shares_value_with(SEAL, population))

    if shared:
        print(f"  FAILED  {SEAL} holds the same value as: {', '.join(shared)}")
        print("    Generate a new seal, re-key the store with it, and only")
        print("    THEN rotate the other credential -- in that order, because")
        print("    rotating first makes every stored matter unreadable.")
        return 1

    print(f"  OBSERVED  {SEAL} shares its value with none of "
          f"{len(population) - 1} credential-shaped variable(s), by digest.")
    print("    BK-21-AC3 STAYS BLOCKED. Its required method is a domain test,")
    print("    and a hermetic Class-A node cannot carry a statement about the")
    print("    machine it happens to run on. This is the check, not the")
    print("    evidence.")
    return 0


# ------------------------------------------------------------ production ----

def production(args) -> int:
    """Prepare a production protocol. It deliberately records no verdict."""
    try:
        criterion = _criterion(args.criterion)
    except ValueError as exc:
        print(f"  REFUSED  {exc}")
        return 1
    if "production_measure" not in criterion.get("required_evidence", []):
        print(f"  REFUSED  {args.criterion} does not require a production measure.")
        return 1
    about = Candidate(commit=_commit(), environment=args.environment,
                      config_digest=args.config_digest)
    PACKS.mkdir(parents=True, exist_ok=True)
    path = PACKS / f"{args.criterion}-production-measure.json"
    path.write_text(json.dumps({
        "schema": 1,
        "kind": "production_measure_protocol",
        "criterion": args.criterion,
        "requirement": criterion.get("requirement"),
        "negative_control": criterion.get("negative_control"),
        "claimed_target": {
            "commit": about.commit,
            "environment": about.environment,
            "configuration_digest": about.config_digest,
            "candidate_identity": about.identity,
            "operation_state": about.operation_state.value,
        },
        "planned_subject": args.subject,
        "planned_method": args.method,
        "prepared_on": _today(),
        "required_result": "an externally observed schema-2 evidence record",
        "note": "This is a protocol assembled from repository and command-line "
                "claims. It is not an observation, carries no PASS and confers "
                "none. Sign the exact schema-2 record and its authority through "
                "the configured P03 trust boundary before promotion.",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  PACK  {path}")
    print(f"  {args.environment!r} remains UNVERIFIED; its name proves nothing.")
    print("  After the target observation is independently signed, promote it with:")
    print("    python tools/measure.py production-record --file <signed-record.json>")
    return 0


def production_record(args) -> int:
    """Promote an authenticated production record; never synthesize one."""
    return _promote_verified(pathlib.Path(args.file),
                             expected_level="production_measure")


# ---------------------------------------------------------------- review ----

def _protocol(protocol_id: str) -> dict:
    document = json.loads(
        (ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf-8"))
    for row in document["manual_review_protocols"]:
        if row["id"] == protocol_id:
            return row
    raise SystemExit(f"{protocol_id} is not a declared review protocol")


def review_pack(args) -> int:
    """Assemble what the reviewer needs. SENDS IT NOWHERE."""
    owning = [row for row in json.loads(
        (ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf-8")
    )["manual_review_protocols"] if args.criterion in row["owner_criteria"]]
    if not owning:
        print(f"  {args.criterion} is not owned by any declared review "
              f"protocol, so there is no protocol to follow yet.")
        return 1
    protocol = owning[0]
    PACKS.mkdir(parents=True, exist_ok=True)
    path = PACKS / f"{args.criterion}-{protocol['id']}.json"
    path.write_text(json.dumps({
        "criterion": args.criterion,
        "protocol": protocol["id"],
        "reviewer_role": protocol["reviewer_role"],
        "commit": _commit(),
        "prepared_on": _today(),
        "required_inputs": protocol["required_inputs"],
        "tasks": protocol["tasks"],
        "failure_conditions": protocol["failure_conditions"],
        "required_output_fields": protocol["required_output_fields"],
        "note": "This pack was assembled by a tool and sent to nobody. It "
                "carries no approval and confers none.",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"  PACK  {path}")
    print(f"  For: {protocol['reviewer_role']}")
    print("  Return a signed record and validate it with:")
    print("    python tools/measure.py review-record --file <signed.json>")
    return 0


def review_record(args) -> int:
    """Promote an authenticated counsel record; never synthesize one."""
    return _promote_verified(pathlib.Path(args.file),
                             expected_level="counsel_review")


# -------------------------------------------------------------- tabletop ----

def tabletop_pack(args) -> int:
    """The exercise the accountable people run. PAGES NOBODY."""
    from nm.domain.incident import load_clocks

    clocks = load_clocks(ROOT)
    PACKS.mkdir(parents=True, exist_ok=True)
    path = PACKS / "incident-tabletop.json"
    path.write_text(json.dumps({
        "scenario_id": "unauthorised-export",
        "scenario_version": 3,
        "criteria": ["BK-85-AC5", "BK-88-AC3"],
        "protocol": "REVIEW-OPERATIONS",
        "prepared_on": _today(),
        "reviewed_clocks": [
            {"clock_id": c.clock_id, "hours": c.hours,
             "starts_from": c.starts_from, "instrument": c.instrument,
             "applicability": c.applicability.value} for c in clocks],
        "injects": [
            "A support account exported material from a matter it does not own.",
            "The primary incident commander does not answer the page.",
            "The scope of what was exported is not yet known.",
        ],
        "record_these": [
            "occurred_at, detected_at and noticed_at as three separate moments",
            "every contact paged, in order, and whether they answered",
            "one notification decision per reviewed clock, with who decided",
            "each containment action and the authority that permitted it",
            "each preserved item by SHA-256, holder and time",
            "every step that was missed, with an owner",
            "the configuration digest of the enabled pilot",
        ],
        "note": "A rehearsal may not notify anybody. The furthest any "
                "notification decision goes is prepared_for_human_"
                "authorisation. Do not put client content in this record: "
                "there is no field that accepts it.",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"  PACK  {path}")
    print("  Run it with the named incident commander, the security/legal")
    print("  owner and an independent recovery witness, then validate with:")
    print("    python tools/measure.py tabletop-record --file <exercise.json>")
    return 0


def tabletop_record(args) -> int:
    """Validate a completed exercise through the domain's own refusals."""
    from nm.domain.incident import (
        Contact,
        Exercise,
        Reached,
        Rota,
        Timeline,
        load_clocks,
        refuse_close,
    )

    done = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    exercise = Exercise(
        exercise_id=done["exercise_id"], scenario_id=done["scenario_id"],
        scenario_version=int(done["scenario_version"]),
        conducted_at=done["conducted_at"],
        timeline=Timeline(**done["timeline"]),
        configuration_digest=done.get("configuration_digest", ""),
        rotas=tuple(Rota(role=r["role"], contacts=tuple(
            Contact(role=r["role"], person_id=c["person_id"],
                    order=int(c["order"]), reached=Reached(c["reached"]),
                    responded_at=c.get("responded_at", ""))
            for c in r["contacts"])) for r in done.get("rotas", [])),
        participants=tuple(done.get("participants", ())))
    refused = refuse_close(exercise, clocks=load_clocks(ROOT),
                           pilot_digest=args.pilot_digest)
    if refused:
        print("  REFUSED  this exercise may not be recorded as complete:")
        for why in refused:
            print(f"    - {why}")
        return 1
    print("  The exercise passes the domain closure checks. This is not yet")
    print("  authenticated evidence. Create and independently sign one schema-2")
    print("  production_measure record per criterion, then use production-record.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="measure", description=__doc__)
    ap.add_argument("--environment", default="working_tree")
    ap.add_argument("--config-digest", default="")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("seal").set_defaults(fn=seal)

    p = sub.add_parser("production")
    p.add_argument("--criterion", required=True)
    p.add_argument("--subject", default="a production measure")
    p.add_argument("--method", default="describe how the target will be observed")
    p.set_defaults(fn=production)

    p = sub.add_parser("production-record")
    p.add_argument("--file", required=True)
    p.set_defaults(fn=production_record)

    p = sub.add_parser("review-pack")
    p.add_argument("--criterion", required=True)
    p.set_defaults(fn=review_pack)

    p = sub.add_parser("review-record")
    p.add_argument("--file", required=True)
    p.set_defaults(fn=review_record)

    sub.add_parser("tabletop-pack").set_defaults(fn=tabletop_pack)

    p = sub.add_parser("tabletop-record")
    p.add_argument("--file", required=True)
    p.add_argument("--pilot-digest", default="")
    p.set_defaults(fn=tabletop_record)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
