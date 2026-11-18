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
    # Plan AN.48 (D306): a journey that borrows another as a named module, alone or with others, is found too.
    (tmp_path / "test_borrows_as_a_module.py").write_text(
        "from tests import test_a_journey as support\n", encoding="utf8")
    (tmp_path / "test_borrows_several.py").write_text(
        "from tests import (\n    test_core_turn,\n    test_borrows_as_a_module,\n)\n", encoding="utf8")
    (tmp_path / "test_names_it_in_a_word_only.py").write_text(
        "# not an import: from tests import test_a_journey\nWORDS = 'import tests.test_a_journey'\n", encoding="utf8")
    assert [path.name for path in journey_files(tmp_path)] == [
        "test_a_journey.py", "test_borrows.py", "test_borrows_again.py", "test_borrows_as_a_module.py",
        "test_borrows_several.py"]


def test_the_shipped_journeys_are_found_and_the_runner_asks_the_tool():
    names = {path.name for path in journey_files(ROOT / "tests")}
    assert {"test_the_journey_login_to_logout.py", "test_conversation_recovery_journey.py",
            "test_required_browser_assets_are_observed.py",
            # Both borrow the login journey as a named module, which the finder missed until D306 (plan AN.48).
            "test_openai_permission_journey.py", "test_email_registration_reaches_a_private_workspace.py"} <= names
    # Six journeys of a matter saved before conversations were retired with its screens (plan AN.57, D292).
    assert "test_core_turn.py" not in names and len(names) >= 16
    workflow = (ROOT / ".github/workflows/offline-tests.yml").read_text(encoding="utf8")
    assert "journey_files.py" in workflow and "playwright install" in workflow
