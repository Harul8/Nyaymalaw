"""Shipped preview DOM/request contracts; not live model or real-user proof."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def test_private_preview_controller_runs_its_nonempty_rejecting_population():
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required for the private preview controller"
    result = subprocess.run(
        [node, "--test", "tests/brain-preview.test.cjs"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# tests 35" in result.stdout and "# pass 35" in result.stdout


def test_preview_is_separate_and_has_a_persistent_warning_before_the_workspace():
    page = (ROOT / "nm/Archives/legal_brain/evaluate/brain-preview.html").read_text(encoding="utf-8")
    marker = "Private fictional-matter evaluation—not client advice or release."
    assert marker in page
    assert page.index('id="evaluation-marker"') < page.index('id="workspace"')
    assert 'id="evaluation-marker" hidden' not in page
    assert '<script src="/static/brain-preview.js" defer>' in page
    assert "/static/app.js" not in page
    controller = (ROOT / "nm/Archives/legal_brain/evaluate/brain-preview.js").read_text(encoding="utf-8")
    for prohibited in ("innerHTML", "localStorage", "/api/turn", "raw_candidate"):
        assert prohibited not in controller, prohibited
