"""Actual shipped controller under a bounded DOM; no browser/served PASS claim."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("witness", [
    "cover", "commission", "casefile", "declaration", "protective", "revoke",
    "stale_read", "stale_write", "wipe", "mutation",
    "confirmation_commission", "confirmation_declaration", "confirmation_revoke",
    "confirmation_mutation", "cover_changed", "declaration_retry", "urgency", "urgency_retry",
])
def test_the_shipped_matter_controller_preserves_its_boundary(witness):
    node = shutil.which("node")
    if node is None:
        pytest.skip("NOT ASSESSED: Node unavailable; matter-controller behavior was not run")
    result = subprocess.run(
        [node, str(ROOT / "tests/js/matter_workspace.mjs"), witness],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS matter workspace {witness}" in result.stdout


def test_the_retired_matter_controls_are_not_served():
    """The owner retired the old matter records on 16 Oct 2026 (F-B-04): each matter's
    Conversation, Board, Documents and Research notes replace them. The archived
    controller above stays as a reference; the served page must not load it."""
    import json

    page = (ROOT / "nm/app/index.html").read_text(encoding="utf-8")
    assert "matter-workspace" not in page
    assets = json.loads((ROOT / "nm/source_layout.json").read_text(encoding="utf-8"))["browser_assets"]
    assert not any("matter-workspace" in name for name in assets)
