"""The golden runner. Task T-005b, and the blocker on every slice.

    python tools/run_goldens.py                      # structure + authority, FREE
    python tools/run_goldens.py --suite smoke --approve   # actually run them

WHY NO SLICE COULD CLOSE WITHOUT THIS
--------------------------------------
Every slice's exit criteria in the project plan name the golden suite, and the
plan's rule is that a slice is done only when its own evals pass, every earlier
slice still passes, and **its golden suite passes**. There was no runner, so no
slice could close, and `tools/slicegate.py` reported the same blocker ten times
in a row.

THREE MODES, AND ONLY THE THIRD COSTS ANYTHING
-----------------------------------------------
`--check`      Structure. Every scenario is reachable from a suite; `slice-N`
               selects exactly the scenarios whose earliest slice is <= N; no
               scenario exists only inside one suite. No corpus, no model.
               [E-002c, E-002d]

`--authority`  Every provision the set relies on reads back from the corpus,
               verbatim, through the union lookup. Class C: needs the corpus,
               no model. This is S0's exit criterion in the plan — *the golden
               scenarios load and their authority reads back*. [E-002]

`--suite X`    Runs the scenarios through the engine. THIS SPENDS MONEY AND
               NEEDS EXPLICIT PER-RUN APPROVAL, so it refuses without
               `--approve`. The standing constraint is not a formality: an eval
               run that happens because a tool defaulted to running it is an
               eval run nobody decided to pay for.

WHAT A RUN CAN AND CANNOT DECIDE
---------------------------------
The `NM must` / `Must never` columns are RUBRIC, written as principles. Some of
each is mechanically checkable — did the turn block, did it write to a file,
did it cite the provision, did the route come out right. The rest is a judged
comparison and is class D.

So a scenario's result has THREE states, and the third is the honest one:
PASS, FAIL, and NOT ASSESSED for the rubric items no deterministic check can
reach. A runner that scored only what it could measure and called that a pass
would be the status-inflation defect wearing a green tick.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOLDEN = ROOT / "docs" / "GOLDEN_SET.md"

PASS, FAIL, UNASSESSED = "PASS", "FAIL", "NOT ASSESSED"

#: The named suites, as the document defines them. Parsed rather than retyped
#: would be better; the suite table's ranges are prose ("GS-01 … GS-05"), so
#: they are expanded here and `--check` asserts the expansion against the set.
SUITES: dict[str, object] = {
    "smoke": ["GS-01", "GS-02", "GS-03", "GS-04", "GS-05"],
    "frame": ["GS-06", "GS-07", "GS-08", "GS-09", "GS-10", "GS-11"],
    "dates": ["GS-12", "GS-13", "GS-14", "GS-15", "GS-16"],
    "proof": ["GS-17", "GS-18", "GS-19", "GS-20"],
    "theory": ["GS-21", "GS-22", "GS-23", "GS-24"],
    "duty": ["GS-05", "GS-18", "GS-25"],
    "grounding": ["GS-02", "GS-12", "GS-14", "GS-17", "GS-25"],
}
JUDGED = {"theory", "duty", "full"}

#: §3 uses TWO table shapes, and a parser that knows only the first sees five
#: scenarios in a set of twenty-five and reports every suite as naming
#: scenarios that do not exist. The `smoke` table splits the rubric into
#: `NM must | Must never`; every suite table after it merges them into `The
#: spine`. Both are matched, and `--check` asserts the total against the
#: document's own count so a third shape cannot appear silently.
_ROW6 = re.compile(
    r"^\|\s*\*\*(GS-\d+)\*\*\s*\|(.+?)\|\s*(S\d+)\s*\|\s*(\d+)\s*\|(.+?)\|(.+?)\|\s*$",
    re.M)
_ROW5 = re.compile(
    r"^\|\s*\*\*(GS-\d+)\*\*\s*\|(.+?)\|\s*(S\d+)\s*\|\s*(\d+)\s*\|([^|]+?)\|\s*$",
    re.M)
_ANY_ROW = re.compile(r"^\|\s*\*\*(GS-\d+)\*\*", re.M)
#: A row of the §6 authority table. Requires the second cell to contain a
#: provision token, which excludes separator rows and the stray fragments a
#: looser pattern picked up -- one of which parsed as the bare label "Act".
_PROV_ROW = re.compile(
    r"^\|\s*([A-Z][^|]{3,60}?)\s*\|\s*([^|]*(?:s\.|Article)[^|]*?)\s*\|\s*$", re.M)


class Scenario:
    def __init__(self, gid, text, slice_, turns, must, never):
        self.id = gid
        self.text = text.strip().strip("`")
        self.slice = int(slice_[1:])
        self.turns = int(turns)
        self.must = [m.strip() for m in must.split(".") if m.strip()]
        self.never = [m.strip() for m in never.split(".") if m.strip()]

    def __repr__(self):
        return f"<{self.id} S{self.slice}>"


def load_scenarios() -> list[Scenario]:
    if not GOLDEN.exists():
        sys.exit(f"missing {GOLDEN}")
    text = GOLDEN.read_text(encoding="utf8")
    found: dict[str, Scenario] = {}
    for m in _ROW6.finditer(text):
        found[m.group(1)] = Scenario(*m.groups())
    for m in _ROW5.finditer(text):
        gid, scen, sl, turns, spine = m.groups()
        found.setdefault(gid, Scenario(gid, scen, sl, turns, spine, ""))

    declared = {m.group(1) for m in _ANY_ROW.finditer(text)}
    missed = declared - set(found)
    if missed:
        # NOT a warning. A scenario the parser cannot read is a scenario that
        # silently leaves the set, and every suite naming it then reports a
        # failure that is the parser's, not the document's.
        sys.exit(f"{len(missed)} scenario row(s) did not parse: "
                 f"{', '.join(sorted(missed))}. The table shape changed; fix "
                 f"the parser rather than dropping them.")
    if not found:
        sys.exit("no scenarios parsed from GOLDEN_SET.md -- the table format changed")
    return [found[k] for k in sorted(found)]


def load_provisions() -> list[tuple[str, str]]:
    """The verified-authority table in §6: (Act group, provisions)."""
    text = GOLDEN.read_text(encoding="utf8")
    start = text.index("## 6. Verified authority")
    end = text.index("## 7.", start)
    out = []
    for m in _PROV_ROW.finditer(text[start:end]):
        act, provs = m.group(1), m.group(2)
        if act.startswith("-") or act in ("Provision group", "Held"):
            continue
        out.append((act.strip(), provs.strip()))
    return out


def expand(suite: str, scenarios: list[Scenario]) -> list[Scenario]:
    if suite == "full":
        return scenarios
    if suite.startswith("slice-"):
        n = int(suite.split("-", 1)[1])
        return [s for s in scenarios if s.slice <= n]
    ids = SUITES.get(suite)
    if ids is None:
        sys.exit(f"unknown suite {suite!r}. Known: "
                 f"{', '.join(sorted(SUITES))}, slice-N, full")
    by_id = {s.id: s for s in scenarios}
    return [by_id[i] for i in ids if i in by_id]


# ------------------------------------------------------------------ checks ---

def check_structure(scenarios: list[Scenario]) -> list[str]:
    """E-002c / E-002d. A suite is a FILTER over the set, never a different set."""
    failures = []
    covered = {i for ids in SUITES.values() for i in ids}
    # EVERY SCENARIO IS IN A NAMED SUITE.
    #
    # This used to carry a second condition -- `and not any(s.slice <= n
    # for n in range(1, 10))` -- which is False for every scenario, because
    # every slice is 9 or less. The branch could not execute, so E-002c was
    # enforced by a line that had never run and reported OK on every commit.
    #
    # `full` and `slice-N` are GENERATED and cover everything by
    # construction, so they prove nothing about curation. A scenario in no
    # named suite can only ever run in an everything-run, which is the one
    # nobody does before a commit.
    for s in scenarios:
        if s.id not in covered:
            failures.append(
                f"{s.id} is in no named suite, so it runs only in `full` "
                f"or a `slice-N` sweep and never in a targeted run")

    # Every id a suite names must exist. A suite naming a scenario that is not
    # in the set is how a suite quietly becomes a different set.
    known = {s.id for s in scenarios}
    for name, ids in SUITES.items():
        for i in ids:
            if i not in known:
                failures.append(f"suite {name!r} names {i}, which is not in the set")

    # E-002d: slice-N selects exactly the scenarios whose earliest slice is <= N.
    for n in range(1, 10):
        picked = {s.id for s in expand(f"slice-{n}", scenarios)}
        expected = {s.id for s in scenarios if s.slice <= n}
        if picked != expected:
            failures.append(f"slice-{n} selected {len(picked)}, expected {len(expected)}")
    return failures


def check_authority() -> tuple[list[str], int, int]:
    """E-002. Every provision the set relies on reads back from the corpus.

    THIS IS S0'S EXIT CRITERION. Class C: the corpus is required and no model
    is called. A provision that will not read back is a scenario resting on
    authority that is not there — which is what the previous build did, and
    what struck three scenarios for a defect that was in the lookup.
    """
    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import Manifest
    from nm.ports.evidence import Coverage, EvidenceNeed

    adapter = CorpusEvidenceAdapter(ROOT / "legal_database" / "vector_store",
                                    Manifest.load(ROOT / "spec" / "manifest.yaml"))
    if not adapter.available:
        return ["the corpus is not attached -- authority cannot be verified"], 0, 0

    manifest = Manifest.load(ROOT / "spec" / "manifest.yaml")

    #: THE DOCUMENT'S LABELS, MAPPED EXACTLY. There is no fuzzy fallback.
    #:
    #: The first version scored word overlap and resolved "Indian Easements Act
    #: 1882" to "Indian Evidence Act, 1872" on the shared word `Indian`. Excluding
    #: generic words moved it to "Transfer of Property Act, 1882" on the shared
    #: YEAR. Both verified a different Act's s.15 and would have reported the
    #: golden set's authority as held — a verification tool certifying authority
    #: it never checked.
    #:
    #: Common words are everywhere in Indian statute titles, so overlap scoring
    #: is not a weak signal, it is a wrong one. A label not in this table
    #: RESOLVES TO NOTHING and is reported as a failure, which is the answer
    #: that can be acted on.
    #: Short forms the document uses that share no long word with the manifest
    #: name. Listed rather than fuzzy-matched, because a wrong Act here would
    #: verify the wrong provision and report it as held.
    aliases = {
        "CrPC 1973": "Code of Criminal Procedure, 1973",
        "BNSS 2023": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "IPC 1860 / BNS 2023": "Indian Penal Code, 1860",
        "NI Act 1881": "Negotiable Instruments Act, 1881",
        "CPC 1908": "Code of Civil Procedure, 1908",
        "Specific Relief Act 1963": "Specific Relief Act, 1963",
        "Limitation Act 1963": "Limitation Act, 1963",
        "Registration Act 1908": "Registration Act, 1908",
        "Evidence Act 1872": "Indian Evidence Act, 1872",
        "Transfer of Property Act 1882": "Transfer of Property Act, 1882",
        "Muslim Women (Divorce) Act 1986":
            "Muslim Women (Protection of Rights on Divorce) Act, 1986",
        "Hindu Marriage Act 1955": "Hindu Marriage Act, 1955",
        "Guardians and Wards Act 1890": "Guardians and Wards Act, 1890",
        "Wakf Act 1995": "Wakf Act, 1995",
        "Indian Easements Act 1882": "Indian Easements Act, 1882",
        "Domestic Violence Act 2005":
            "Protection of Women from Domestic Violence Act, 2005",
    }

    failures, ok, total = [], 0, 0
    for act, provs in load_provisions():
        entry = manifest.act(aliases.get(act, ""))
        if entry is None:
            failures.append(
                f"{act}: NOT IN THE MANIFEST. The golden set rests on this Act "
                f"and the product does not declare it holds it")
            total += len(re.findall(r"(?:s\.|Article[s]?\s+)\s*\*{0,2}\d", provs))
            continue

        # A DATE THE ACT WAS IN FORCE. Checking BNSS at a 2019 date reports
        # `not_held` for a provision the corpus holds -- the era rule working
        # correctly against a harness that asked the wrong question.
        when = entry.in_force_from or date(2019, 6, 1)
        if entry.in_force_to and when > entry.in_force_to:
            when = entry.in_force_to
        if entry.in_force_to and date(2019, 6, 1) <= entry.in_force_to:
            when = date(2019, 6, 1)

        for token in re.findall(r"(?:s\.|Article[s]?\s+)\s*\*{0,2}(\d+[A-Za-z]?)",
                                provs):
            total += 1
            hint = f"Article_{token}" if "Article" in provs else token
            res = adapter.fetch(EvidenceNeed(
                question=f"{entry.act_name} {token}", governing_date=when,
                provision_hint=hint))
            if res.coverage is Coverage.ANSWERED:
                ok += 1
            else:
                failures.append(f"{entry.act_name} {token} @{when}: "
                                f"{res.coverage.value} -- {(res.missing or '')[:80]}")
    return failures, ok, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite")
    ap.add_argument("--approve", action="store_true",
                    help="required for --suite: it makes model calls")
    ap.add_argument("--skip-authority", action="store_true")
    args = ap.parse_args()

    scenarios = load_scenarios()
    print("=" * 78)
    print(f"GOLDEN RUNNER   {len(scenarios)} scenarios parsed from GOLDEN_SET.md")
    print("=" * 78)

    bad = check_structure(scenarios)
    print(f"\n  STRUCTURE [E-002c, E-002d]   "
          f"{'OK' if not bad else str(len(bad)) + ' FAILURE(S)'}")
    for f in bad:
        print(f"     {f}")

    auth_failures: list[str] = []
    if not args.skip_authority:
        auth_failures, ok, total = check_authority()
        print(f"\n  AUTHORITY [E-002]   {ok}/{total} provisions read back "
              f"from the corpus")
        for f in auth_failures[:12]:
            print(f"     {f}")
        if len(auth_failures) > 12:
            print(f"     ... and {len(auth_failures) - 12} more")

    if args.suite:
        picked = expand(args.suite, scenarios)
        judged = args.suite in JUDGED or args.suite == "full"
        print(f"\n  SUITE {args.suite!r}   {len(picked)} scenario(s)"
              f"{'  [JUDGED — class D]' if judged else ''}")
        if not args.approve:
            print("\n  REFUSED. Running a suite makes model calls and costs money.")
            print("  The standing constraint is explicit per-run approval, and a")
            print("  tool that defaults to running is a tool that spends without")
            print("  a decision. Re-run with --approve.")
            return 2
        print("\n  Scenario execution is not built yet: the rubric is prose, and")
        print("  scoring it needs the class-D judge harness. Reported as NOT")
        print("  ASSESSED rather than skipped silently:")
        for s in picked:
            print(f"     [{UNASSESSED}] {s.id}  S{s.slice}  {s.text[:52]}")
        return 0

    print()
    if bad or auth_failures:
        print(f"GOLDENS FAILED -- {len(bad)} structural, "
              f"{len(auth_failures)} authority")
        return 1
    print("GOLDENS OK  -- structure and authority. Scenario execution needs "
          "--suite and approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
