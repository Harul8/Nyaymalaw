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
    r = run("trace.py", "--skip-regen")
    assert r.returncode == 0, f"trace already failing:\n{r.stdout}"
    assert "TRACE OK" in r.stdout


def test_trace_rejects_an_implements_naming_no_feature():
    """T2 COUNTEREXAMPLE: code claiming a feature id the spec does not contain."""
    offender = ROOT / "nm" / "core" / "_trace_probe.py"
    offender.write_text(textwrap.dedent("""
        from nm.obs.traceability import implements

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
        # Pick the first feature that declares at least one eval id.
        import yaml
        doc = yaml.safe_load(text)
        target = next(f for f in doc["features"] if f.get("eval_ids"))
        target_id = target["id"]
        for f in doc["features"]:
            if f["id"] == target_id:
                f["status"] = "tested"
        spec.write_text(
            "# temporary probe\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf8")

        # Satisfy T3 so the failure we observe is unambiguously T4.
        probe.write_text(textwrap.dedent(f"""
            from nm.obs.traceability import implements

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
