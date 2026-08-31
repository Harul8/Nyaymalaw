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
        text = spec.read_text(encoding="utf8")
        # Flip exactly one feature to `built` without implementing it.
        assert "  status: decided\n" in text
        text = text.replace("  status: decided\n", "  status: built\n", 1)
        spec.write_text(text, encoding="utf8")

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

        # Pick a feature whose evals have NOT run. The first draft of this test
        # took "the first feature with eval ids" and broke the moment real evals
        # started running -- the TEST was wrong, not the code. The condition
        # under test is "tested claimed with no eval run behind it", so the test
        # must construct exactly that rather than assume it.
        results = ROOT / ".nm" / "eval_results.json"
        ran = set()
        if results.exists():
            ran = set(json.loads(results.read_text(encoding="utf8")).get("evals_run", []))
        target = next(f for f in doc["features"]
                      if f.get("eval_ids") and not (set(f["eval_ids"]) & ran))
        target_id = target["id"]
        for f in doc["features"]:
            if f["id"] == target_id:
                f["status"] = "tested"
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
        elif old not in path.read_text(encoding="utf8"):
            stale.append(f"{label}: anchor not found in {rel}")
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
