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


