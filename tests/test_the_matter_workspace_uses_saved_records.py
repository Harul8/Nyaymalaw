"""The retired matter controller stays out of the served page."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def test_the_retired_matter_controls_are_not_served():
    """The owner retired the old matter records on 16 Oct 2026 (F-B-04): each matter's
    Conversation, Board, Documents and Research notes replace them. The archived
    controller was deleted on 19 Oct 2026 (P24); the served page must not load it."""
    import json

    page = (ROOT / "nm/app/index.html").read_text(encoding="utf-8")
    assert "matter-workspace" not in page
    assets = json.loads((ROOT / "nm/source_layout.json").read_text(encoding="utf-8"))["browser_assets"]
    assert not any("matter-workspace" in name for name in assets)
