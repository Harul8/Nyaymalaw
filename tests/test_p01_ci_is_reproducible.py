"""P01's clean-checkout and approval-boundary controls.

The exporter executes the JavaScript PRD generator.  A developer machine can
hide a missing CI dependency behind an untracked ``node_modules`` directory,
which is exactly how the first P01 implementation passed locally and failed in
an isolated checkout.  The workflow and lockfile are therefore one contract.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def test_class_a_ci_installs_the_locked_prd_renderer_before_running_export():
    workflow = yaml.load(
        (ROOT / ".github/workflows/class-a.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["class-a"]["steps"]

    setup = next((row for row in steps
                  if row.get("uses") == "actions/setup-node@v4"), None)
    assert setup is not None, "a clean Class-A worker never installs Node"
    assert setup.get("with", {}).get("node-version") == "22"
    assert setup["with"].get("cache-dependency-path") == \
        "spec/prd/package-lock.json"

    install = next((row for row in steps
                    if row.get("name") == "Install locked PRD renderer dependencies"),
                   None)
    assert install is not None
    assert install.get("working-directory") == "spec/prd"
    assert install.get("run") == "npm ci --ignore-scripts"

    package = json.loads((ROOT / "spec/prd/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "spec/prd/package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"][""]["dependencies"] == package["dependencies"]
    renderer = lock["packages"].get("node_modules/docx")
    assert renderer and renderer.get("integrity") and renderer.get("resolved")


def test_approval_bound_populations_are_absent_from_every_local_default():
    from tools.evidence import CLASS_A_SELECTOR

    assert CLASS_A_SELECTOR == \
        "class_a and not class_c and not class_d and not journey"
    source = (ROOT / "tools/check.py").read_text(encoding="utf-8")
    recorder = (ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    tier_test = (ROOT / "tests/test_reads_registry.py").read_text(encoding="utf-8")
    assert "CLASS_A_PYTEST_ARGS" in source and "CLASS_A_PYTEST_ARGS" in recorder
    assert '"not class_c and not class_d and not journey"' in source
    assert "@pytest.mark.class_d\ndef test_the_judge_is_not_the_model_under_test" \
        in tier_test
