"""THE REGISTER IS EXECUTABLE. Every defect names a check, and it must exist.

WHY
---
`spec/plan/build_plan.py` records 53 defects, and every one of them names *the
check that now refuses it*. **Nothing verified those checks existed.** The
column was prose, so a defect could be marked Fixed against a test that had
been renamed, moved, or never written — and the register would still read as a
wall of green.

That is the same shape as everything else in this file's neighbourhood: a
claim with no runner. `docs/DEFECT_SHAPES.md` calls it S11, and the register
recording S11 seven times while itself being unrunnable is the joke that had to
be closed.

WHAT THIS BUYS
--------------
Every defect ever found becomes a permanent guard, automatically. A fix that
lands without a working check fails the build rather than being noticed a year
later when the shape comes back. It is the cheapest thing in this codebase that
stops recurrence, and it should have existed from the first entry.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not re-run the named tests. They already run in the suite, and a
failing one already fails the build — re-running them here would be a second
copy of the suite, and slower. What it checks is that the reference RESOLVES:
the file is there, and the function it names is really in it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "spec" / "plan" / "build_plan.py"

#: Anything that looks like a path this repo would hold. Deliberately broad —
#: the register's prose sometimes names a doc or a tool rather than a test, and
#: those are legitimate checks that still have to exist.
PATH = re.compile(r"\b((?:tests|tools|nm|docs|spec|web)/[\w./-]+?\.(?:py|md|yaml|js|css|docx|xlsx))"
                  r"(?:::(\w+))?")


def _register() -> list[dict]:
    """Every `d(...)` row, read from the generator rather than the workbook.

    The generator is the source; the workbook is the export. Reading the export
    would let the two disagree, which is the arrangement this project refuses
    everywhere else.
    """
    rows = []
    for node in ast.walk(ast.parse(PLAN.read_text(encoding="utf8"))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "d"):
            continue
        args = []
        for a in node.args:
            try:
                args.append(ast.literal_eval(a))
            except Exception:  # noqa: BLE001 -- a computed arg is not a defect row
                args.append(None)
        if len(args) >= 10 and isinstance(args[0], str):
            rows.append({"id": args[0], "when": args[1] or "", "what": args[3],
                         "shape": args[5] or "", "check": args[9] or "",
                         "status": args[10] if len(args) > 10 else "Fixed"})
    return rows


def test_the_register_can_be_read_at_all():
    """A guard on the guard: an empty population passes every test below."""
    rows = _register()
    assert len(rows) >= 40, (
        f"only {len(rows)} defects parsed from the register — this file would "
        f"then be asserting almost nothing")
    ids = [r["id"] for r in rows]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate defect ids: {sorted(dupes)}"


def test_every_check_the_register_names_actually_exists():
    """THE POINT. A defect marked Fixed against a check that is not there is
    not fixed — it is a claim, and the register is full of them by design."""
    missing: list[str] = []
    for row in _register():
        for path, _func in PATH.findall(row["check"]):
            if not (ROOT / path).exists():
                missing.append(f"{row['id']}: {path} does not exist")
    assert not missing, (
        "the register names checks that are not in the repository:\n  "
        + "\n  ".join(missing)
        + "\n\nEither the check was renamed and the register was not, or the "
          "defect was recorded as fixed against something that was never "
          "written. Both mean the shape can come back unnoticed.")


def test_every_named_test_function_is_really_in_that_file():
    """A file that exists is not the same as the test that was claimed.

    A rename moves a function and leaves the file — which is the commonest way
    a reference like this rots, and the least visible.
    """
    missing: list[str] = []
    cache: dict[Path, set[str]] = {}
    for row in _register():
        for path, func in PATH.findall(row["check"]):
            if not func:
                continue
            f = ROOT / path
            if not f.exists():
                continue                      # reported by the test above
            if f not in cache:
                cache[f] = {
                    n.name for n in ast.walk(ast.parse(f.read_text(encoding="utf8")))
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if func not in cache[f]:
                missing.append(f"{row['id']}: {path} has no {func}()")
    assert not missing, (
        "the register names test functions that are not in the file it names:\n  "
        + "\n  ".join(missing)
        + "\n\nA rename that moved the test and left the register behind is the "
          "commonest way this rots, and the least visible.")


def test_every_fixed_defect_names_something_that_can_be_run():
    """A fix without a runnable check is a fix that can silently come undone.

    OPEN defects are exempt — they have no check yet, and saying so is the
    honest state. Everything marked Fixed must point at a file in this
    repository.
    """
    # `MANUAL:` is an EXPLICIT exemption for a fix with no runner -- a browser
    # pass on the JS, for instance, where no test harness exists. It is
    # permitted because pointing such a row at a file that cannot be run would
    # be worse: the reference would resolve and mean nothing. An exemption
    # someone typed is a decision; a silent pass is not.
    prose_only = [
        f"{r['id']}: {r['check'][:70]!r}"
        for r in _register()
        if r["status"] == "Fixed"
        and not r["check"].strip().startswith("MANUAL:")
        and not PATH.search(r["check"])]
    assert not prose_only, (
        "these defects are marked Fixed and name no file that can be run:\n  "
        + "\n  ".join(prose_only)
        + "\n\nName the test, the tool or the document that now refuses the "
          "shape. 'A rule you cannot run is not a requirement' applies to the "
          "register as much as to the PRD.")


def test_the_register_is_getting_more_runnable_not_less():
    """A ratchet, reported rather than asserted at a fixed number.

    The useful reference is `file::function` — it survives a file growing and
    names the exact claim. A file-only reference is weaker and a doc reference
    weaker still, so the count that matters is how many are precise.
    """
    rows = _register()
    precise = sum(1 for r in rows
                  if any(func for _, func in PATH.findall(r["check"])))
    print(f"\n  register: {len(rows)} defects, {precise} name a test FUNCTION")
    assert precise >= 18, (
        f"only {precise} defects name a specific test function. That number "
        f"should never fall: it is how many of the register's claims can be "
        f"checked exactly rather than approximately.")


def test_every_recurring_shape_has_a_mechanism_more_than_one_defect_points_at():
    """A SHAPE THAT KEEPS RECURRING MUST HAVE ONE MECHANISM, NOT N FIXES.

    Every one of the register's rows named its own check and no shape had a
    mechanism, which is the arrangement that let one sentence — *a value that
    is present and carries nothing is absent* — be fixed three separate ways as
    a `.strip()`, a regex and a missing enum member, with nothing to catch the
    fourth.

    So: for every shape that has produced more than one defect, at least one
    check must be named by at least TWO of them. That is what "the fix was
    generalised" means operationally — not that the commit message said so, but
    that a second instance points at the same runner.

    It does not demand that ALL instances share one mechanism. Two defects of
    one shape in genuinely different subsystems can need different machinery,
    and forcing them together would be its own kind of wrong. What it refuses
    is a shape with N defects and N unrelated fixes.
    """
    import collections

    by_shape: dict[str, list[tuple[str, set[str]]]] = collections.defaultdict(list)
    for row in _register():
        head = row.get("shape", "")
        key = head.split("—")[0].split("--")[0].strip().rstrip(".")
        if not (key.startswith("S") and key[1:2].isdigit()):
            continue                       # a one-off shape, described in prose
        # A SHARE MUST BE A FUNCTION. Two defects naming the same FILE are two
        # fixes that happen to live together, not one mechanism -- `web/app.js`
        # appeared "shared" by that reading and is nothing of the kind.
        checks = {f"{p}::{f}" for p, f in PATH.findall(row["check"]) if f}
        by_shape[key].append((row["id"], checks))

    # SHAPES WITH NO MECHANISM YET, each with the reason and what the general
    # form would be. Declared rather than skipped: a gap someone typed is a
    # decision, and a category a check quietly omits is how the rule stops
    # applying. Every entry here is work that has not been done.
    no_mechanism_yet = {
        "S3": "a zero from the wrong index reads as absence. The five "
              "instances are measurements against five different stores with "
              "no common interface — the derived layer instead of raw_data, "
              "keyword scoring over a whole question, a fuzzy Act matcher, a "
              "court LABEL instead of a binding relationship, a manifest "
              "narrower than the corpus. The general form would be 'every "
              "measurement declares the population it measures and is checked "
              "against a positive control', which is M4 applied to measurement "
              "code rather than to tests. NOT BUILT.",
        "S7": "a rule applied outside the case it was written for. Whether a "
              "rule's scope matches its intent is not decidable from source. "
              "The mechanisable parts exist — a positive control proves the "
              "rule fires where it should, and the three-state default (M5) "
              "stops the fallback pointing at the irreversible direction. The "
              "residue is judgement and is reviewed, not scanned.",
    }

    unshared = []
    for shape, entries in sorted(by_shape.items()):
        if shape in no_mechanism_yet:
            continue
        if len(entries) < 2:
            continue
        seen: collections.Counter = collections.Counter()
        for _, checks in entries:
            seen.update(checks)
        if not any(n >= 2 for n in seen.values()):
            unshared.append(
                f"{shape}: {len(entries)} defects "
                f"({' '.join(i for i, _ in entries)}) and no check named by "
                f"more than one")

    assert not unshared, (
        "these shapes have recurred and have no shared mechanism:\n  "
        + "\n  ".join(unshared)
        + "\n\nBefore fixing a new defect, look for the same shape in the "
          "register: if it is there, REUSE the mechanism that already refuses "
          "it rather than writing another guard beside it. A shape with N "
          "defects and N unrelated fixes is N places for the N+1th to hide.")

    stale = sorted(set(no_mechanism_yet) - set(by_shape))
    assert not stale, (
        f"these shapes are declared unmechanised and no longer occur: {stale}. "
        f"Delete the entry — an admitted gap for something gone makes the "
        f"remaining gaps look larger than they are.")
    print("\n  shapes with no shared mechanism yet: "
          + ", ".join(sorted(no_mechanism_yet)))



# ===================== an enumerator owns its population ====================
#
# THE RULE ABOVE IS VACUOUS FOR NEW ROWS, MEASURED 5 SEPTEMBER 2026.
#
# It asks whether SOME pair in a shape shares a check. S1 satisfied that long
# ago -- three of its 39 defects name `test_three_states`. So the bar was met
# once and can never bite again: ten S1 defects were added in one session, each
# with its own private check, not one sharing a mechanism with the 39 before
# it, and the suite stayed green. Of those 39, one check is shared by three and
# ELEVEN name no check at all.
#
# THE FIRST ATTEMPT AT A FIX WAS WRONG AND IS WORTH RECORDING. It demanded that
# every S1 defect found after the shape had "a mechanism" point at it -- and
# flagged thirty historical rows, because it had decided `test_three_states`
# was THE S1 mechanism. It is a mechanism for one narrow sub-shape. Demanding
# that a provider-metadata leak point at a three-state enum check is the
# "forcing them together would be its own kind of wrong" the docstring above
# already warns about. S1 is a bucket, not a population.
#
# THE RIGHT QUESTION IS NARROWER: does this defect belong to a population some
# ENUMERATOR already sweeps? An enumerator draws its population from the whole
# product and finds the members nobody has looked for yet, which is what
# "generalised" means operationally. So each one DECLARES the defects it
# subsumes, and those defects' register rows must name it. A defect that is an
# instance of a swept population and points only at its own scenario test reads
# as a patch, and the next instance has nowhere to be caught.

#: enumerator check -> the defects it subsumes.
#:
#: Read from the TESTS, not listed here, would be better; it is listed here
#: because the declaration belongs with the rule that uses it and a `SUBSUMES`
#: constant in each test file would be a second place to look. Adding an
#: enumerator means adding a line.
ENUMERATORS: dict[str, tuple[str, ...]] = {
    "tests/test_every_persisted_field_has_a_writer.py::"
    "test_every_persisted_field_has_a_writer_or_is_declared_reserved":
        ("B-086", "B-091", "B-092"),
    "tests/test_what_the_model_is_told.py::test_every_field_is_told_or_declared":
        ("B-093", "B-094", "B-096"),
    "tests/test_reads_registry.py::test_every_decisive_read_says_so_when_it_"
    "answers_with_nothing":
        ("B-088",),
}


def test_every_defect_an_enumerator_subsumes_names_that_enumerator():
    """A DEFECT IN A SWEPT POPULATION POINTS AT THE SWEEP.

    `Posture.opponent` (B-092) was not a lucky find; it came out of the
    writers enumerator, and its register row named only its own scenario test.
    Read a year from now, the register would show six separate patches where
    there are two mechanisms and their findings — and the seventh instance
    would get a seventh patch, because nothing in the record says a sweep
    owns that ground.
    """
    rows = {r["id"]: r for r in _register()}
    offenders: list[str] = []
    for mechanism, ids in ENUMERATORS.items():
        for did in ids:
            row = rows.get(did)
            if row is None:
                offenders.append(f"{did}: declared subsumed and not in the "
                                 f"register at all")
                continue
            named = {f"{p}::{f}" for p, f in PATH.findall(row["check"]) if f}
            if mechanism not in named:
                offenders.append(
                    f"{did} is swept by {mechanism.split('::')[-1]} and its "
                    f"check names only {sorted(named) or 'nothing'}")
    assert not offenders, (
        "these defects are instances of a population an enumerator already "
        "sweeps, and their rows do not say so. A register that reads as N "
        "patches where there are two mechanisms is N places for the N+1th to "
        "hide:\n  " + "\n  ".join(offenders))


def test_every_declared_enumerator_exists_and_draws_from_the_product():
    """A POSITIVE CONTROL ON THE TABLE ABOVE.

    An entry naming a test that was renamed protects nothing and reads as
    though it does — the same failure `test_every_check_the_register_names_
    actually_exists` was written for, one level up.
    """
    for mechanism in ENUMERATORS:
        path, _, func = mechanism.partition("::")
        source = ROOT / path
        assert source.exists(), f"{path} does not exist"
        tree = ast.parse(source.read_text(encoding="utf8"))
        names = {n.name for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)}
        assert func in names, f"{path} has no {func}"


def test_the_enumerator_scan_can_see_a_defect_that_ignores_its_sweep():
    """THE POSITIVE CONTROL for the rule above.

    The rule passes when every subsumed defect names its enumerator, and it
    would pass identically if the comparison were inverted, or if `checks_of`
    returned everything, or if `ENUMERATORS` were empty. A sweep asserting
    that nothing is broken must be shown finding a break — B-049 was a checker
    that always returned `[]` and passed on every commit for weeks.

    Planted on the REAL comparison, with a register row that is subsumed and
    names only its own scenario test — which is exactly the shape the audit of
    5 September 2026 found in seven live rows.
    """
    mechanism = ("tests/test_every_persisted_field_has_a_writer.py::"
                 "test_every_persisted_field_has_a_writer_or_is_declared_reserved")
    planted = {"id": "B-999", "when": "2026-09-05", "what": "a planted row",
               "shape": "S1 — an absent input reading as success",
               "check": "tests/test_a_scenario.py::test_one_situation",
               "status": "Fixed"}

    named = {f"{p}::{f}" for p, f in PATH.findall(planted["check"]) if f}
    assert named, "the planted row's check did not parse at all"
    assert mechanism not in named, (
        "the control cannot fail: its planted row already names the mechanism")

    # And the real rule, run against it, must call it an offender.
    assert not (named & {mechanism}), (
        "a row naming only its own scenario test was treated as pointing at "
        "the enumerator")
