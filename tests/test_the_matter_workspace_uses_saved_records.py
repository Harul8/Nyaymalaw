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


def test_the_served_page_includes_the_matter_controls_after_the_shared_client():
    page = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert '/static/matter-workspace.css' in page
    assert '/static/matter-workspace.js' in page
    assert page.index('/static/app.js') < page.index('/static/matter-workspace.js')
