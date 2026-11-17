"""The runner finds every browser journey from the source (plan AN.57, piece 57a; D263; the second review of 17 Nov 2026).

Until the journeys job, the hosted runner left every journey out and nineteen of twenty-three journey checks failed unseen.
The job runs the files a small tool lists: each test file that names the browser library, and each that borrows - directly or
through another file - from one that does. A list kept by hand would miss the next journey; this is found, and a planted
file shows the finding works.
"""
from __future__ import annotations

from pathlib import Path

from development_environment.developer_tooling.journey_files import journey_files

ROOT = Path(__file__).resolve().parents[1]


def test_a_file_that_uses_the_browser_and_those_that_borrow_from_it_are_found(tmp_path):
    (tmp_path / "test_a_journey.py").write_text("playwright_api = pytest.importorskip('playwright.sync_api')\n", encoding="utf8")
    (tmp_path / "test_borrows.py").write_text("from tests.test_a_journey import page\n", encoding="utf8")
    (tmp_path / "test_borrows_again.py").write_text("import pytest\nfrom tests.test_borrows import page\n", encoding="utf8")
    (tmp_path / "test_plain.py").write_text("from tests.test_core_turn import run\n", encoding="utf8")
    assert [path.name for path in journey_files(tmp_path)] == ["test_a_journey.py", "test_borrows.py", "test_borrows_again.py"]


def test_the_shipped_journeys_are_found_and_the_runner_asks_the_tool():
    names = {path.name for path in journey_files(ROOT / "tests")}
    assert {"test_the_journey_login_to_logout.py", "test_opening_journey.py",
            "test_required_browser_assets_are_observed.py"} <= names
    assert "test_core_turn.py" not in names and len(names) >= 19
    workflow = (ROOT / ".github/workflows/offline-tests.yml").read_text(encoding="utf8")
    assert "journey_files.py" in workflow and "playwright install" in workflow
