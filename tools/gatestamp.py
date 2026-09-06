"""Did the gate pass on THIS tree, or on one that no longer exists?

    python tools/gatestamp.py            # is the tree the one the gate passed on?
    python tools/gatestamp.py --write    # record a pass (tools/check.py calls this)

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

WHY THIS DIGEST IS NOT `source_fingerprint`
---------------------------------------------
`nm.domain.identity.source_fingerprint` covers `nm` and `tests`, because it
answers "what code is this process running". The file that broke was in
`spec/`, which the gate checks and the server never runs -- so that digest
would not have moved, and this check would have passed on the very commit that
prompted it.

Two different questions need two different digests, and conflating them is the
defect this whole file is about. This one covers WHAT THE GATE CHECKS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._console import utf8_console  # noqa: E402

utf8_console()

#: Everything `tools/check.py` reads. Wider than `source_fingerprint`'s two
#: trees, and deliberately: layercheck, export_spec, trace and speccheck all
#: read `spec/`, and the tools themselves are what run the checks.
CHECKED = ("nm", "tests", "tools", "spec")

#: Not versioned. `.nm/` is gitignored, which is right -- a stamp is a fact
#: about ONE machine's last run, and a shared one would tell every other
#: machine its tree was green when nothing there had been checked.
STAMP = ROOT / ".nm" / "last_green.json"


def tree_digest(root: Path | None = None) -> str:
    """Path-and-content over everything the gate reads.

    Sorted, so it is reproducible; content rather than mtime, so a checkout
    that restores a file does not read as a change. `spec/prd/node_modules`
    is skipped -- it is a dependency tree nobody edits and walking it costs
    more than the rest of the repository put together.
    """
    root = root or ROOT
    h = hashlib.sha256()
    for top in CHECKED:
        base = root / top
        if not base.exists():
            # NOT ASSESSED, and it must not read as "nothing has changed".
            h.update(f"<absent:{top}>".encode())
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts or "node_modules" in p.parts:
                continue
            h.update(str(p.relative_to(root)).replace("\\", "/").encode("utf8"))
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def record(digest: str | None = None) -> str:
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    digest = digest or tree_digest()
    STAMP.write_text(json.dumps({"tree": digest}), encoding="utf8")
    return digest


def state() -> tuple[str, str]:
    """(verdict, sentence). THREE STATES, and the third is the common one.

    `not_assessed` when no gate has ever passed on this machine -- which is
    NOT "stale" and NOT "current". Reporting it as either would be the
    absent-input defect on the check built to catch a stale result.
    """
    now = tree_digest()
    if not STAMP.exists():
        return ("not_assessed",
                "no gate run has been recorded on this machine, so nothing "
                "can be said about whether this tree was checked. Run "
                "`python tools/check.py`.")
    try:
        was = json.loads(STAMP.read_text(encoding="utf8")).get("tree") or ""
    except (OSError, json.JSONDecodeError) as exc:
        return ("not_assessed",
                f"the recorded gate stamp could not be read ({type(exc).__name__}), "
                f"so nothing can be said about this tree.")
    if was == now:
        return ("current", f"the gate passed on this tree ({now}).")
    return ("stale",
            f"the gate last passed on {was} and this tree is {now}. Something "
            f"changed after the gate ran, so the green you are relying on is "
            f"about a tree that no longer exists.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="record that the gate passed on this tree")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.write:
        print(f"gate stamp recorded: {record()}")
        return 0

    verdict, sentence = state()
    if verdict == "current":
        if not args.quiet:
            print(f"GATESTAMP OK  -- {sentence}")
        return 0

    print(f"GATESTAMP {verdict.upper()}  -- {sentence}")
    print()
    print("  Run `python tools/check.py`, or commit with --no-verify if you")
    print("  mean to: an unchecked commit is a decision, and this is only")
    print("  here so it is one somebody makes rather than one they discover.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
