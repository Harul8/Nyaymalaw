"""Archives are retained files, never active module or browser dependencies."""
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from assurance.common.module_roles import LayoutError, classify_sources, load_module_roles
from assurance.gate.layercheck import check
from nm.shared.source_layout import LayoutRefused, browser_assets, load_layout
from tests.test_journey_module_roles_keep_dependency_boundaries import _manifests
from tests.source_role_fixtures import role_tree


def _tree(tmp_path):
    roles = role_tree(tmp_path, "")
    current, _ = _manifests(tmp_path, roles)
    return roles, current


def test_owned_archives_are_not_active_sources_in_either_registry(tmp_path):
    roles, _ = _tree(tmp_path)
    archive = tmp_path / "nm/Archives/brain"
    archive.mkdir(parents=True)
    (archive / "old.py").write_text("raise RuntimeError('not runtime')", encoding="utf-8")
    assert set(load_layout(tmp_path)["modules"]) == set(roles)
    assert set(load_module_roles(root=tmp_path).roles) == set(roles)


@pytest.mark.parametrize("directory", ["nm/new_activity", "nm/features/Archives", "nm/tests"])
def test_an_arbitrary_active_folder_cannot_hide_unregistered_sources(tmp_path, directory):
    roles, _ = _tree(tmp_path)
    hidden = tmp_path / directory
    hidden.mkdir(parents=True)
    (hidden / "undeclared.py").write_text("", encoding="utf-8")
    with pytest.raises(LayoutRefused, match="actual Python population"):
        load_layout(tmp_path)
    with pytest.raises(LayoutError, match="unclassified"):
        classify_sources(root=tmp_path, roles=roles)


def test_a_declared_archive_cannot_reenter_the_active_population(tmp_path):
    roles, current = _tree(tmp_path)
    archive = tmp_path / "nm/Archives"
    archive.mkdir()
    (archive / "old.py").write_text("", encoding="utf-8")
    roles["nm.Archives.old"] = "core"
    current["modules"] = roles
    current["expected_roles"] = dict(Counter(roles.values()))
    (tmp_path / "nm/source_layout.json").write_text(json.dumps(current), encoding="utf-8")
    with pytest.raises(LayoutRefused, match="archived module"):
        load_layout(tmp_path)
    with pytest.raises(LayoutError, match="archived sources"):
        classify_sources(root=tmp_path, roles=roles)


def test_an_active_source_importing_an_archive_is_a_dependency_failure(tmp_path):
    roles, _ = _tree(tmp_path)
    (tmp_path / "nm/work_the_file/probe.py").write_text(
        "from nm.Archives.brain.turn import execute\n", encoding="utf-8")
    _, problems = check(classify_sources(root=tmp_path, roles=roles))
    assert any("unclassified imported module nm.Archives.brain.turn" in row for row in problems)


def test_archived_browser_assets_cannot_be_served(tmp_path):
    _, current = _tree(tmp_path)
    archive = tmp_path / "nm/Archives"
    archive.mkdir()
    (archive / "old.js").write_text("alert('archived');", encoding="utf-8")
    current["browser_assets"] = {"old.js": "nm/Archives/old.js"}
    (tmp_path / "nm/source_layout.json").write_text(json.dumps(current), encoding="utf-8")
    with pytest.raises(LayoutRefused, match="browser asset"):
        browser_assets(root=tmp_path)
    with pytest.raises(LayoutError, match="browser asset"):
        load_module_roles(root=tmp_path)


def test_current_page_only_references_active_declared_browser_assets():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "nm/source_layout.json").read_text(encoding="utf-8"))
    html = (root / "nm/app/index.html").read_text(encoding="utf-8")
    assets = manifest["browser_assets"]
    for name in re.findall(r'(?:src|href)="/static/([^"?]+)', html):
        assert name in assets
        assert not assets[name].startswith("nm/Archives/")
        assert (root / assets[name]).is_file()
    script = (root / "nm/app/app.js").read_text(encoding="utf-8")
    for retired in ("NMAdvocatePreferences", "NMLoopProgress", "openSourceReader",
                    "closeSourceReader"):
        assert retired not in script


def test_service_status_is_preserved_on_reopen_and_displayed_separately():
    root = Path(__file__).resolve().parents[1]
    script = (root / "nm/app/app.js").read_text(encoding="utf-8")
    restoration = script[script.index("function restoredTurn("):script.index("function renderBriefing(")]
    assert "service_status: typeof turn.service_status === 'string' ? turn.service_status : null" in restoration
    rendering = script[script.index("function renderTurn("):script.index("function repaint(")]
    assert "stateBlock('quiet service-status', entry.answer.service_status)" in rendering
    assert "status.setAttribute('role', 'status')" in rendering
    assert "wrap.appendChild(status)" in rendering
