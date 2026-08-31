"""The counterexample tests for the tooling itself.

Written BEFORE trusting either tool, because the rule this project runs on is
that a check which has never rejected anything is an unexercised claim, not
evidence of health. These tests build the exact defect each tool exists to
catch, and assert the tool rejects it.

If any test here starts passing for the wrong reason -- an import error, a
missing file -- it proves nothing. Each therefore asserts on the tool's own
reported reason, not merely on a non-zero exit code.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), *args],
        capture_output=True, text=True, cwd=str(cwd or ROOT), encoding="utf8",
    )


# --------------------------------------------------------------------------
# layercheck
# --------------------------------------------------------------------------

def test_layercheck_passes_on_the_real_tree():
    """Baseline: the tool must be green before a counterexample means anything."""
    r = run("layercheck.py")
    assert r.returncode == 0, f"layercheck already failing:\n{r.stdout}"
    assert "LAYERCHECK OK" in r.stdout


def test_layercheck_rejects_core_importing_an_adapter(tmp_path):
    """THE COUNTEREXAMPLE: the import that quietly destroys the class-A cadence."""
    offender = ROOT / "nm" / "core" / "_layercheck_probe.py"
    offender.write_text(
        "from nm.adapters import anything  # noqa: F401\n", encoding="utf8")
    try:
        r = run("layercheck.py")
        assert r.returncode == 1, "layercheck did NOT reject core -> adapters"
        assert "may not import nm.adapters" in r.stdout
        assert "_layercheck_probe.py" in r.stdout
    finally:
        offender.unlink()


def test_layercheck_rejects_a_provider_client_in_core():
    """THE COUNTEREXAMPLE: a model client reachable from the pure core."""
    offender = ROOT / "nm" / "core" / "_provider_probe.py"
    offender.write_text("import openai  # noqa: F401\n", encoding="utf8")
    try:
        r = run("layercheck.py")
        assert r.returncode == 1, "layercheck did NOT reject openai in core"
        assert "'openai'" in r.stdout
        assert "belong in nm.adapters" in r.stdout
    finally:
        offender.unlink()


def test_layercheck_allows_core_importing_ports():
    """The rule must permit what it is supposed to permit."""
    ok = ROOT / "nm" / "core" / "_allowed_probe.py"
    ok.write_text("from nm.ports import model  # noqa: F401\n", encoding="utf8")
    try:
        r = run("layercheck.py")
        assert r.returncode == 0, f"layercheck wrongly rejected core -> ports:\n{r.stdout}"
    finally:
        ok.unlink()


# --------------------------------------------------------------------------
# trace
# --------------------------------------------------------------------------

def test_trace_passes_on_the_real_spec():
    """Trace must pass on a CURRENT spec.

    The first version of this test ran trace against whatever happened to be on
    disk, and failed twice -- not because trace was wrong, but because a
    generator had been edited and the spec not yet regenerated. A test that
    asserts on live repo state it does not control is testing the author's
    editing sequence rather than the tool. So it establishes its own
    precondition first, then asserts.
    """
    regen = run("export_spec.py")
    assert regen.returncode == 0, f"export_spec failed:\n{regen.stdout}{regen.stderr}"
    r = run("trace.py", "--skip-regen")
    assert r.returncode == 0, f"trace failing on a freshly generated spec:\n{r.stdout}"
    assert "TRACE OK" in r.stdout


def test_trace_rejects_an_implements_naming_no_feature():
    """T2 COUNTEREXAMPLE: code claiming a feature id the spec does not contain."""
    offender = ROOT / "nm" / "core" / "_trace_probe.py"
    offender.write_text(textwrap.dedent("""
        from nm.domain.traceability import implements

        @implements("ZZ-99")
        def not_a_real_feature():
            return None
    """).lstrip(), encoding="utf8")
    try:
        r = run("trace.py", "--skip-regen")
        assert r.returncode == 1, "trace did NOT reject an unknown feature id"
        assert "[T2]" in r.stdout
        assert "ZZ-99" in r.stdout
    finally:
        offender.unlink()


def test_trace_rejects_a_built_claim_with_no_code(tmp_path):
    """T3 COUNTEREXAMPLE: status inflation -- the defect that ended the last build.

    A feature is marked `built` while nothing anywhere declares it implemented.
    217 stories were reported done on exactly this basis.
    """
    spec = ROOT / "spec" / "features.yaml"
    backup = tmp_path / "features.yaml"
    shutil.copy2(spec, backup)
    try:
        import yaml
        doc = yaml.safe_load(spec.read_text(encoding="utf8"))

        # PLANT the feature rather than flipping one that is already here.
        # Flipping whichever `decided` feature came first stopped working the
        # moment enough of them acquired an `@implements`: T3 then had nothing
        # to object to, and the test failed for being out of date rather than
        # for finding a defect.
        #
        # A counterexample the repo has to supply is one the repo can stop
        # supplying, and it stops supplying it exactly as the build gets
        # healthier -- so the check goes quiet when it is most needed.
        doc["features"].append({
            "id": "ZZ-T3", "title": "a planted claim with no code",
            "phase": "Z", "slice": "S1", "status": "built",
            "does": [], "never": [], "produces": [], "eval_prose": [],
            "eval_ids": [], "counterexample": "", "tasks": [],
        })
        spec.write_text(yaml.safe_dump(doc, sort_keys=False,
                                       allow_unicode=True), encoding="utf8")

        r = run("trace.py", "--skip-regen")
        assert r.returncode == 1, "trace did NOT reject a built claim with no code"
        assert "[T3]" in r.stdout
        assert "no @implements anywhere" in r.stdout
    finally:
        shutil.copy2(backup, spec)


def test_trace_rejects_a_tested_claim_whose_evals_never_ran(tmp_path):
    """T4 COUNTEREXAMPLE: `tested` asserted with no eval run behind it."""
    spec = ROOT / "spec" / "features.yaml"
    backup = tmp_path / "features.yaml"
    shutil.copy2(spec, backup)
    probe = ROOT / "nm" / "core" / "_tested_probe.py"
    try:
        text = spec.read_text(encoding="utf8")
        import json

        import yaml
        doc = yaml.safe_load(text)

        # PLANT IT. The first draft took "the first feature with eval ids" and
        # broke the moment real evals started running; the second draft
        # searched for a feature whose evals had NOT run, and broke the moment
        # every feature had one -- which is a good thing to have happened and
        # still a broken test. Both were the repo supplying the counterexample.
        #
        # A planted eval id nothing has ever run is the condition under test,
        # stated rather than found.
        del json
        target_id = "ZZ-T4"
        doc["features"].append({
            "id": target_id, "title": "a planted tested claim",
            "phase": "Z", "slice": "S1", "status": "tested",
            "does": [], "never": [], "produces": [], "eval_prose": [],
            "eval_ids": ["E-ZZZ-never-run"], "counterexample": "", "tasks": [],
        })
        spec.write_text(
            "# temporary probe\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf8")

        # Satisfy T3 so the failure we observe is unambiguously T4.
        probe.write_text(textwrap.dedent(f"""
            from nm.domain.traceability import implements

            @implements({target_id!r})
            def probe():
                return None
        """).lstrip(), encoding="utf8")

        r = run("trace.py", "--skip-regen")
        assert r.returncode == 1, "trace did NOT reject a tested claim with no eval run"
        assert "[T4]" in r.stdout
        assert "has ever run" in r.stdout
    finally:
        shutil.copy2(backup, spec)
        if probe.exists():
            probe.unlink()


def test_trace_detects_a_stale_spec(tmp_path):
    """T1 COUNTEREXAMPLE: the generator moved and the spec was not regenerated."""
    spec = ROOT / "spec" / "features.yaml"
    backup = tmp_path / "features.yaml"
    shutil.copy2(spec, backup)
    try:
        spec.write_text(spec.read_text(encoding="utf8").replace(
            "  status: decided\n", "  status: decided  # tampered\n", 1), encoding="utf8")
        r = run("trace.py")  # full run, regeneration enabled
        assert r.returncode == 1, "trace did NOT detect a stale spec"
        assert "[T1]" in r.stdout
        assert "was stale" in r.stdout
    finally:
        shutil.copy2(backup, spec)


# ================== the mutation anchors, checked in seconds ================


def _stale_anchors(mutations) -> list[str]:
    """The scan, ONE COPY, so the control below exercises what the test does.

    A control that reimplements the check proves the reimplementation works.
    """
    import tools.mutate as mutate

    stale = []
    for label, rel, old, *_ in mutations:
        path = mutate.ROOT / rel
        if not path.exists():
            stale.append(f"{label}: {rel} does not exist")
            continue
        # EXACTLY ONCE. Presence is not enough: `replace(old, new, 1)` takes
        # the first match, so an anchor matching two lines mutates whichever
        # comes first -- which need not be the one the named test guards.
        found = path.read_text(encoding="utf8").count(old)
        if found == 0:
            stale.append(f"{label}: anchor not found in {rel}")
        elif found > 1:
            stale.append(f"{label}: anchor matches {found} places in {rel}")
    return stale


def test_every_mutation_anchor_still_matches_the_source():
    """A MUTATION WHOSE ANCHOR NO LONGER MATCHES NEVER RUNS.

    `tools/mutate.py` is right to score a missing anchor as SURVIVED — a
    mutation that did not execute must never read as one that was caught. But
    that verdict costs a fifteen-minute run to reach, and it arrives labelled
    as a weak test rather than as what it is: a rename that was not swept.

    It happened the day this was written. `_derive` gained a `facts` argument,
    two call sites were updated, and the copy of one of them living inside a
    mutation anchor was not. Ruff, pyflakes and pylint E0601/E0606 were all
    clean — CLAUDE.md §6 exactly: a signature change is a rename and static
    checks do not catch it.

    So the same fact is asserted here, in under a second, on every commit.
    """
    import tools.mutate as mutate

    stale = _stale_anchors(mutate.MUTATIONS)
    assert not stale, (
        "these mutations cannot run, so the tests they name are unproven:\n  "
        + "\n  ".join(stale)
        + "\n\nThe anchor is a copy of a line of source. When that line moves, "
          "the copy has to move with it — sweeping a rename includes this file.")


def test_the_anchor_check_can_see_a_stale_anchor():
    """THE POSITIVE CONTROL. A scan over anchors that all happen to match
    proves nothing about the scan; a checker that always returns [] satisfies
    the assertion above identically.

    So a mutation with an anchor the source does not contain is planted, and
    the SAME function has to report it.
    """
    planted = [("a mutation whose line no longer exists", "nm/core/turn.py",
                "    def _a_method_no_rename_ever_produced(self):",
                "x", "some_test", "E-000")]
    reported = _stale_anchors(planted)
    assert len(reported) == 1 and "anchor not found" in reported[0]

    # AND A FILE THAT IS GONE ENTIRELY is a different failure with its own
    # message -- a rename of the module, not of the line.
    moved = [("a mutation whose module moved", "nm/core/no_such_module.py",
              "anything", "x", "some_test", "E-000")]
    assert "does not exist" in _stale_anchors(moved)[0]

    # AND AN ANCHOR MATCHING TWO PLACES, which is the failure that actually
    # happened. Presence alone passed it: both mutations ran, mutated the
    # wrong line, and were reported as SURVIVED -- which reads as a weak test
    # and was really an anchor that had stopped being specific.
    ambiguous = [("a mutation whose anchor is not unique", "nm/core/turn.py",
                  "        return None", "x", "some_test", "E-000")]
    reported = _stale_anchors(ambiguous)
    assert reported and "matches" in reported[0], (
        "an anchor matching many lines was accepted, so a mutation can "
        "silently move to a site no test guards")


# ============ the scenario runner: a run that measured nothing =============


def test_the_served_process_reports_which_code_it_loaded():
    """A RUNNING PROCESS IS AN ARTEFACT AND CARRIES ITS IDENTITY.

    Measured on 31 August 2026: five golden scenarios were run against an API
    server started the previous evening. They made live model calls, found none
    of the slice they existed to prove, and the run exited 0. Every element
    printed was about code superseded that morning.

    The fingerprint is captured at IMPORT, never per request. Read from disk
    when the request arrives it would describe the working tree — which a stale
    server matches perfectly while serving yesterday's code, so the check would
    pass exactly when it needed to fail.
    """
    import nm.edge.api as api
    from nm.domain.identity import source_fingerprint

    assert api.SERVING == source_fingerprint(), (
        "the module-level fingerprint does not match the tree it was imported "
        "from")
    assert not api.SERVING.startswith("unknown"), api.SERVING

    # IT IS A CONSTANT, not a call. The check depends on this: a property or a
    # function evaluated per request would re-read the disk.
    assert isinstance(api.SERVING, str)
    assert "SERVING = source_fingerprint()" in (
        Path(api.__file__).read_text(encoding="utf8")), (
        "the fingerprint is no longer captured once at import — a per-request "
        "computation describes the working tree, not the running process")


def test_the_fingerprint_has_one_owner():
    """`tools/_fingerprint.py` re-exports and defines nothing.

    Two digests would agree until the day they did not, and the disagreement
    would look like a code change rather than like a bug in the checker.
    """
    import tools._fingerprint as shim
    from nm.domain.identity import source_fingerprint

    assert shim.source_fingerprint is source_fingerprint
    src = Path(shim.__file__).read_text(encoding="utf8")
    assert "hashlib" not in src, (
        "tools/_fingerprint.py computes a digest of its own again")


def test_a_fingerprint_notices_a_changed_source_file(tmp_path):
    """THE POSITIVE CONTROL. A digest that never changes would let every stale
    server pass, and it would look exactly like this one."""
    from nm.domain.identity import source_fingerprint

    (tmp_path / "nm").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "nm" / "a.py").write_text("x = 1", encoding="utf8")
    before = source_fingerprint(tmp_path)

    (tmp_path / "nm" / "a.py").write_text("x = 2", encoding="utf8")
    assert source_fingerprint(tmp_path) != before, "content change not seen"

    # A NEW FILE COUNTS TOO — the S4 wiring was mostly new modules.
    (tmp_path / "nm" / "b.py").write_text("x = 2", encoding="utf8")
    assert source_fingerprint(tmp_path) != before, "an added module not seen"

    # AND A MISSING TREE IS NOT SILENTLY SKIPPED. Digesting nothing would make
    # a deployment without `tests/` match across changes it never looked at.
    import shutil
    shutil.rmtree(tmp_path / "tests")
    assert source_fingerprint(tmp_path) != before


def test_the_runner_tells_an_unreachable_server_from_a_stale_one():
    """THREE STATES, and the middle one is why this returns a pair.

    `None` is "could not be established" — the server is down, or too old to
    carry the field. That is not the same as a fingerprint that differs, and
    collapsing them would tell the reader to restart a process that is not
    running.
    """
    import tools.run_scenario as runner

    fp, why = runner.server_fingerprint()
    assert (fp is None) == (why != "ok")
    if fp is None:
        assert why and why != "ok", "no reason was given for the refusal"
    else:
        assert not fp.startswith("unknown")


def test_a_scenario_with_no_scripted_turns_is_refused_not_skipped():
    """THE THIRD S1 IN ONE RUN. Five scenarios were named, three had no
    scripted turns, and the runner printed a note, continued, and reported
    success. A scenario that could not run must never read as one that passed.
    """
    import tools.run_scenario as runner

    src = Path(runner.__file__).read_text(encoding="utf8")
    assert "no turns scripted" not in src, (
        "the skip is back: a named scenario with no turns is being passed over "
        "rather than refused")
    assert "have no scripted" in src

    # AND THE NAMES IT KNOWS ARE REAL. A TURNS key that matches no scenario in
    # the golden set would script a conversation nothing is graded against.
    golden = (Path(runner.ROOT) / "docs" / "GOLDEN_SET.md").read_text(
        encoding="utf8")
    unknown = [g for g in runner.TURNS if g not in golden]
    assert not unknown, f"scripted scenarios not in the golden set: {unknown}"


# ============ the console every tool writes its verdict to =================


def _entry_point_tools() -> list[Path]:
    """Every tool that can be run directly. The population, from the tree."""
    return [p for p in sorted((ROOT / "tools").glob("*.py"))
            if not p.name.startswith("_")
            and "__main__" in p.read_text(encoding="utf8")]


def test_every_tool_makes_its_console_survive_the_prose_it_prints():
    """A REPORT THAT DIES HALFWAY IS WORSE THAN ONE THAT DOES NOT RUN.

    `run_goldens.py --suite full` raised `UnicodeEncodeError: 'charmap' codec
    can't encode character '\u2194'` on scenario sixteen — `IPC s.447 <-> BNS
    s.329`. Ten of the twenty-five never printed. It had already printed
    fifteen rows so it looked like a report, and it exited non-zero so it
    looked like a verdict, and nothing said the list was cut short.

    Windows gives these processes a cp1252 stdout and the docstrings in this
    repo are written with en-dashes and arrows, so it was latent in all
    fourteen. `check.py` runs most of them as subprocesses, which captures
    through a different encoding path — which is exactly why it stayed hidden
    until one was run directly.
    """
    offenders = [p.name for p in _entry_point_tools()
                 if "utf8_console()" not in p.read_text(encoding="utf8")]
    assert not offenders, (
        "these tools can die partway through their own report on a dash:\n  "
        + "\n  ".join(offenders)
        + "\n\nAdd `from tools._console import utf8_console` and call it. One "
          "definition, called everywhere — a line copied into fourteen files "
          "is fourteen chances to differ and one guarantee the fifteenth tool "
          "will not have it.")


def test_the_console_scan_can_see_a_tool_that_does_not_call_it():
    """THE POSITIVE CONTROL, and it plants a real file.

    A scan over tools that all happen to call it proves nothing about the scan.
    """
    probe = ROOT / "tools" / "zz_console_probe.py"
    probe.write_text('print("no guard here")\nif __name__ == "__main__":\n'
                     '    pass\n', encoding="utf8")
    try:
        offenders = [p.name for p in _entry_point_tools()
                     if "utf8_console()" not in p.read_text(encoding="utf8")]
        assert "zz_console_probe.py" in offenders, (
            "the scan did not see a tool with no console guard")
    finally:
        probe.unlink()


def test_utf8_console_survives_a_stream_it_cannot_reconfigure():
    """It runs under pytest's capture, under a pipe, and inside a subprocess
    wrapper. None of those is a failure and none may raise — a guard that
    crashes on the ordinary case would be worse than the bug."""
    from tools._console import utf8_console

    utf8_console()
    utf8_console()  # idempotent


def test_an_unscored_golden_suite_is_not_reported_as_a_pass():
    """NOT MEASURED EXITS NON-ZERO EXACTLY LIKE FAIL.

    `--suite full` printed `NOT ASSESSED` twenty-five times and returned 0.
    The honest half of the job was done and the half that matters was not:
    every caller reads the exit code, not the prose, and RG-21 is a BLOCKING
    release criterion. A criterion nobody computed is the one that gets
    assumed.
    """
    r = run("run_goldens.py", "--suite", "full", "--approve")
    assert r.returncode != 0, (
        "an all-unscored judged suite reported success:\n" + r.stdout[-2000:])
    assert "NOT MEASURED" in r.stdout
    assert "not a pass" in r.stdout

    # AND EVERY SCENARIO IS LISTED. The report was being truncated by the
    # encoding crash at fifteen of twenty-five, with nothing saying so.
    assert r.stdout.count("NOT ASSESSED") == 25, (
        f"only {r.stdout.count('NOT ASSESSED')} of 25 scenarios reached the "
        f"report")
