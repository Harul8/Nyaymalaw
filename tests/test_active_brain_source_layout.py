"""Archives are retained files, never active module or browser dependencies."""
from pathlib import Path




def test_service_status_is_preserved_on_reopen_and_displayed_separately():
    root = Path(__file__).resolve().parents[1]
    script = (root / "nm/app/app.js").read_text(encoding="utf-8")
    restoration = script[script.index("function restoredTurn("):script.index("function renderBriefing(")]
    assert "service_status: typeof turn.service_status === 'string' ? turn.service_status : null" in restoration
    rendering = script[script.index("function renderTurn("):script.index("function repaint(")]
    assert "stateBlock('quiet service-status', entry.answer.service_status)" in rendering
    assert "status.setAttribute('role', 'status')" in rendering
    assert "wrap.appendChild(status)" in rendering
