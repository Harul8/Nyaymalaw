"""Did the gate pass on THIS tree, or on one that no longer exists?

    python tools/gatestamp.py            # is the tree the one the gate passed on?
`tools/check.py` is the only command that records a pass. This reader cannot
turn its own invocation into evidence.

WHAT HAPPENED, 6 September 2026
--------------------------------
A heredoc collapsed `\\n\\n` inside a nested string literal, `spec/plan/
build_plan.py` stopped parsing, and it went to HEAD. The register could not be
read at all for the length of one commit.

The gate would have caught it. The gate had already run. THE ORDER WAS: run
the gate, edit, commit -- so the green being relied on described a tree that no
longer existed, and nothing anywhere compared the two.

That is B-111 one layer out, and B-114 one layer further. B-111 gave the gate a
fingerprint so it could not measure a moving tree. B-114 gave the served
product one so nobody could draw a conclusion about code that is not running.
This gives the COMMIT one, so nobody can rely on a green that is about
something else. Same rule each time: A RESULT MUST NAME THE THING IT IS ABOUT.

WHY THIS DIGEST IS THE CHECKED-TREE IDENTITY
---------------------------------------------
`nm.domain.identity.source_fingerprint` covers `nm` and `tests`, because it
answers "what code is this process running". The file that broke was in
`spec/`, which the gate checks and the server never runs -- so that digest
would not have moved, and this check would have passed on the very commit that
prompted it.

Class-A evidence, the running gate and this stamp all use the one explicit
checked-tree manifest. A stamp cannot therefore stay current for an input the
gate or its evidence identity omitted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._console import utf8_console  # noqa: E402
from tools.evidence import (  # noqa: E402
    IDENTITY_MANIFEST,
    verification_fingerprint,
)

utf8_console()

#: Kept as a readable view for diagnostics and older callers; the digest owner
#: is IDENTITY_MANIFEST in tools.evidence, not a second list in this module.
CHECKED = tuple(source.path for source in IDENTITY_MANIFEST)

#: Not versioned. `.nm/` is gitignored, which is right -- a stamp is a fact
#: about ONE machine's last run, and a shared one would tell every other
#: machine its tree was green when nothing there had been checked.
STAMP = ROOT / ".nm" / "last_green.json"
STAMP_POPULATION = "local-engineering:no-class-c,no-class-d,no-journey"


def tree_digest(root: Path | None = None) -> str:
    """The same canonical checked-tree identity Class-A evidence uses."""
    return verification_fingerprint(root or ROOT)


def staged_tree_digest(root: Path | None = None) -> str:
    """Materialise and identify exactly what the Git index would commit."""
    root = root or ROOT
    with tempfile.TemporaryDirectory(prefix="nm-staged-tree-") as scratch:
        candidate = Path(scratch) / "tree"
        candidate.mkdir()
        proc = subprocess.run(
            ["git", "-C", str(root), "checkout-index", "--all", "--force",
             f"--prefix={candidate}{os.sep}"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if proc.returncode:
            detail = (proc.stderr or proc.stdout).strip()
            raise RuntimeError(f"cannot materialise staged tree: {detail}")
        return tree_digest(candidate)


def record(digest: str | None = None, *, kind: str = "full",
           waived: list[str] | None = None, baseline: str = "") -> str:
    """Record a pass, SAYING WHICH KIND OF PASS IT WAS. BK-80-AC7.

    A stamp used to be one field -- the tree -- so every green looked alike. A
    scoped build pass over a declared, owned red is a different fact from a
    full green, and a caller asking "may I release" must not receive the same
    answer as one asking "may I commit". The kind travels with the stamp, and
    the waived ids travel with it too so the stamp says what it excluded rather
    than merely that it excluded something.

    `baseline` is the known-failure registry's digest. A stamp naming a
    baseline that no longer matches is not current: the declared red changed
    under it, which is precisely when a scoped pass stops meaning anything.
    """
    if kind not in ("full", "scoped"):
        raise ValueError(f"a gate stamp is full or scoped, not {kind!r}")
    waived = waived or []
    if kind == "full" and (baseline or waived):
        raise ValueError("a full gate stamp cannot carry a waiver or baseline")
    if kind == "scoped" and (
            not re.fullmatch(r"[0-9a-f]{64}", baseline)
            or not waived
            or len(waived) != len(set(waived))
            or not all(isinstance(item, str) and item for item in waived)):
        raise ValueError(
            "a scoped gate stamp needs a full baseline and unique waiver ids")
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    digest = digest or tree_digest()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("a gate stamp tree must be a full sha256 identity")
    STAMP.write_text(json.dumps({
        "schema": 2,
        "profile": "checked-tree-v2",
        "population": STAMP_POPULATION,
        "tree": digest,
        "kind": kind,
        "waived": sorted(waived or []),
        "baseline": baseline,
    }), encoding="utf8")
    return digest


def state(*, require_index: bool = False) -> tuple[str, str]:
    """(verdict, sentence). THREE STATES, and the third is the common one.

    `not_assessed` when no gate has ever passed on this machine -- which is
    NOT "stale" and NOT "current". Reporting it as either would be the
    absent-input defect on the check built to catch a stale result.
    """
    now = tree_digest()
    staged = ""
    if require_index:
        try:
            staged = staged_tree_digest()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            return (
                "not_assessed",
                "the staged commit candidate could not be identified "
                f"({type(exc).__name__}: {exc}), so the hook cannot certify it.",
            )
    if not STAMP.exists():
        return ("not_assessed",
                "no gate run has been recorded on this machine, so nothing "
                "can be said about whether this tree was checked. Run "
                "`python tools/check.py`.")
    try:
        stamp = json.loads(STAMP.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ("not_assessed",
                f"the recorded gate stamp could not be read ({type(exc).__name__}), "
                f"so nothing can be said about this tree.")
    if (not isinstance(stamp, dict) or stamp.get("schema") != 2
            or stamp.get("profile") != "checked-tree-v2"
            or stamp.get("population") != STAMP_POPULATION
            or stamp.get("kind") not in ("full", "scoped")
            or not isinstance(stamp.get("tree"), str)):
        return ("not_assessed",
                "the recorded gate stamp has no supported schema, profile, "
                "population, tree and kind, so it cannot certify this tree.")
    if stamp["kind"] == "full" and (
            stamp.get("waived") != [] or stamp.get("baseline") != ""):
        return (
            "not_assessed",
            "the full local gate stamp carries waiver data, so its payload is "
            "internally contradictory and cannot certify this tree.",
        )
    was = stamp["tree"]
    if require_index and was != staged:
        return (
            "stale",
            f"the gate passed on {was}, but the staged commit candidate is "
            f"{staged}. The commit is not the tree that was checked.",
        )
    if was == now:
        kind = stamp["kind"]
        if kind == "scoped":
            from tools.known_failures import load, registry_digest

            waived = stamp.get("waived")
            baseline = stamp.get("baseline")
            if (not isinstance(waived, list) or not waived
                    or len(waived) != len(set(waived))
                    or not all(isinstance(item, str) and item for item in waived)
                    or not isinstance(baseline, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", baseline)):
                return ("not_assessed",
                        "the scoped gate stamp does not name a valid failure "
                        "baseline and waiver set, so it cannot certify this tree.")
            if baseline != registry_digest():
                return ("stale",
                        "the scoped gate passed against a different declared "
                        "failure set than the one now in "
                        "docs/backlog/known_failures.yaml, so what it waived "
                         "is not what this tree declares.")
            try:
                expected_waivers = {row.id for row in load()}
            except Exception as exc:  # noqa: BLE001 -- an unreadable red is not a pass
                return (
                    "not_assessed",
                    "the declared failure set could not be read "
                    f"({type(exc).__name__}), so the scoped stamp cannot certify it.",
                )
            if set(waived) != expected_waivers:
                return (
                    "not_assessed",
                    "the scoped stamp's waiver ids are not exactly the current "
                    "declared failure population.",
                )
            return ("current_scoped",
                    f"a SCOPED build gate passed on this tree ({now}); the "
                    f"FULL gate is RED over {len(waived)} declared, owned "
                    f"failure(s): {', '.join(waived)}.")
        return (
            "current",
            f"the unscoped local engineering gate passed on this tree ({now}). "
            "Its population excludes Class C, Class D and served journeys; it "
            "is not release or professional sign-off evidence.",
        )
    return ("stale",
            f"the gate last passed on {was} and this tree is {now}. Something "
            f"changed after the gate ran, so the green you are relying on is "
            f"about a tree that no longer exists.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--require-index", action="store_true",
                    help="also require the staged Git snapshot to be the exact "
                         "tree that passed; used by the pre-commit hook")
    ap.add_argument("--require-full", action="store_true",
                    help="require the unscoped form of this local engineering "
                         "population. This still does not establish corpus, "
                         "model, browser, professional or release evidence.")
    args = ap.parse_args()

    verdict, sentence = state(require_index=args.require_index)
    if verdict == "current":
        if not args.quiet:
            print(f"GATESTAMP OK  -- {sentence}")
        return 0

    # A SCOPED PASS IS A PASS FOR COMMITTING AND FOR NOTHING ELSE.
    #
    # It prints on every commit rather than staying quiet, because the whole
    # risk of this mechanism is that a red people stop seeing becomes a red
    # nobody owns. `--require-full` is how a caller says it needs the other
    # question answered, and it gets NO.
    if verdict == "current_scoped" and not args.require_full:
        print("SCOPED BUILD PASS -- FULL GATE RED")
        print(f"  {sentence}")
        print("  This permits a commit. It is not a release, not a sign-off, "
              "and no acceptance criterion derives done from it.")
        return 0

    print(f"GATESTAMP {verdict.upper()}  -- {sentence}")
    print()
    print("  Run `python tools/check.py`, or commit with --no-verify if you")
    print("  mean to: an unchecked commit is a decision, and this is only")
    print("  here so it is one somebody makes rather than one they discover.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
