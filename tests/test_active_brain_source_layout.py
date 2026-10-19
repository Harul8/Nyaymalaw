"""Archives are retained files, never active module or browser dependencies."""
from pathlib import Path
import json
import re


def test_service_status_is_preserved_on_reopen_and_displayed_separately():
    root = Path(__file__).resolve().parents[1]
    script = (root / "nm/app/app.js").read_text(encoding="utf-8")
    restoration = script[script.index("function restoredTurn("):script.index("function renderBriefing(")]
    assert "service_status: typeof turn.service_status === 'string' ? turn.service_status : null" in restoration
    rendering = script[script.index("function renderTurn("):script.index("function repaint(")]
    assert "stateBlock('quiet service-status', entry.answer.service_status)" in rendering
    assert "status.setAttribute('role', 'status')" in rendering
    assert "wrap.appendChild(status)" in rendering


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
